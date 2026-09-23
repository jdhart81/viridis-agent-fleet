"""Release manifests must never hash or enumerate known live credential files."""
from candidate_file_manifest import RELEASE_EXCLUDES, build_manifest


def test_known_secret_paths_are_excluded_by_default(tmp_path):
    private = tmp_path / "Agent harvest " / "secrets" / "dummy.txt"
    private.parent.mkdir(parents=True)
    private.write_text("test fixture")
    backup = (tmp_path / "production-backups" / "2026-08-06" / "snapshot"
              / "production-after-stage.json")
    backup.parent.mkdir(parents=True)
    backup.write_text("test fixture")
    public = tmp_path / "public.txt"
    public.write_text("test fixture")

    result = build_manifest(tmp_path, set())
    assert result["file_count"] == 1
    assert result["excluded"] == sorted(RELEASE_EXCLUDES)
