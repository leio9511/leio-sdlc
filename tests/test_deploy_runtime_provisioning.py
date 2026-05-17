import subprocess
from pathlib import Path

from deploy_test_support import canonical_skill_dir, install_fake_python_toolchain, isolated_repo_env


REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_deploy(repo_root, env):
    return subprocess.run(
        ["bash", str(Path(repo_root) / "deploy.sh"), "--no-restart"],
        cwd=str(repo_root),
        env=env,
        capture_output=True,
        text=True,
    )


def _log_lines(log_path):
    return log_path.read_text(encoding="utf-8").splitlines()


def _line_index(lines, prefix):
    return next(index for index, line in enumerate(lines) if line.startswith(prefix))


def test_deploy_creates_runtime_venv_in_staging_before_atomic_swap():
    with isolated_repo_env(REPO_ROOT) as isolated:
        log_path = install_fake_python_toolchain(isolated["repo_root"], isolated["env"])

        result = _run_deploy(isolated["repo_root"], isolated["env"])

        assert result.returncode == 0, result.stderr + result.stdout
        prod_dir = Path(canonical_skill_dir(isolated["mock_home"], "leio-sdlc"))
        assert (prod_dir / ".venv" / "bin" / "python").exists()
        lines = _log_lines(log_path)
        assert _line_index(lines, "venv:") < _line_index(lines, "runtime-smoke:")
        assert result.stdout.index("🐍 Provisioning runtime Python in staging release") < result.stdout.index(
            "🔄 Performing atomic directory swap"
        )
        assert result.stdout.index("✅ Runtime provisioning and smoke validation passed") < result.stdout.index(
            "🔄 Performing atomic directory swap"
        )


def test_deploy_installs_dependencies_from_unique_requirements_entry():
    with isolated_repo_env(REPO_ROOT) as isolated:
        repo_root = Path(isolated["repo_root"])
        (repo_root / "requirements-dev.txt").write_text("dev-only\n", encoding="utf-8")
        (repo_root / "requirements-test.txt").write_text("test-only\n", encoding="utf-8")
        (repo_root / "pyproject.toml").write_text("[project]\nname='ambient'\n", encoding="utf-8")
        log_path = install_fake_python_toolchain(repo_root, isolated["env"])

        result = _run_deploy(repo_root, isolated["env"])

        assert result.returncode == 0, result.stderr + result.stdout
        lines = _log_lines(log_path)
        pip_lines = [line for line in lines if line.startswith("pip:")]
        assert len(pip_lines) == 1
        assert pip_lines[0].endswith("/.tmp_leio-sdlc/requirements.txt")
        assert "requirements-dev.txt" not in pip_lines[0]
        assert "requirements-test.txt" not in pip_lines[0]
        assert "pyproject.toml" not in pip_lines[0]


def test_deploy_runs_import_and_official_runtime_smoke_before_swap():
    with isolated_repo_env(REPO_ROOT) as isolated:
        log_path = install_fake_python_toolchain(isolated["repo_root"], isolated["env"])

        result = _run_deploy(isolated["repo_root"], isolated["env"])

        assert result.returncode == 0, result.stderr + result.stdout
        lines = _log_lines(log_path)
        import_index = _line_index(lines, "import-smoke:")
        smoke_index = _line_index(lines, "runtime-smoke:")
        assert import_index < smoke_index
        assert "scripts/runtime_smoke.py" in lines[smoke_index]
        assert str(Path(isolated["mock_home"]) / ".openclaw" / "skills" / ".tmp_leio-sdlc") in lines[smoke_index]
        assert result.stdout.index("Running minimal import smoke") < result.stdout.index("🔄 Performing atomic directory swap")
        assert result.stdout.index("Running official runtime smoke") < result.stdout.index("🔄 Performing atomic directory swap")


def test_deploy_fail_fast_prevents_atomic_swap_when_runtime_provisioning_fails():
    for fail_step in ("venv", "pip", "import", "runtime_smoke"):
        with isolated_repo_env(REPO_ROOT) as isolated:
            repo_root = Path(isolated["repo_root"])
            prod_dir = Path(canonical_skill_dir(isolated["mock_home"], "leio-sdlc"))
            prod_dir.mkdir(parents=True)
            marker = prod_dir / "production-marker.txt"
            marker.write_text("keep me", encoding="utf-8")
            install_fake_python_toolchain(repo_root, isolated["env"], fail_step=fail_step)

            result = _run_deploy(repo_root, isolated["env"])

            assert result.returncode != 0
            assert marker.exists(), fail_step
            assert marker.read_text(encoding="utf-8") == "keep me"
            assert not (prod_dir / "scripts" / "runtime_smoke.py").exists(), fail_step


def test_runtime_venv_is_rebuilt_per_release_and_not_reused_from_prod():
    with isolated_repo_env(REPO_ROOT) as isolated:
        repo_root = Path(isolated["repo_root"])
        install_fake_python_toolchain(repo_root, isolated["env"])
        first = _run_deploy(repo_root, isolated["env"])
        assert first.returncode == 0, first.stderr + first.stdout
        prod_dir = Path(canonical_skill_dir(isolated["mock_home"], "leio-sdlc"))
        marker = prod_dir / ".venv" / "old-prod-marker.txt"
        marker.write_text("must not survive", encoding="utf-8")

        second = _run_deploy(repo_root, isolated["env"])

        assert second.returncode == 0, second.stderr + second.stdout
        assert not marker.exists()
        assert (prod_dir / ".venv" / "bin" / "python").exists()


def test_deploy_runtime_contract_does_not_affect_other_skills():
    with isolated_repo_env(REPO_ROOT) as isolated:
        pm_skill = Path(canonical_skill_dir(isolated["mock_home"], "pm-skill"))
        pm_skill.mkdir(parents=True)
        sentinel = pm_skill / ".venv" / "sentinel.txt"
        sentinel.parent.mkdir()
        sentinel.write_text("untouched", encoding="utf-8")
        install_fake_python_toolchain(isolated["repo_root"], isolated["env"])

        result = _run_deploy(isolated["repo_root"], isolated["env"])

        assert result.returncode == 0, result.stderr + result.stdout
        assert sentinel.exists()
        assert sentinel.read_text(encoding="utf-8") == "untouched"
