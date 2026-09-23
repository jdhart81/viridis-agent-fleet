#!/usr/bin/env python3
"""Build and verify the exact Security Preflight conversion source packet."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import sys
import tarfile
from typing import Any


SCHEMA = "viridis-security-preflight-conversion-source-bundle-v1"
MANIFEST_NAME = "source-bundle-manifest.json"
HISTORICAL_SOURCE_ROOT = (
    "deploy/droplet/history/security_preflight_conversion_20260806")
EXPECTED_FILES = (
    (
        "deploy/gateway/agents.html",
        "production/agents.html",
        "089d60fec369597cd5356740fab9cafe24c0097237236290d9473045a7dc9be5",
    ),
    (
        "deploy/gateway/quickstart.html",
        "production/quickstart.html",
        "3ea80610cbc8b74d971d1b91841fbd34bfc8fa68691071f379baace1f19dd2fc",
    ),
    (
        "scripts/x402_demo_client.py",
        "public/scripts/x402_demo_client.py",
        "eb71c466ad17c81d36e3f03c5ba308a4a0f8922337cef5116cc604deab87252d",
    ),
    (
        "deploy/gateway/test_wave9_activation.py",
        "verification/test_wave9_activation.py",
        "963bd8d11f1e09dc2783200e20b2d4f45a30fc6a83fda95cbd354b711202c30a",
    ),
    (
        "docs/deployment/SECURITY_PREFLIGHT_BUYER_PATH_CANDIDATE_2026-08-06.md",
        "evidence/SECURITY_PREFLIGHT_BUYER_PATH_CANDIDATE_2026-08-06.md",
        "7ebc693b0e6becfdedb067a62dcb251140106162b7357e559d1167c5a6ff8989",
    ),
    (
        "docs/deployment/patches/security-preflight-buyer-path-ee2b479.patch",
        "public/security-preflight-buyer-path-ee2b479.patch",
        "df4d873597f4ff72606510787a755698ddb707cb0bfd26368b4245150737dfbd",
    ),
    (
        "deploy/droplet/gateway_runtime_parity_hardened_20260804.py",
        "controls/gateway_runtime_parity_hardened_20260804.py",
        "6b43fa30e510bb460ce137a6dc95b43e0df6f4287ba02ccda432f92c317dfc8b",
    ),
    (
        "deploy/droplet/history/regulatory_radar_gateway_wedge_20260726/"
        "gateway_runtime_parity.py",
        "history/regulatory-radar-gateway-wedge-20260726/"
        "gateway_runtime_parity.py",
        "7c907daba1264bb26de0da6803f85a7bdbf55ffaec484bac12729da421bd87d3",
    ),
    (
        "deploy/mcp-publish/wavefunction-search-agent/server.json",
        "coherence/mcp-publish/wavefunction-search-agent/server.json",
        "02154b4b9ef7f435c38f1c0db8a103d7395b8b576eab212b4ef2421e512131ef",
    ),
    (
        "deploy/mcp-publish-github/wavefunction-search-agent/server.json",
        "coherence/mcp-publish-github/wavefunction-search-agent/server.json",
        "02154b4b9ef7f435c38f1c0db8a103d7395b8b576eab212b4ef2421e512131ef",
    ),
    (
        "deploy/mcp-publish/subscriptions-agent/server.json",
        "coherence/mcp-publish/subscriptions-agent/server.json",
        "6223b8dbaf34f5dc7ed452af0aefa16408834a166f5bb80be16ee8136cc0f1e9",
    ),
    (
        "deploy/mcp-publish-github/subscriptions-agent/server.json",
        "coherence/mcp-publish-github/subscriptions-agent/server.json",
        "6223b8dbaf34f5dc7ed452af0aefa16408834a166f5bb80be16ee8136cc0f1e9",
    ),
    (
        "deploy/glama/test_subscription_publish_contract.py",
        "verification/test_subscription_publish_contract.py",
        "ea1c76a17d5e8e6ab1e6c2839cb9ae79e200d3c6bd95bc2794620adb0b18b2a8",
    ),
)


class BundleFailure(RuntimeError):
    """The source packet is not exact, complete, and safe."""


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tar_info(name: str, content: bytes) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.size = len(content)
    info.mode = 0o600
    info.mtime = 0
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    return info


def _safe_member(name: str) -> bool:
    path = PurePosixPath(name)
    return not path.is_absolute() and ".." not in path.parts


def build_bundle(root: Path, output: Path) -> dict[str, Any]:
    if output.exists():
        raise BundleFailure("refusing to overwrite an existing source bundle")
    contents: list[tuple[str, bytes]] = []
    records = []
    for source_name, archive_name, expected_sha256 in EXPECTED_FILES:
        # Reproduce the sealed August packet from its verified historical
        # bytes. Current serving sources must be free to evolve independently.
        source = root / HISTORICAL_SOURCE_ROOT / (source_name + ".source")
        if not source.is_file():
            raise BundleFailure(f"source is missing: {source_name}")
        content = source.read_bytes()
        actual_sha256 = _sha256_bytes(content)
        if actual_sha256 != expected_sha256:
            raise BundleFailure(f"source hash changed: {source_name}")
        records.append({
            "source": source_name,
            "archive_name": archive_name,
            "sha256": actual_sha256,
            "size_bytes": len(content),
        })
        contents.append((archive_name, content))

    manifest = {
        "schema": SCHEMA,
        "classification": "source_candidate_not_published_not_production",
        "file_count": len(records),
        "files": records,
        "authorization": {
            "github_publication": False,
            "production_promotion": False,
            "payment": False,
            "outreach": False,
        },
    }
    manifest_bytes = (
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
            with tarfile.open(fileobj=gz, mode="w", format=tarfile.GNU_FORMAT) as archive:
                for name, content in contents:
                    archive.addfile(_tar_info(name, content), io.BytesIO(content))
                archive.addfile(
                    _tar_info(MANIFEST_NAME, manifest_bytes),
                    io.BytesIO(manifest_bytes),
                )
    result = verify_bundle(output, _sha256_file(output))
    result.update({
        "archive": str(output),
        "archive_sha256": _sha256_file(output),
        "size_bytes": output.stat().st_size,
    })
    return result


def verify_bundle(path: Path, expected_sha256: str) -> dict[str, Any]:
    if _sha256_file(path) != expected_sha256:
        raise BundleFailure("source bundle bytes do not match the expected hash")
    expected_names = {item[1] for item in EXPECTED_FILES} | {MANIFEST_NAME}
    with tarfile.open(path, "r:gz") as archive:
        members = archive.getmembers()
        names = [member.name for member in members]
        if len(names) != len(set(names)):
            raise BundleFailure("source bundle contains duplicate members")
        if set(names) != expected_names or not all(_safe_member(name) for name in names):
            raise BundleFailure("source bundle member set is unsafe or incomplete")
        manifest_file = archive.extractfile(MANIFEST_NAME)
        if manifest_file is None:
            raise BundleFailure("source bundle manifest is missing")
        manifest = json.load(manifest_file)
        if manifest.get("schema") != SCHEMA:
            raise BundleFailure("source bundle schema mismatch")
        if manifest.get("authorization") != {
            "github_publication": False,
            "outreach": False,
            "payment": False,
            "production_promotion": False,
        }:
            raise BundleFailure("source bundle authorization boundary changed")
        by_name = {item["archive_name"]: item for item in manifest["files"]}
        for _, archive_name, expected in EXPECTED_FILES:
            member = archive.extractfile(archive_name)
            if member is None or _sha256_bytes(member.read()) != expected:
                raise BundleFailure(f"source bundle member hash failed: {archive_name}")
            if by_name.get(archive_name, {}).get("sha256") != expected:
                raise BundleFailure(f"manifest member hash failed: {archive_name}")
    return {"status": "ok", "file_count": len(EXPECTED_FILES)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--root", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--bundle", type=Path, required=True)
    verify.add_argument("--sha256", required=True)
    args = parser.parse_args(argv)
    try:
        result = (
            build_bundle(args.root, args.output)
            if args.command == "build"
            else verify_bundle(args.bundle, args.sha256)
        )
    except (BundleFailure, OSError, tarfile.TarError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
