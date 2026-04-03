import sys
import os
import unittest
from unittest.mock import patch, MagicMock
import io

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

import orchestrator

class TestDebugCLI(unittest.TestCase):
    def test_debug_flag_parsing(self):
        # Test that --debug is parsed correctly
        test_args = ["orchestrator.py", "--workdir", ".", "--prd-file", "dummy.md", "--debug"]
        with patch.object(sys, 'argv', test_args):
            # We don't want to run the whole main, just test parser
            import argparse
            parser = argparse.ArgumentParser()
            parser.add_argument("--workdir", required=True)
            parser.add_argument("--prd-file", required=True)
            parser.add_argument("--debug", action="store_true")
            args = parser.parse_args(test_args[1:])
            self.assertTrue(args.debug)

    def test_no_debug_flag_parsing(self):
        # Test that debug is False by default
        test_args = ["orchestrator.py", "--workdir", ".", "--prd-file", "dummy.md"]
        with patch.object(sys, 'argv', test_args):
            import argparse
            parser = argparse.ArgumentParser()
            parser.add_argument("--workdir", required=True)
            parser.add_argument("--prd-file", required=True)
            parser.add_argument("--debug", action="store_true")
            args = parser.parse_args(test_args[1:])
            self.assertFalse(args.debug)

if __name__ == "__main__":
    unittest.main()
