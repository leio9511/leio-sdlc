#!/usr/bin/env python3
import argparse
import os
import sys

def main():
    parser = argparse.ArgumentParser(description="Initialize a new PRD based on the template.")
    parser.add_argument("--project", required=True, help="Target project name (e.g., leio-sdlc, AMS)")
    parser.add_argument("--title", required=True, help="Short title for the PRD (used in filename)")
    parser.add_argument("--workdir", default=None, help="Working directory where docs/PRDs is located")
    parser.add_argument("--enable-exec-from-workspace", action="store_true", help="Bypass the workspace path check")
    args = parser.parse_args()

    if args.workdir:
        workdir = os.path.abspath(args.workdir)
    else:
        workdir = os.path.abspath(os.getcwd())

    prds_dir = os.path.join(workdir, "docs", "PRDs")
    os.makedirs(prds_dir, exist_ok=True)
    
    safe_title = args.title.replace(" ", "_").replace("/", "_")
    target_prd_path = os.path.join(prds_dir, f"PRD_{safe_title}.md")

    if os.path.exists(target_prd_path):
        print(f"[SUCCESS] Target PRD already exists at: {target_prd_path}")
        print("Please use the 'edit' or 'write' tool to update this file directly.")
        sys.exit(0)

    # Resolve Template
    template_path = os.path.join(workdir, "docs", "TEMPLATES", "PRD.md.template")
    fallback_template_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "TEMPLATES", "PRD.md.template")
    
    if os.path.exists(template_path):
        with open(template_path, "r") as f:
            template_content = f.read()
    elif os.path.exists(fallback_template_path):
        with open(fallback_template_path, "r") as f:
            template_content = f.read()
    else:
        print(f"Error: Could not find PRD template at {template_path} or {fallback_template_path}", file=sys.stderr)
        sys.exit(1)

    # Inject project name
    template_content = template_content.replace("[Project Name]", args.title)
    
    # Save new PRD
    with open(target_prd_path, "w") as f:
        f.write(template_content)

    print(f"[SUCCESS] Blank PRD scaffold created at: {target_prd_path}")
    print("Please use the 'edit' or 'write' tool to fill in the contents based on your discussion.")

if __name__ == "__main__":
    main()