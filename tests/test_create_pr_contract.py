import os
import unittest
import tempfile
import sys
from unittest.mock import patch

# Add scripts directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))

from create_pr_contract import calculate_index

class TestCalculateIndex(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.job_dir = self.temp_dir.name
        
    def tearDown(self):
        self.temp_dir.cleanup()

    def touch_file(self, filename):
        with open(os.path.join(self.job_dir, filename), "w") as f:
            f.write("")

    def test_calculate_index_standard_slice(self):
        self.touch_file("PR_002_Failed.md")
        index = calculate_index(self.job_dir, "002")
        self.assertEqual(index, "002_1")
        
        self.touch_file("PR_002_1_Failed.md")
        index = calculate_index(self.job_dir, "002")
        self.assertEqual(index, "002_2")

    def test_calculate_index_nested_slice(self):
        self.touch_file("PR_002_1_Stub.md")
        self.touch_file("PR_002_2_Stub.md")
        index = calculate_index(self.job_dir, "002_2_1")
        self.assertEqual(index, "002_3")

    def test_calculate_index_fabricated_primary(self):
        self.touch_file("PR_002_Failed.md")
        with self.assertRaises(ValueError) as context:
            calculate_index(self.job_dir, "003")
        self.assertEqual(str(context.exception), "Fabricated primary PR number '003' does not exist in job queue.")

    def test_calculate_index_no_zero_padding_on_subindex(self):
        self.touch_file("PR_002_Failed.md")
        for i in range(1, 10):
            self.touch_file(f"PR_002_{i}_Stub.md")
        index = calculate_index(self.job_dir, "002")
        self.assertEqual(index, "002_10")
        
if __name__ == '__main__':
    unittest.main()
