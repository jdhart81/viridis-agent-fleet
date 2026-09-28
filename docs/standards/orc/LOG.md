# Tamper-evident, publicly witnessed receipt log

The log records digest-level seal metadata, never tool arguments or outputs. A public witness makes later rewrites detectable. Operator control, witness outages and missing hourly observations remain limitations. A deployed endpoint alone is not evidence that a witness commit has landed.

ISSUED means issuer binding only; it is not evidence of payment, correctness, validation, or buyer-confirmed usefulness. Thermo describes modeled energy per sealed result. Only external issuers count as adoption; viridis and related counts stay separate.

## Row and root method v1

Rows have increasing seq, commitment, digest, issuer_id, issuer_class, profile, agent, tool, registered_at, prev_hash and row_hash, plus bounded digest-level registry metadata. The previous hash starts at 64 zeroes. row_hash is SHA-256 of the UTF-8 previous hex hash concatenated with ORC canonical JSON of every row field except row_hash. Metadata is covered too. Existing records are imported once; their original issue time remains in metadata while registered_at is the import time. This prevents insertion into a closed hour.

An hour is UTC YYYY-MM-DDTHH. Leaves are commitment hex strings in seq order. Pair nodes hash the UTF-8 concatenation of the two hex strings; odd levels duplicate the last node. An empty tree is SHA-256 of the empty string. root is SHA-256 of prev_root + merkle_root + hour + decimal count, all UTF-8. Only completed hours are finalized. Stored roots are never replaced. A proof identifies its leaf index and left/right siblings.

Fetch /orc/v0/proof/COMMITMENT and obtain the hour's JSON from this repository's orc-roots/YYYY/MM/DD/HH.json at a witness commit you trust. Run `fleet_utils.orc_witness.verify_proof(proof, witnessed_root)`; it checks the leaf, path, index, count and root binding. Verify the commit history and root predecessor links separately. Do not substitute a root supplied by the proof server for an independent witness.

The hourly workflow uses a public GET and the repository's own GITHUB_TOKEN. It needs no production credentials. It refuses to overwrite a different witness at the same path. Scheduling delays can leave gaps; the latest-only collector does not claim complete historical coverage. Review GitHub run and commit history for actual witness availability.

/verify displays Viridis and outside issuer totals separately; related issuers are disclosed separately in stats and never folded into adoption. Roots and proofs establish log inclusion, not payment or correctness.

Witness files are committed only to the dedicated `orc-witness` branch, created from `main` when absent. Main does not receive hourly bot commits. Before the log publishes its first root, HTTP 404 is a successful no-op; other fetch errors fail.
