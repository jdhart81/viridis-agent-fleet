#!/usr/bin/env python3
"""Build the exact non-serving Security Preflight candidate transport."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import sys
import tarfile


SCHEMA = "viridis-security-preflight-conversion-candidate-bundle-v1"
MANIFEST_NAME = "candidate-bundle-manifest.json"
HISTORICAL_SOURCE_ROOT = (
    "deploy/droplet/history/security_preflight_conversion_20260806")
EXPECTED_FILES = (
    (
        "deploy/gateway/Dockerfile.security-preflight-conversion-candidate-20260806",
        "build-context/deploy/gateway/"
        "Dockerfile.security-preflight-conversion-candidate-20260806",
        "b5ec1686a389f0142a7c37700359c565e1cd9f8f697a2bc8ae4eda4282b604cc",
    ),
    (
        "deploy/gateway/agents.html",
        "build-context/deploy/gateway/agents.html",
        "089d60fec369597cd5356740fab9cafe24c0097237236290d9473045a7dc9be5",
    ),
    (
        "deploy/gateway/quickstart.html",
        "build-context/deploy/gateway/quickstart.html",
        "3ea80610cbc8b74d971d1b91841fbd34bfc8fa68691071f379baace1f19dd2fc",
    ),
    (
        "deploy/droplet/gateway_state_backup.py",
        "build-context/deploy/droplet/gateway_state_backup.py",
        "a4d1ae3ae6959d3c2a9c2aca9a88b5359d9d7b9daa5ec2eca3df15c547b8a101",
    ),
    (
        "deploy/droplet/stage_security_preflight_conversion_candidate_20260806.sh",
        "stage_security_preflight_conversion_candidate_20260806.sh",
        "8ceb359110a1532228b1420386ea044e9db3fd9fa4a78e707a07a0538493a3ab",
    ),
    (
        "deploy/droplet/test_stage_security_preflight_conversion_candidate_20260806.py",
        "verification/test_stage_security_preflight_conversion_candidate_20260806.py",
        "ea0e38ece97ea49a3d488ef90bb1d792fba7cf472f3e76886d30253d2e48785a",
    ),
)


class BundleFailure(RuntimeError):
    pass


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _file_sha(path: Path) -> str:
    return _sha(path.read_bytes())


def _info(name: str, content: bytes, executable: bool = False) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.size = len(content)
    info.mode = 0o700 if executable else 0o600
    info.mtime = 0
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    return info


def build_bundle(root: Path, output: Path) -> dict:
    if output.exists():
        raise BundleFailure("refusing to overwrite an existing candidate bundle")
    records = []
    contents = []
    for source_name, archive_name, expected in EXPECTED_FILES:
        # Match the original sealed packet, never a mutable serving checkout.
        source = root / HISTORICAL_SOURCE_ROOT / (source_name + ".source")
        if not source.is_file():
            raise BundleFailure(f"candidate source is missing: {source_name}")
        content = source.read_bytes()
        if _sha(content) != expected:
            raise BundleFailure(f"candidate source hash changed: {source_name}")
        records.append({
            "source": source_name,
            "archive_name": archive_name,
            "sha256": expected,
            "size_bytes": len(content),
        })
        contents.append((archive_name, content))
    manifest = {
        "schema": SCHEMA,
        "classification": "non_serving_candidate_transport_not_authorization",
        "file_count": len(records),
        "expected_live_image": (
            "sha256:4d465097726f8ca0c50eaf90559df0669be2a36715b24b7e06be2aa1556846ed"),
        "expected_backup_sha256": (
            "9f70148d95cc4ac417a5102f4fbdda5d51c2ad19330d506d7839039e29b0f0a1"),
        "production_promotion_authorized": False,
        "files": records,
    }
    manifest_bytes = (
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
            with tarfile.open(fileobj=gz, mode="w", format=tarfile.GNU_FORMAT) as archive:
                for name, content in contents:
                    archive.addfile(
                        _info(name, content, executable=name.endswith((".py", ".sh"))),
                        io.BytesIO(content),
                    )
                archive.addfile(_info(MANIFEST_NAME, manifest_bytes), io.BytesIO(manifest_bytes))
    archive_sha = _file_sha(output)
    verify_bundle(output, archive_sha)
    return {
        "status": "ok",
        "archive": str(output),
        "archive_sha256": archive_sha,
        "size_bytes": output.stat().st_size,
        "file_count": len(records),
    }


def verify_bundle(path: Path, expected_sha256: str) -> dict:
    if _file_sha(path) != expected_sha256:
        raise BundleFailure("candidate bundle bytes do not match expected hash")
    expected_names = {item[1] for item in EXPECTED_FILES} | {MANIFEST_NAME}
    with tarfile.open(path, "r:gz") as archive:
        names = archive.getnames()
        if len(names) != len(set(names)):
            raise BundleFailure("candidate bundle contains duplicate members")
        if set(names) != expected_names:
            raise BundleFailure("candidate bundle member set is incomplete")
        if any(PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts
               for name in names):
            raise BundleFailure("candidate bundle contains an unsafe path")
        manifest_file = archive.extractfile(MANIFEST_NAME)
        if manifest_file is None:
            raise BundleFailure("candidate manifest is missing")
        manifest = json.load(manifest_file)
        if manifest.get("schema") != SCHEMA:
            raise BundleFailure("candidate manifest schema mismatch")
        if manifest.get("production_promotion_authorized") is not False:
            raise BundleFailure("candidate bundle changed the production gate")
        for _, archive_name, expected in EXPECTED_FILES:
            member = archive.extractfile(archive_name)
            if member is None or _sha(member.read()) != expected:
                raise BundleFailure(f"candidate member hash failed: {archive_name}")
    return {"status": "ok", "file_count": len(EXPECTED_FILES)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("--root", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    verify = sub.add_parser("verify")
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
