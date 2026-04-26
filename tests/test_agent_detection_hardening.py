import unittest
import sys
import os
from unittest.mock import patch, MagicMock

# Add scripts directory to path to import agent_driver
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../scripts')))
import agent_driver

class TestAgentDetectionHardening(unittest.TestCase):

    def test_openclaw_agent_exists_with_annotations(self):
        sample_output = """
- my-agent (default)
  Model: gpt-4
- another-agent
  Model: claude-3
"""
        self.assertTrue(agent_driver.openclaw_agent_exists(sample_output, "my-agent"))
        self.assertTrue(agent_driver.openclaw_agent_exists(sample_output, "another-agent"))

    def test_openclaw_agent_exists_false_positive_prevention(self):
        sample_output = "- my-agent-extra\n  Model: gpt-4"
        self.assertFalse(agent_driver.openclaw_agent_exists(sample_output, "my-agent"))

    def test_validate_openclaw_agent_model_with_annotations(self):
        sample_output = """
- my-agent (default)
  Model: gpt-4
- another-agent
  Model: claude-3
"""
        mock_res = MagicMock()
        mock_res.stdout = sample_output
        mock_res.returncode = 0
        
        with patch('subprocess.run', return_value=mock_res):
            with patch('sys.exit') as mock_exit:
                # Should not exit if model matches
                agent_driver.validate_openclaw_agent_model("openclaw", "my-agent", "gpt-4")
                mock_exit.assert_not_called()
                
                # Should exit if model mismatched
                agent_driver.validate_openclaw_agent_model("openclaw", "my-agent", "wrong-model")
                mock_exit.assert_called_with(1)

    def test_openclaw_agent_exists_exact_match(self):
        sample_output = "- my-agent\n  Model: gpt-4"
        self.assertTrue(agent_driver.openclaw_agent_exists(sample_output, "my-agent"))

    def test_openclaw_agent_exists_with_other_annotations(self):
        sample_output = "- my-agent (active, gpt-4)\n  Model: gpt-4"
        self.assertTrue(agent_driver.openclaw_agent_exists(sample_output, "my-agent"))

if __name__ == '__main__':
    unittest.main()
