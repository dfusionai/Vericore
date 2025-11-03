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
EMISSION_CONTROL_PERC = 0.5

def find_target_uid(metagraph, hotkey):
    for neuron in metagraph.neurons:
        if neuron.hotkey == hotkey:
            emission_control_uid = neuron.uid
            return emission_control_uid

def burn_weights(weights, metagraph):
    target_uid = find_target_uid(metagraph, EMISSION_CONTROL_HOTKEY)
    if not target_uid:
        bt.logging.info(f"target emission control hotkey {EMISSION_CONTROL_HOTKEY} is not found")
        return weights

    total_score = np.sum(weights)
    new_target_score = EMISSION_CONTROL_PERC * total_score
    remaining_weight = (1 - EMISSION_CONTROL_PERC) * total_score
    total_other_scores = total_score - weights[target_uid]

    if total_other_scores == 0:
        bt.logging.warning("All scores are zero except target UID, cannot scale.")
        return weights

    new_scores = np.zeros_like(weights, dtype=float)
    uids = metagraph.uids

    for i, (uid, weight) in enumerate(zip(uids, weights)):
        if uid == target_uid:
            new_scores[i] = new_target_score
        else:
            new_scores[i] = (weight / total_other_scores) * remaining_weight

    return new_scores


class WeightedMinerRecord:
    calculated_score: float = 0
    count: int = 0
    wallet_hotkey:str = ""

def get_config():
    parser = argparse.ArgumentParser()
    parser.add_argument("--custom", default="my_custom_value", help="Custom value")
    parser.add_argument("--netuid", type=int, default=1, help="Chain subnet uid")
    bt.Subtensor.add_args(parser)
    bt.logging.add_args(parser)
    bt.Wallet.add_args(parser)
    config = bt.Config(parser)
    config.full_path = os.path.expanduser(
        "{}/{}/{}/netuid{}/validator".format(
            config.logging.logging_dir,
            config.wallet.name,
            config.wallet.hotkey,
            config.netuid,
        )
    )
    os.makedirs(config.full_path, exist_ok=True)
    return config

def setup_bittensor_objects(config):
    wallet = bt.Wallet(config=config)
    bt.logging.info(f"Wallet: {wallet}")
    subtensor = bt.Subtensor(config=config)
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

                bt.logging.info(f"DAEMON | {my_uid} | Moving scores: {moving_scores}")
                arr = np.array(moving_scores, dtype=np.float32)
                scale = 4.0
                deltas = arr.max() - arr
                exp_dec = np.exp(-deltas / scale)
                weights = ((exp_dec / exp_dec.sum()) * 65535).tolist()
                weights_burned = burn_weights(weights, metagraph).tolist() if ENABLE_EMISSION_CONTROL else weights
                bt.logging.info(f"DAEMON | {my_uid} | Setting weights on chain: {weights_burned}")
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
