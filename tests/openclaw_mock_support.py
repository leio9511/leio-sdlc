import os
import stat
import tempfile
import json
import contextlib

@contextlib.contextmanager
def provision_fake_openclaw():
    with tempfile.TemporaryDirectory() as temp_bin:
        mock_path = os.path.join(temp_bin, "openclaw")
        record_path = os.path.join(temp_bin, "openclaw_calls.json")
        
        # Create an empty JSON array initially
        with open(record_path, "w", encoding="utf-8") as f:
            json.dump([], f)
        
        # The fake openclaw script will append its arguments to the JSON file
        script_content = f"""#!/usr/bin/env python3
import sys
import json
import os

record_file = "{record_path}"
try:
    with open(record_file, "r") as f:
        calls = json.load(f)
except Exception:
    calls = []

calls.append(sys.argv)

with open(record_file, "w") as f:
    json.dump(calls, f)

print("Fake openclaw executed successfully")
"""
        with open(mock_path, "w", encoding="utf-8") as f:
            f.write(script_content)
        
        # Make it executable
        os.chmod(mock_path, os.stat(mock_path).st_mode | stat.S_IEXEC)
        
        # Store original PATH
        original_path = os.environ.get("PATH", "")
        
        def get_calls():
            try:
                with open(record_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return []
                
        try:
            # Prepend to PATH
            os.environ["PATH"] = f"{temp_bin}:{original_path}"
            yield temp_bin, get_calls
        finally:
            os.environ["PATH"] = original_path
# PR-003: provision_fake_openclaw successfully isolates Family B tests
