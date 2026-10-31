"""Exercise the retirement shell step without a publisher, token or network.

The pinned publisher v1.7.9 supports --yes for --all-versions. Its default
confirmation reads stdin before sending PATCH; Actions has no interactive stdin.
"""
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import textwrap


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/retire-verdigraph-mcp.yml"
STALE = "io.github.jdhart81/verdigraph-mcp"
LIVE = "io.github.jdhart81/verdigraph"


def status_step(source):
    block = source.split("      - name: Set stale listing status (R1, R3)\n", 1)[1]
    block = block.split("      - name: Verify registry state (R4)\n", 1)[0]
    return textwrap.dedent(block.split("        run: |\n", 1)[1])


def run_status_step(tmp_path, script, *, operational_failure=False):
    """Only the external executable path is redirected into an isolated fixture."""
    fixture = tmp_path / "publisher.py"
    fixture.write_text(textwrap.dedent('''\
        import json
        import os
        from pathlib import Path
        import sys

        args = sys.argv[1:]
        with open(os.environ["CALLS"], "a") as stream:
            stream.write(json.dumps(args) + "\\n")
        if (not args or args[0] != "status"
                or args[-1] != "io.github.jdhart81/verdigraph-mcp"
                or args[args.index("--status") + 1] != "deprecated"
                or "--all-versions" not in args):
            raise SystemExit("unexpected operation scope")
        # Go's flag parser stops at the positional server name.
        if "--yes" not in args[:-1] and "-y" not in args[:-1]:
            print("Continue? [y/N]", flush=True)
            if not sys.stdin.readline():
                print("Error: failed to read response: EOF", file=sys.stderr)
                raise SystemExit(2)
            raise SystemExit("fixture does not accept interactive confirmation")
        if os.environ["OPERATIONAL_FAILURE"] == "1":
            print("fixture registry unavailable", file=sys.stderr)
            raise SystemExit(7)
        Path(os.environ["MUTATION_MARKER"]).write_text("fixture-only status operation")
    '''))
    publisher = tmp_path / "publisher-stub"
    publisher.write_text(
        "#!/bin/sh\nexec " + shlex.quote(sys.executable) + " "
        + shlex.quote(str(fixture)) + ' "$@"\n'
    )
    publisher.chmod(0o700)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    sleep = bindir / "sleep"
    sleep.write_text("#!/bin/sh\nexit 0\n")
    sleep.chmod(0o700)
    calls, marker = tmp_path / "calls.jsonl", tmp_path / "fixture-operation.txt"
    script = script.replace("/tmp/mcp-publisher", shlex.quote(str(publisher)))
    # No inherited auth environment or home directory reaches the fixture.
    env = {
        "PATH": str(bindir) + os.pathsep + os.defpath,
        "NEW_STATUS": "deprecated", "STALE": STALE, "LIVE": LIVE,
        "CALLS": str(calls), "MUTATION_MARKER": str(marker),
        "OPERATIONAL_FAILURE": "1" if operational_failure else "0",
    }
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", script],
        env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=10,
    )
    records = [json.loads(line) for line in calls.read_text().splitlines()]
    return result, records, marker


def test_old_closed_stdin_path_reproduces_eof_without_status_operation(tmp_path):
    script = status_step(WORKFLOW.read_text()).replace(" --yes", "")
    result, calls, marker = run_status_step(tmp_path, script)
    assert result.returncode != 0
    assert "failed to read response: EOF" in result.stderr
    assert len(calls) == 3  # Existing retry policy is not changed by this fix.
    assert not marker.exists()


def test_bulk_status_is_noninteractive_and_keeps_deprecated_legacy_scope(tmp_path):
    result, calls, marker = run_status_step(tmp_path, status_step(WORKFLOW.read_text()))
    assert result.returncode == 0, result.stderr
    assert len(calls) == 1
    assert calls[0] == [
        "status", "--status", "deprecated", "--all-versions", "--yes",
        "--message", "Superseded by " + LIVE
        + " (https://mcp.viridisconservation.com/verdigraph/mcp)", STALE,
    ]
    assert marker.exists()
    assert "Continue?" not in result.stdout


def test_noninteractive_flag_does_not_hide_operational_failure(tmp_path):
    result, calls, marker = run_status_step(
        tmp_path, status_step(WORKFLOW.read_text()), operational_failure=True,
    )
    assert result.returncode != 0
    assert "fixture registry unavailable" in result.stderr
    assert len(calls) == 3
    assert not marker.exists()


def test_workflow_retains_scope_and_existing_safety_gates():
    source = WORKFLOW.read_text()
    assert "default: deprecated" in source
    assert "  STALE: " + STALE in source
    assert "  LIVE: " + LIVE in source
    assert "  contents: read\n  id-token: write" in source
    assert "mcp-publisher_linux_amd64.tar.gz" in source
    assert "ab128162b0616090b47cf245afe0a23f3ef08936fdce19074f5ba0a4469281ac" in source
    assert "replacement is active and answering (R1, R2)" in source
    assert "Verify registry state (R4)" in source
    step = status_step(source)
    assert "|" not in step  # No broad yes/printf confirmation pipe.
    assert "--all-versions --yes" in step
