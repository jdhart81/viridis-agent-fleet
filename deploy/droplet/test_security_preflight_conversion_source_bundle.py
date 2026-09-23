import io
import json
from pathlib import Path
import tarfile

import pytest

from deploy.droplet import security_preflight_conversion_source_bundle as bundle


ROOT = Path(bundle.__file__).resolve().parents[2]


def test_bundle_is_deterministic_exact_and_self_verifying(tmp_path):
    first = bundle.build_bundle(ROOT, tmp_path / "first.tar.gz")
    second = bundle.build_bundle(ROOT, tmp_path / "second.tar.gz")
    assert first["archive_sha256"] == second["archive_sha256"]
    # Receipt dated 2026-08-06: reproduce the original packet byte for byte.
    assert first["archive_sha256"] == (
        "08f17ac2c82aedaa6327cc32a32d134b7d508023691233a053cd7401f824ee27")
    assert first["size_bytes"] == second["size_bytes"]
    assert first["file_count"] == len(bundle.EXPECTED_FILES) == 13
    assert bundle.verify_bundle(
        Path(first["archive"]), first["archive_sha256"]
    )["status"] == "ok"


def test_manifest_preserves_external_authorization_gates(tmp_path):
    result = bundle.build_bundle(ROOT, tmp_path / "bundle.tar.gz")
    with tarfile.open(result["archive"], "r:gz") as archive:
        manifest_file = archive.extractfile(bundle.MANIFEST_NAME)
        assert manifest_file is not None
        manifest = json.load(manifest_file)
    assert manifest["classification"] == \
        "source_candidate_not_published_not_production"
    assert manifest["authorization"] == {
        "github_publication": False,
        "outreach": False,
        "payment": False,
        "production_promotion": False,
    }


def test_bundle_carries_production_public_evidence_and_distinct_history(tmp_path):
    result = bundle.build_bundle(ROOT, tmp_path / "bundle.tar.gz")
    with tarfile.open(result["archive"], "r:gz") as archive:
        names = set(archive.getnames())
        assert "production/agents.html" in names
        assert "production/quickstart.html" in names
        assert "public/security-preflight-buyer-path-ee2b479.patch" in names
        assert "controls/gateway_runtime_parity_hardened_20260804.py" in names
        assert (
            "history/regulatory-radar-gateway-wedge-20260726/"
            "gateway_runtime_parity.py"
        ) in names


def test_build_refuses_source_drift(tmp_path, monkeypatch):
    source_name, archive_name, _ = bundle.EXPECTED_FILES[0]
    monkeypatch.setattr(
        bundle,
        "EXPECTED_FILES",
        ((source_name, archive_name, "0" * 64),),
    )
    with pytest.raises(bundle.BundleFailure, match="hash changed"):
        bundle.build_bundle(ROOT, tmp_path / "bundle.tar.gz")


def test_verify_rejects_unsafe_or_duplicate_archive(tmp_path):
    archive_path = tmp_path / "unsafe.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        for name in ("../escape", "../escape"):
            content = b"x"
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    digest = bundle._sha256_file(archive_path)
    with pytest.raises(bundle.BundleFailure, match="duplicate|unsafe"):
        bundle.verify_bundle(archive_path, digest)


def test_build_refuses_overwrite(tmp_path):
    output = tmp_path / "bundle.tar.gz"
    output.write_bytes(b"keep")
    with pytest.raises(bundle.BundleFailure, match="overwrite"):
        bundle.build_bundle(ROOT, output)
    assert output.read_bytes() == b"keep"
