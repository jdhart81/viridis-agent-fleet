#!/usr/bin/env python3
"""Build and verify the exact Radar gateway promotion transport bundle."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import tarfile
from typing import Any


SCHEMA = "viridis-regulatory-radar-gateway-promotion-bundle-v1"
MANIFEST_NAME = "promotion-bundle-manifest.json"
EXPECTED_FILES = (
    (
        "deploy/droplet/regulatory_radar_wedge_public_probe.py",
        "regulatory_radar_wedge_public_probe.py",
        "3b7bbd923bc331ffbc8edd895b1e401050f267c8e7b135a40ef5c1d3c5b98470",
    ),
    (
        "deploy/droplet/regulatory_radar_promotion_backup_gate.py",
        "regulatory_radar_promotion_backup_gate.py",
        "abf5c5738adfd5c8d1e6fe13cdac05da1b167125b7fb2b87d504b6d143837d3b",
    ),
    (
        "deploy/droplet/promote_regulatory_radar_gateway_wedge.sh",
        "promote_regulatory_radar_gateway_wedge.sh",
        "0d8ab8ba5b40993b20b9a50dc61d05f4b84c50ae53066c506b760d6275d7bb23",
    ),
    (
        "scripts/regulatory_radar_margin_gate.py",
        "regulatory_radar_margin_gate.py",
        "210d5410aa4e50997de90a5aa97791643fdb5a94a564e1324d6bf3e00ec208d3",
    ),
    (
        "regulatory-radar-agent/commercial_contract.json",
        "commercial_contract.json",
        "09b212cb569f835d7ce1ffc6b921f56a9201ac5af45b5b46c58fdc585909765f",
    ),
    (
        ("deploy/droplet/history/regulatory_radar_gateway_wedge_20260726/"
         "gateway_runtime_parity.py"),
        "gateway_runtime_parity.py",
        "7c907daba1264bb26de0da6803f85a7bdbf55ffaec484bac12729da421bd87d3",
    ),
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class BundleFailure(RuntimeError):
    """The promotion transport bundle is not exact and safe."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise BundleFailure(message)


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tar_info(name: str, content: bytes, *, executable: bool) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.size = len(content)
    info.mode = 0o700 if executable else 0o600
    info.mtime = 0
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    return info


def build_bundle(root: Path, output: Path) -> dict[str, Any]:
    require(not output.exists(), "refusing to overwrite an existing bundle")
    records = []
    contents: list[tuple[str, bytes, bool]] = []
    for source_name, archive_name, expected_sha256 in EXPECTED_FILES:
        source = root / source_name
        require(source.is_file(), f"promotion source is missing: {source_name}")
        content = source.read_bytes()
        actual_sha256 = _sha256_bytes(content)
        require(
            actual_sha256 == expected_sha256,
            f"promotion source hash changed: {source_name}",
        )
        executable = archive_name.endswith((".py", ".sh"))
        records.append({
            "source": source_name,
            "archive_name": archive_name,
            "sha256": actual_sha256,
            "size_bytes": len(content),
            "mode": "0700" if executable else "0600",
        })
        contents.append((archive_name, content, executable))

    manifest = {
        "schema": SCHEMA,
        "file_count": len(records),
        "files": records,
    }
    manifest_bytes = (
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as raw:
        with gzip.GzipFile(
            filename="",
            mode="wb",
            fileobj=raw,
            mtime=0,
        ) as compressed:
            with tarfile.open(
                fileobj=compressed,
                mode="w",
                format=tarfile.GNU_FORMAT,
            ) as archive:
                for name, content, executable in contents:
                    archive.addfile(
                        _tar_info(name, content, executable=executable),
                        io.BytesIO(content),
                    )
                archive.addfile(
                    _tar_info(
                        MANIFEST_NAME,
                        manifest_bytes,
                        executable=False,
                    ),
                    io.BytesIO(manifest_bytes),
                )
    archive_sha256 = _sha256_file(output)
    verified = verify_bundle(output, archive_sha256)
    return {
        "status": "ok",
        "archive": str(output),
        "archive_sha256": archive_sha256,
        "size_bytes": output.stat().st_size,
        "file_count": verified["file_count"],
        "files": records,
    }


def verify_bundle(archive_path: Path, expected_sha256: str) -> dict[str, Any]:
    require(archive_path.is_file(), "promotion bundle is missing")
    require(
        _SHA256.fullmatch(expected_sha256) is not None,
        "expected bundle SHA-256 is malformed",
    )
    require(
        _sha256_file(archive_path) == expected_sha256,
        "promotion bundle bytes do not match the pin",
    )
    with tarfile.open(archive_path, mode="r:gz") as archive:
        members = archive.getmembers()
        expected_names = {
            archive_name for _, archive_name, _ in EXPECTED_FILES
        } | {MANIFEST_NAME}
        names = [member.name for member in members]
        require(len(names) == len(set(names)), "promotion bundle has duplicates")
        require(set(names) == expected_names, "promotion bundle member set changed")
        for member in members:
            require(member.isfile(), "promotion bundle contains a non-file")
            require(
                "/" not in member.name
                and member.name not in {".", ".."}
                and not member.name.startswith("."),
                "promotion bundle member path is unsafe",
            )
        manifest_member = archive.getmember(MANIFEST_NAME)
        extracted = archive.extractfile(manifest_member)
        require(extracted is not None, "promotion manifest cannot be read")
        manifest = json.loads(extracted.read().decode("utf-8"))
        require(manifest.get("schema") == SCHEMA, "bundle schema changed")
        require(
            manifest.get("file_count") == len(EXPECTED_FILES),
            "bundle file count changed",
        )
        manifest_records = manifest.get("files")
        require(isinstance(manifest_records, list), "bundle records are missing")
        by_name = {
            record.get("archive_name"): record
            for record in manifest_records
            if isinstance(record, dict)
        }
        require(
            len(by_name) == len(EXPECTED_FILES),
            "bundle manifest records changed",
        )
        for source_name, archive_name, expected_file_sha in EXPECTED_FILES:
            member = archive.getmember(archive_name)
            extracted = archive.extractfile(member)
            require(extracted is not None, f"cannot read {archive_name}")
            content = extracted.read()
            record = by_name.get(archive_name)
            require(isinstance(record, dict), f"manifest omits {archive_name}")
            require(record.get("source") == source_name, "bundle source changed")
            require(
                record.get("sha256") == expected_file_sha,
                f"manifest digest changed: {archive_name}",
            )
            require(
                record.get("size_bytes") == len(content),
                f"manifest size changed: {archive_name}",
            )
            require(
                _sha256_bytes(content) == expected_file_sha,
                f"bundle content changed: {archive_name}",
            )
            expected_mode = 0o700 if archive_name.endswith((".py", ".sh")) else 0o600
            require(member.mode == expected_mode, f"bundle mode changed: {archive_name}")
    return {
        "status": "ok",
        "archive": str(archive_path),
        "archive_sha256": expected_sha256,
        "file_count": len(EXPECTED_FILES),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build")
    build.add_argument("--root", type=Path, default=Path.cwd())
    build.add_argument("--output", type=Path, required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--archive", type=Path, required=True)
    verify.add_argument("--expected-sha256", required=True)
    args = parser.parse_args()
    try:
        if args.command == "build":
            result = build_bundle(args.root, args.output)
        else:
            result = verify_bundle(args.archive, args.expected_sha256)
    except Exception as exc:
        print(json.dumps({
            "status": "error",
            "error": {
                "code": "PROMOTION_BUNDLE_FAILED",
                "message": str(exc),
            },
        }, sort_keys=True))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
