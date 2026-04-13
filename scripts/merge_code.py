#!/usr/bin/env python3
import os
import sys
import argparse
import subprocess
from utils_json import extract_and_parse_json

# Global marker for Git Hook authentication (PRD-1012)
os.environ["SDLC_ORCHESTRATOR_RUNNING"] = "1"

def parse_review_verdict(content):
    """
    Parses structured JSON review status using the new schema.
    """
    try:
        data = extract_and_parse_json(content)
        if data and isinstance(data, dict):
            assessment = data.get("overall_assessment")
            if assessment in ["EXCELLENT", "GOOD_WITH_MINOR_SUGGESTIONS"]:
                return "APPROVED"
            elif assessment in ["NEEDS_ATTENTION", "NEEDS_IMMEDIATE_REWORK"]:
                return "ACTION_REQUIRED"
    except Exception:
        pass
    return None

def main():
    parser = argparse.ArgumentParser(description="Merge a git branch.")
    parser.add_argument("--branch", required=True, help="The branch to merge")
    parser.add_argument("--review-file", required=True, help="Path to the Review Report file")
    parser.add_argument("--force-approved", action="store_true", help="Force merge even without APPROVED status")
    args = parser.parse_args()

    if not os.path.isfile(args.review_file):
        print(f"[Pre-flight Failed] Merge rejected. Review artifact '{args.review_file}' not found. You MUST run spawn_reviewer.py first.")
        sys.exit(1)

    if not args.force_approved:
        with open(args.review_file, "r") as f:
            content = f.read()
            verdict = parse_review_verdict(content)
            if verdict != "APPROVED":
                print(f"[Pre-flight Failed] Merge rejected. The file '{args.review_file}' does not contain an 'APPROVED' status in JSON. You must fix the code and re-review, or use --force-approved to override.")
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
            # Use -c flag to pass runtime authentication to hook
            result = subprocess.run(["git", "-c", "sdlc.runtime=1", "merge", branch], check=True, text=True, capture_output=True)
            print(result.stdout)
        except subprocess.CalledProcessError as e:
            print(f"Merge failed: {e.stderr}. Aborting merge.", file=sys.stderr)
            subprocess.run(["git", "merge", "--abort"], check=False)
            sys.exit(1)

if __name__ == "__main__":
    main()
