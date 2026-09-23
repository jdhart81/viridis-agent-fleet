#!/usr/bin/env python3
"""Rebuild the two-link correction using source already on the same server."""
import hashlib,io,json,os,tarfile
from pathlib import Path
ROOT=Path('/home/deploy/releases/17afb0b4e90b-security-domain')
ARCHIVE=Path('/home/deploy/releases/926cd1a7a55b-agent-discovery/source.tar.gz')
ARCHIVE_SHA='8ba0c5bb4d1ba6431ee5e1eb46252967b3b00175baa3a75fc540ad1eaa1a265b'
BASE_TREE='0bdca7f6b22eff6dc7886b1a9a9018d4992bb63a8eb8a6c23d806a3b7baf4ea7'
TARGET_TREE='f28515f9b2b07608ea91f1e51b968a48a247a9de332b9c37fc67772fa4dcbaae'
COMMIT='17afb0b4e90bd40c5cbe8748faf1bac40e972462'

def digest_records(records):return hashlib.sha256(json.dumps(sorted(records),separators=(',',':')).encode()).hexdigest()
def archive_tree(tar):
 records=[]
 for m in tar.getmembers():
  if m.isdir():continue
  assert m.isfile() or m.issym()
  contents=tar.extractfile(m).read() if m.isfile() else m.linkname.encode()
  records.append([m.name,(0o755 if m.mode & 0o111 else 0o644) if m.isfile() else 0o777,'file' if m.isfile() else 'symlink',hashlib.sha256(contents).hexdigest()])
 return digest_records(records)
def folder_tree(root):
 records=[]
 for p in root.rglob('*'):
  if p.is_dir():continue
  kind='symlink' if p.is_symlink() else 'file'
  contents=os.readlink(p).encode() if p.is_symlink() else p.read_bytes()
  records.append([str(p.relative_to(root)),0o777 if p.is_symlink() else (0o755 if p.stat().st_mode & 0o111 else 0o644),kind,hashlib.sha256(contents).hexdigest()])
 return digest_records(records)
def main():
 os.umask(0o077)
 assert hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()==ARCHIVE_SHA
 source=ROOT/'source';source.mkdir(parents=True,exist_ok=True)
 populated=any(source.iterdir())
 with tarfile.open(ARCHIVE) as tar:
  assert archive_tree(tar)==BASE_TREE
  for m in tar.getmembers():assert not Path(m.name).is_absolute() and '..' not in Path(m.name).parts
  if not populated:tar.extractall(source,filter='data')
 assert folder_tree(source)==BASE_TREE
 for rel in ['src/components/PublicNav.tsx','src/app/developers/page.tsx']:
  p=source/rel;s=p.read_text();assert 'https://mcp.viridisconservation.com/security-preflight' in s
  s=s.replace('https://mcp.viridisconservation.com/security-preflight','https://mcp.viridis-security.com/security-preflight')
  s=s.replace('https://mcp.viridisconservation.com/x402/catalog','https://mcp.viridis-security.com/security-preflight/service.json').replace('Read the agent service catalog','Read the Preflight service contract')
  p.write_text(s)
 assert folder_tree(source)==TARGET_TREE,'Reconstructed tree must match the committed source exactly'
 with tarfile.open(ROOT/'source.tar.gz','w:gz') as tar:
  for p in sorted(source.rglob('*')):tar.add(p,arcname=str(p.relative_to(source)),recursive=False)
 evidence={'status':'EXACT_COMMITTED_TREE_RECONSTRUCTED','commit':COMMIT,'base_archive_sha256':ARCHIVE_SHA,'base_tree_digest':BASE_TREE,'candidate_tree_digest':TARGET_TREE,'source_exported':False,'source_origin':'existing release archive on this same host'}
 (ROOT/'source-reconstruction.json').write_text(json.dumps(evidence,indent=2)+'\n')
 print(json.dumps(evidence))
if __name__=='__main__':main()
