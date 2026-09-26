"""Stdio proxy: put orc-seal in front of ANY MCP server, in any language.

    orc-seal --issuer did:web:example.com -- npx -y @acme/some-mcp-server

The client talks to orc-seal exactly as it talked to the server. Every
message passes through unchanged (P1), except successful `tools/call`
responses, which gain a receipt under result._meta (sealer M1/M6).

--- INVARIANTS ---
P1  Transparency: lines that are not JSON objects, requests, notifications,
    and responses to anything other than tools/call are forwarded byte-for-byte.
P2  Ordering: server->client lines are written in the order received.
P3  The proxy never originates JSON-RPC messages of its own.
P4  Exit: when the server exits, the proxy exits with the server's code.
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
from typing import IO, Optional

from .sealer import Sealer


class Tracker:
    """Remembers tools/call requests by id until their response arrives."""

    def __init__(self):
        self._lock = threading.Lock()
        self._pending: dict = {}

    def note_client_line(self, line: bytes) -> None:
        try:
            msg = json.loads(line)
        except Exception:
            return
        if isinstance(msg, dict) and msg.get("method") == "tools/call" and "id" in msg:
            with self._lock:
                self._pending[json.dumps(msg["id"])] = msg

    def take(self, msg_id) -> Optional[dict]:
        with self._lock:
            return self._pending.pop(json.dumps(msg_id), None)


def transform_server_line(line: bytes, tracker: Tracker, sealer: Sealer) -> bytes:
    try:
        msg = json.loads(line)
    except Exception:
        return line                                                       # P1
    if not isinstance(msg, dict) or "id" not in msg or "method" in msg:
        return line                                                       # P1
    req = tracker.take(msg["id"])
    if req is None:
        return line                                                       # P1
    out = sealer.seal_tools_call(req, msg)
    if out is msg:
        return line
    nl = b"\r\n" if line.endswith(b"\r\n") else b"\n"
    return json.dumps(out, separators=(",", ":")).encode() + nl


def pump_client(src: IO[bytes], dst: IO[bytes], tracker: Tracker) -> None:
    for line in iter(src.readline, b""):
        tracker.note_client_line(line)
        try:
            dst.write(line)
            dst.flush()
        except (BrokenPipeError, ValueError):
            break
    try:
        dst.close()
    except Exception:
        pass


def pump_server(src: IO[bytes], dst: IO[bytes], tracker: Tracker, sealer: Sealer) -> None:
    for line in iter(src.readline, b""):                                  # P2
        dst.write(transform_server_line(line, tracker, sealer))
        dst.flush()


def run(cmd: list[str], sealer: Sealer, stdin: IO[bytes] = None,
        stdout: IO[bytes] = None) -> int:
    stdin = stdin or sys.stdin.buffer
    stdout = stdout or sys.stdout.buffer
    child = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    tracker = Tracker()
    t_in = threading.Thread(target=pump_client, args=(stdin, child.stdin, tracker), daemon=True)
    t_in.start()
    pump_server(child.stdout, stdout, tracker, sealer)
    return child.wait()                                                   # P4
