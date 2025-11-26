import unittest
import sys
import os

# Add the parent directory to the path to import the validator module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

# Create a comprehensive mock bittensor module before importing validator_daemon
class MockBt:
    class logging:
        @staticmethod
        def set_trace():
            pass  # Mock for debugging
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

# Patch the bittensor module before importing
sys.modules['bittensor'] = MockBt()

# Import the actual function and constants from validator_daemon
from validator.validator_daemon import distribute_weights_by_ranking, DEFAULT_TOTAL_WEIGHT, RANKING_EMISSION_TOP_PERC


class TestDistributeWeightsByRanking(unittest.TestCase):
    """Test suite for distribute_weights_by_ranking function"""

    def test_empty_scores(self):
        """Test with empty scores array"""
        moving_scores = []
        result = distribute_weights_by_ranking(moving_scores)
        self.assertEqual(result, [])

    def test_single_score(self):
        """Test with single score"""
        moving_scores = [10.0]
        result = distribute_weights_by_ranking(moving_scores)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], int(DEFAULT_TOTAL_WEIGHT))
        self.assertEqual(sum(result), int(DEFAULT_TOTAL_WEIGHT))

    def test_two_scores_descending(self):
        """Test with two scores in descending order"""
        moving_scores = [10.0, 5.0]
        result = distribute_weights_by_ranking(moving_scores)

        self.assertEqual(len(result), 2)
        # Top should get 50% of total_weight
        expected_top = int(DEFAULT_TOTAL_WEIGHT * RANKING_EMISSION_TOP_PERC)
        # Second should get 25% of total_weight
        expected_second = int(DEFAULT_TOTAL_WEIGHT * 0.25)
        # Remainder goes to top
        remainder = int(DEFAULT_TOTAL_WEIGHT) - expected_top - expected_second
        expected_top += remainder

        self.assertEqual(result[0], expected_top)  # Highest score gets top allocation
        self.assertEqual(result[1], expected_second)
        self.assertEqual(sum(result), int(DEFAULT_TOTAL_WEIGHT))

    def test_two_scores_ascending(self):
        """Test with two scores in ascending order - should still rank correctly"""
        moving_scores = [5.0, 10.0]
        result = distribute_weights_by_ranking(moving_scores)

        self.assertEqual(len(result), 2)
        # Index 1 has higher score, so should get top allocation
        self.assertGreater(result[1], result[0])
        self.assertEqual(sum(result), int(DEFAULT_TOTAL_WEIGHT))

    def test_geometric_progression(self):
        """Test that weights follow geometric progression (50%, 25%, 12.5%, etc.)"""
        moving_scores = [10.0, 8.0, 6.0, 4.0, 2.0]
        result = distribute_weights_by_ranking(moving_scores)

        self.assertEqual(len(result), 5)
        self.assertEqual(sum(result), int(DEFAULT_TOTAL_WEIGHT))

        # Verify ranking order (higher scores get more weight)
        self.assertGreater(result[0], result[1])  # Top > second
        self.assertGreater(result[1], result[2])  # Second > third
        self.assertGreater(result[2], result[3])  # Third > fourth
        self.assertGreater(result[3], result[4])  # Fourth > fifth

        # Verify approximate percentages (allowing for rounding)
        total = float(sum(result))
        self.assertAlmostEqual(result[0] / total, RANKING_EMISSION_TOP_PERC, delta=0.01)
        self.assertAlmostEqual(result[1] / total, 0.25, delta=0.01)
        self.assertAlmostEqual(result[2] / total, 0.125, delta=0.01)

    def test_equal_scores(self):
        """Test with equal scores - first one should get top allocation"""
        moving_scores = [5.0, 5.0, 5.0]
        result = distribute_weights_by_ranking(moving_scores)

        self.assertEqual(len(result), 3)
        self.assertEqual(sum(result), int(DEFAULT_TOTAL_WEIGHT))
        # First index gets top allocation (stable sort)
        self.assertGreaterEqual(result[0], result[1])
        self.assertGreaterEqual(result[1], result[2])

    def test_zero_scores(self):
        """Test with all zero scores"""
        moving_scores = [0.0, 0.0, 0.0]
        result = distribute_weights_by_ranking(moving_scores)

        self.assertEqual(len(result), 3)
        self.assertEqual(sum(result), int(DEFAULT_TOTAL_WEIGHT))
        # All should get equal allocation when scores are equal
        self.assertGreaterEqual(min(result), 0)

    def test_mixed_positive_negative(self):
        """Test with mixed positive and negative scores"""
        moving_scores = [10.0, -5.0, 3.0]
        result = distribute_weights_by_ranking(moving_scores)

        self.assertEqual(len(result), 3)
        self.assertEqual(sum(result), int(DEFAULT_TOTAL_WEIGHT))
        # Highest score (10.0) should get most weight
        self.assertGreater(result[0], result[2])  # 10.0 > 3.0
        self.assertGreater(result[2], result[1])  # 3.0 > -5.0

    def test_custom_total_weight(self):
        """Test with custom total_weight"""
        moving_scores = [10.0, 5.0]
        custom_total = 1000.0
        result = distribute_weights_by_ranking(moving_scores, total_weight=custom_total)

        self.assertEqual(len(result), 2)
        self.assertEqual(sum(result), int(custom_total))
        # Top should get 50% of custom_total
        expected_top = int(custom_total * RANKING_EMISSION_TOP_PERC)
        remainder = int(custom_total) - expected_top - int(custom_total * 0.25)
        expected_top += remainder
        self.assertEqual(result[0], expected_top)

    def test_custom_top_percentage(self):
        """Test with custom top_percentage"""
        moving_scores = [10.0, 5.0, 3.0]
        custom_percentage = 0.6  # 60% for top
        result = distribute_weights_by_ranking(moving_scores, top_percentage=custom_percentage)

        self.assertEqual(len(result), 3)
        self.assertEqual(sum(result), int(DEFAULT_TOTAL_WEIGHT))

        # Verify top gets approximately 60%
        total = float(sum(result))
        self.assertAlmostEqual(result[0] / total, custom_percentage, delta=0.01)
        # Second should get 30% (60% * 0.5)
        self.assertAlmostEqual(result[1] / total, 0.30, delta=0.01)

    def test_large_number_of_scores(self):
        """Test with many scores"""
        moving_scores = [float(i) for i in range(20, 0, -1)]  # 20 down to 1
        result = distribute_weights_by_ranking(moving_scores)

        self.assertEqual(len(result), 20)
        self.assertEqual(sum(result), int(DEFAULT_TOTAL_WEIGHT))

        # Verify descending order
        for i in range(len(result) - 1):
            self.assertGreaterEqual(result[i], result[i + 1])

    def test_very_small_scores(self):
        """Test with very small score values"""
        moving_scores = [0.001, 0.002, 0.003]
        result = distribute_weights_by_ranking(moving_scores)

        self.assertEqual(len(result), 3)
        self.assertEqual(sum(result), int(DEFAULT_TOTAL_WEIGHT))
        # Highest score should get most weight
        self.assertGreater(result[2], result[1])
        self.assertGreater(result[1], result[0])

    def test_very_large_scores(self):
        """Test with very large score values"""
        moving_scores = [1e10, 2e10, 3e10]
        result = distribute_weights_by_ranking(moving_scores)

        self.assertEqual(len(result), 3)
        self.assertEqual(sum(result), int(DEFAULT_TOTAL_WEIGHT))
        # Highest score should get most weight
        self.assertGreater(result[2], result[1])
        self.assertGreater(result[1], result[0])

    def test_sum_equals_total_weight(self):
        """Test that sum always equals total_weight exactly"""
        test_cases = [
            [1.0],
            [1.0, 2.0],
            [1.0, 2.0, 3.0, 4.0, 5.0],
            [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
        ]

        for moving_scores in test_cases:
            with self.subTest(moving_scores=moving_scores):
                result = distribute_weights_by_ranking(moving_scores)
                self.assertEqual(sum(result), int(DEFAULT_TOTAL_WEIGHT),
                               f"Failed for scores: {moving_scores}")

    def test_ranking_preserved(self):
        """Test that ranking is preserved (higher scores get more weight)"""
        moving_scores = [1.0, 5.0, 3.0, 7.0, 2.0]
        result = distribute_weights_by_ranking(moving_scores)

        # Expected ranking: index 3 (7.0) > index 1 (5.0) > index 2 (3.0) > index 4 (2.0) > index 0 (1.0)
        self.assertGreater(result[3], result[1])  # 7.0 > 5.0
        self.assertGreater(result[1], result[2])  # 5.0 > 3.0
        self.assertGreater(result[2], result[4])  # 3.0 > 2.0
        self.assertGreater(result[4], result[0])  # 2.0 > 1.0

    def test_all_weights_non_negative(self):
        """Test that all weights are non-negative"""
        moving_scores = [-10.0, -5.0, 0.0, 5.0, 10.0]
        result = distribute_weights_by_ranking(moving_scores)

        for weight in result:
            self.assertGreaterEqual(weight, 0, "All weights should be non-negative")

    def test_returns_integers(self):
        """Test that function returns list of integers"""
        moving_scores = [1.0, 2.0, 3.0]
        result = distribute_weights_by_ranking(moving_scores)

        self.assertIsInstance(result, list)
        for weight in result:
            self.assertIsInstance(weight, int, "All weights should be integers")


if __name__ == '__main__':
    unittest.main()

