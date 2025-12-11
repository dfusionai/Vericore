import os
import time
import json
import argparse
import random
import shutil
import traceback
import numpy as np
import bittensor as bt
import logging
from typing import List
from datetime import datetime

from shared.environment_variables import INITIAL_WEIGHT, IMMUNITY_WEIGHT, IMMUNITY_PERIOD
from shared.log_data import LoggerType
from shared.proxy_log_handler import register_proxy_log_handler
from shared.store_results_handler import (
    register_validator_results_data_handler,
    ValidatorResultsDataHandler,
)

from shared.validator_results_data import ValidatorResultsData

bt.logging.set_trace()

ENABLE_EMISSION_CONTROL = True
EMISSION_CONTROL_HOTKEY = "5FWMeS6ED6NG6t5ovKQNZvGWEWVtZPve5BhYWM9wics5FgJ9"
EMISSION_CONTROL_PERC = 0.50
USE_RANKING_EMISSION_CONTROL = True
RANKING_EMISSION_TOP_PERC = 0.5
ENABLE_WEIGHTS_TRACKING = False

# Weight distribution constants
DEFAULT_TOTAL_WEIGHT = 65535.0  # Standard Bittensor weight total
EXPONENTIAL_DECAY_SCALE = 4.0  # Scaling factor for exponential decay distribution

def find_target_uid(metagraph, hotkey):
    for neuron in metagraph.neurons:
        if neuron.hotkey == hotkey:
            emission_control_uid = neuron.uid
            return emission_control_uid

def get_validator_uids(metagraph, subtensor, netuid):
    """
    Identify validator UIDs using validator_permit from neurons.

    Args:
        metagraph: Bittensor metagraph object
        subtensor: Bittensor subtensor object
        netuid: Network UID

    Returns:
        Set of UIDs that are validators
    """
    validator_uids = set()
    try:
        # Get neurons to check validator_permit
        neurons = subtensor.neurons(netuid=netuid)

        for neuron in neurons:
            if neuron.validator_permit and neuron.axon_info.is_serving:
                validator_uids.add(neuron.uid)

        bt.logging.info(f"Found {len(validator_uids)} validators with validator_permit: {sorted(validator_uids)}")

    except Exception as e:
        bt.logging.warning(f"Error identifying validators: {e}")

    return validator_uids

def find_burn_miner(weights, metagraph):
    """
    Validate and find the target burn miner UID.

    Args:
        weights: Array of weights to be processed
        metagraph: Bittensor metagraph object

    Returns:
        Target UID if found and valid, None otherwise
    """
    target_uid = find_target_uid(metagraph, EMISSION_CONTROL_HOTKEY)
    if target_uid is None:
        bt.logging.info(f"target emission control hotkey {EMISSION_CONTROL_HOTKEY} is not found")
        return None

    # Ensure target_uid is within bounds
    if target_uid >= len(weights):
        bt.logging.warning(f"Target UID {target_uid} is out of bounds for weights array of length {len(weights)}")
        return None

    return target_uid

def burn_weights(weights, metagraph, exclude_uids=None, subtensor=None, netuid=None):
    """
    Apply emission control by burning weights and redistributing to target UID.

    Args:
        weights: Array of weights to be processed
        metagraph: Bittensor metagraph object
        exclude_uids: Set of UIDs to exclude from weight redistribution (e.g., validators)
        subtensor: Bittensor subtensor object (for validator identification if needed)
        netuid: Network UID (for validator identification if needed)

    Returns:
        Processed weights with emission control applied
    """
    exclude_uids = exclude_uids or set()
    target_uid = find_burn_miner(weights, metagraph)
    if target_uid is None:
        return weights

    # Exclude validators and target from total calculation for redistribution
    uids = metagraph.uids
    valid_weights = np.array([w if uid not in exclude_uids and uid != target_uid else 0.0
                              for uid, w in zip(uids, weights)])

    total_score = np.sum(weights)
    new_target_score = EMISSION_CONTROL_PERC * total_score
    remaining_weight = (1 - EMISSION_CONTROL_PERC) * total_score
    total_other_scores = np.sum(valid_weights)

    if total_other_scores == 0:
        bt.logging.warning("All scores are zero except target UID and excluded UIDs, cannot scale.")
        return weights

    new_scores = np.zeros_like(weights, dtype=float)

    for i, (uid, weight) in enumerate(zip(uids, weights)):
        if uid == target_uid:
            new_scores[i] = new_target_score
        elif uid in exclude_uids:
            # Validators get zero weight
            new_scores[i] = 0.0
        else:
            new_scores[i] = (weight / total_other_scores) * remaining_weight

    # Ensure sum is exactly total_score (handle floating point precision)
    actual_sum = np.sum(new_scores)
    if abs(actual_sum - total_score) > 1e-6:  # Only adjust if significant difference
        diff = total_score - actual_sum
        # Add/subtract difference to target UID to maintain exact total
        target_idx = None
        for i, uid in enumerate(uids):
            if uid == target_uid:
                target_idx = i
                break
        if target_idx is not None:
            new_scores[target_idx] += diff

    return new_scores

def distribute_weights_by_ranking(moving_scores, total_weight=DEFAULT_TOTAL_WEIGHT, top_percentage=RANKING_EMISSION_TOP_PERC, exclude_uids=None):
    """
    Distribute weights using ranking-based geometric progression.
    Top miner gets top_percentage (default RANKING_EMISSION_TOP_PERC), second gets 25%, third gets 12.5%, etc.

    Args:
        moving_scores: List of calculated scores for each miner
        total_weight: Total weight to distribute (default DEFAULT_TOTAL_WEIGHT)
        top_percentage: Percentage of total weight for top miner (default RANKING_EMISSION_TOP_PERC)
        exclude_uids: Set of UIDs to exclude from weight distribution (e.g., validators)

    Returns:
        List of normalized weights summing to total_weight (as integers)
    """
    if len(moving_scores) == 0:
        return []

    exclude_uids = exclude_uids or set()

    # Sort scores descending, excluding validators
    sorted_pairs = sorted(
        [(idx, score) for idx, score in enumerate(moving_scores) if idx not in exclude_uids],
        key=lambda x: x[1],
        reverse=True
    )

    if len(sorted_pairs) == 0:
        # All UIDs excluded, return zeros
        return [0] * len(moving_scores)

    weights = [0.0] * len(moving_scores)
    current_percentage = top_percentage

    # Distribute weights based on ranking (only to non-excluded UIDs)
    for i, (idx, _) in enumerate(sorted_pairs):
        if i == 0:
            allocated = total_weight * top_percentage
        else:
            current_percentage *= 0.5
            allocated = total_weight * current_percentage
        weights[idx] = allocated

    # Give any remainder to the first miner to ensure sum is exactly total_weight
    weight_sum = sum(weights)
    if weight_sum > 0 and weight_sum < total_weight:
        # Add remainder to top miner
        top_idx = sorted_pairs[0][0]
        weights[top_idx] += (total_weight - weight_sum)

    return [int(round(w)) for w in weights]

def distribute_weights_by_exponential_decay(moving_scores, total_weight=DEFAULT_TOTAL_WEIGHT, scale=EXPONENTIAL_DECAY_SCALE):
    """
    Distribute weights using exponential decay based on score differences.
    Higher scores receive exponentially more weight than lower scores.

    Args:
        moving_scores: List of calculated scores for each miner
        total_weight: Total weight to distribute (default DEFAULT_TOTAL_WEIGHT)
        scale: Scaling factor for exponential decay (default EXPONENTIAL_DECAY_SCALE)
               Higher values result in more gradual decay

    Returns:
        List of normalized weights summing to total_weight
    """
    arr = np.array(moving_scores, dtype=np.float32)
    deltas = arr.max() - arr
    exp_dec = np.exp(-deltas / scale)
    weights = ((exp_dec / exp_dec.sum()) * total_weight).tolist()
    return weights

def convert_scores_to_weights(moving_scores, use_ranking=True, exclude_uids=None):
    """
    Convert moving scores to normalized weights using exponential decay or ranking-based distribution.

    Args:
        moving_scores: List of calculated scores for each miner
        use_ranking: If True, use ranking-based distribution (top miner gets RANKING_EMISSION_TOP_PERC, second 25%, etc.)
                     If False, use exponential decay
        exclude_uids: Set of UIDs to exclude from weight distribution (e.g., validators)

    Returns:
        List of normalized weights summing to DEFAULT_TOTAL_WEIGHT
    """
    if use_ranking:
        return distribute_weights_by_ranking(moving_scores, exclude_uids=exclude_uids)
    else:
        return distribute_weights_by_exponential_decay(moving_scores)


def move_miner_weights(moving_scores, metagraph, my_uid, subtensor, netuid):
    """
    Convert moving scores to normalized weights with exponential decay and optional emission control burning.
    Validators and burn miner are excluded from weight distribution.

    Args:
        moving_scores: List of calculated scores for each miner
        metagraph: Bittensor metagraph object
        my_uid: Validator UID for logging purposes
        subtensor: Bittensor subtensor object
        netuid: Network UID

    Returns:
        List of processed weights ready to be set on chain
    """
    bt.logging.info(f"DAEMON | {my_uid} | Moving scores: {moving_scores}")

    # Identify validators to exclude
    validator_uids = get_validator_uids(metagraph, subtensor, netuid)

    # Identify burn miner to exclude from initial distribution
    burn_miner_uid = None
    if ENABLE_EMISSION_CONTROL:
        # Create dummy weights array for burn miner identification
        dummy_weights = [1.0] * len(moving_scores)  # All equal weights for identification
        burn_miner_uid = find_burn_miner(dummy_weights, metagraph)
        if burn_miner_uid is not None:
            bt.logging.info(f"DAEMON | {my_uid} | Burn miner UID {burn_miner_uid} will get {EMISSION_CONTROL_PERC*100}% emission control weight only")

    # Combine exclusion sets
    exclude_uids = validator_uids.copy()
    if burn_miner_uid is not None:
        exclude_uids.add(burn_miner_uid)

    bt.logging.info(f"DAEMON | {my_uid} | Excluding {len(exclude_uids)} UIDs from weight distribution: {sorted(exclude_uids)}")

    weights = convert_scores_to_weights(moving_scores, use_ranking=USE_RANKING_EMISSION_CONTROL, exclude_uids=exclude_uids)

    # Validate weights sum before emission control
    weights_sum = sum(weights)
    if abs(weights_sum - DEFAULT_TOTAL_WEIGHT) > 1.0:
        bt.logging.warning(
            f"DAEMON | {my_uid} | Weights sum mismatch before burn: {weights_sum} vs expected {DEFAULT_TOTAL_WEIGHT} "
            f"(diff: {weights_sum - DEFAULT_TOTAL_WEIGHT})"
        )

    # Apply emission control burning if enabled
    if ENABLE_EMISSION_CONTROL:
        weights_burned = burn_weights(weights, metagraph, exclude_uids=validator_uids, subtensor=subtensor, netuid=netuid).tolist()

        # Validate weights sum after emission control
        burned_sum = sum(weights_burned)
        if abs(burned_sum - weights_sum) > 1.0:
            bt.logging.warning(
                f"DAEMON | {my_uid} | Weights sum mismatch after burn: {burned_sum} vs expected {weights_sum} "
                f"(diff: {burned_sum - weights_sum})"
            )
    else:
        weights_burned = weights

    bt.logging.info(f"DAEMON | {my_uid} | Setting weights on chain: {weights_burned}")

    return weights_burned

class WeightedMinerRecord:
    calculated_score: float = 0
    count: int = 0
    wallet_hotkey:str = ""

def get_config():
    parser = argparse.ArgumentParser()
    parser.add_argument("--custom", default="my_custom_value", help="Custom value")
    parser.add_argument("--netuid", type=int, default=1, help="Chain subnet uid")
    bt.subtensor.add_args(parser)
    bt.logging.add_args(parser)
    bt.wallet.add_args(parser)
    config = bt.config(parser)
    config.full_path = os.path.expanduser(
        "{}/{}/{}/netuid{}/validator".format(
            config.logging.logging_dir,
            config.wallet.name,
            config.wallet.hotkey_str,
            config.netuid,
        )
    )
    os.makedirs(config.full_path, exist_ok=True)
    return config

def setup_bittensor_objects(config):
    wallet = bt.wallet(config=config)
    bt.logging.info(f"Wallet: {wallet}")
    subtensor = bt.subtensor(config=config)
    bt.logging.info(f"Subtensor: {subtensor}")
    metagraph = subtensor.metagraph(config.netuid)
    bt.logging.info(f"Metagraph: {metagraph}")
    if wallet.hotkey.ss58_address not in metagraph.hotkeys:
        bt.logging.error("Wallet not registered on chain. Run 'btcli register'.")
        exit()
    return wallet, subtensor, metagraph

def setup_logging(wallet, config):
    bt.logging(config=config, logging_dir=config.full_path)
    bt.logging.info("Starting Validator Daemon with config:")
    bt.logging.info(config)
    bt_logger = logging.getLogger("bittensor")
    register_proxy_log_handler(bt_logger, LoggerType.Validator, wallet)


def send_validator_response_data(
    store_response_handler: ValidatorResultsDataHandler,
    validator_uid: int,
    validator_hotkey: str,
    unique_id: str,
    block_number: int,
    has_summary_data: bool,
    vericore_responses: List[dict],
    moving_scores: List[float],
    weights: List[float],
    incentives: List[float],
):
    if store_response_handler is not None:
        bt.logging.info(f"DAEMON | {validator_uid} | block number: {block_number}")
        validator_response_data = ValidatorResultsData()
        validator_response_data.validator_uid = validator_uid
        validator_response_data.validator_hotkey = validator_hotkey
        validator_response_data.block_number = block_number
        validator_response_data.unique_id = unique_id
        validator_response_data.has_summary_data = has_summary_data
        validator_response_data.timestamp = time.time()
        validator_response_data.vericore_responses = vericore_responses
        validator_response_data.moving_scores = moving_scores
        validator_response_data.calculated_weights = weights
        validator_response_data.incentives = incentives
        store_response_handler.send_json(validator_response_data)

def send_results(
    unique_id: str,
    validator_uid: int,
    validator_hotkey: str,
    block_number: int,
    results_dir: str,
    destination_dir: str,
    validator_results_data_handler: ValidatorResultsDataHandler
):
    """
    Scan the results directory for JSON files (each a query result), update moving_scores
    for each miner based on the reported final_score, then delete each processed file.
    """
    files = [
        {
            "filepath": os.path.join(results_dir, f),
            "filename": f
        }
        for f in os.listdir(results_dir)
        if f.endswith(".json")
    ]
    if not files:
        return None

    vericore_responses = []

    bt.logging.info(f"DAEMON | {validator_uid} | Processing vericore responses")
    for file_dto in files:
        try:

            with open(file_dto["filepath"], "r") as f:
                result = json.load(f)
                vericore_responses.append(result)
        except Exception as e:
            bt.logging.error(f"DAEMON | {validator_uid} | Error processing file {file_dto['filepath']}: {e}")
            return None

    if len(vericore_responses) > 0:
        # Send
        bt.logging.info(f"DAEMON | {validator_uid} | Sending {len(vericore_responses)} vericore responses")
        send_validator_response_data(
            store_response_handler=validator_results_data_handler,
            validator_uid=validator_uid,
            validator_hotkey=validator_hotkey,
            unique_id=unique_id,
            block_number=block_number,
            has_summary_data=False,
            vericore_responses=vericore_responses,
            incentives=[],
            weights=[],
            moving_scores=[],
        )
        bt.logging.info(f"DAEMON | {validator_uid} | Sent {len(vericore_responses)} vericore responses ")

    bt.logging.info(f"DAEMON | {validator_uid} | Moving files: {len(files)}")
    for filepath in files:
        try:
            sourceFile = filepath["filepath"]
            destinationFile = os.path.join(destination_dir, filepath["filename"])

            shutil.move(sourceFile, destinationFile)
        except Exception as e:
            bt.logging.error(f"DAEMON | {validator_uid} | Error processing file {filepath}: {e}")
            return None

    bt.logging.info(f"DAEMON | {validator_uid} | Moved files: {len(files)}")

    return vericore_responses

def list_json_files(directory):
    return [
        os.path.join(directory, f)
        for f in os.listdir(directory)
        if f.endswith(".json")
    ]

def calculate_moving_scores(validator_uid: int, response_directory: str, miner_score_cache, vericore_responses, add_to_vericore_responses: bool):
    files = list_json_files(response_directory)
    if not files:
        return False

    score_updated = False
    for filepath in files:
        try:

            with open(filepath, "r") as f:
                result = json.load(f)
                if add_to_vericore_responses:
                    vericore_responses.append(result)

            for res in result.get("results", []):
                miner_uid = res.get("miner_uid")
                final_score = res.get("final_score")
                if miner_uid is not None and final_score is not None:
                    # if miner is new, his final score sets the basis for next iteration, else its a weighted score between current and previous results
                    if miner_score_cache[miner_uid].count <= IMMUNITY_PERIOD:
                        if miner_score_cache[miner_uid].count == 0:
                            calculated_score = final_score
                        else:
                            calculated_score = miner_score_cache[miner_uid].calculated_score * (1 - IMMUNITY_WEIGHT) + final_score * IMMUNITY_WEIGHT
                        bt.logging.info(
                            f"DAEMON | {validator_uid} | Using immunity calculation for uid {miner_uid} average: {calculated_score}"
                        )
                    else:
                        calculated_score = miner_score_cache[miner_uid].calculated_score * INITIAL_WEIGHT + final_score * (1 - INITIAL_WEIGHT)

                    bt.logging.info(
                        f"DAEMON | {validator_uid} | Moving score for uid: {miner_uid} and final score: {final_score} with calculated scored {calculated_score}"
                    )
                    miner_score_cache[miner_uid].count = miner_score_cache[miner_uid].count + 1
                    miner_score_cache[miner_uid].calculated_score = calculated_score
                    score_updated = True

        except Exception as e:
            bt.logging.error(f"DAEMON | {validator_uid} | Error processing file {filepath}: {e}")
        finally:
            try:
                os.remove(filepath)
                bt.logging.info(f"DAEMON | {validator_uid} | Deleted processed file {filepath}")
            except Exception as e:
                bt.logging.error(f"DAEMON | {validator_uid} | Error deleting file {filepath}: {e}")
    return score_updated


def aggregate_results(validator_uid: int, results_dir, processed_results_dir, miner_score_cache):
    """
    Scan the results directory for JSON files (each a query result), update moving_scores
    for each miner based on the reported final_score, then delete each processed file.
    """
    vericore_responses = []

    score_updated_results = calculate_moving_scores(
        validator_uid,
        results_dir,
        miner_score_cache,
        vericore_responses,
        add_to_vericore_responses=True
    )

    score_updated_processed = calculate_moving_scores(
        validator_uid,
        processed_results_dir,
        miner_score_cache,
        vericore_responses,
        add_to_vericore_responses=False
    )

    return vericore_responses, score_updated_processed or score_updated_results

def generate_unique_id(validator_uid: int) -> str:
    timestamp = int(time.time() * 1000)
    random_suffix = random.randint(1000, 9999)
    return f"{timestamp}{random_suffix}{str(validator_uid).zfill(3)}"


def save_weights_tracking(moving_scores, weights_burned, metagraph, my_uid, incentives=None, tracking_dir="weights_tracking"):
    """
    Save moving scores and weights burned calculations to a JSON file for tracking.
    Creates a new file with datetime in the filename for each tracking entry.

    Args:
        moving_scores: List of calculated moving scores for each miner
        weights_burned: List of final weights after burning/emission control
        metagraph: Bittensor metagraph object
        my_uid: Validator UID
        incentives: Optional list of incentives for each miner
        tracking_dir: Directory to save tracking files
    """
    try:
        # Create tracking directory if it doesn't exist
        os.makedirs(tracking_dir, exist_ok=True)

        # Get current block number if available
        try:
            block_number = metagraph.block.item() if hasattr(metagraph.block, 'item') else int(metagraph.block)
        except:
            block_number = -1

        # Generate filename with datetime
        timestamp = datetime.utcnow()
        filename = f"weights_tracking_{timestamp.strftime('%Y%m%d_%H%M%S')}_{my_uid}_{block_number}.json"
        tracking_file = os.path.join(tracking_dir, filename)

        # Create tracking entry
        tracking_entry = {
            "timestamp": timestamp.isoformat(),
            "validator_uid": my_uid,
            "block_number": block_number,
            "total_miners": len(moving_scores),
            "miners": []
        }

        # Add data for each miner
        for uid in range(len(moving_scores)):
            miner_data = {
                "uid": int(uid),
                "hotkey": metagraph.hotkeys[uid] if uid < len(metagraph.hotkeys) else "unknown",
                "moving_score": float(moving_scores[uid]) if uid < len(moving_scores) else 0.0,
                "weight_burned": float(weights_burned[uid]) if uid < len(weights_burned) else 0.0
            }
            # Add incentive if available
            if incentives is not None and uid < len(incentives):
                miner_data["incentive"] = float(incentives[uid])
            tracking_entry["miners"].append(miner_data)

        # Save to file (each file contains a single entry)
        with open(tracking_file, 'w') as f:
            json.dump(tracking_entry, f, indent=2)

        bt.logging.info(f"DAEMON | {my_uid} | Saved weights tracking to {tracking_file}")

    except Exception as e:
        bt.logging.error(f"DAEMON | {my_uid} | Error saving weights tracking: {e}")


def main():
    config = get_config()
    wallet, subtensor, metagraph = setup_bittensor_objects(config)
    setup_logging(wallet, config)

    output_dir = "results"
    os.makedirs(output_dir, exist_ok=True)

    processed_results_dir = "result_processed"
    os.makedirs(processed_results_dir, exist_ok=True)

    my_uid = metagraph.hotkeys.index(wallet.hotkey.ss58_address)
    metagraph.sync()
    # set initial moving_scores before loop, so it does not clear score history every iteration
    miner_score_cache = []
    for uid in range(len(metagraph.hotkeys)):
        miner_record = WeightedMinerRecord()
        miner_record.wallet_hotkey = metagraph.hotkeys[uid]
        miner_score_cache.insert(
            uid,
            miner_record
        )

    validator_results_data_handler = register_validator_results_data_handler(
        my_uid, wallet
    )

    tempo = subtensor.tempo(config.netuid)
    unique_id = generate_unique_id(my_uid)
    bt.logging.info(f"DAEMON | {my_uid} | Starting Validator Daemon loop.")
    while True:
        try:
            last_update = subtensor.blocks_since_last_update(config.netuid, my_uid)
            bt.logging.info(
                f"DAEMON | {my_uid} | Will aggregate results: {last_update} > {tempo + 1} = {last_update > tempo + 1} "
            )
            if last_update > tempo + 1:
            # if True:
                bt.logging.info(f"DAEMON | {my_uid} | Aggregating results")
                metagraph.sync()
                # check if uid-hotkey pair changed, if so, remove score history
                uid_hotkey_dict_temp={uid: metagraph.hotkeys[uid] for uid in range(len(metagraph.hotkeys))}

                cache_size = len(miner_score_cache)
                for uid in range(len(metagraph.hotkeys)):
                    if uid >= cache_size:
                        new_miner_record = WeightedMinerRecord()
                        new_miner_record.wallet_hotkey = uid_hotkey_dict_temp[uid]
                        miner_score_cache.insert(uid, new_miner_record)
                    elif miner_score_cache[uid].wallet_hotkey !=uid_hotkey_dict_temp[uid]:
                        new_miner_record = WeightedMinerRecord()
                        new_miner_record.wallet_hotkey = uid_hotkey_dict_temp[uid]
                        miner_score_cache[uid] = new_miner_record

                # need to cater for if the hotkeys shrink

                vericore_responses, scores_updated = aggregate_results(
                    my_uid,
                    output_dir,
                    processed_results_dir,
                    miner_score_cache
                )

                # create new moving scores array in case new miners have been loaded
                moving_scores= [miner_score_record.calculated_score for miner_score_record in miner_score_cache]

                bt.logging.info(f"DAEMON | {my_uid} | Moving scores: {moving_scores}")

                if not scores_updated:
                    bt.logging.warning(f"DAEMON | {my_uid} | Skipped setting of weights")
                    # Sleep for 10 seconds
                    time.sleep(10)
                    # Don't update weights if  all moving scores are 0 otherwise it might rate the weights equally.
                    continue

                weights_burned = move_miner_weights(moving_scores, metagraph, my_uid, subtensor, config.netuid)

                subtensor.set_weights(
                    netuid=config.netuid,
                    wallet=wallet,
                    uids=metagraph.uids,
                    weights=weights_burned,
                    wait_for_inclusion=True,
                )

                incentives = [
                    neuron.incentive
                    for neuron in subtensor.neurons(netuid=config.netuid)
                ]

                # Save tracking data for moving scores, weights burned, and incentives
                if ENABLE_WEIGHTS_TRACKING:
                    save_weights_tracking(moving_scores, weights_burned, metagraph, my_uid, incentives)

                bt.logging.info(f"DAEMON | {my_uid} | Preparing to send json data")

                send_validator_response_data(
                    store_response_handler=validator_results_data_handler,
                    validator_uid=my_uid,
                    validator_hotkey= wallet.hotkey.ss58_address,
                    unique_id=unique_id,
                    block_number=subtensor.block,
                    has_summary_data=True,
                    vericore_responses=vericore_responses,
                    moving_scores=moving_scores,
                    weights=weights_burned,
                    incentives=incentives,
                )

                # reset unique id
                unique_id = generate_unique_id(my_uid)
            else:
                send_results(
                    validator_uid=my_uid,
                    validator_hotkey=wallet.hotkey.ss58_address,
                    unique_id=unique_id,
                    block_number=-1,
                    results_dir=output_dir,
                    destination_dir=processed_results_dir,
                    validator_results_data_handler=validator_results_data_handler,
                )

            metagraph.sync()

            time.sleep(60)
        except KeyboardInterrupt:
            bt.logging.info(f"DAEMON | {my_uid} | Validator Daemon interrupted. Exiting.")
            break
        except Exception as e:
            bt.logging.error(f"DAEMON | {my_uid} | Error in daemon loop: {e}")
            traceback.print_exc()
            time.sleep(10)


if __name__ == "__main__":
    main()
