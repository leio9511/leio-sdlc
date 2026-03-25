status: open

## Objective
Integrate `--workdir` guardrails across Orchestrator scripts (`spawn_planner.py`, `spawn_coder.py`, `spawn_reviewer.py`) and complete TDD coverage.

## Requirements
1. **Argparse & OS Lock**: Add `parser.add_argument("--workdir", required=True)`, normalize to absolute path, and execute `os.chdir(workdir)` in `spawn_planner.py`, `spawn_coder.py`, and `spawn_reviewer.py`.
2. **Dynamic Engine Addressing**: In `spawn_planner.py`, dynamically locate the SDLC directory: `SDLC_DIR = os.path.dirname(os.path.abspath(__file__))` and use `os.path.join(SDLC_DIR, "create_pr_contract.py")` in instructions.
3. **Mind-Lock Prompting**: Inject `"ATTENTION: Your root workspace is rigidly locked to {workdir}. You are strictly forbidden from reading, writing, or modifying files outside this absolute path. Use 'git add .' to stage changes safely within your directory."` into the system prompts of Planner, Coder, and Reviewer.
4. **Testing**: Extend `scripts/test_cwd_guardrail.sh` with T1 (for spawn_*.py), T2 (Relative Path Normalization), T3 (Strict Sandbox Isolation for Coder/Planner), and T4 (Toolchain Dynamic Path Resolution).
5. **Preflight Updates**: Update `preflight.sh` to pass `--workdir "$(pwd)"` to all legacy test invocations.
