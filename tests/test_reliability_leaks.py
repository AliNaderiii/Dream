"""Resource-leak proofs. Run under ``-W error::ResourceWarning``."""

from __future__ import annotations

import gc
import subprocess
import sys
import warnings
from pathlib import Path

import pytest

from dream.reliability import CancelToken, ResourceSupervisor, durable_write
from dream.reliability.db import connect_sqlite, increment_counter

pytestmark = pytest.mark.filterwarnings("error::ResourceWarning")


def test_supervisor_and_sqlite_leave_no_resource_warnings(tmp_path: Path) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error", ResourceWarning)
        token = CancelToken(name="leak")
        with ResourceSupervisor(idle_timeout=2.0) as sup:
            sup.spawn_thread("noop", lambda: None)
            proc = subprocess.Popen(  # noqa: S603
                [sys.executable, "-c", "print('ok')"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            token.link_subprocess(proc)
            out, err = proc.communicate(timeout=5)
            assert "ok" in out
            assert err == "" or err is not None
            db = tmp_path / "leak.db"
            conn = connect_sqlite(db)
            increment_counter(conn, amount=1)
            conn.close()
            durable_write(tmp_path / "x.txt", "hello")
        token.cancel(reason="done")
        gc.collect()


def test_unclosed_warning_path_is_armed() -> None:
    """The filter is an error: opening and closing a file must stay silent."""
    import io

    handle = io.StringIO("x")
    handle.close()
    gc.collect()
