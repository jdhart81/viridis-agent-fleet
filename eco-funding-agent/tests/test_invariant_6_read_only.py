"""Invariant 6 - Read-only externally: the code only reads public data and writes nothing
to VergeCommon or any other service.

Three layers: (1) static scan of the source for any HTTP client, write verb or request
body; (2) runtime spy on every request the VergeCommon hook issues; (3) the MCP tools
all carry read-only annotations and never write files.
"""

from __future__ import annotations

import ast
import io
import json
import re
import shutil
from pathlib import Path

import pytest
from conftest import ROOT

from viridis_eco_funding.vergecommon import (
    ReadOnlyVergeCommonClient,
    VergeCommonError,
    fetch_and_bind,
)

SRC = ROOT / "src" / "viridis_eco_funding"


FORBIDDEN_MODULES = {"requests", "httpx", "httpx2", "aiohttp", "urllib3", "http", "socket",
                     "socketserver", "ssl", "smtplib", "ftplib", "telnetlib", "imaplib", "poplib",
                     "nntplib", "xmlrpc", "webbrowser", "asyncio", "paramiko", "boto3", "botocore",
                     "websockets", "websocket", "grpc", "subprocess", "asyncssh", "pycurl", "ctypes"}
URL_OPENERS = {"urlopen", "build_opener", "install_opener", "OpenerDirector", "Request",
               "HTTPHandler", "HTTPSHandler", "urlretrieve"}
WRITE_VERBS = [r"method\s*=\s*['\"](?:POST|PUT|PATCH|DELETE)['\"]", r"\.(?:post|put|patch|delete)\s*\("]


def scan_network(src: Path) -> list[str]:
    """Static read-only scan of a source tree; returns a list of violations."""
    hits = []
    for path in sorted(src.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for pattern in WRITE_VERBS:
            for match in re.finditer(pattern, text):
                hits.append(f"{path.name}: {match.group(0)!r}")
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in FORBIDDEN_MODULES:
                        hits.append(f"{path.name}: imports {alias.name}")
                    if alias.name.startswith("urllib") and path.name != "vergecommon.py":
                        hits.append(f"{path.name}: imports {alias.name} outside vergecommon.py")
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                if node.module.split(".")[0] in FORBIDDEN_MODULES:
                    hits.append(f"{path.name}: imports from {node.module}")
                if node.module.startswith("urllib") and any(a.name in URL_OPENERS or a.name == "*"
                                                            for a in node.names):
                    hits.append(f"{path.name}: from {node.module} import opener (aliasable)")
            elif isinstance(node, (ast.Attribute, ast.Name)):
                name = node.attr if isinstance(node, ast.Attribute) else node.id
                if name in URL_OPENERS and path.name != "vergecommon.py":
                    hits.append(f"{path.name}:{node.lineno}: references {name}")
            if isinstance(node, ast.Call):
                name = getattr(node.func, "attr", getattr(node.func, "id", ""))
                keywords = {kw.arg: kw.value for kw in node.keywords}
                if name == "Request":
                    ok = (len(node.args) == 1 and isinstance(keywords.get("method"), ast.Constant)
                          and keywords["method"].value == "GET"
                          and isinstance(keywords.get("data"), ast.Constant)
                          and keywords["data"].value is None and None not in keywords)
                    if not ok:
                        hits.append(f"{path.name}:{node.lineno}: Request must be url-only, data=None, method='GET'")
                if name in {"urlopen", "open"} and isinstance(node.func, ast.Attribute) and \
                        getattr(node.func.value, "attr", "") in {"request", "OpenerDirector"}:
                    if len(node.args) > 1 or "data" in keywords or None in keywords:
                        hits.append(f"{path.name}:{node.lineno}: urlopen with a body")
                if name in {"urlopen", "build_opener", "install_opener", "urlretrieve"} and \
                        path.name == "vergecommon.py" and name != "urlopen":
                    hits.append(f"{path.name}:{node.lineno}: {name} not allowed")
    return hits


def test_static_source_is_read_only():
    hits = scan_network(SRC) + scan_network(ROOT / "adapters")
    assert not hits, "\n".join(hits)


NETWORK_INJECTIONS = [
    ("vergecommon.py", "urllib.request.urlopen(url, data=payload)"),
    ("vergecommon.py", "urllib.request.urlopen(url, payload)"),
    ("vergecommon.py", "urllib.request.Request(url, payload, method='GET')"),
    ("vergecommon.py", "urllib.request.Request(url, data=None, method='POST')"),
    ("valuation.py", "from urllib.request import urlopen as _fetch"),
    ("valuation.py", "import urllib.request"),
    ("simulator.py", "import asyncio"),
    ("simulator.py", "import xmlrpc.client"),
    ("simulator.py", "import http.client"),
    ("bound.py", "x = client.post(url)"),
    ("receipt.py", "opener = urllib.request.build_opener()"),
]


@pytest.mark.parametrize("target, line", NETWORK_INJECTIONS)
def test_network_scanner_catches_injected_violations(tmp_path, target, line):
    copy = tmp_path / "src"
    shutil.copytree(SRC, copy, ignore=shutil.ignore_patterns("__pycache__"))
    assert scan_network(copy) == []
    path = next(copy.rglob(target))
    path.write_text(path.read_text() + "\n\ndef _injected():\n    " + line + "\n")
    assert scan_network(copy), f"scanner missed {line!r} in {target}"


def test_static_no_file_writes_in_source():
    for path in list(SRC.rglob("*.py")) + list((ROOT / "adapters").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for pattern in (r"open\([^)]*['\"][wax]\+?b?['\"]", r"\.write_text\(", r"\.write_bytes\(",
                        r"\bos\.remove\b", r"\bshutil\b"):
            assert not re.search(pattern, text), f"{path.name}: {pattern}"


class _Response(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class Spy:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append(request)
        if "id=" in request.full_url:
            return _Response(self.payload)
        return _Response(b'{"coops": []}')


def test_runtime_every_request_is_a_bodiless_https_get(synthetic_record, woodland_site):
    spy = Spy(synthetic_record)
    client = ReadOnlyVergeCommonClient(opener=spy)
    source = fetch_and_bind(woodland_site, client)
    client.list_public_coops(5)
    assert len(spy.requests) == 2
    for request in spy.requests:
        assert request.get_method() == "GET"
        assert request.data is None
        assert request.full_url.startswith("https://vergecommon.com/api/network?")
        headers = {k.lower() for k in request.headers}
        assert "authorization" not in headers and "cookie" not in headers
    assert source["project_kind"] == "woodland"


def test_runtime_rejects_non_allowlisted_hosts_and_plain_http():
    with pytest.raises(VergeCommonError, match="allowlist"):
        ReadOnlyVergeCommonClient(base_url="https://evil.example")
    with pytest.raises(VergeCommonError, match="https"):
        ReadOnlyVergeCommonClient(base_url="http://vergecommon.com")


def test_global_urlopen_never_called_with_write_methods(monkeypatch, synthetic_record, woodland_site):
    """Even through the default opener path, only GET reaches urllib."""
    import urllib.request

    seen = []

    def fake_urlopen(request, timeout=None):
        seen.append((request.get_method(), request.data))
        return _Response(json.dumps(synthetic_record).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    fetch_and_bind(woodland_site, ReadOnlyVergeCommonClient())
    assert seen == [("GET", None)]


def test_mcp_tools_are_annotated_read_only():
    pytest.importorskip("mcp.server.mcpserver", reason="standalone vef-mcp server needs mcp 2.x")
    import asyncio

    from viridis_eco_funding.mcp_server import build_server

    tools = asyncio.run(build_server().list_tools())
    assert len(tools) == 5
    for tool in tools:
        assert tool.annotations.read_only_hint is True
        assert tool.annotations.destructive_hint is False
        assert tool.annotations.idempotent_hint is True
