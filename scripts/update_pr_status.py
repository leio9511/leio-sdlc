#!/usr/bin/env python3
import argparse
import os
import sys

# Ensure scripts directory is in path so we can import structured_state_parser
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import structured_state_parser

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pr-file", dest="pr_file", required=True)
    parser.add_argument("--status", choices=["open", "closed", "blocked", "in_progress"], required=True)
    args = parser.parse_args()

    pr_file = args.pr_file
    new_status = args.status

    if not os.path.exists(pr_file):
        print(f"[Pre-flight Failed] Cannot update status. PR file '{pr_file}' not found.")
        sys.exit(1)

    try:
        structured_state_parser.update_status(pr_file, new_status)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

    print(f"[STATUS_UPDATED] {pr_file} is now {new_status}.")
    sys.exit(0)

if __name__ == "__main__":
    main()
