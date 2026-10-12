#!/usr/bin/env python3
"""Offline installer tests. Run with: python3 -m unittest discover -s tests -v."""
import hashlib
import os
from pathlib import Path
import pty
import select
import shlex
import shutil
import subprocess
import tempfile
import time
import unittest

REPO = Path(__file__).resolve().parents[1]
BASH = os.environ.get("TEST_BASH", "/bin/bash")


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="skills tests ")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root / "project with spaces"
        self.project.mkdir()
        self.source = self.root / "source files"
        shutil.copytree(REPO / "skills", self.source / "skills")
        shutil.copy(REPO / "manifest.sha256", self.source / "manifest.sha256")

    def run_install(self, *args, ok=True, local=True, env=None):
        command = [BASH, str(REPO / "install.sh")]
        if local:
            command += ["--source-dir", str(self.source)]
        result = subprocess.run(command + list(args), cwd=self.project,
                                stdin=subprocess.DEVNULL, capture_output=True,
                                text=True, start_new_session=True, env=env)
        if ok:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def install(self, *args, **kwargs):
        return self.run_install("--harnesses", "all", "--skills", "all", "--yes", *args, **kwargs)

    def skill_path(self, root=".agents"):
        return self.project / root / "skills/review-checklist/SKILL.md"

    def test_spaces_multiple_harnesses_and_shared_pi(self):
        self.install()
        self.assertEqual(self.skill_path().read_bytes(), (self.source / "skills/review-checklist/SKILL.md").read_bytes())
        self.assertTrue(self.skill_path(".claude").exists())
        self.assertFalse((self.project / ".pi").exists())
        self.assertFalse((self.project / ".llm-skills-install.lock").exists())

    def test_repeat_preserves_user_edits(self):
        self.install()
        self.skill_path().write_text("user edits")
        result = self.install()
        self.assertEqual(self.skill_path().read_text(), "user edits")
        self.assertIn("2 preservado(s)", result.stdout)

    def test_overwrite_keeps_backup(self):
        self.install()
        self.skill_path().write_text("user edits")
        self.install("--overwrite")
        backups = list(self.project.glob(".llm-skills-backup.*/.agents/skills/review-checklist/SKILL.md"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), "user edits")
        self.assertNotEqual(self.skill_path().read_text(), "user edits")

    def test_individual_harness_and_numbered_skill(self):
        for harness in ("codex", "pi", "2", "3"):
            self.run_install("--harnesses", harness, "--skills", "01", "--yes")
        self.assertTrue(self.skill_path().exists())
        self.assertFalse((self.project / ".claude").exists())

    def test_invalid_arguments_do_not_write_project(self):
        for args in (("--harnesses", "all,invalid", "--skills", "all", "--yes"),
                     ("--harnesses", "claude", "--skills", "all,invalid", "--yes"),
                     ("--harnesses", "claude", "--skills", "0", "--yes"),
                     ("--yes",), ("--ref", "../bad"), ("--unknown",)):
            self.run_install(*args, ok=False)
        self.assertEqual(list(self.project.iterdir()), [])

    def test_missing_tty_explains_flags(self):
        result = self.run_install(ok=False)
        self.assertIn("Sem terminal", result.stderr)
        self.assertEqual(list(self.project.iterdir()), [])

    def test_tampered_checksum_aborts_before_writes(self):
        (self.source / "skills/review-checklist/SKILL.md").write_text("tampered")
        self.install(ok=False)
        self.assertEqual(list(self.project.iterdir()), [])

    def test_bad_manifest_paths_and_duplicates(self):
        valid = (self.source / "manifest.sha256").read_text()
        for path in ("../outside", "skills/review-checklist/../../outside", "/tmp/outside",
                     "skills/review-checklist//foo", "skills/review-checklist/-foo"):
            (self.source / "manifest.sha256").write_text("0" * 64 + "  " + path + "\n")
            self.install(ok=False)
        (self.source / "manifest.sha256").write_text(valid + valid)
        self.install(ok=False)
        self.assertEqual(list(self.project.iterdir()), [])

    def test_destination_symlinks_refused(self):
        outside = self.root / "outside"
        outside.mkdir()
        (self.project / ".agents").symlink_to(outside, target_is_directory=True)
        self.install("--overwrite", ok=False)
        self.assertEqual(list(outside.iterdir()), [])
        self.assertFalse((self.project / ".claude").exists())

    def test_skill_symlink_refused(self):
        target = self.project / ".agents/skills"
        target.mkdir(parents=True)
        (target / "review-checklist").symlink_to(self.source / "skills/review-checklist")
        self.install("--overwrite", ok=False)

    def test_source_symlinks_refused(self):
        skill = self.source / "skills/review-checklist/SKILL.md"
        skill.unlink()
        skill.symlink_to(REPO / "skills/review-checklist/SKILL.md")
        self.install(ok=False)
        self.assertEqual(list(self.project.iterdir()), [])

    def test_lock_is_respected(self):
        lock = self.project / ".llm-skills-install.lock"
        lock.mkdir()
        self.install(ok=False)
        self.assertTrue(lock.is_dir())
        self.assertFalse(self.skill_path().exists())

    def test_download_flow_and_failure_with_mock_curl(self):
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        curl = bin_dir / "curl"
        curl.write_text('#!/bin/bash\nset -e\nurl=""\nout=""\nwhile [ "$#" -gt 0 ]; do\ncase "$1" in\nhttps://*) url=$1; shift;;\n--output) out=$2; shift 2;;\n*) shift;;\nesac\ndone\ncase "$url" in\nhttps://raw.githubusercontent.com/mariombn/my-skills/main/*) ;;\n*) exit 97;;\nesac\npath=${url#https://raw.githubusercontent.com/mariombn/my-skills/main/}\ncp "$MOCK_SOURCE/$path" "$out"\n')
        curl.chmod(0o755)
        env = dict(os.environ, PATH=str(bin_dir) + os.pathsep + os.environ["PATH"], MOCK_SOURCE=str(self.source))
        self.install(local=False, env=env)
        curl.write_text("#!/bin/bash\nexit 22\n")
        self.install(local=False, env=env, ok=False)

    def test_interactive_pipe_uses_controlling_terminal(self):
        # A real controlling PTY; Bash stdin is the installer pipe, answers use /dev/tty.
        pid, master = pty.fork()
        if pid == 0:
            os.chdir(self.project)
            script = "cat " + shlex.quote(str(REPO / "install.sh")) + " | " + shlex.quote(BASH) + " -s -- --source-dir " + shlex.quote(str(self.source))
            os.execv(BASH, [BASH, "-c", script])
        output = b""
        responses = [(b"> ", b"1,2,3\n"), (b"ou all): ", b"1\n"), (b"[s/N] ", b"s\n")]
        deadline = time.monotonic() + 15
        status = None
        try:
            while time.monotonic() < deadline:
                ready, _, _ = select.select([master], [], [], 0.1)
                if ready:
                    try:
                        chunk = os.read(master, 8192)
                    except OSError:
                        break
                    if not chunk:
                        break
                    output += chunk
                    if responses and responses[0][0] in output:
                        _, response = responses.pop(0)
                        os.write(master, response)
                done, value = os.waitpid(pid, os.WNOHANG)
                if done:
                    status = value
                    break
            if status is None:
                done, value = os.waitpid(pid, os.WNOHANG)
                if done:
                    status = value
                else:
                    os.kill(pid, 9)
                    _, status = os.waitpid(pid, 0)
        finally:
            os.close(master)
        self.assertEqual(status, 0, output.decode(errors="replace"))
        self.assertEqual(responses, [], output.decode(errors="replace"))
        self.assertTrue(self.skill_path().exists())
        self.assertTrue(self.skill_path(".claude").exists())


if __name__ == "__main__":
    unittest.main()
