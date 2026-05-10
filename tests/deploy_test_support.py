import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path


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
)


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

        if repo_root.name == "leio-sdlc":
            raise AssertionError("Isolated checkout basename must not be leio-sdlc")

        inherited_artifacts = [name for name in (".dist", ".sdlc", ".sdlc_runs") if (repo_root / name).exists()]
        if inherited_artifacts:
            raise AssertionError(
                f"Isolated checkout inherited generated repo state: {', '.join(sorted(inherited_artifacts))}"
            )

        env = os.environ.copy()
        env["HOME_MOCK"] = str(mock_home)

        yield {
            "repo_root": str(repo_root),
            "mock_home": str(mock_home),
            "env": env,
        }
    finally:
        shutil.rmtree(parent_dir, ignore_errors=True)
