import re

with open("tests/test_cleanup_flag.py", "r") as f:
    content = f.read()

# Replace test_cleanup_quarantine
content = content.replace("        os.chdir(td)", "        orig_dir = os.getcwd()\n        try:\n            os.chdir(td)")
# Find where def test_cleanup_lock_blocked(): starts, insert finally before it
content = content.replace("def test_cleanup_lock_blocked():", "        finally:\n            os.chdir(orig_dir)\n\ndef test_cleanup_lock_blocked():")

# Replace test_cleanup_lock_blocked
content = content.replace("        os.chdir(td)", "        orig_dir = os.getcwd()\n        try:\n            os.chdir(td)")
content = content.replace("if __name__ == \"__main__\":", "        finally:\n            os.chdir(orig_dir)\n\nif __name__ == \"__main__\":")

with open("tests/test_cleanup_flag.py", "w") as f:
    f.write(content)
print("Patched test_cleanup_flag.py")
