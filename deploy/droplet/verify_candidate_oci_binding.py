#!/usr/bin/env python3
"""Verify a frozen Docker/OCI archive's manifest-to-config identity binding."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tarfile
from pathlib import Path
from typing import Any


class BindingFailure(RuntimeError):
    """The archive does not match the pinned OCI identity."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise BindingFailure(message)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_member(archive: tarfile.TarFile, name: str) -> tuple[bytes, Any]:
    try:
        member = archive.getmember(name)
    except KeyError as exc:
        raise BindingFailure(f"archive member is missing: {name}") from exc
    require(member.isfile(), f"archive member is not a file: {name}")
    handle = archive.extractfile(member)
    require(handle is not None, f"archive member is unreadable: {name}")
    raw = handle.read()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise BindingFailure(f"archive member is not valid JSON: {name}") from exc
    return raw, payload


def verify_binding(
    archive_path: Path,
    *,
    expected_archive_sha256: str,
    expected_size_bytes: int,
    expected_manifest_digest: str,
    expected_config_digest: str,
    expected_tag: str,
) -> dict[str, Any]:
    require(archive_path.is_file(), "candidate archive is missing")
    require(
        archive_path.stat().st_size == expected_size_bytes,
        "candidate archive size mismatch",
    )
    require(
        _file_sha256(archive_path) == expected_archive_sha256,
        "candidate archive SHA-256 mismatch",
    )
    require(
        expected_manifest_digest.startswith("sha256:")
        and len(expected_manifest_digest) == 71,
        "expected manifest digest is malformed",
    )
    require(
        expected_config_digest.startswith("sha256:")
        and len(expected_config_digest) == 71,
        "expected config digest is malformed",
    )
    manifest_hex = expected_manifest_digest.removeprefix("sha256:")
    config_hex = expected_config_digest.removeprefix("sha256:")
    manifest_member = f"blobs/sha256/{manifest_hex}"
    config_member = f"blobs/sha256/{config_hex}"

    try:
        with tarfile.open(archive_path, "r:gz") as archive:
            _, index = _json_member(archive, "index.json")
            _, legacy = _json_member(archive, "manifest.json")
            manifest_raw, manifest = _json_member(archive, manifest_member)
            config_raw, config = _json_member(archive, config_member)
    except (tarfile.TarError, OSError) as exc:
        raise BindingFailure("candidate archive is not a valid gzip tar") from exc

    require(isinstance(index, dict), "OCI index is not an object")
    require(index.get("schemaVersion") == 2, "OCI index schema changed")
    descriptors = index.get("manifests")
    require(
        isinstance(descriptors, list) and len(descriptors) == 1,
        "OCI index must contain exactly one manifest",
    )
    descriptor = descriptors[0]
    require(
        isinstance(descriptor, dict)
        and descriptor.get("digest") == expected_manifest_digest,
        "OCI index manifest digest mismatch",
    )
    require(
        descriptor.get("mediaType")
        == "application/vnd.oci.image.manifest.v1+json",
        "OCI index manifest media type changed",
    )
    require(
        _sha256(manifest_raw) == manifest_hex,
        "OCI manifest bytes do not match their digest",
    )
    require(
        isinstance(manifest, dict)
        and manifest.get("mediaType")
        == "application/vnd.oci.image.manifest.v1+json",
        "OCI manifest media type changed",
    )
    config_descriptor = manifest.get("config")
    require(
        isinstance(config_descriptor, dict)
        and config_descriptor.get("digest") == expected_config_digest,
        "OCI manifest config digest mismatch",
    )
    require(
        config_descriptor.get("mediaType")
        == "application/vnd.oci.image.config.v1+json",
        "OCI config media type changed",
    )
    require(
        int(config_descriptor.get("size", -1)) == len(config_raw),
        "OCI config size mismatch",
    )
    require(
        _sha256(config_raw) == config_hex,
        "OCI config bytes do not match their digest",
    )
    require(isinstance(config, dict), "OCI config is not an object")
    layers = manifest.get("layers")
    require(
        isinstance(layers, list) and len(layers) > 0,
        "OCI manifest has no filesystem layers",
    )

    require(
        isinstance(legacy, list) and len(legacy) == 1,
        "Docker manifest must contain exactly one image",
    )
    legacy_image = legacy[0]
    require(isinstance(legacy_image, dict), "Docker manifest entry changed")
    require(
        legacy_image.get("Config") == config_member,
        "Docker manifest config path mismatch",
    )
    require(
        legacy_image.get("RepoTags") == [expected_tag],
        "Docker manifest tag mismatch",
    )

    return {
        "status": "ok",
        "archive": str(archive_path),
        "archive_sha256": expected_archive_sha256,
        "archive_size_bytes": expected_size_bytes,
        "oci_manifest_digest": expected_manifest_digest,
        "oci_config_digest": expected_config_digest,
        "tag": expected_tag,
        "layer_count": len(layers),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--archive-sha256", required=True)
    parser.add_argument("--size-bytes", type=int, required=True)
    parser.add_argument("--manifest-digest", required=True)
    parser.add_argument("--config-digest", required=True)
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()
    try:
        result = verify_binding(
            args.archive,
            expected_archive_sha256=args.archive_sha256,
            expected_size_bytes=args.size_bytes,
            expected_manifest_digest=args.manifest_digest,
            expected_config_digest=args.config_digest,
            expected_tag=args.tag,
        )
    except Exception as exc:
        print(json.dumps({
            "status": "failed",
            "error_type": type(exc).__name__,
            "message": str(exc),
        }, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
