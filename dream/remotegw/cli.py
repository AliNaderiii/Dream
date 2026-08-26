"""Headless CLI for the remote gateway. Works offline; --help never hangs."""

from __future__ import annotations

import argparse
import json
import sys

from dream.remotegw.bind import DEFAULT_PORT, resolve_bind
from dream.remotegw.errors import RemoteGwError, RemoteGwSecurityError
from dream.remotegw.service import RemoteGwService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dream-serve",
        description="Serve Dream's JSON-RPC on loopback. LAN bind is explicit. WAN is refused.",
    )
    parser.add_argument("--lan", action="store_true", help="Allow a private RFC1918 bind host")
    parser.add_argument("--host", default=None, help="Bind host (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Bind port (default 8765)")
    parser.add_argument("--preview", action="store_true", help="Print bind URL and exit")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        bind = resolve_bind(lan=args.lan, host=args.host, port=args.port)
    except RemoteGwSecurityError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.preview:
        print(json.dumps({"bind": bind, "url": f"http://{bind['host']}:{bind['port']}/"}, indent=2))
        return 0
    service = RemoteGwService()
    try:
        started = service.start(lan=args.lan, host=args.host, port=args.port)
    except (RemoteGwError, RemoteGwSecurityError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"dream-serve listening on http://{started['bind']['host']}:{started['bind']['port']}/")
    print("Authorization: Bearer <token>. Query-string tokens are refused.")
    try:
        while True:
            try:
                line = sys.stdin.readline()
            except KeyboardInterrupt:
                break
            if line == "":
                break
    finally:
        service.stop()
    return 0
