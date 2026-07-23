from __future__ import annotations

import unittest

from src.experiments.batch import parse_experiments, resolve_batch


class ExperimentBatchTests(unittest.TestCase):
    def test_experiment_ranges_are_expanded_once(self):
        self.assertEqual(parse_experiments("0-2,2,4,6"), [0, 1, 2, 4, 6])

    def test_one_based_start_and_limit_become_half_open_slice(self):
        self.assertEqual(
            resolve_batch(
                100, start=21, limit=20, batch_index=None, batch_size=None
            ),
            (20, 40),
        )

    def test_batch_index_is_one_based_and_final_batch_is_clipped(self):
        self.assertEqual(
            resolve_batch(
                45, start=None, limit=None, batch_index=3, batch_size=20
            ),
            (40, 45),
        )

    def test_batch_selection_modes_cannot_be_mixed(self):
        with self.assertRaises(ValueError):
            resolve_batch(100, start=1, limit=20, batch_index=1, batch_size=20)


if __name__ == "__main__":
    unittest.main()
