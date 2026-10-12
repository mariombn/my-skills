#!/usr/bin/env python3
"""Offline installer tests. Run with: python3 -m unittest discover -s tests -v."""
import errno
import hashlib
import os
from pathlib import Path
import pty
import select
import shlex
import shutil
import signal
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
        self.home = self.root / "home with spaces"
        self.home.mkdir()
        self.tmpdir = self.root / "temporary files"
        self.tmpdir.mkdir()
        self.source = self.root / "source files"
        shutil.copytree(REPO / "skills", self.source / "skills")
        shutil.copy(REPO / "manifest.sha256", self.source / "manifest.sha256")

    def isolated_env(self, overrides=None):
        # Never let either subprocess.run or a controlling-PTY child inherit HOME.
        env = dict(os.environ, HOME=str(self.home), TMPDIR=str(self.tmpdir))
        env.pop("BASH_ENV", None)
        env.pop("ENV", None)
        for key, value in (overrides or {}).items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = str(value)
        return env

    def run_install(self, *args, ok=True, local=True, env=None):
        command = [BASH, str(REPO / "install.sh")]
        if local:
            command += ["--source-dir", str(self.source)]
        result = subprocess.run(command + list(args), cwd=self.project,
                                stdin=subprocess.DEVNULL, capture_output=True,
                                text=True, start_new_session=True,
                                env=self.isolated_env(env), timeout=20)
        if ok:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def run_interactive(self, responses, *args, ok=True, pipe=True, env=None):
        """Use a controlling PTY, including when Bash's stdin is a script pipe."""
        command = [BASH, str(REPO / "install.sh"), "--source-dir", str(self.source), *args]
        if pipe:
            script = "cat " + shlex.quote(str(REPO / "install.sh"))
            script += " | " + shlex.join([BASH, "-s", "--", "--source-dir", str(self.source), *args])
            command = [BASH, "-c", script]
        child_env = self.isolated_env(env)
        pid, master = pty.fork()
        if pid == 0:
            try:
                os.chdir(self.project)
                os.execve(BASH, command, child_env)
            finally:
                os._exit(127)
        pending = [(marker.encode(), answer.encode()) for marker, answer in responses]
        output = b""
        consumed = 0
        deadline = time.monotonic() + 15
        status = None
        eof = False
        try:
            while time.monotonic() < deadline:
                if not eof:
                    ready, _, _ = select.select([master], [], [], 0.1)
                    if ready:
                        try:
                            chunk = os.read(master, 8192)
                        except OSError as exc:
                            if exc.errno != errno.EIO:
                                raise
                            chunk = b""
                        if chunk:
                            output += chunk
                            while pending:
                                marker, answer = pending[0]
                                found = output.find(marker, consumed)
                                if found < 0:
                                    break
                                consumed = found + len(marker)
                                pending.pop(0)
                                os.write(master, answer)
                        else:
                            eof = True
                else:
                    time.sleep(0.01)
                if status is None:
                    done, value = os.waitpid(pid, os.WNOHANG)
                    if done:
                        status = value
                # Drain the PTY after exit so very fast cancellation does not lose
                # its final message between the response write and waitpid.
                if status is not None and eof:
                    break
        finally:
            if status is None:
                os.killpg(pid, signal.SIGKILL)
                _, status = os.waitpid(pid, 0)
            os.close(master)
        text = output.decode(errors="replace")
        if ok:
            self.assertEqual(status, 0, text)
        else:
            self.assertNotEqual(status, 0, text)
        self.assertEqual(pending, [], text)
        return text

    def install(self, *args, **kwargs):
        return self.run_install("--harnesses", "all", "--skills", "all", "--yes", *args, **kwargs)

    def skill_path(self, root=".agents", scope="project", name="review-checklist"):
        target = self.home if scope == "user" else self.project
        return target / root / "skills" / name / "SKILL.md"

    def catalog(self):
        # Installer numbering follows first appearance in the manifest, not a fixed index.
        return list(dict.fromkeys(line.split()[1].split("/")[1]
                                  for line in (self.source / "manifest.sha256").read_text().splitlines()
                                  if line.strip()))

    def assert_no_installer_artifacts(self, target):
        self.assertFalse((target / ".llm-skills-install.lock").exists())
        self.assertEqual(list(target.rglob(".llm-skills-stage.*")), [])

    def test_packaged_skills_include_metadata_and_valid_checksums(self):
        required = {"grill-me", "grilling", "review-checklist"}
        self.assertTrue(required.issubset(self.catalog()))
        manifest = {}
        for line in (self.source / "manifest.sha256").read_text().splitlines():
            digest, path = line.split()
            self.assertNotIn(path, manifest)
            manifest[path] = digest
            self.assertEqual(hashlib.sha256((self.source / path).read_bytes()).hexdigest(), digest, path)
        for name in required:
            self.assertIn(f"skills/{name}/SKILL.md", manifest)
        # Upstream MIT attribution and app metadata belong to the imported pair;
        # the existing review-checklist retains its original licensing status.
        for name in ("grill-me", "grilling"):
            for filename in ("LICENSE", "agents/openai.yaml"):
                path = f"skills/{name}/{filename}"
                self.assertIn(path, manifest)
                self.assertTrue((self.source / path).is_file())

    def test_spaces_multiple_harnesses_and_shared_pi(self):
        self.install()
        self.assertEqual(self.skill_path().read_bytes(), (self.source / "skills/review-checklist/SKILL.md").read_bytes())
        self.assertTrue(self.skill_path(".claude").exists())
        self.assertFalse((self.project / ".pi").exists())
        self.assertEqual(list(self.home.iterdir()), [])
        self.assert_no_installer_artifacts(self.project)

    def test_explicit_project_scope(self):
        self.install("--scope", "project")
        self.assertTrue(self.skill_path().is_file())
        self.assertTrue(self.skill_path(".claude").is_file())
        self.assertEqual(list(self.home.iterdir()), [])

    def test_user_scope_multiple_harnesses_and_skills(self):
        result = self.run_install("--scope", "user", "--harnesses", "claude,codex,pi,codex",
                                  "--skills", "review-checklist,grilling,review-checklist", "--yes")
        for root in (".claude", ".agents"):
            for name in ("review-checklist", "grilling"):
                path = self.skill_path(root, scope="user", name=name)
                self.assertEqual(path.read_bytes(), (self.source / "skills" / name / "SKILL.md").read_bytes())
            self.assertFalse((self.home / root / "skills/grill-me").exists())
        installed = [line for line in result.stdout.splitlines() if line.startswith("Instalado:")]
        self.assertEqual(len(installed), 4, result.stdout)
        self.assertFalse((self.home / ".pi").exists())
        self.assertEqual(list(self.project.iterdir()), [])
        self.assert_no_installer_artifacts(self.home)

    def test_grill_me_installs_grilling_dependency_in_both_scopes(self):
        for scope in ("project", "user"):
            with self.subTest(scope=scope):
                self.run_install("--scope", scope, "--harnesses", "codex,pi",
                                 "--skills", "grill-me", "--yes")
                for name in ("grill-me", "grilling"):
                    path = self.skill_path(scope=scope, name=name)
                    self.assertTrue(path.is_file())
                    self.assertTrue((path.parent / "LICENSE").is_file())
                    self.assertTrue((path.parent / "agents/openai.yaml").is_file())
                self.assertFalse(self.skill_path(scope=scope).exists())

    def test_explicit_dependency_is_not_installed_twice(self):
        result = self.run_install("--scope", "user", "--harnesses", "codex,pi",
                                  "--skills", "grill-me,grilling,grill-me", "--yes")
        for name in ("grill-me", "grilling"):
            self.assertEqual(result.stdout.count("Instalado: .agents/skills/" + name + "\n"), 1)
        self.assertNotIn("Preservado:", result.stdout)

    def test_repeat_preserves_user_edits(self):
        self.install()
        self.skill_path().write_text("user edits")
        result = self.install()
        self.assertEqual(self.skill_path().read_text(), "user edits")
        self.assertIn(f"{2 * len(self.catalog())} preservado(s)", result.stdout)

    def test_overwrite_keeps_backup(self):
        self.install()
        self.skill_path().write_text("user edits")
        self.install("--overwrite")
        backups = list(self.project.glob(".llm-skills-backup.*/.agents/skills/review-checklist/SKILL.md"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), "user edits")
        self.assertNotEqual(self.skill_path().read_text(), "user edits")

    def test_user_repeat_and_overwrite_keep_home_backup(self):
        self.install("--scope", "user")
        self.skill_path(scope="user").write_text("personal changes")
        self.skill_path(".claude", scope="user").write_text("claude changes")
        result = self.install("--scope", "user")
        self.assertEqual(self.skill_path(scope="user").read_text(), "personal changes")
        self.assertEqual(self.skill_path(".claude", scope="user").read_text(), "claude changes")
        self.assertIn(f"{2 * len(self.catalog())} preservado(s)", result.stdout)
        self.assertEqual(list(self.home.glob(".llm-skills-backup.*")), [])
        self.install("--scope", "user", "--overwrite")
        backups = list(self.home.glob(".llm-skills-backup.*"))
        self.assertEqual(len(backups), 1)
        for root, original in ((".agents", "personal changes"), (".claude", "claude changes")):
            self.assertEqual((backups[0] / root / "skills/review-checklist/SKILL.md").read_text(), original)
            self.assertEqual(self.skill_path(root, scope="user").read_bytes(),
                             (self.source / "skills/review-checklist/SKILL.md").read_bytes())
        self.assertEqual(list(self.project.iterdir()), [])
        self.assert_no_installer_artifacts(self.home)

    def test_scopes_do_not_overwrite_each_other(self):
        self.install("--scope", "project")
        self.skill_path().write_text("project-specific edits")
        self.install("--scope", "user", "--overwrite")
        self.assertEqual(self.skill_path().read_text(), "project-specific edits")
        self.skill_path(scope="user").write_text("user-specific edits")
        self.install("--scope", "project", "--overwrite")
        self.assertEqual(self.skill_path(scope="user").read_text(), "user-specific edits")

    def test_individual_harness_and_numbered_skill(self):
        number = f"{self.catalog().index('review-checklist') + 1:02d}"
        for harness in ("codex", "pi", "2", "3"):
            self.run_install("--harnesses", harness, "--skills", number, "--yes")
        self.assertTrue(self.skill_path().exists())
        self.assertFalse((self.project / ".claude").exists())
        self.assertFalse(self.skill_path(name="grill-me").exists())

    def test_invalid_arguments_do_not_write_targets(self):
        for args in (("--harnesses", "all,invalid", "--skills", "all", "--yes"),
                     ("--harnesses", "claude", "--skills", "all,invalid", "--yes"),
                     ("--harnesses", "claude", "--skills", "0", "--yes"),
                     ("--scope", "invalid", "--harnesses", "all", "--skills", "all", "--yes"),
                     ("--scope", "user", "--yes"), ("--scope",), ("--scope", ""),
                     ("--yes",), ("--ref", "../bad"), ("--unknown",)):
            with self.subTest(args=args):
                self.run_install(*args, ok=False)
        self.assertEqual(list(self.project.iterdir()), [])
        self.assertEqual(list(self.home.iterdir()), [])

    def test_missing_tty_explains_flags(self):
        result = self.run_install(ok=False)
        self.assertIn("Sem terminal", result.stderr)
        self.assertEqual(list(self.project.iterdir()), [])
        self.assertEqual(list(self.home.iterdir()), [])

    def test_omitted_scope_without_yes_still_requires_terminal(self):
        self.run_install("--harnesses", "codex", "--skills", "review-checklist", ok=False)
        self.assertEqual(list(self.project.iterdir()), [])
        self.assertEqual(list(self.home.iterdir()), [])

    def test_user_scope_rejects_invalid_home(self):
        relative = self.project / "relative-home"
        relative.mkdir()
        home_file = self.root / "home-is-file"
        home_file.write_text("unchanged")
        for value in (None, "", "relative-home", "./relative-home", str(self.root / "missing-home"), str(home_file)):
            with self.subTest(home=value):
                self.install("--scope", "user", env={"HOME": value}, ok=False)
                self.assertEqual(list(relative.iterdir()), [])
                self.assertEqual(list(self.home.iterdir()), [])
                self.assertEqual(list(self.project.iterdir()), [relative])
                self.assertEqual(home_file.read_text(), "unchanged")
                self.assertFalse((self.root / "missing-home").exists())

    def test_project_scope_does_not_require_home(self):
        self.install("--scope", "project", env={"HOME": None})
        self.assertTrue(self.skill_path().exists())
        self.assertEqual(list(self.home.iterdir()), [])

    def test_user_scope_resolves_physical_home(self):
        alias = self.root / "home alias"
        alias.symlink_to(self.home, target_is_directory=True)
        result = self.install("--scope", "user", env={"HOME": str(alias)})
        self.assertTrue(self.skill_path(scope="user").is_file())
        self.assertIn(str(self.home.resolve()), result.stdout)
        self.assertNotIn(str(alias), result.stdout)
        self.assertEqual(list(self.project.iterdir()), [])

    def test_tampered_checksum_aborts_before_writes(self):
        (self.source / "skills/review-checklist/SKILL.md").write_text("tampered")
        for scope in ("project", "user"):
            self.install("--scope", scope, ok=False)
        self.assertEqual(list(self.project.iterdir()), [])
        self.assertEqual(list(self.home.iterdir()), [])

    def test_dependency_checksum_is_checked_before_any_user_writes(self):
        (self.source / "skills/grilling/SKILL.md").write_text("tampered dependency")
        result = self.run_install("--scope", "user", "--harnesses", "all", "--skills", "grill-me", "--yes", ok=False)
        self.assertIn("SHA-256", result.stderr)
        self.assertEqual(list(self.project.iterdir()), [])
        self.assertEqual(list(self.home.iterdir()), [])

    def test_missing_dependency_aborts_before_any_writes(self):
        manifest = self.source / "manifest.sha256"
        rows = [line for line in manifest.read_text().splitlines()
                if line.split()[1].split("/")[1] != "grilling"]
        manifest.write_text("\n".join(rows) + "\n")
        for scope in ("project", "user"):
            with self.subTest(scope=scope):
                result = self.run_install("--scope", scope, "--harnesses", "all",
                                          "--skills", "grill-me", "--yes", ok=False)
                self.assertIn("grilling", result.stderr)
                self.assertEqual(list(self.project.iterdir()), [])
                self.assertEqual(list(self.home.iterdir()), [])

    def test_bad_manifest_paths_and_duplicates(self):
        valid = (self.source / "manifest.sha256").read_text()
        for path in ("../outside", "skills/review-checklist/../../outside", "/tmp/outside",
                     "skills/review-checklist//foo", "skills/review-checklist/-foo"):
            (self.source / "manifest.sha256").write_text("0" * 64 + "  " + path + "\n")
            for scope in ("project", "user"):
                self.install("--scope", scope, ok=False)
        (self.source / "manifest.sha256").write_text(valid + valid)
        for scope in ("project", "user"):
            self.install("--scope", scope, ok=False)
        self.assertEqual(list(self.project.iterdir()), [])
        self.assertEqual(list(self.home.iterdir()), [])

    def test_destination_symlinks_refused(self):
        outside = self.root / "outside"
        outside.mkdir()
        (self.project / ".agents").symlink_to(outside, target_is_directory=True)
        self.install("--overwrite", ok=False)
        self.assertEqual(list(outside.iterdir()), [])
        self.assertFalse((self.project / ".claude").exists())

    def test_user_destination_symlinks_refused_before_any_writes(self):
        outside = self.root / "outside"
        outside.mkdir()
        for relative in (".agents", ".agents/skills", ".agents/skills/grill-me"):
            with self.subTest(relative=relative):
                dest = self.home / relative
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.symlink_to(outside, target_is_directory=True)
                self.install("--scope", "user", "--overwrite", ok=False)
                self.assertEqual(list(outside.iterdir()), [])
                self.assertFalse((self.home / ".claude").exists())
                self.assertEqual(list(self.project.iterdir()), [])
                self.assert_no_installer_artifacts(self.home)
                dest.unlink()
                if (self.home / ".agents").exists():
                    shutil.rmtree(self.home / ".agents")

    def test_skill_symlink_refused(self):
        target = self.project / ".agents/skills"
        target.mkdir(parents=True)
        (target / "review-checklist").symlink_to(self.source / "skills/review-checklist")
        self.install("--overwrite", ok=False)

    def test_source_symlinks_refused(self):
        skill = self.source / "skills/review-checklist/SKILL.md"
        skill.unlink()
        skill.symlink_to(REPO / "skills/review-checklist/SKILL.md")
        for scope in ("project", "user"):
            self.install("--scope", scope, ok=False)
        self.assertEqual(list(self.project.iterdir()), [])
        self.assertEqual(list(self.home.iterdir()), [])

    def test_lock_is_respected(self):
        lock = self.project / ".llm-skills-install.lock"
        lock.mkdir()
        self.install(ok=False)
        self.assertTrue(lock.is_dir())
        self.assertFalse(self.skill_path().exists())

    def test_user_lock_is_respected_and_project_is_independent(self):
        lock = self.home / ".llm-skills-install.lock"
        lock.mkdir()
        self.install("--scope", "user", ok=False)
        self.assertEqual(list(self.home.iterdir()), [lock])
        self.assertEqual(list(self.project.iterdir()), [])
        self.install("--scope", "project")
        self.assertTrue(self.skill_path().exists())
        self.assertTrue(lock.is_dir())

    def test_user_lock_symlink_is_not_followed_or_removed(self):
        outside = self.root / "outside-lock"
        outside.mkdir()
        lock = self.home / ".llm-skills-install.lock"
        lock.symlink_to(outside, target_is_directory=True)
        self.install("--scope", "user", ok=False)
        self.assertTrue(lock.is_symlink())
        self.assertEqual(list(outside.iterdir()), [])
        self.assertEqual(list(self.home.iterdir()), [lock])
        self.assertEqual(list(self.project.iterdir()), [])

    def test_project_lock_does_not_block_user_scope(self):
        lock = self.project / ".llm-skills-install.lock"
        lock.mkdir()
        self.install("--scope", "user")
        self.assertTrue(self.skill_path(scope="user").exists())
        self.assertEqual(list(self.project.iterdir()), [lock])

    def test_download_flow_and_failure_with_mock_curl(self):
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        curl = bin_dir / "curl"
        curl.write_text('#!/bin/bash\nset -e\nurl=""\nout=""\nwhile [ "$#" -gt 0 ]; do\ncase "$1" in\nhttps://*) url=$1; shift;;\n--output) out=$2; shift 2;;\n*) shift;;\nesac\ndone\ncase "$url" in\nhttps://raw.githubusercontent.com/mariombn/my-skills/main/*) ;;\n*) exit 97;;\nesac\npath=${url#https://raw.githubusercontent.com/mariombn/my-skills/main/}\ncp "$MOCK_SOURCE/$path" "$out"\n')
        curl.chmod(0o755)
        env = {"PATH": str(bin_dir) + os.pathsep + os.environ["PATH"], "MOCK_SOURCE": str(self.source)}
        self.install(local=False, env=env)
        self.install("--scope", "user", local=False, env=env)
        self.assertTrue(self.skill_path(scope="user", name="grill-me").exists())
        curl.write_text("#!/bin/bash\nexit 22\n")
        self.install(local=False, env=env, ok=False)
        self.install("--scope", "user", local=False, env=env, ok=False)

    def test_interactive_pipe_uses_controlling_terminal(self):
        output = self.run_interactive([("Escopo [1]: ", "\n"), ("> ", "1,2,3\n"),
                                       ("ou all): ", "review-checklist\n"), ("[s/N] ", "s\n")])
        self.assertLess(output.index("Escopo [1]: "), output.index("Escolha os agentes"))
        self.assertTrue(self.skill_path().exists())
        self.assertTrue(self.skill_path(".claude").exists())
        self.assertEqual(list(self.home.iterdir()), [])

    def test_interactive_project_scope_aliases(self):
        for answer in ("1\n", "project\n"):
            with self.subTest(answer=answer):
                self.run_interactive([("Escopo [1]: ", answer), ("[s/N] ", "s\n")],
                                     "--harnesses", "codex", "--skills", "review-checklist")
                self.assertTrue(self.skill_path().exists())
                self.assertEqual(list(self.home.iterdir()), [])

    def test_interactive_user_scope_aliases(self):
        for answer in ("2\n", "user\n"):
            with self.subTest(answer=answer):
                output = self.run_interactive([("Escopo [1]: ", answer), ("> ", "1,2,3\n"),
                                               ("ou all): ", "grill-me,review-checklist\n"),
                                               ("[s/N] ", "s\n")])
                self.assertLess(output.index("Escopo [1]: "), output.index("Escolha os agentes"))
                for root in (".claude", ".agents"):
                    for name in ("grill-me", "grilling", "review-checklist"):
                        self.assertTrue(self.skill_path(root, scope="user", name=name).exists())
                self.assertEqual(list(self.project.iterdir()), [])
                self.assert_no_installer_artifacts(self.home)

    def test_explicit_scope_has_no_scope_menu(self):
        for scope in ("project", "user"):
            with self.subTest(scope=scope):
                output = self.run_interactive([("[s/N] ", "s\n")], "--scope", scope,
                                              "--harnesses", "codex", "--skills", "review-checklist")
                self.assertNotIn("1)", output)
                self.assertNotIn("Escolha os agentes", output)
                self.assertTrue(self.skill_path(scope=scope).exists())

    def test_yes_omitted_scope_uses_project_without_interactive_menu(self):
        output = self.run_interactive([], "--harnesses", "codex", "--skills", "review-checklist", "--yes")
        self.assertNotIn("Escopo [1]:", output)
        self.assertNotIn("Escolha os agentes", output)
        self.assertTrue(self.skill_path().exists())
        self.assertEqual(list(self.home.iterdir()), [])

    def test_interactive_invalid_scope_fails_without_writes(self):
        self.run_interactive([("Escopo [1]: ", "invalid\n")], ok=False)
        self.assertEqual(list(self.project.iterdir()), [])
        self.assertEqual(list(self.home.iterdir()), [])

    def test_interactive_cancel_leaves_both_scopes_untouched(self):
        for scope in ("1\n", "2\n"):
            with self.subTest(scope=scope):
                output = self.run_interactive([("Escopo [1]: ", scope), ("> ", "all\n"),
                                               ("ou all): ", "grill-me\n"), ("[s/N] ", "\n")])
                self.assertIn("Cancelado", output)
                self.assertEqual(list(self.project.iterdir()), [])
                self.assertEqual(list(self.home.iterdir()), [])

    def test_interactive_eof_at_scope_cancels_without_writes(self):
        self.run_interactive([("Escopo [1]: ", "\x04")], ok=False)
        self.assertEqual(list(self.project.iterdir()), [])
        self.assertEqual(list(self.home.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
