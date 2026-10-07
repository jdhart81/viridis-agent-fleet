import importlib.util
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
GUARD_PATH = REPO_ROOT / "scripts" / "public_boundary_guard.py"
SPEC = importlib.util.spec_from_file_location("public_boundary_guard", GUARD_PATH)
assert SPEC is not None and SPEC.loader is not None
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)


@pytest.mark.parametrize(
    "path",
    [
        "deploy/service.yaml",
        "gateway/service.py",
        "runtime/service.py",
        "env/local.env",
        "production-backups/snapshot.json",
        "backups/snapshot.json",
        "package/secrets/key.txt",
    ],
)
def test_g1_blocks_hosted_service_paths(path):
    assert guard.check([path], read=lambda _: "") == [("G1", path)]


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("deploy/mcp-publish/org/server.json", []),
        ("deploy/mcp-publish/org/server.py", [("G1", "deploy/mcp-publish/org/server.py")]),
        ("deploy/mcp-publish-github/org/server.json", []),
    ],
)
def test_g1_allows_registry_manifests_but_not_python_code(path, expected):
    assert guard.check([path], read=lambda _: "") == expected


@pytest.mark.parametrize("filename", sorted(guard.SERVICE_FILES))
def test_g2_blocks_hosted_service_filenames_in_any_directory(filename):
    path = "some/nested/directory/" + filename
    assert guard.check([path], read=lambda _: "") == [("G2", path)]


@pytest.mark.parametrize(
    "text",
    [
        "sk_" + "live_" + "A" * 24,
        "rk_" + "live_" + "B" * 24,
        "whsec_" + "C" * 24,
        "-----BEGIN " + "PRIVATE KEY-----",
        "AKIA" + "0" * 16,
        "ghp_" + "D" * 36,
        "xoxb-" + "E" * 20,
    ],
)
def test_g3_detects_each_secret_pattern(text):
    assert guard.check(["safe.txt"], read=lambda _: text) == [("G3", "safe.txt")]


def test_g3_allows_test_key_near_miss():
    text = "sk_" + "test_" + "A" * 24
    assert guard.check(["safe.txt"], read=lambda _: text) == []


def test_reader_oserror_does_not_skip_path_checks():
    def unreadable(_):
        raise OSError("fixture read failed")

    assert guard.check(["gateway/unreadable.txt"], read=unreadable) == [
        ("G1", "gateway/unreadable.txt")
    ]


def test_tracked_files_are_root_relative_from_scripts(monkeypatch):
    monkeypatch.chdir(REPO_ROOT / "scripts")
    files = guard.tracked_files()
    assert "scripts/public_boundary_guard.py" in files
    assert "README.md" in files


def test_check_reads_relative_to_repo_root_from_another_directory(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    working_directory = tmp_path / "working"
    root.mkdir()
    working_directory.mkdir()
    (root / "fixture.txt").write_text("sk_" + "live_" + "Z" * 24)

    monkeypatch.setattr(guard, "REPO_ROOT", root)
    monkeypatch.chdir(working_directory)

    assert guard.check(["fixture.txt"]) == [("G3", "fixture.txt")]
