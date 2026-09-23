import json
from pathlib import Path
import tarfile

import pytest

from deploy.droplet import security_preflight_conversion_candidate_bundle as bundle


ROOT = Path(bundle.__file__).resolve().parents[2]


def test_candidate_bundle_is_deterministic_and_self_verifying(tmp_path):
    first = bundle.build_bundle(ROOT, tmp_path / "first.tar.gz")
    second = bundle.build_bundle(ROOT, tmp_path / "second.tar.gz")
    assert first["archive_sha256"] == second["archive_sha256"]
    assert first["archive_sha256"] == (
        "45d19d930bc2736aad562ef780cddf6d13efa745e26f83687413d8dd4d3f0db7")
    assert first["file_count"] == len(bundle.EXPECTED_FILES) == 6
    assert bundle.verify_bundle(
        Path(first["archive"]), first["archive_sha256"]
    )["status"] == "ok"


def test_candidate_manifest_pins_live_backup_and_production_hold(tmp_path):
    result = bundle.build_bundle(ROOT, tmp_path / "bundle.tar.gz")
    with tarfile.open(result["archive"], "r:gz") as archive:
        manifest_file = archive.extractfile(bundle.MANIFEST_NAME)
        assert manifest_file is not None
        manifest = json.load(manifest_file)
    assert manifest["classification"] == \
        "non_serving_candidate_transport_not_authorization"
    assert manifest["expected_live_image"].startswith("sha256:4d465097")
    assert manifest["expected_backup_sha256"].startswith("9f70148d")
    assert manifest["production_promotion_authorized"] is False


def test_candidate_bundle_refuses_source_drift(tmp_path, monkeypatch):
    source_name, archive_name, _ = bundle.EXPECTED_FILES[0]
    monkeypatch.setattr(
        bundle, "EXPECTED_FILES", ((source_name, archive_name, "0" * 64),)
    )
    with pytest.raises(bundle.BundleFailure, match="hash changed"):
        bundle.build_bundle(ROOT, tmp_path / "bundle.tar.gz")


def test_candidate_bundle_refuses_overwrite(tmp_path):
    output = tmp_path / "bundle.tar.gz"
    output.write_bytes(b"keep")
    with pytest.raises(bundle.BundleFailure, match="overwrite"):
        bundle.build_bundle(ROOT, output)
    assert output.read_bytes() == b"keep"
