import argparse
import unittest

from benchmarks.cli import build_parser


class BenchmarkCliTest(unittest.TestCase):
    def test_yaml_run_is_the_only_public_training_entry(self):
        parser = build_parser()
        subparsers = next(
            action
            for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)
        )
        self.assertIn("run", subparsers.choices)
        self.assertNotIn("train", subparsers.choices)
        self.assertNotIn("commands", subparsers.choices)
        self.assertNotIn("vib2mol", subparsers.choices)


if __name__ == "__main__":
    unittest.main()
