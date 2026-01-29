import unittest
import sys
import os
from unittest.mock import patch

# Add the parent directory to the path to import the validator module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

# Create a comprehensive mock bittensor module before importing validator_daemon
class MockBt:
    class logging:
        @staticmethod
        def set_trace():
            pass

        @staticmethod
        def warning(msg):
            print(f"WARNING: {msg}")

        @staticmethod
        def info(msg):
            print(f"INFO: {msg}")

        @staticmethod
        def error(msg):
            print(f"ERROR: {msg}")

        @staticmethod
        def config(*args, **kwargs):
            pass

        @staticmethod
        def add_args(*args, **kwargs):
            pass

    class subtensor:
        @staticmethod
        def add_args(*args, **kwargs):
            pass

    class wallet:
        @staticmethod
        def add_args(*args, **kwargs):
            pass

sys.modules['bittensor'] = MockBt()

from validator.validator_daemon import (
    distribute_weights_burn_base_remainder,
    get_banned_hotkeys,
    move_miner_weights,
    convert_scores_to_weights,
    find_target_uid,
    DEFAULT_TOTAL_WEIGHT,
    EMISSION_CONTROL_PERC,
    BASE_WEIGHT_FRACTION,
    EMISSION_CONTROL_HOTKEY,
    USE_RANKING_EMISSION_CONTROL,
)


def make_neuron(uid, hotkey, validator_permit=False):
    n = type('Neuron', (), {})()
    n.uid = uid
    n.hotkey = hotkey
    n.validator_permit = validator_permit
    return n


def make_metagraph(neurons):
    m = type('Metagraph', (), {})()
    m.neurons = neurons
    return m


def _burn_weights_old(weights, metagraph, burn_perc=EMISSION_CONTROL_PERC):
    """Previous burn logic: give burn_perc of total to burn UID, split the rest proportionally. Used only for tests."""
    target_uid = find_target_uid(metagraph, EMISSION_CONTROL_HOTKEY)
    if target_uid is None or target_uid >= len(weights):
        return list(weights)
    weights = list(weights)
    total = sum(weights)
    new_target = burn_perc * total
    remaining = (1 - burn_perc) * total
    total_other = total - weights[target_uid]
    if total_other == 0:
        return weights
    result = [0.0] * len(weights)
    for i in range(len(weights)):
        if i == target_uid:
            result[i] = new_target
        else:
            result[i] = (weights[i] / total_other) * remaining
    return result


class TestDistributeWeightsBurnBaseRemainder(unittest.TestCase):
    """Test suite for burn -> base -> remainder weight distribution."""

    def test_total_weight_equals_65535(self):
        """After running the new distribution, sum(weights) == 65535."""
        neurons = [
            make_neuron(0, EMISSION_CONTROL_HOTKEY, False),
        ] + [
            make_neuron(i, f"hotkey_{i}", False) for i in range(1, 256)
        ]
        metagraph = make_metagraph(neurons)
        moving_scores = [1.0] * 256
        result = distribute_weights_burn_base_remainder(moving_scores, metagraph)
        self.assertEqual(len(result), 256)
        self.assertEqual(sum(result), int(DEFAULT_TOTAL_WEIGHT))

    def test_burn_uid_gets_80_percent(self):
        """Burn UID weight == 52_428 (0.80 * TOTAL); allow for rounding."""
        burn_uid = 0
        neurons = [make_neuron(burn_uid, EMISSION_CONTROL_HOTKEY, False)]
        neurons += [make_neuron(i, f"hotkey_{i}", False) for i in range(1, 10)]
        metagraph = make_metagraph(neurons)
        moving_scores = [1.0] * 10
        result = distribute_weights_burn_base_remainder(moving_scores, metagraph)
        expected_burn = int(EMISSION_CONTROL_PERC * DEFAULT_TOTAL_WEIGHT)
        self.assertGreaterEqual(result[burn_uid], expected_burn - 2)
        self.assertLessEqual(result[burn_uid], expected_burn + 2)

    def test_current_burn_same_as_previous_burn_calculation(self):
        """Current burn returns the same as the previous burn calculation (80% of total to burn UID)."""
        burn_uid = 0
        neurons = [make_neuron(burn_uid, EMISSION_CONTROL_HOTKEY, False)]
        neurons += [make_neuron(i, f"hotkey_{i}", False) for i in range(1, 20)]
        metagraph = make_metagraph(neurons)
        moving_scores = [float(i) for i in range(20, 0, -1)]
        # Previous flow: ranking then burn (80% to burn UID, 20% proportional)
        weights_ranking = convert_scores_to_weights(moving_scores, use_ranking=USE_RANKING_EMISSION_CONTROL)
        old_burn = _burn_weights_old(weights_ranking, metagraph)
        # Current flow: burn first, then base, then remainder (diff applied to miner so burn stays exact)
        new_result = distribute_weights_burn_base_remainder(moving_scores, metagraph)
        previous_burn_weight = old_burn[burn_uid]  # float: 0.80 * DEFAULT_TOTAL_WEIGHT
        current_burn_weight = new_result[burn_uid]  # int
        self.assertEqual(current_burn_weight, int(round(previous_burn_weight)))

    def test_base_pool_and_per_miner(self):
        """For 256 miners, base_pool = 655.35, each miner gets at least base_per_miner ~ 2.56; validators get 0."""
        burn_uid = 0
        neurons = [make_neuron(burn_uid, EMISSION_CONTROL_HOTKEY, False)]
        neurons += [make_neuron(i, f"hotkey_{i}", False) for i in range(1, 256)]
        metagraph = make_metagraph(neurons)
        moving_scores = [0.5] * 256
        result = distribute_weights_burn_base_remainder(moving_scores, metagraph)
        base_pool = BASE_WEIGHT_FRACTION * DEFAULT_TOTAL_WEIGHT
        n_miners = 255
        base_per_miner = base_pool / n_miners
        for uid in range(1, 256):
            self.assertGreaterEqual(result[uid], int(base_per_miner) - 1)

    def test_remainder_distributed_by_ranking(self):
        """Remainder is split among miners only; top miners by moving_scores get base + larger share."""
        burn_uid = 0
        neurons = [make_neuron(burn_uid, EMISSION_CONTROL_HOTKEY, False)]
        neurons += [make_neuron(i, f"hotkey_{i}", False) for i in range(1, 5)]
        metagraph = make_metagraph(neurons)
        moving_scores = [0.0, 1.0, 2.0, 3.0, 4.0]
        result = distribute_weights_burn_base_remainder(moving_scores, metagraph)
        self.assertEqual(sum(result), int(DEFAULT_TOTAL_WEIGHT))
        self.assertGreater(result[4], result[3])
        self.assertGreater(result[3], result[2])
        self.assertGreater(result[2], result[1])

    def test_validators_get_zero(self):
        """Mock metagraph with validator_permit=True; those UIDs have weight 0."""
        burn_uid = 0
        neurons = [make_neuron(burn_uid, EMISSION_CONTROL_HOTKEY, False)]
        neurons += [make_neuron(1, "hotkey_1", True)]
        neurons += [make_neuron(i, f"hotkey_{i}", False) for i in range(2, 5)]
        metagraph = make_metagraph(neurons)
        moving_scores = [1.0] * 5
        result = distribute_weights_burn_base_remainder(moving_scores, metagraph)
        self.assertEqual(result[1], 0)

    def test_banned_wallets_get_zero(self):
        """Mock metagraph with hotkeys in BANNED_WALLET_HOTKEYS; those UIDs have weight 0."""
        burn_uid = 0
        banned_hk = "banned_hotkey_2"
        neurons = [make_neuron(burn_uid, EMISSION_CONTROL_HOTKEY, False)]
        neurons += [make_neuron(1, "hotkey_1", False)]
        neurons += [make_neuron(2, banned_hk, False)]
        neurons += [make_neuron(3, "hotkey_3", False)]
        metagraph = make_metagraph(neurons)
        moving_scores = [1.0] * 4
        prev = os.environ.get("BANNED_WALLET_HOTKEYS")
        try:
            os.environ["BANNED_WALLET_HOTKEYS"] = banned_hk
            result = distribute_weights_burn_base_remainder(
                moving_scores, metagraph, banned_hotkeys={banned_hk}
            )
            self.assertEqual(result[2], 0)
        finally:
            if prev is not None:
                os.environ["BANNED_WALLET_HOTKEYS"] = prev
            else:
                os.environ.pop("BANNED_WALLET_HOTKEYS", None)

    def test_burn_uid_not_found(self):
        """When burn UID is missing, no crash; full total distributed as base + remainder."""
        neurons = [make_neuron(i, f"hotkey_{i}", False) for i in range(5)]
        metagraph = make_metagraph(neurons)
        moving_scores = [1.0] * 5
        result = distribute_weights_burn_base_remainder(moving_scores, metagraph)
        self.assertEqual(len(result), 5)
        self.assertEqual(sum(result), int(DEFAULT_TOTAL_WEIGHT))
        self.assertGreater(min(result), 0)

    def test_zero_miners(self):
        """When all UIDs are validators (or burn only), no division by zero; weights sum to total."""
        burn_uid = 0
        neurons = [make_neuron(burn_uid, EMISSION_CONTROL_HOTKEY, False)]
        neurons += [make_neuron(i, f"hotkey_{i}", True) for i in range(1, 5)]
        metagraph = make_metagraph(neurons)
        moving_scores = [1.0] * 5
        result = distribute_weights_burn_base_remainder(moving_scores, metagraph)
        self.assertEqual(sum(result), int(DEFAULT_TOTAL_WEIGHT))
        self.assertEqual(result[burn_uid], int(DEFAULT_TOTAL_WEIGHT))
        for uid in range(1, 5):
            self.assertEqual(result[uid], 0)

    def test_emission_control_false_equals_convert_scores_to_weights(self):
        """When ENABLE_EMISSION_CONTROL is False, move_miner_weights returns same as convert_scores_to_weights (old way)."""
        neurons = [make_neuron(i, f"hotkey_{i}", False) for i in range(5)]
        metagraph = make_metagraph(neurons)
        moving_scores = [1.0, 2.0, 3.0, 4.0, 5.0]
        with patch("validator.validator_daemon.ENABLE_EMISSION_CONTROL", False):
            result_move = move_miner_weights(moving_scores, metagraph, my_uid=0, banned_hotkeys=None)
        result_old = convert_scores_to_weights(
            moving_scores, use_ranking=USE_RANKING_EMISSION_CONTROL
        )
        self.assertEqual(result_move, result_old)

    def test_256_nodes_formula(self):
        """Explicit check: sum == 65535, burn ~ 52_428, per-miner base ~ 2.56 for 255 miners."""
        burn_uid = 0
        neurons = [make_neuron(burn_uid, EMISSION_CONTROL_HOTKEY, False)]
        neurons += [make_neuron(i, f"hotkey_{i}", False) for i in range(1, 256)]
        metagraph = make_metagraph(neurons)
        moving_scores = [float(i % 10) for i in range(256)]
        result = distribute_weights_burn_base_remainder(moving_scores, metagraph)
        self.assertEqual(sum(result), 65535)
        expected_burn = 52428
        self.assertGreaterEqual(result[burn_uid], expected_burn - 150)
        self.assertLessEqual(result[burn_uid], expected_burn + 150)
        base_pool = BASE_WEIGHT_FRACTION * DEFAULT_TOTAL_WEIGHT
        base_per_miner = base_pool / 255
        self.assertAlmostEqual(base_per_miner, 2.56, delta=0.1)


class TestGetBannedHotkeys(unittest.TestCase):
    """Test get_banned_hotkeys from env."""

    def test_empty_when_unset(self):
        os.environ.pop("BANNED_WALLET_HOTKEYS", None)
        self.assertEqual(get_banned_hotkeys(), set())

    def test_parses_comma_separated(self):
        prev = os.environ.get("BANNED_WALLET_HOTKEYS")
        try:
            os.environ["BANNED_WALLET_HOTKEYS"] = " a , b , c "
            self.assertEqual(get_banned_hotkeys(), {"a", "b", "c"})
        finally:
            if prev is not None:
                os.environ["BANNED_WALLET_HOTKEYS"] = prev
            else:
                os.environ.pop("BANNED_WALLET_HOTKEYS", None)

    def test_skips_empty(self):
        prev = os.environ.get("BANNED_WALLET_HOTKEYS")
        try:
            os.environ["BANNED_WALLET_HOTKEYS"] = " x ,  , y "
            self.assertEqual(get_banned_hotkeys(), {"x", "y"})
        finally:
            if prev is not None:
                os.environ["BANNED_WALLET_HOTKEYS"] = prev
            else:
                os.environ.pop("BANNED_WALLET_HOTKEYS", None)


if __name__ == '__main__':
    unittest.main()
