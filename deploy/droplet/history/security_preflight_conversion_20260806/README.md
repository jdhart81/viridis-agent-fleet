# Reproducible August Security Preflight packets

These `.source` files are recovered verbatim from the sealed August 6 source
and candidate archives. The archive hashes are recorded in the original
deployment receipts and in `provenance.json`. Both builders now reproduce
those original archive hashes exactly, independent of today's serving files.

The former builders mixed August package metadata with later source hashes.
The corrected pins come from the original sealed manifests, not current
serving files. The archives and original deployment receipts are unchanged.
The `.source` extension prevents historical test files from being collected
as current release tests. These files are evidence, not serving code.
