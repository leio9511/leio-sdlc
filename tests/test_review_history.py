import os
import sys
import tempfile
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../scripts')))
import orchestrator

def test_preserve_review_history_multiple_rounds():
    with tempfile.TemporaryDirectory() as td:
        workdir = os.path.join(td, "workdir")
        global_dir = os.path.join(td, "global")
        os.makedirs(workdir)
        os.makedirs(os.path.join(workdir, ".git"))
        os.makedirs(global_dir)
        
        prd_file = os.path.join(td, "dummy_prd.md")
        with open(prd_file, "w") as f:
            f.write("# Dummy PRD")

        target_project_name = os.path.basename(os.path.abspath(workdir))
        base_name = os.path.splitext(os.path.basename(prd_file))[0]
        run_dir = os.path.abspath(os.path.join(global_dir, ".sdlc_runs", target_project_name, base_name))
        os.makedirs(run_dir, exist_ok=True)
        
        pr_file = os.path.join(run_dir, "PR_001_Feature.md")
        with open(pr_file, "w") as f:
            f.write("---\nstatus: in_progress\n---\n")
            
        with open(os.path.join(run_dir, "run_manifest.json"), "w") as f:
            f.write("{}")

        review_report_path = os.path.join(run_dir, "review_report.json")
        reviews_dir = os.path.join(run_dir, "reviews")

        def fake_subprocess_run(cmd, *args, **kwargs):
            res = MagicMock()
            res.returncode = 0
            res.stdout = ""
            cmd_str = " ".join([str(c) for c in cmd])
            if "get_next_pr.py" in cmd_str:
                res.stdout = pr_file + "\n"
            elif "git" in cmd_str and "rev-parse" in cmd_str:
                res.stdout = "abc123def456789012345678901234567890abcd\n"
            return res

        call_count = {"reviewer": 0}

        def fake_dpopen(cmd, *args, **kwargs):
            cmd_str = " ".join([str(c) for c in cmd])
            
            # Use a real integer for returncode, not a MagicMock!
            class DummyProc:
                def __init__(self, code=0):
                    self.returncode = code
                    self.pid = 12345
                def wait(self, *args, **kwargs):
                    pass
                def poll(self):
                    return self.returncode
            proc = DummyProc(0)
            
            if "spawn_planner.py" in cmd_str:
                proc.returncode = 1
                raise SystemExit()
            elif "spawn_coder.py" in cmd_str:
                with open(os.path.join(workdir, "dummy.py"), "w") as f:
                    f.write("code")
                return proc
            elif "spawn_reviewer.py" in cmd_str:
                call_count["reviewer"] += 1
                if call_count["reviewer"] == 1:
                    with open(review_report_path, "w") as f:
                        f.write('{"overall_assessment": "NEEDS_ATTENTION"}')
                elif call_count["reviewer"] == 2:
                    with open(review_report_path, "w") as f:
                        f.write('{"overall_assessment": "EXCELLENT"}')
                return proc
            elif "spawn_verifier.py" in cmd_str:
                raise SystemExit()
            return proc

        test_args = [
            "orchestrator.py",
            "--workdir", workdir,
            "--global-dir", global_dir,
            "--prd-file", prd_file,
            "--channel", "test", "--enable-exec-from-workspace", "--force-replan", "false"
        ]

        with patch("sys.argv", test_args), \
             patch("subprocess.run", side_effect=fake_subprocess_run), \
             patch("orchestrator.dpopen", side_effect=fake_dpopen), \
             patch("orchestrator.notify_channel"), \
             patch("orchestrator.get_head_commit_hash", return_value="hash1"), \
             patch("orchestrator.classify_coder_null_output", return_value=(False, "", "hash2")), \
             patch("git_utils.check_git_boundary"):
            try:
                orchestrator.main()
            except SystemExit:
                pass

        assert os.path.exists(reviews_dir), "reviews directory should be created"
        
        hist1 = os.path.join(reviews_dir, "PR_001_Feature.1.review.json")
        assert os.path.exists(hist1), "First attempt snapshot should exist"
        with open(hist1, "r") as f:
            assert "NEEDS_ATTENTION" in f.read()
            
        hist2 = os.path.join(reviews_dir, "PR_001_Feature.2.review.json")
        assert os.path.exists(hist2), "Second attempt snapshot should exist"
        with open(hist2, "r") as f:
            assert "EXCELLENT" in f.read()

def test_failed_reviewer_does_not_increment_attempt():
    with tempfile.TemporaryDirectory() as td:
        workdir = os.path.join(td, "workdir")
        global_dir = os.path.join(td, "global")
        os.makedirs(workdir)
        os.makedirs(os.path.join(workdir, ".git"))
        os.makedirs(global_dir)
        
        prd_file = os.path.join(td, "dummy_prd.md")
        with open(prd_file, "w") as f:
            f.write("# Dummy PRD")

        target_project_name = os.path.basename(os.path.abspath(workdir))
        base_name = os.path.splitext(os.path.basename(prd_file))[0]
        run_dir = os.path.abspath(os.path.join(global_dir, ".sdlc_runs", target_project_name, base_name))
        os.makedirs(run_dir, exist_ok=True)
        
        pr_file = os.path.join(run_dir, "PR_001_Feature.md")
        with open(pr_file, "w") as f:
            f.write("---\nstatus: in_progress\n---\n")
            
        with open(os.path.join(run_dir, "run_manifest.json"), "w") as f:
            f.write("{}")

        review_report_path = os.path.join(run_dir, "review_report.json")
        reviews_dir = os.path.join(run_dir, "reviews")

        def fake_subprocess_run(cmd, *args, **kwargs):
            res = MagicMock()
            res.returncode = 0
            res.stdout = ""
            cmd_str = " ".join([str(c) for c in cmd])
            if "get_next_pr.py" in cmd_str:
                res.stdout = pr_file + "\n"
            elif "git" in cmd_str and "rev-parse" in cmd_str:
                res.stdout = "abc123def456789012345678901234567890abcd\n"
            return res

        call_count = {"reviewer": 0}

        def fake_dpopen(cmd, *args, **kwargs):
            cmd_str = " ".join([str(c) for c in cmd])
            
            class DummyProc:
                def __init__(self, code=0):
                    self.returncode = code
                    self.pid = 12345
                def wait(self, *args, **kwargs):
                    pass
                def poll(self):
                    return self.returncode
            proc = DummyProc(0)
            
            if "spawn_coder.py" in cmd_str:
                return proc
            elif "spawn_reviewer.py" in cmd_str:
                call_count["reviewer"] += 1
                if call_count["reviewer"] == 1:
                    with open(review_report_path, "w") as f:
                        f.write('invalid json')
                elif call_count["reviewer"] == 2:
                    with open(review_report_path, "w") as f:
                        f.write('{"overall_assessment": "NOT_STARTED"}')
                elif call_count["reviewer"] == 3:
                    with open(review_report_path, "w") as f:
                        f.write('{"overall_assessment": "EXCELLENT"}')
                return proc
            elif "spawn_verifier.py" in cmd_str:
                raise SystemExit()
            return proc

        test_args = [
            "orchestrator.py",
            "--workdir", workdir,
            "--global-dir", global_dir,
            "--prd-file", prd_file,
            "--channel", "test", "--enable-exec-from-workspace", "--force-replan", "false"
        ]

        with patch("sys.argv", test_args), \
             patch("subprocess.run", side_effect=fake_subprocess_run), \
             patch("orchestrator.dpopen", side_effect=fake_dpopen), \
             patch("orchestrator.notify_channel"), \
             patch("orchestrator.get_head_commit_hash", return_value="hash1"), \
             patch("orchestrator.classify_coder_null_output", return_value=(False, "", "hash2")), \
             patch("git_utils.check_git_boundary"):
            try:
                orchestrator.main()
            except SystemExit:
                pass

        hist1 = os.path.join(reviews_dir, "PR_001_Feature.1.review.json")
        assert os.path.exists(hist1), "First attempt snapshot should exist"
        with open(hist1, "r") as f:
            assert "EXCELLENT" in f.read()
            
        hist2 = os.path.join(reviews_dir, "PR_001_Feature.2.review.json")
        assert not os.path.exists(hist2), "Second attempt snapshot should not exist"

