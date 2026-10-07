"""Build a deterministic, credential-free submission archive from explicit files."""
import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[3] / "plugins/viridis-agent-reliability"
FILES = (
    'plugin.json', 'mcp.json', '.mcp.json',
    '.codex-plugin/plugin.json', '.claude-plugin/plugin.json',
    'README.md', 'COMPATIBILITY.md', 'PRIVACY.md', 'icon.png', 'LICENSE',
    'TOOL_CONTRACT.json', 'skills/agent-reliability-check/SKILL.md',
)


def build(output, root=ROOT):
    root = Path(root).resolve()
    contents = {}
    for relative in FILES:
        source = root / relative
        if source.is_symlink() or not source.is_file():
            raise ValueError('Package file missing or symlink: ' + relative)
        if not source.resolve().is_relative_to(root):
            raise ValueError('Package file escaped root: ' + relative)
        contents[relative] = source.read_bytes()
    # Checkout/reviewer credentials and developer caches are never traversed.
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, 'w', compression=ZIP_DEFLATED) as archive:
        for relative, data in sorted(contents.items()):
            entry = ZipInfo(relative, date_time=(2026, 10, 6, 0, 0, 0))
            entry.compress_type = ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, data)
    return {'version': json.loads(contents['plugin.json'])['version'],
            'file_count': len(contents),
            'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
            'file_sha256': {name: hashlib.sha256(data).hexdigest()
                            for name, data in contents.items()},
            'submitted': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.output), indent=2))
