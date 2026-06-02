import os
import shutil
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path


ROOT_SKILL_SLUG = "leio-sdlc"
IGNORED_REPO_STATE = (
    ".git",
    ".dist",
    ".sdlc",
    ".sdlc_runs",
    ".tmp_home_mock",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "*.lock",
    ".tmp",
    "mock_scaffold_project",
    "*sandbox*",
)


def assert_isolated_checkout(repo_root: str | os.PathLike[str]) -> None:
    checkout_name = Path(repo_root).resolve().name
    if checkout_name == ROOT_SKILL_SLUG:
        raise AssertionError("Isolated checkout basename must not be leio-sdlc")


def canonical_openclaw_home(mock_home: str | os.PathLike[str]) -> str:
    return os.path.join(os.fspath(mock_home), ".openclaw")


def canonical_skill_dir(mock_home: str | os.PathLike[str], slug: str) -> str:
    return os.path.join(canonical_openclaw_home(mock_home), "skills", slug)


def canonical_releases_dir(mock_home: str | os.PathLike[str], slug: str) -> str:
    return os.path.join(canonical_openclaw_home(mock_home), ".releases", slug)


def install_fake_python_toolchain(
    repo_root: str | os.PathLike[str], env: dict[str, str], *, fail_step: str | None = None
) -> Path:
    """Install a network-free fake python3/venv/pip toolchain for deploy tests."""
    fake_bin = Path(repo_root) / "fake-bin"
    fake_bin.mkdir(exist_ok=True)
    log_path = Path(repo_root) / "deploy-python.log"
    real_python = os.environ.get("PYTHON", sys.executable)

    python_sh = fake_bin / "python3"
    python_sh.write_text(
        f"""#!/bin/sh
set -eu
LOG_FILE=\"${{LEIO_DEPLOY_TEST_LOG:-{log_path}}}\"
REAL_PYTHON={real_python!r}
if [ \"${{1:-}}\" = \"-m\" ] && [ \"${{2:-}}\" = \"venv\" ]; then
  VENV_DIR=\"${{3:-}}\"
  echo \"venv:$VENV_DIR\" >> \"$LOG_FILE\"
  if [ \"${{LEIO_DEPLOY_FAKE_FAIL_STEP:-}}\" = \"venv\" ]; then exit 91; fi
  mkdir -p \"$VENV_DIR/bin\"
  cat > \"$VENV_DIR/bin/python\" <<PY
#!/bin/sh
set -eu
LOG_FILE=\"\\${{LEIO_DEPLOY_TEST_LOG:-{log_path}}}\"
if [ \"\\${{1:-}}\" = \"-m\" ] && [ \"\\${{2:-}}\" = \"pip\" ]; then
  REQUIREMENTS_ARG=\"\"
  for arg in \"\\$@\"; do
    REQUIREMENTS_ARG=\"\\$arg\"
  done
  echo \"pip:\\$REQUIREMENTS_ARG\" >> \"\\$LOG_FILE\"
  if [ \"\\${{LEIO_DEPLOY_FAKE_FAIL_STEP:-}}\" = \"pip\" ]; then exit 92; fi
  exit 0
fi
if [ \"\\${{1:-}}\" = \"-c\" ]; then
  echo \"import-smoke:\\$0\" >> \"\\$LOG_FILE\"
  if [ \"\\${{LEIO_DEPLOY_FAKE_FAIL_STEP:-}}\" = \"import\" ]; then exit 93; fi
  exit 0
fi
case \"\\${{1:-}}\" in
  */scripts/runtime_smoke.py)
    echo \"runtime-smoke:\\$0:\\$*\" >> \"\\$LOG_FILE\"
    if [ \"\\${{LEIO_DEPLOY_FAKE_FAIL_STEP:-}}\" = \"runtime_smoke\" ]; then exit 94; fi
    exit 0
    ;;
esac
exec \"$REAL_PYTHON\" \"\\$@\"
PY
  chmod +x \"$VENV_DIR/bin/python\"
  exit 0
fi
exec \"$REAL_PYTHON\" \"$@\"
""",
        encoding="utf-8",
    )
    python_sh.chmod(0o755)

    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    env["LEIO_DEPLOY_TEST_LOG"] = str(log_path)
    if fail_step:
        env["LEIO_DEPLOY_FAKE_FAIL_STEP"] = fail_step
    return log_path


@contextmanager
def isolated_repo_env(source_repo: str | os.PathLike[str]):
    source_root = Path(source_repo).resolve()
    parent_dir = tempfile.mkdtemp(prefix="deploy-isolation-")
    repo_root = Path(parent_dir) / "isolated-sdlc-repo"
    mock_home = Path(parent_dir) / "home"

    try:
        shutil.copytree(
            source_root,
            repo_root,
            dirs_exist_ok=False,
            ignore=shutil.ignore_patterns(*IGNORED_REPO_STATE, "*.pyc"),
        )
        mock_home.mkdir(parents=True, exist_ok=True)

        assert_isolated_checkout(repo_root)

        inherited_artifacts = [name for name in (".dist", ".sdlc", ".sdlc_runs") if (repo_root / name).exists()]
        if inherited_artifacts:
            raise AssertionError(
                f"Isolated checkout inherited generated repo state: {', '.join(sorted(inherited_artifacts))}"
            )

        env = os.environ.copy()
        env["HOME_MOCK"] = str(mock_home)
        env["HOME"] = str(mock_home)

        # Create transient mock-bin for gemini stub
        mock_bin_dir = Path(parent_dir) / "mock-bin"
        mock_bin_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(source_root / "tests" / "trap_stub_gemini.sh", mock_bin_dir / "gemini")
        (mock_bin_dir / "gemini").chmod(0o755)
        env["PATH"] = f"{mock_bin_dir}:{env.get('PATH', '')}"

        yield {
            "repo_root": str(repo_root),
            "mock_home": str(mock_home),
            "env": env,
        }
    finally:
        shutil.rmtree(parent_dir, ignore_errors=True)
