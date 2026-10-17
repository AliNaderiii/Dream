# Code execution — the active path, the contract, and what is actually isolated

This document is the reference for MASTER-P0: the Code surface, its wire
contract, and the isolation Dream does and does not provide. It replaces the
previous situation, in which three modules each described a different execution
story.

**Scope note.** Everything below describes the *container* path. The research and
data-Q&A pipelines have their own AST gate and their own documented dev escape
hatch; see [Other execution surfaces](#8-other-execution-surfaces).

---

## 1. The active call chain

Verified against the dispatch table the bridge actually builds, not against a
docstring. Reproduce it with:

```bash
python - <<'PY'
from dream.bridge.methods import BridgeMethods
import tempfile, os
tmp = tempfile.mkdtemp()
bm = BridgeMethods(sessions_path=f"{tmp}/s.json", projects_path=f"{tmp}/p.json",
                   disabled_skills_path=f"{tmp}/d.json", providers_path=f"{tmp}/pr.json",
                   provenance_dir=f"{tmp}/prov", mcp_config_path=f"{tmp}/m.json",
                   acp_config_path=f"{tmp}/a.json")
h = bm.handlers["sandbox.run_code"]
print(h.__module__, h.__qualname__)
PY
# -> dream.bridge.methods BridgeMethods.sandbox_run_code
```

```
apps/desktop/src/v5/views/code.js          run()                ← user presses «اجرا»
  └─ apps/desktop/src/v5/lib/bridge.js     api.sandboxRun(code, timeoutSeconds)
       └─ Tauri IPC  invoke('bridge_send', {id, method: "sandbox.run_code", params})
            └─ apps/desktop/src-tauri/src/bridge/mod.rs   bridge_send()
                 └─ newline-delimited JSON-RPC 2.0 over the sidecar's stdin
                      └─ dream/bridge/server.py            _handle_line → _dispatch
                           └─ dream/bridge/methods.py      BridgeMethods.sandbox_run_code
                                └─ dream/security/codeexec.py
                                     CodeExecutionRequest.from_params(...)   ← validation
                                     CodeExecutionRuntime.run(request)       ← the runner
                                          └─ dream/docker_sandbox.py  DockerSandbox.run_code
                                               └─ `docker run …` (see §4)
                                ← CodeExecutionResponse.to_dict()
                      ← JSON-RPC result
                 ← Tauri returns the same JSON
            ← code.js renderStage()
```

### Where `sandbox.run_code` is *not* defined

`dream/bridge/methods_sandbox.py` (the auto-discovered `sandbox.*` extension) used
to declare its own `sandbox.run_code`, backed by a stateful host
`eval`/`exec` interpreter. It only ever lost to the built-in handler because
`dream.bridge.extensions.Registry.publish` **drops** extension methods that
collide with a built-in. That is a collision-resolution accident, not a security
control: a rename, a registry ordering change, or the removal of the built-in
handler would have exposed a host interpreter behind the same RPC.

The extension no longer declares the method, and
`tests/test_code_execution_route_containment.py` fails if it reappears.

---

## 2. The contract

One request type, one response type, defined in `dream/security/codeexec.py`.
The desktop view, the bridge handler, and the tests all use it.

### 2.1 Request — `sandbox.run_code` params

| Field | Type | Default | Bounds |
| --- | --- | --- | --- |
| `code` | string | required | 1 … 1 000 000 bytes (UTF-8), non-blank |
| `language` | string | `"python"` | only `python` (`SUPPORTED_LANGUAGES`) |
| `timeout_seconds` | number | `15` | `> 0` … `120` |
| `memory_mb` | integer | `1024` | `64` … `4096` |
| `cpu_count` | number | `1.0` | `0.1` … `8` |
| `pids_limit` | integer | `64` | `1` … `512` |
| `max_output_bytes` | integer | `200000` | `1000` … `2000000` (per stream) |
| `workspace` | string \| null | `null` | must resolve **inside** the sandbox root |
| `execution_id` | string \| null | generated | `[A-Za-z0-9._-]{1,64}` |

Validation is on the backend. The frontend sends only `code` and
`timeout_seconds`, and the view's own checks are display conveniences.

### 2.2 Fields that are **refused by name**

These used to be accepted and used to widen the boundary. They are now rejected
with `status: "denied"` and `error.code == "removed_field"` — refused, never
silently ignored, so a client that believes it is configuring something finds
out that it is not.

| Field | Why it is gone |
| --- | --- |
| `resource_limits` | let a request set `network_enabled: true` and pick its own memory/timeout |
| `network_enabled` | the sandbox network is fixed off; there is no switch |
| `workspace_path` | mounted an **arbitrary host directory** into the container |
| `mount_workspace_read_write` | combined with the above, a host-filesystem write primitive |
| `env_vars` | injected caller-chosen environment variables into the code process |
| `docker_host` | let a caller point the runner at another daemon socket |

Any other unrecognised field is `denied` with `error.code == "unknown_field"`.
The schema is closed.

### 2.3 Response

```json
{
  "status": "success | error | timeout | cancelled | denied | unavailable",
  "execution_id": "exe-1a2b3c4d5e6f",
  "result": {
    "status": "success",
    "execution_id": "exe-1a2b3c4d5e6f",
    "stdout": "…",
    "stderr": "…",
    "stdout_path": "…/stdout.txt",
    "stderr_path": "…/stderr.txt",
    "exit_code": 0,
    "duration_ms": 42.5,
    "timed_out": false,
    "truncated": false,
    "artifacts": [{"name": "chart.png", "file_path": "…", "mime_type": "image/png", "size_bytes": 2048}],
    "error": {"code": "…", "reason_en": "…", "reason_fa": "…", "detail": "…"},
    "error_message": "…\n…",
    "variables_updated": [],
    "isolation": {"backend": "docker", "network": "none", "rootfs": "read-only", "…": "…"},
    "limits": {"timeout_seconds": 15, "network_enabled": false, "…": "…"}
  }
}
```

`status` appears at the top level **and** inside `result`, always with the same
value. The top level is what the view switches on; `result` is the detail panel.
Repeating it means a client cannot read one and miss the other.

**Status meaning**

| Status | Meaning |
| --- | --- |
| `success` | the program ran and exited `0` |
| `error` | the program ran and exited non-zero, *or* the runner failed before reporting |
| `timeout` | the backend deadline fired and the container was terminated |
| `cancelled` | the run was cancelled and the container was terminated |
| `denied` | the request never reached a runner (bad field, oversized code, escaping workspace) |
| `unavailable` | no reachable isolated runner — **nothing ran on the host** |

**The profile is always present.** `result.isolation` is computed before any
early return, so a `denied` or `unavailable` response carries the profile too.
The client can show what the sandbox *is* even when nothing ran — the
alternative (an empty object on failure) invites a UI that renders the safety
properties only on the happy path.

**Bounded output.** Each stream is truncated to `max_output_bytes`; `truncated`
is set, the text ends with an explicit marker, and the untruncated stream is
written to `stdout_path` / `stderr_path` inside the run's own workspace. Output
is passed through `dream.security.secrets.redact_text` before the caller sees it.

**Errors carry no internals.** `error` is a structured `{code, reason_en,
reason_fa, detail}`; `detail` is redacted and capped at 200 characters. No host
traceback, no filesystem path beyond the sandbox root, no stack frame ever
crosses the wire. `variables_updated` is always `[]`, honestly: each run is a
fresh container, so there is no persistent namespace.

### 2.4 Sibling methods

| Method | Contract |
| --- | --- |
| `sandbox.cancel` | `{execution_id}` → `{status: "cancelled" \| "not_running", container_killed}`. Terminates the container tree. |
| `sandbox.get_status` | Runner availability, backend identity, sandbox root, run/artifact counters, enforced limits. `available` is the honest field. |
| `sandbox.list_artifacts` | Files produced by real runs. Read-only; executes nothing. |
| `sandbox.reset` | Clears run history and per-run workspaces **under the sandbox root only**; refuses to follow a symlink out of it. |
| `sandbox.status` | Docker daemon probe (`docker info`) with a bounded 10 s wait. |
| `sandbox.analyze_data` | Dataset profiling. Parses data; executes nothing. |

---

## 3. Fail-closed behaviour

There is no path from a failed, missing, or misconfigured runner to a host
interpreter. Concretely:

| Condition | Result |
| --- | --- |
| No runner object in this build | `unavailable` (`error.code: "runner_missing"`) |
| `docker info` fails / daemon down | `unavailable` (`error.code: "docker_unavailable"`) |
| Daemon probe raises | `unavailable` |
| `docker` binary missing at run time | `unavailable` (`DockerUnavailableError`) |
| Runner raises during the step | `error` (`error.code: "runner_failure"`), `exit_code: -1` |
| Deadline exceeded | `timeout`; the container is force-removed |
| Caller cancels mid-run | `cancelled`; the container is force-removed |
| Container exits non-zero | `error` with the container's real `exit_code` and stderr |

`unavailable` and `error` are never rendered as success, and the view shows the
bilingual reason instead of an empty panel.

---

## 4. What the container actually enforces

The boundary is the argv `DockerSandbox._exec_in_container` builds. Each row below
is asserted against that argv in `tests/test_docker_sandbox_hardening.py`, so
these are **requested** flags with test evidence — not a claim about the kernel.

| Control | Flag / mechanism |
| --- | --- |
| No Linux capabilities | `--cap-drop=ALL` |
| No privilege gain | `--security-opt=no-new-privileges:true` |
| Not privileged | no `--privileged`, no `--cap-add` |
| Immutable image filesystem | `--read-only` |
| One writable scratch area | `--tmpfs /tmp:rw,nosuid,nodev,size=64m` |
| Non-root process | `--user <uid>:<gid>` (host ids; `65534:65534` if the app runs as root) |
| No network | `--network=none` |
| Syscall filtering | `--security-opt seccomp=<profile>` (see the caveat below) |
| Bounded memory, no swap escape | `--memory=<n>m`, `--memory-swap=0` |
| Bounded process count | `--pids-limit=<n>` |
| Bounded CPU | `--cpus=<n>` |
| Exactly one host mount | `-v <sandbox-root>/<run>:/workspace:rw` |
| No host environment | every `-e` carries a literal value; no `--env-file`, no bare `-e NAME` |
| No Docker socket | never mounted |
| Whole-tree teardown | `docker rm -f <name>` on timeout, cancellation, and in `finally` |

**Workspace rule.** The only host path ever mounted is
`<DREAM_SANDBOX_ROOT>/runs/<execution_id>` (default root
`~/.dream/sandbox`; override with `DREAM_SANDBOX_ROOT`). A caller may name an
existing directory, but it must resolve — **symlinks followed** — inside the
sandbox root. Absolute paths, `..` traversal, and symlink escapes are all
`denied`. See `tests/test_code_execution_contract.py`.

**The seccomp caveat.** The profile in `docker_sandbox.py` is a permissive
allow-list: it permits `socket`, `execve`, `clone`, `mount`, and friends. The
real network control is `--network=none` plus `--cap-drop=ALL`, not the profile.
Treating that file as a syscall sandbox would be an overstatement.

---

## 5. Timeouts, cancellation, and resource limits

- The **backend** owns the deadline. `MAX_TIMEOUT_SECONDS` is 120 s and the
  client's IPC timeout is 180 s, deliberately *above* it: the side that fires
  first must be the side that can terminate the container. A shorter client
  timeout would abandon a live container instead of killing it.
- On timeout the container is removed with `docker rm -f`, not merely
  abandoned — killing the `docker run` client leaves the container and every
  process inside it alive.
- `sandbox.cancel {execution_id}` does the same on demand, and the Code view
  offers a «لغو» button while a run is in flight.
- An `asyncio` cancellation of the handler (bridge shutdown, drain) also removes
  the container before the exception propagates.
- Resource ceilings are clamped server-side: memory ≤ 4096 MB, CPUs ≤ 8,
  PIDs ≤ 512, output ≤ 2 MB per stream. A request outside a range is `denied`,
  never coerced.

---

## 6. Supported platforms and prerequisites

| Platform | Status |
| --- | --- |
| Linux | Supported. Docker Engine ≥ 20.10, daemon reachable. |
| macOS | Supported. Docker Desktop (or Colima); `--user` is left to the image default because the container VM owns the id mapping — this is reported per run in `result.isolation.user` rather than claimed. |
| Windows | Supported. Docker Desktop with the WSL2 backend. No `os.getuid`, so `--user` is the image default, reported honestly. Bind-mount ownership follows Docker Desktop's mapping. |

**Prerequisite: a working Docker daemon.** Without one, the Code surface is
`unavailable` by design. Dream will not run the program locally to keep the
button working.

The first run pulls `python:3.12-slim` (~50 MB). Set `DREAM_SANDBOX_IMAGE` to
pin a mirror, an air-gapped local image, or a digest. The override applies to
the **Python** language only — the language this contract exposes — so an R or
Bash run can never be silently redirected to a Python image and fail
confusingly. `tests/test_docker_sandbox_hardening.py` asserts both the override
reaching `docker run` and the language scoping.

---

## 7. Verified vs. unverified

**Verified in CI (no daemon needed):**

- the registered `sandbox.run_code` handler is the container handler, and is
  the only definition of that method anywhere in the bridge;
- the full request validation matrix, including every refused field;
- workspace confinement: absolute paths, `..`, symlink escapes, symlinked
  parents, artifact paths, and `reset` refusing to follow a link out of the root;
- fail-closed behaviour for a missing runner, an unreachable daemon, a raising
  probe, a crashing runner, a timeout, and a cancellation;
- output truncation, the overflow reference, and secret redaction;
- the exact `docker run` argv: capabilities, non-root user, read-only rootfs,
  tmpfs, `--network=none`, memory/swap/PID bounds, the single bind mount,
  no host environment, no socket;
- container-tree teardown on timeout, on cancellation, and on the `finally` path;
- absence of `eval`/`exec`/`compile` in `dream/sandbox/**`, and absence of the
  old host-execution entry points from the bridge and from the model's tool
  `REGISTRY`;
- **no local fallback**: `tests/test_no_local_execution_fallback.py` sets
  `DREAM_DATA_LOCAL_EXEC=1`, blockades the `dream.docker_sandbox` import, and
  kills the daemon at run time — under a process recorder that raises on any
  spawn — and asserts a typed `unavailable` result every time, with the bridge
  answering `UNAVAILABLE` (-32010) rather than `INVALID_PARAMS`;
- the **real transport**: `tests/test_code_execution_end_to_end.py` spawns
  `python -m dream.bridge` and speaks newline-delimited JSON-RPC over real
  pipes, so the header, the dispatch table built at startup, the JSON encoder,
  and the exact wire key set are all exercised — an in-process handler test can
  pass while the registered method is wrong.

**Not verified here — state this plainly, do not imply otherwise:**

- that a **real** container honours those flags. CI has no Docker daemon, so no
  test in this repository has executed a container as part of MASTER-P0. The
  argv tests prove what Dream asks for; proving what the kernel enforces needs a
  host with Docker and is an integration-test task.
- Docker/kernel escape. A `runc` or kernel bug is outside Dream's control; the
  container is Docker's boundary, not Dream's.
- `--userns=remap`. It needs `userns-remap` configured on the daemon, so it is
  **opt-in** (`ResourceLimits.userns_remap`) and off by default; on a stock
  daemon the flag makes `docker run` fail outright, which would turn hardening
  into an outage. Enable it explicitly if your daemon is configured for it.
- Bash / R inside the container. The bridge contract accepts `python` only, so
  the other languages are unreachable through this RPC; `DockerSandbox.run_code`
  itself still supports them for internal callers.

---

## 8. Other execution surfaces

Catalogued by an independent review pass, with the reason each is not a bypass:

| Surface | Status |
| --- | --- |
| `dream/sandbox/executor.py` (`SandboxExecutor`) | **Disabled.** No `eval`/`exec`/`compile` call site remains; `execute_python` returns `UNAVAILABLE`. It used to be a stateful host interpreter guarded by a seven-regex blocklist. |
| `dream/sandbox/isolation/` (`WasmMicroSandbox`, `IsolatedExecutionEngine`) | **Disabled.** No host interpreter remains; the runtime reports `available = False` and exit code 126. It was never WASM, was never kernel-level, and is no longer described as either. The static syscall audit and the output clamp survive as real (but static) helpers. |
| `sandbox_execute_python` (LLM tool) | **Unreachable and refusing.** `dream.tools.base.REGISTRY` never contained it, so `filter_tools` could never hand it to the model; the wrapper now reports `available: False` as well. |
| `/code` slash command | **Not wired.** `cli.py` never dispatched it; the handler now reports the fail-closed state. |
| `tool.execute` | Resolves through `REGISTRY` only; an unregistered name is `INVALID_PARAMS`. |
| `workspace.shell_execute` | Approval-bound: it takes an `approval_id` for a suggestion made by `workspace.shell_propose`, never a raw command string. Separate surface, separate controls. |
| `sandbox.list_backends` / `sandbox.set_backend` | **A naming trap, not a route.** These speak to `dream.terminal.manager.TerminalManager` — the `!shell` terminal's backend — so the `local` entry means "the host shell the *terminal* uses". The Code runtime never consults `TerminalManager`; `set_backend` cannot make `sandbox.run_code` run locally. The namespace collision is misleading and worth renaming in a future slice. |
| `notebook.execute` / `notebook.run_cell` | Runs notebook cells on the dataset kernel — a separate, explicit Jupyter surface, not reachable from the Code view. |
| `research.*` / `dataqa.*` CodeAct | Uses `dream.security.agentcode` (AST allowlist, path confinement, network fixed off) on top of the same `DockerSandbox`. **Container-only since D1:** the `DREAM_DATA_LOCAL_EXEC=1` opt-in and the import-failure fallback were both removed, so when no container runtime is available the run stops with `ContainerUnavailableError` and the session reports `FAILED` — nothing executes on the host. `run.start` reports the executor's real `backend` and `sandbox_available`, so a missing daemon can no longer be displayed as a Docker sandbox. |
| `dream/tools/system_tools.py` (`run_shell`) | A different, approval-gated surface (§A5 in the threat model), not a code-execution route for the Code view. |
| `dream/dataqa/executor.py` (plan worker) | Runs **a plan the planner built**, not model-authored source: `dream/dataqa/worker.py` branches on `plan["action"]` and never evaluates a plan value. It is a resource-limited host subprocess (`RLIMIT_CPU`/`AS`/`FSIZE`/`NOFILE`/`NPROC`, ≤ 30 s) and is *not* described as a sandbox. |

---

## 9. Residual risks

1. **No real-container integration test in CI.** Highest-value next step: a
   nightly job with a Docker daemon that runs a canary payload (network attempt,
   `/etc/shadow` read, `~` write, fork bomb, output flood) and asserts each is
   refused, plus a timeout test asserting the container is gone.
2. **Docker/kernel escape.** Out of Dream's control; accepted.
3. **`--userns=remap` is off by default** (see §7). Enable it if your daemon is
   configured for it.
4. **The seccomp profile is permissive** (§4). Tightening it is a separate,
   evidence-requiring change; the network and capability controls do not depend
   on it.
5. **Pinned image.** `python:3.12-slim` is pulled by tag, not digest. An operator
   with a tamper-sensitive threat model should set `DREAM_SANDBOX_IMAGE` to a
   digest-pinned image.
6. **`sandbox.analyze_data` with a path argument** profiles a host file. It is
   guarded by `dream.security.pathsafety.is_sensitive_path` and returns
   statistics plus a sample preview, not raw contents wholesale — but it is a
   data-read surface on the host, and a stricter "sandbox-root only" rule is a
   reasonable future tightening.
7. **The container has no CPU *time* cap**, only `--cpus` (a rate) and the wall
   clock. A run cannot exceed its wall-clock budget, but it can consume its full
   CPU share for that budget.
8. **Retired by D1: `DREAM_DATA_LOCAL_EXEC`.** The host-execution opt-in no
   longer exists in the product, and neither does the import-failure fallback;
   `LocalPythonExecutor` was deleted. The only local runner left is
   `LocalTestExecutor` in `tests/_data_science_helpers.py`, which is a test
   fixture no product module imports (asserted by
   `tests/test_no_local_execution_fallback.py`).

---

## 10. Rollback

Revert the MASTER-P0 commit range. Two things must be reverted together, or the
Code view will render nothing:

- the backend contract (`dream/security/codeexec.py`,
  `dream/bridge/methods.py::sandbox_run_code`,
  `dream/bridge/methods_sandbox.py`, `dream/docker_sandbox.py`), **and**
- the frontend readers (`apps/desktop/src/v5/views/code.js`,
  `apps/desktop/src/v5/lib/bridge.js`).

Reverting only the backend restores the old
`{stdout, stderr, return_code, …}` response that `code.js` cannot read. Reverting
only the frontend restores a view that reads `result.result.stdout` while the
backend returns a flat shape. Neither half is meaningful alone.

No data migration is required: run history is in memory and per-run workspaces
live under `DREAM_SANDBOX_ROOT`, which is safe to delete.

---

## 11. References

- `dream/security/codeexec.py` — the contract, validation, and the runtime.
- `dream/security/agentcode.py` — the additional AST gate for agentic callers.
- `dream/docker_sandbox.py` — the container runner and its argv.
- `apps/desktop/src/v5/views/code.js` — the view.
- `tests/test_code_execution_contract.py` — the contract and adversarial matrix.
- `tests/test_docker_sandbox_hardening.py` — the argv assertions.
- `tests/test_code_execution_route_containment.py` — the absence proofs.
- `tests/test_code_execution_end_to_end.py` — the real sidecar over real pipes.
- `tests/test_no_local_execution_fallback.py` — the D1 fail-closed proofs.
- `tests/test_desktop_sandbox_bridge.py` — the bridge surface.
- `tests/test_sandbox_isolation_and_seccomp.py`,
  `tests/test_code_sandbox_and_interpreter.py` — the retired local routes.
- `apps/desktop/src/v5/views/code.test.js` — the frontend contract tests.
- `docs/STATUS.md` — the MASTER-P0 entry.
- `docs/bridge/protocol.md` §3.18 — the wire specification.
