import os
import shutil
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

        yield {
            "repo_root": str(repo_root),
            "mock_home": str(mock_home),
            "env": env,
        }
    finally:
        shutil.rmtree(parent_dir, ignore_errors=True)
