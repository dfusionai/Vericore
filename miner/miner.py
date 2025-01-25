import os
import time
import argparse
import traceback
import bittensor as bt
from typing import Tuple, List

from veridex_protocol import VeridexSynapse, SourceEvidence

class Miner:
    def __init__(self):
        self.config = self.get_config()
        self.setup_logging()
        self.setup_bittensor_objects()

    def get_config(self):
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "--custom",
            default="my_custom_value",
            help="Adds a custom value to the parser.",
        )
        parser.add_argument(
            "--netuid", type=int, default=1, help="The chain subnet uid."
        )
        bt.subtensor.add_args(parser)
        bt.logging.add_args(parser)
        bt.wallet.add_args(parser)
        bt.axon.add_args(parser)

        config = bt.config(parser)
        config.full_path = os.path.expanduser(
            "{}/{}/{}/netuid{}/{}".format(
                config.logging.logging_dir,
                config.wallet.name,
                config.wallet.hotkey_str,
                config.netuid,
                "miner",
            )
        )
        os.makedirs(config.full_path, exist_ok=True)
        return config

    def setup_logging(self):
        bt.logging(config=self.config, logging_dir=self.config.full_path)
        bt.logging.info(
            f"Running miner for subnet: {self.config.netuid} on network: {self.config.subtensor.network} with config:"
        )
        bt.logging.info(self.config)

    def setup_bittensor_objects(self):
        bt.logging.info("Setting up Bittensor objects.")
        self.wallet = bt.wallet(config=self.config)
        bt.logging.info(f"Wallet: {self.wallet}")

        self.subtensor = bt.subtensor(config=self.config)
        bt.logging.info(f"Subtensor: {self.subtensor}")

        self.metagraph = self.subtensor.metagraph(self.config.netuid)
        bt.logging.info(f"Metagraph: {self.metagraph}")

        if self.wallet.hotkey.ss58_address not in self.metagraph.hotkeys:
            bt.logging.error(
                f"\nYour miner: {self.wallet} is not registered to chain connection: {self.subtensor} \nRun 'btcli register' and try again."
            )
            exit()
        else:
            self.my_subnet_uid = self.metagraph.hotkeys.index(
                self.wallet.hotkey.ss58_address
            )
            bt.logging.info(f"Running miner on uid: {self.my_subnet_uid}")

    def blacklist_fn(self, synapse: VeridexSynapse) -> Tuple[bool, str]:
        # basic check for recognized hotkeys
        if synapse.dendrite.hotkey not in self.metagraph.hotkeys:
            bt.logging.trace(
                f"Blacklisting unrecognized hotkey {synapse.dendrite.hotkey}"
            )
            return True, None
        bt.logging.trace(
            f"Not blacklisting recognized hotkey {synapse.dendrite.hotkey}"
        )
        return False, None

    def veridex_forward(self, synapse: VeridexSynapse) -> VeridexSynapse:
        """
        Naive logic that returns a couple of made-up snippet references.
        Typically, you'd want to do real searching or indexing here. 
        """
        # Example: we look at the statement, do a naive check if "Bitcoin" is in it
        # and pick a relevant snippet. Otherwise return generic snippet(s).

        example_response = []
        if "bitcoin" in synapse.statement.lower():
            # Suppose we "found" a snippet on Wikipedia
            e1 = SourceEvidence(
                url="https://en.wikipedia.org/wiki/Bitcoin",
                xpath="//div[@id='mw-content-text']",
                start_char=0,
                end_char=200,
                excerpt="Bitcoin is a decentralized digital currency..."
            )
            example_response.append(e1)
            # Another random one
            e2 = SourceEvidence(
                url="https://cointelegraph.com/bitcoin-article",
                xpath="//body/article[1]",
                start_char=0,
                end_char=150,
                excerpt="Cointelegraph coverage of Bitcoin suggests..."
            )
            example_response.append(e2)
        else:
            # Generic response if we have no special logic
            e3 = SourceEvidence(
                url="https://en.wikipedia.org/wiki/Example",
                xpath="//div[@id='mw-content-text']",
                start_char=0,
                end_char=120,
                excerpt="Example domain text about something..."
            )
            example_response.append(e3)

        synapse.veridex_response = example_response

        bt.logging.info(
            f"Miner received statement: '{synapse.statement}' with sources: {synapse.sources}.\n"
            f"Returning {synapse.veridex_response}"
        )
        return synapse

    def setup_axon(self):
        self.axon = bt.axon(wallet=self.wallet, config=self.config)
        bt.logging.info("Attaching forward function to axon.")
        self.axon.attach(
            forward_fn=self.veridex_forward,
            blacklist_fn=self.blacklist_fn,
        )
        bt.logging.info(
            f"Serving axon on network: {self.config.subtensor.network} with netuid: {self.config.netuid}"
        )
        self.axon.serve(netuid=self.config.netuid, subtensor=self.subtensor)
        bt.logging.info(f"Axon: {self.axon}")

        bt.logging.info(f"Starting axon server on port: {self.config.axon.port}")
        self.axon.start()

    def run(self):
        self.setup_axon()
        bt.logging.info(f"Starting main loop")
        step = 0
        while True:
            try:
                # periodically update metagraph
                if step % 60 == 0:
                    self.metagraph.sync()
                    log = (
                        f"Block: {self.metagraph.block.item()} | "
                        f"Incentive: {self.metagraph.I[self.my_subnet_uid]} | "
                    )
                    bt.logging.info(log)
                step += 1
                time.sleep(1)

            except KeyboardInterrupt:
                self.axon.stop()
                bt.logging.success("Miner killed by keyboard interrupt.")
                break
            except Exception as e:
                bt.logging.error(traceback.format_exc())
                continue

if __name__ == "__main__":
    miner = Miner()
    miner.run()
