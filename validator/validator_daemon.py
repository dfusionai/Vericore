import os
import time
import json
import argparse
import traceback
import numpy as np
import bittensor as bt
import logging

from shared.debug_util import DEBUG_LOCAL
from shared.log_data import LoggerType
from shared.proxy_log_handler import register_proxy_log_handler

from dotenv import load_dotenv

bt.logging.set_trace()

load_dotenv()

INITIAL_WEIGHT = 0.0


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


def aggregate_results(results_dir, moving_scores):
    """
    Scan the results directory for JSON files (each a query result), update moving_scores
    for each miner based on the reported final_score, then delete each processed file.
    """
    files = [
        os.path.join(results_dir, f)
        for f in os.listdir(results_dir)
        if f.endswith(".json")
    ]
    if not files:
        return moving_scores

    for filepath in files:
        try:
            with open(filepath, "r") as f:
                result = json.load(f)
            for res in result.get("results", []):
                miner_uid = res.get("miner_uid")
                final_score = res.get("final_score")
                if miner_uid is not None and final_score is not None:
                    calculated_score = moving_scores[miner_uid] + final_score

                    bt.logging.info(
                        f"Moving score for uid: {miner_uid} and final score: {final_score} with calculated scored {calculated_score}"
                    )
                    moving_scores[miner_uid] = calculated_score
        except Exception as e:
            bt.logging.error(f"Error processing file {filepath}: {e}")
        finally:
            try:
                os.remove(filepath)
                bt.logging.info(f"Deleted processed file {filepath}")
            except Exception as e:
                bt.logging.error(f"Error deleting file {filepath}: {e}")
    return moving_scores


def main():
    config = get_config()
    wallet, subtensor, metagraph = setup_bittensor_objects(config)
    setup_logging(wallet, config)
    results_dir = "results"
    os.makedirs(results_dir, exist_ok=True)

    tempo = subtensor.tempo(config.netuid)
    my_uid = metagraph.hotkeys.index(wallet.hotkey.ss58_address)
    bt.logging.info("Starting Validator Daemon loop.")
    while True:
        try:
            last_update = subtensor.blocks_since_last_update(config.netuid, my_uid)
            bt.logging.info(
                f"Will aggregate results: {last_update} > {tempo + 1} = {last_update > tempo + 1} "
            )
            if last_update > tempo + 1:
            # if True:
                bt.logging.info(f"Aggregating results")
                metagraph.sync()

                # create new moving scores array in case new miners have been loaded
                moving_scores = [INITIAL_WEIGHT] * len(metagraph.S)
                moving_scores = aggregate_results(results_dir, moving_scores)

                if all(scores == 0 for scores in moving_scores):
                    bt.logging.warning(f"Skipped setting of weights")
                    # Sleep for 5 seconds
                    time.sleep(10)
                    # Don't update weights if  all moving scores are 0 otherwise it might rate the weights equally.
                    continue

                bt.logging.info(f"Moving scores: {moving_scores}")
                arr = np.array(moving_scores, dtype=np.float32)
                scale   = 8.0
                deltas  = arr.max() - arr
                exp_dec = np.exp(-deltas / scale)
                weights = ((exp_dec / exp_dec.sum())*65535).tolist()
                bt.logging.info(f"Setting weights on chain: {weights}")
                subtensor.set_weights(
                    netuid=config.netuid,
                    wallet=wallet,
                    uids=metagraph.uids,
                    weights=weights,
                    wait_for_inclusion=True,
                )
                if DEBUG_LOCAL:
                    for neuron in subtensor.neurons(netuid=config.netuid):
                        print(f"Miner UID: {neuron.uid} INCENTIVE: {neuron.incentive} ")

            metagraph.sync()
            time.sleep(60)
        except KeyboardInterrupt:
            bt.logging.info(f"Validator Daemon interrupted. Exiting.")
            break
        except Exception as e:
            bt.logging.error(f"Error in daemon loop: {e}")
            traceback.print_exc()
            time.sleep(10)


if __name__ == "__main__":
    main()
