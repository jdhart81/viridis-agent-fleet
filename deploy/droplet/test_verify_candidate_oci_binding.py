import gzip
import hashlib
import io
import json
import tarfile

import pytest

from deploy.droplet.verify_candidate_oci_binding import (
    BindingFailure,
    verify_binding,
)


TAG = "viridis-stable:test-candidate"


def stable(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def build_archive(tmp_path, *, config_override=None, tag=TAG):
    config = stable(config_override or {"architecture": "amd64", "os": "linux"})
    config_hex = hashlib.sha256(config).hexdigest()
    config_digest = f"sha256:{config_hex}"
    layer = b"layer fixture"
    layer_hex = hashlib.sha256(layer).hexdigest()
    manifest = stable({
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.manifest.v1+json",
        "config": {
            "mediaType": "application/vnd.oci.image.config.v1+json",
            "digest": config_digest,
            "size": len(config),
        },
        "layers": [{
            "mediaType": "application/vnd.oci.image.layer.v1.tar",
            "digest": f"sha256:{layer_hex}",
            "size": len(layer),
        }],
    })
    manifest_hex = hashlib.sha256(manifest).hexdigest()
    manifest_digest = f"sha256:{manifest_hex}"
    index = stable({
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.index.v1+json",
        "manifests": [{
            "mediaType": "application/vnd.oci.image.manifest.v1+json",
            "digest": manifest_digest,
            "size": len(manifest),
        }],
    })
    legacy = stable([{
        "Config": f"blobs/sha256/{config_hex}",
        "RepoTags": [tag],
        "Layers": [f"blobs/sha256/{layer_hex}"],
    }])
    members = {
        "index.json": index,
        "manifest.json": legacy,
        f"blobs/sha256/{manifest_hex}": manifest,
        f"blobs/sha256/{config_hex}": config,
        f"blobs/sha256/{layer_hex}": layer,
    }
    raw_tar = io.BytesIO()
    with tarfile.open(fileobj=raw_tar, mode="w") as archive:
        for name, raw in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(raw)
            info.mtime = 0
            archive.addfile(info, io.BytesIO(raw))
    path = tmp_path / "candidate.tar.gz"
    path.write_bytes(gzip.compress(raw_tar.getvalue(), mtime=0))
    return path, manifest_digest, config_digest


def verify_fixture(path, manifest_digest, config_digest, *, tag=TAG):
    return verify_binding(
        path,
        expected_archive_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        expected_size_bytes=path.stat().st_size,
        expected_manifest_digest=manifest_digest,
        expected_config_digest=config_digest,
        expected_tag=tag,
    )


def test_accepts_exact_manifest_to_config_binding(tmp_path):
    path, manifest_digest, config_digest = build_archive(tmp_path)
    result = verify_fixture(path, manifest_digest, config_digest)
    assert result["status"] == "ok"
    assert result["layer_count"] == 1


def test_refuses_archive_digest_mismatch(tmp_path):
    path, manifest_digest, config_digest = build_archive(tmp_path)
    with pytest.raises(BindingFailure, match="archive SHA-256"):
        verify_binding(
            path,
            expected_archive_sha256="0" * 64,
            expected_size_bytes=path.stat().st_size,
            expected_manifest_digest=manifest_digest,
            expected_config_digest=config_digest,
            expected_tag=TAG,
        )


def test_refuses_manifest_digest_mismatch(tmp_path):
    path, _, config_digest = build_archive(tmp_path)
    with pytest.raises(BindingFailure, match="archive member is missing"):
        verify_fixture(path, "sha256:" + "0" * 64, config_digest)


def test_refuses_config_digest_mismatch(tmp_path):
    path, manifest_digest, _ = build_archive(tmp_path)
    with pytest.raises(BindingFailure, match="archive member is missing"):
        verify_fixture(path, manifest_digest, "sha256:" + "0" * 64)


def test_refuses_tag_mismatch(tmp_path):
    path, manifest_digest, config_digest = build_archive(tmp_path)
    with pytest.raises(BindingFailure, match="tag mismatch"):
        verify_fixture(
            path, manifest_digest, config_digest, tag="viridis-stable:wrong"
        )
