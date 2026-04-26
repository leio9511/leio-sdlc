import os
import json
import tempfile
import shutil
import pytest
from scripts.planner_envelope import save_debug_artifacts

def test_save_debug_artifacts_creates_files():
    with tempfile.TemporaryDirectory() as temp_dir:
        out_dir = os.path.join(temp_dir, "my_out_dir")
        os.makedirs(out_dir)
        
        envelope_dict = {"key": "value"}
        rendered_prompt = "Hello World"
        scaffold_command = "python3 create_pr_contract.py"
        
        save_debug_artifacts(out_dir, envelope_dict, rendered_prompt, scaffold_command)
        
        debug_dir = os.path.join(out_dir, "planner_debug")
        assert os.path.isdir(debug_dir)
        
        packet_path = os.path.join(debug_dir, "startup_packet.json")
        prompt_path = os.path.join(debug_dir, "startup_prompt.txt")
        scaffold_path = os.path.join(debug_dir, "scaffold_contract.txt")
        
        assert os.path.isfile(packet_path)
        assert os.path.isfile(prompt_path)
        assert os.path.isfile(scaffold_path)
        
        with open(packet_path, "r") as f:
            loaded_json = json.load(f)
            assert loaded_json == envelope_dict
            
        with open(prompt_path, "r") as f:
            assert f.read() == rendered_prompt
            
        with open(scaffold_path, "r") as f:
            assert f.read() == scaffold_command

def test_save_debug_artifacts_existing_dir():
    with tempfile.TemporaryDirectory() as temp_dir:
        out_dir = os.path.join(temp_dir, "my_out_dir")
        debug_dir = os.path.join(out_dir, "planner_debug")
        
        # Pre-create the directory to test exist_ok
        os.makedirs(debug_dir)
        
        envelope_dict = {"key": "new_value"}
        rendered_prompt = "New Hello"
        scaffold_command = "python3 another.py"
        
        # This should not raise FileExistsError
        save_debug_artifacts(out_dir, envelope_dict, rendered_prompt, scaffold_command)
        
        packet_path = os.path.join(debug_dir, "startup_packet.json")
        with open(packet_path, "r") as f:
            loaded_json = json.load(f)
            assert loaded_json == envelope_dict
