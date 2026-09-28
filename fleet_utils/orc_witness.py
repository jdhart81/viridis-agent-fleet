"""Portable verification for the tamper-evident, publicly witnessed ORC log."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re

ZERO = '0' * 64

def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()

def merkle(leaves):
    level = list(leaves)
    if not level:
        return sha('')
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [sha(level[i] + level[i+1]) for i in range(0, len(level), 2)]
    return level[0]

def root_hash(previous, tree, hour, count):
    return sha(previous + tree + hour + str(count))

def inclusion(leaves, index):
    level = list(leaves); path = []
    if not 0 <= index < len(level):
        raise ValueError('leaf index out of range')
    while len(level) > 1:
        if len(level) % 2: level.append(level[-1])
        sibling = index ^ 1
        path.append({'side': 'left' if sibling < index else 'right', 'hash': level[sibling]})
        index //= 2
        level = [sha(level[i] + level[i+1]) for i in range(0, len(level), 2)]
    return path

def valid_root(root):
    try:
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}', root['hour']): return False
        if type(root['count']) is not int or root['count'] < 0: return False
        if any(not re.fullmatch('[0-9a-f]{64}', root[k]) for k in ('prev_root', 'merkle_root', 'root')): return False
        return root['root'] == root_hash(root['prev_root'], root['merkle_root'], root['hour'], root['count'])
    except (KeyError, TypeError): return False

def verify_proof(proof, witnessed_root):
    """A proof binds to the independently retrieved witness, not its own root."""
    try:
        if not valid_root(witnessed_root) or proof['hour'] != witnessed_root['hour']: return False
        index = proof['index']; count = witnessed_root['count']
        if type(index) is not int or not 0 <= index < count: return False
        value = proof['commitment']
        if not re.fullmatch('[0-9a-f]{64}', value): return False
        steps = iter(proof['path'])
        while count > 1:
            step = next(steps)
            if step['side'] != ('left' if index % 2 else 'right'): return False
            sibling = step['hash']
            if not re.fullmatch('[0-9a-f]{64}', sibling): return False
            if count % 2 and index == count-1 and sibling != value: return False
            value = sha(sibling + value) if index % 2 else sha(value + sibling)
            index //= 2; count = (count+1)//2
        if next(steps, None) is not None: return False
        return value == witnessed_root['merkle_root']
    except (KeyError, TypeError, StopIteration, ValueError): return False

def save_witness(root, directory):
    """Never overwrite an existing witness, including a conflicting root."""
    if not valid_root(root): raise ValueError('invalid root')
    hour = root['hour']; target = Path(directory) / (hour.replace('-', '/').replace('T', '/') + '.json')
    payload = json.dumps(root, sort_keys=True, separators=(',', ':')) + '\n'
    if target.exists():
        if json.loads(target.read_text()) != root: raise ValueError('witness conflict')
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('x') as f: f.write(payload)
    return True

def main():
    import argparse
    import urllib.request
    import urllib.error
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='https://mcp.viridisconservation.com/orc/v0/roots/latest')
    parser.add_argument('--directory', default='orc-roots')
    args = parser.parse_args()
    try:
        with urllib.request.urlopen(args.url, timeout=30) as response:
            body = response.read(65537)
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
        print('no root published')
        return 0
    if len(body) > 65536: raise ValueError('root response too large')
    print('new' if save_witness(json.loads(body), args.directory) else 'already witnessed')


if __name__ == "__main__":
    raise SystemExit(main())
