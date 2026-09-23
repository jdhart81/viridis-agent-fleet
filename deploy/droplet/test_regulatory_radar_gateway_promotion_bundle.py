import io
import json
from pathlib import Path
import tarfile

import pytest

from deploy.droplet import regulatory_radar_gateway_promotion_bundle as bundle


ROOT = Path(bundle.__file__).resolve().parents[2]


def test_build_is_deterministic_and_self_verifying(tmp_path):
    first = bundle.build_bundle(ROOT, tmp_path / "first.tar.gz")
    second = bundle.build_bundle(ROOT, tmp_path / "second.tar.gz")
    assert first["archive_sha256"] == second["archive_sha256"]
    assert first["size_bytes"] == second["size_bytes"]
    assert first["file_count"] == 6
    assert bundle.verify_bundle(
        tmp_path / "first.tar.gz",
        first["archive_sha256"],
    )["status"] == "ok"


def test_bundle_contains_only_six_files_and_manifest(tmp_path):
    result = bundle.build_bundle(ROOT, tmp_path / "bundle.tar.gz")
    with tarfile.open(result["archive"], "r:gz") as archive:
        assert set(archive.getnames()) == {
            name for _, name, _ in bundle.EXPECTED_FILES
        } | {bundle.MANIFEST_NAME}


def test_manifest_matches_every_pinned_source(tmp_path):
    result = bundle.build_bundle(ROOT, tmp_path / "bundle.tar.gz")
    with tarfile.open(result["archive"], "r:gz") as archive:
        manifest_file = archive.extractfile(bundle.MANIFEST_NAME)
        assert manifest_file is not None
        manifest = json.load(manifest_file)
    assert manifest["schema"] == bundle.SCHEMA
    assert manifest["file_count"] == 6
    assert {
        item["sha256"] for item in manifest["files"]
    } == {
        digest for _, _, digest in bundle.EXPECTED_FILES
    }


def test_build_refuses_source_hash_drift(tmp_path, monkeypatch):
    source_name, archive_name, _ = bundle.EXPECTED_FILES[0]
    monkeypatch.setattr(
        bundle,
        "EXPECTED_FILES",
        ((
            source_name,
            archive_name,
            "0" * 64,
        ),),
    )
    with pytest.raises(bundle.BundleFailure, match="hash changed"):
        bundle.build_bundle(ROOT, tmp_path / "bundle.tar.gz")


def test_build_refuses_overwrite(tmp_path):
    output = tmp_path / "bundle.tar.gz"
    output.write_bytes(b"keep")
    with pytest.raises(bundle.BundleFailure, match="overwrite"):
        bundle.build_bundle(ROOT, output)
    assert output.read_bytes() == b"keep"


def test_verify_rejects_archive_byte_tamper(tmp_path):
    result = bundle.build_bundle(ROOT, tmp_path / "bundle.tar.gz")
    with Path(result["archive"]).open("ab") as handle:
        handle.write(b"tamper")
    with pytest.raises(bundle.BundleFailure, match="bytes"):
        bundle.verify_bundle(
            Path(result["archive"]),
            result["archive_sha256"],
        )


def _unsafe_archive(path: Path, *, duplicate: bool) -> str:
    with tarfile.open(path, "w:gz") as archive:
        names = ["../escape"] if not duplicate else ["same", "same"]
        for name in names:
            content = b"x"
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    return bundle._sha256_file(path)


def test_verify_rejects_unsafe_member_path(tmp_path):
    archive = tmp_path / "unsafe.tar.gz"
    digest = _unsafe_archive(archive, duplicate=False)
    with pytest.raises(bundle.BundleFailure, match="member set|unsafe"):
        bundle.verify_bundle(archive, digest)


def test_verify_rejects_duplicate_members(tmp_path):
    archive = tmp_path / "duplicate.tar.gz"
    digest = _unsafe_archive(archive, duplicate=True)
    with pytest.raises(bundle.BundleFailure, match="duplicates"):
        bundle.verify_bundle(archive, digest)
