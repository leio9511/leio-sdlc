#!/usr/bin/env python3
import os
import sys
import argparse
import subprocess

def main():
    parser = argparse.ArgumentParser(description="Merge a git branch.")
    parser.add_argument("--branch", required=True, help="The branch to merge")
    parser.add_argument("--review-file", required=True, help="Path to the Review Report file")
    parser.add_argument("--force-lgtm", action="store_true", help="Force merge even without [LGTM] in review")
    args = parser.parse_args()

    if not os.path.isfile(args.review_file):
        print(f"[Pre-flight Failed] Merge rejected. Review artifact '{args.review_file}' not found. You MUST run spawn_reviewer.py first.")
        sys.exit(1)

    if not args.force_lgtm:
        with open(args.review_file, "r") as f:
            content = f.read()
            if "[LGTM]" not in content:
                print(f"[Pre-flight Failed] Merge rejected. The file '{args.review_file}' does not contain [LGTM]. You must fix the code and re-review, or use --force-lgtm to override a nitpicky Reviewer.")
                sys.exit(1)

    branch = args.branch
    test_mode = os.environ.get("SDLC_TEST_MODE", "").lower() == "true"

    if test_mode:
        log_entry = str({'tool': 'merge_code', 'args': {'branch': branch}}) + "\n"
        log_dir = "tests"
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, 'tool_calls.log')
        with open(log_file, "a") as f:
            f.write(log_entry)
        print('{"status": "mock_success", "action": "merge"}')
        sys.exit(0)
    else:
        try:
            result = subprocess.run(["git", "merge", branch], check=True, text=True, capture_output=True)
            print(result.stdout)
        except subprocess.CalledProcessError as e:
            print(f"Merge failed: {e.stderr}. Aborting merge.", file=sys.stderr)
            subprocess.run(["git", "merge", "--abort"], check=False)
            sys.exit(1)

if __name__ == "__main__":
    main()
