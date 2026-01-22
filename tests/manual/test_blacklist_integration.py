"""
Integration test for miner blacklist_fn function.
This test uses REAL Bittensor objects - no mocking.
It connects to the actual network and tests with real wallets and metagraph.

Usage:
    # Basic usage (mainnet, subnet 1)
    python tests/manual/test_blacklist_integration.py --wallet.name mywallet --wallet.hotkey miner_hotkey --netuid 1

    # Mainnet (Finney) - explicit
    python tests/manual/test_blacklist_integration.py --wallet.name mywallet --wallet.hotkey miner_hotkey --netuid 1 --subtensor.network finney

    # Testnet
    python tests/manual/test_blacklist_integration.py --wallet.name mywallet --wallet.hotkey miner_hotkey --netuid 1 --subtensor.network test

    # Local/Development
    python tests/manual/test_blacklist_integration.py --wallet.name mywallet --wallet.hotkey miner_hotkey --netuid 1 --subtensor.network ws://127.0.0.1:9944

Note:
    - The wallet does NOT need to be registered on the subnet you're testing
    - The wallet is only used to connect to the network
    - The test will test with real validators/miners from the network
    - Your wallet will only be tested if it's registered on that subnet

This test will:
1. Load a real wallet (any wallet, doesn't need to be registered)
2. Connect to the Bittensor network
3. Load the real metagraph for the specified subnet
4. Test the blacklist_fn with real validator hotkeys from the network
5. Test with real miner hotkeys (should be rejected)
6. Test with unknown hotkeys (should be rejected)
7. Optionally test with your own wallet if it's registered
8. Verify validator_permit checks work correctly
"""

import sys
import os
import argparse
import bittensor as bt

# Add the parent directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from miner.perplexica.miner import Miner
from shared.veridex_protocol import VericoreSynapse


def create_real_synapse(hotkey, metagraph=None):
    """Create a real synapse object with the given hotkey"""
    # Create a minimal synapse for testing
    # The synapse needs statement as it's required, but we're only testing blacklist_fn
    synapse = VericoreSynapse(statement="test statement")

    # The dendrite represents the requester (validator/miner making the request)
    # We need to create a proper TerminalInfo object with the CORRECT hotkey
    # NOTE: We cannot use neuron.axon_info directly because axon_info.hotkey
    # may not match the neuron's hotkey in metagraph.hotkeys[uid]

    # Find any neuron with axon_info to use as a template
    template_axon = None
    if metagraph and len(metagraph.neurons) > 0:
        for neuron in metagraph.neurons:
            if neuron.axon_info:
                template_axon = neuron.axon_info
                break

    if template_axon:
        try:
            # Create a new TerminalInfo with the correct hotkey
            # Use model_dump to get dict, set correct hotkey, then model_validate
            if hasattr(template_axon, 'model_dump'):
                axon_dict = template_axon.model_dump()
            else:
                axon_dict = dict(template_axon.__dict__)

            axon_dict['hotkey'] = hotkey

            # Use model_validate to create new TerminalInfo
            if hasattr(template_axon, 'model_validate'):
                terminal = template_axon.__class__.model_validate(axon_dict)
            else:
                terminal = type(template_axon)(**axon_dict)

            synapse.dendrite = terminal
            return synapse
        except Exception as e1:
            # Try using type() constructor
            try:
                terminal_dict = {
                    'version': getattr(template_axon, 'version', 0),
                    'ip': getattr(template_axon, 'ip', '0.0.0.0'),
                    'port': getattr(template_axon, 'port', 0),
                    'ip_type': getattr(template_axon, 'ip_type', 4),
                    'hotkey': hotkey,
                    'coldkey': getattr(template_axon, 'coldkey', ''),
                }
                terminal = type(template_axon)(**terminal_dict)
                synapse.dendrite = terminal
                return synapse
            except Exception as e2:
                # Final fallback: bypass Pydantic validation
                pass

    # Fallback: Create a minimal object with just the hotkey attribute
    # and bypass Pydantic validation using object.__setattr__
    class MinimalTerminal:
        def __init__(self, hotkey):
            self.hotkey = hotkey

    object.__setattr__(synapse, 'dendrite', MinimalTerminal(hotkey))
    return synapse


def get_validators_from_metagraph(metagraph, max_validators=10):
    """Get a list of validators from the metagraph"""
    validators = []
    for i, neuron in enumerate(metagraph.neurons):
        if neuron.validator_permit:
            validators.append({
                'uid': i,
                'hotkey': neuron.hotkey,
                'validator_permit': neuron.validator_permit,
                'axon_info': neuron.axon_info
            })
            if len(validators) >= max_validators:
                break
    return validators


def get_miners_from_metagraph(metagraph, max_miners=5):
    """Get a list of miners (non-validators) from the metagraph"""
    miners = []
    for i, neuron in enumerate(metagraph.neurons):
        if not neuron.validator_permit and neuron.hotkey in metagraph.hotkeys:
            miners.append({
                'uid': i,
                'hotkey': neuron.hotkey,
                'validator_permit': neuron.validator_permit,
                'axon_info': neuron.axon_info
            })
            if len(miners) >= max_miners:
                break
    return miners


def test_blacklist_with_real_network(config):
    """Test blacklist_fn using real Bittensor network"""
    print("=" * 70)
    print("Integration Test: Miner Blacklist Function (Real Network)")
    print("=" * 70)
    print(f"\nNetwork: {config.subtensor.network}")
    print(f"Netuid: {config.netuid}")
    print(f"Wallet: {config.wallet.name}/{config.wallet.hotkey_str}")
    print()

    try:
        # Initialize real Bittensor objects
        print("Initializing Bittensor objects...")
        wallet = bt.wallet(config=config)
        print(f"✓ Wallet loaded: {wallet.hotkey.ss58_address}")

        subtensor = bt.subtensor(config=config)
        print(f"✓ Subtensor connected: {subtensor.network}")

        metagraph = subtensor.metagraph(config.netuid)
        print(f"✓ Metagraph loaded: {len(metagraph.neurons)} neurons")

        # Sync metagraph to ensure it's up-to-date
        print("Syncing metagraph to ensure latest state...")
        metagraph.sync()
        print(f"✓ Metagraph synced: {len(metagraph.neurons)} neurons")
        print()

        # Create miner instance (partial initialization for testing)
        miner = Miner.__new__(Miner)
        miner.metagraph = metagraph
        miner.config = config

        # Get real validators and miners from the network
        print("Fetching validators and miners from network...")
        validators = get_validators_from_metagraph(metagraph, max_validators=5)
        miners = get_miners_from_metagraph(metagraph, max_miners=3)

        print(f"✓ Found {len(validators)} validators")
        print(f"✓ Found {len(miners)} miners")
        print()

        if len(validators) == 0:
            print("⚠ WARNING: No validators found in metagraph!")
            print("  Cannot test validator permit check.")
            return False

        if len(miners) == 0:
            print("⚠ WARNING: No miners found in metagraph!")
            print("  Cannot test miner rejection.")

        # Test results
        passed = 0
        failed = 0
        results = []

        # Test 1: Test with real validators (should ALLOW)
        print("=" * 70)
        print("Test 1: Testing with REAL Validators (should ALLOW)")
        print("=" * 70)
        print()

        for i, validator in enumerate(validators, 1):
            print(f"Test {i}: Validator UID {validator['uid']}")
            print(f"  Hotkey: {validator['hotkey']}")
            print(f"  Validator Permit: {validator['validator_permit']}")

            synapse = create_real_synapse(validator['hotkey'], metagraph)

            try:
                # Verify synapse is created correctly
                if synapse.dendrite.hotkey != validator['hotkey']:
                    print(f"  ⚠ WARNING: Synapse hotkey mismatch! Expected: {validator['hotkey']}, Got: {synapse.dendrite.hotkey}")

                should_blacklist, reason = miner.blacklist_fn(synapse)

                if not should_blacklist:
                    print(f"  ✓ PASSED - Validator allowed (as expected)")
                    passed += 1
                    results.append({
                        'type': 'validator',
                        'uid': validator['uid'],
                        'hotkey': validator['hotkey'],
                        'passed': True
                    })
                else:
                    print(f"  ✗ FAILED - Validator was blacklisted (unexpected!)")
                    print(f"    Reason: {reason}")
                    failed += 1
                    results.append({
                        'type': 'validator',
                        'uid': validator['uid'],
                        'hotkey': validator['hotkey'],
                        'passed': False,
                        'error': 'Validator incorrectly blacklisted'
                    })
            except Exception as e:
                print(f"  ✗ ERROR - Exception: {e}")
                failed += 1
                results.append({
                    'type': 'validator',
                    'uid': validator['uid'],
                    'hotkey': validator['hotkey'],
                    'passed': False,
                    'error': str(e)
                })
            print()

        # Test 2: Test with real miners (should REJECT)
        if len(miners) > 0:
            print("=" * 70)
            print("Test 2: Testing with REAL Miners (should REJECT)")
            print("=" * 70)
            print()

            for i, miner_node in enumerate(miners, 1):
                print(f"Test {i}: Miner UID {miner_node['uid']}")
                print(f"  Hotkey: {miner_node['hotkey']}")
                print(f"  Validator Permit: {miner_node['validator_permit']}")

                synapse = create_real_synapse(miner_node['hotkey'], metagraph)

                try:
                    # Debug: Check what the synapse has
                    print(f"  DEBUG: Synapse dendrite type: {type(synapse.dendrite)}")
                    print(f"  DEBUG: Synapse dendrite hotkey: {synapse.dendrite.hotkey}")
                    print(f"  DEBUG: Expected hotkey: {miner_node['hotkey']}")
                    print(f"  DEBUG: Hotkeys match: {synapse.dendrite.hotkey == miner_node['hotkey']}")
                    print(f"  DEBUG: Hotkey in metagraph: {synapse.dendrite.hotkey in miner.metagraph.hotkeys}")
                    if synapse.dendrite.hotkey in miner.metagraph.hotkeys:
                        neuron_uid = miner.metagraph.hotkeys.index(synapse.dendrite.hotkey)
                        neuron = miner.metagraph.neurons[neuron_uid]
                        print(f"  DEBUG: Found neuron UID: {neuron_uid}")
                        print(f"  DEBUG: Neuron hotkey: {neuron.hotkey}")
                        print(f"  DEBUG: Neuron validator_permit: {neuron.validator_permit}")
                        print(f"  DEBUG: Expected validator_permit: {miner_node['validator_permit']}")
                        print(f"  DEBUG: Neuron hotkey matches synapse: {neuron.hotkey == synapse.dendrite.hotkey}")

                    should_blacklist, reason = miner.blacklist_fn(synapse)
                    print(f"  DEBUG: blacklist_fn returned: should_blacklist={should_blacklist}, reason={reason}")

                    if should_blacklist:
                        print(f"  ✓ PASSED - Miner correctly blacklisted")
                        passed += 1
                        results.append({
                            'type': 'miner',
                            'uid': miner_node['uid'],
                            'hotkey': miner_node['hotkey'],
                            'passed': True
                        })
                    else:
                        print(f"  ✗ FAILED - Miner was NOT blacklisted (SECURITY ISSUE!)")
                        print(f"    This miner should be rejected because validator_permit=False")
                        failed += 1
                        results.append({
                            'type': 'miner',
                            'uid': miner_node['uid'],
                            'hotkey': miner_node['hotkey'],
                            'passed': False,
                            'error': 'Miner incorrectly allowed (SECURITY ISSUE)'
                        })
                except Exception as e:
                    print(f"  ✗ ERROR - Exception: {e}")
                    failed += 1
                    results.append({
                        'type': 'miner',
                        'uid': miner_node['uid'],
                        'hotkey': miner_node['hotkey'],
                        'passed': False,
                        'error': str(e)
                    })
                print()

        # Test 3: Test with unknown hotkey (should REJECT)
        print("=" * 70)
        print("Test 3: Testing with Unknown Hotkey (should REJECT)")
        print("=" * 70)
        print()

        unknown_hotkey = "5FHneW46xGXgs5mUiveU4sbTyGBzmstUspZC92UhjJM694ty"  # Random hotkey
        print(f"Test: Unknown Hotkey")
        print(f"  Hotkey: {unknown_hotkey}")

        synapse = create_real_synapse(unknown_hotkey, metagraph)

        try:
            # Debug: Check what the synapse has
            print(f"  DEBUG: Synapse dendrite hotkey: {synapse.dendrite.hotkey}")
            print(f"  DEBUG: Expected hotkey: {unknown_hotkey}")
            print(f"  DEBUG: Hotkeys match: {synapse.dendrite.hotkey == unknown_hotkey}")
            print(f"  DEBUG: Hotkey in metagraph: {synapse.dendrite.hotkey in miner.metagraph.hotkeys}")

            should_blacklist, reason = miner.blacklist_fn(synapse)

            if should_blacklist:
                print(f"  ✓ PASSED - Unknown hotkey correctly blacklisted")
                passed += 1
            else:
                print(f"  ✗ FAILED - Unknown hotkey was NOT blacklisted (SECURITY ISSUE!)")
                failed += 1
        except Exception as e:
            print(f"  ✗ ERROR - Exception: {e}")
            failed += 1
        print()

        # Test 4: Test with your own wallet (if it's a validator, should allow; if miner, should reject)
        print("=" * 70)
        print("Test 4: Testing with Your Wallet")
        print("=" * 70)
        print()

        your_hotkey = wallet.hotkey.ss58_address
        print(f"Your Hotkey: {your_hotkey}")

        # Check if your wallet is in the metagraph
        if your_hotkey in metagraph.hotkeys:
            your_uid = metagraph.hotkeys.index(your_hotkey)
            your_neuron = metagraph.neurons[your_uid]
            print(f"Your UID: {your_uid}")
            print(f"Your Validator Permit: {your_neuron.validator_permit}")

            synapse = create_real_synapse(your_hotkey, metagraph)

            try:
                should_blacklist, reason = miner.blacklist_fn(synapse)

                if your_neuron.validator_permit:
                    # You're a validator, should be allowed
                    if not should_blacklist:
                        print(f"  ✓ PASSED - Your validator wallet is correctly allowed")
                        passed += 1
                    else:
                        print(f"  ✗ FAILED - Your validator wallet was incorrectly blacklisted")
                        failed += 1
                else:
                    # You're a miner, should be rejected
                    if should_blacklist:
                        print(f"  ✓ PASSED - Your miner wallet is correctly blacklisted")
                        passed += 1
                    else:
                        print(f"  ✗ FAILED - Your miner wallet was incorrectly allowed")
                        print(f"    Note: This is expected if you're testing as a miner")
                        failed += 1
            except Exception as e:
                print(f"  ✗ ERROR - Exception: {e}")
                failed += 1
        else:
            print(f"  ⚠ INFO - Your wallet is not registered in this subnet")
            print(f"    Cannot test with your own wallet")
        print()

        # Summary
        print("=" * 70)
        print("Test Summary")
        print("=" * 70)
        print(f"Total tests: {passed + failed}")
        print(f"Passed: {passed} ✓")
        print(f"Failed: {failed} ✗")
        print()

        # Security check
        print("Security Check:")
        print("-" * 70)
        validator_tests = [r for r in results if r.get('type') == 'validator']
        miner_tests = [r for r in results if r.get('type') == 'miner']

        validator_passed = all(r.get('passed', False) for r in validator_tests)
        miner_blocked = all(r.get('passed', False) for r in miner_tests)

        if validator_passed:
            print("✓ Validators are correctly allowed")
        else:
            print("✗ Some validators were incorrectly rejected!")

        if miner_blocked:
            print("✓ Miners are correctly blocked")
        else:
            print("✗ Some miners were incorrectly allowed! (CRITICAL SECURITY ISSUE)")

        print()

        if failed == 0:
            print("=" * 70)
            print("✓ ALL TESTS PASSED - Blacklist function is working correctly!")
            print("=" * 70)
            return True
        else:
            print("=" * 70)
            print(f"✗ {failed} TEST(S) FAILED")
            print("=" * 70)
            return False

    except Exception as e:
        print(f"\n✗ ERROR: Test execution failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def get_config():
    """Get Bittensor config from command line arguments"""
    parser = argparse.ArgumentParser(description="Integration test for miner blacklist function")
    parser.add_argument("--netuid", type=int, default=1, help="Subnet UID")
    bt.subtensor.add_args(parser)
    bt.wallet.add_args(parser)
    bt.logging.add_args(parser)

    config = bt.config(parser)
    return config


if __name__ == '__main__':
    print("\n" + "=" * 70)
    print("Miner Blacklist Function - Integration Test (Real Network)")
    print("=" * 70)
    print("\nThis test uses REAL Bittensor objects and connects to the actual network.")
    print("No mocking - tests with real wallets and metagraph.\n")

    try:
        config = get_config()
        success = test_blacklist_with_real_network(config)
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
