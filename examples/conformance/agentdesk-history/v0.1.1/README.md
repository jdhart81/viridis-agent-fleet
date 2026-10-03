# Proposed synthetic history fixture v0.1.1

Four-file, standard-library-only candidate: fixture.json, validate.py,
test_validate.py and this README. All identities, events and timestamps are
synthetic. No live service, account, credential, payment or collection is used.

Run from this directory:

```sh
python validate.py
python -m unittest -v test_validate.py
```

The stored_events array is the offline test oracle; each case has its own
explicit returned_events array. Both must be strictly ordered by ascending
positive integer sequence, with unique sequence and event_id values. The
validator rejects unsorted, duplicated or altered rows rather than sorting or
repairing them. An inconsistent reported returned_range is malformed input,
not evidence of complete coverage.

Each case's coverage_basis supplies a required inclusive sequence interval and
an expected earliest-sequence/event anchor. Modeled completeness requires the
actual returned sequence set to equal every integer in that interval exactly.
Gaps, an empty readback or extra rows yield INSUFFICIENT_COVERAGE. Neither the
oracle, supplied endpoints nor timestamps fill missing readback rows.

Complete initial history is BLOCKED; the full retry preserves original event
content, sequence and timestamp and uses a distinct run under the same trial.
Its later synthetic probe result is RECOVERED_WITH_PRIOR_BLOCKER, never a clean
first-pass completion. BLOCKED, RECOVERED_WITH_PRIOR_BLOCKER and UNRESOLVED are
fixture-local proposals; INSUFFICIENT_COVERAGE is the requested conformance
outcome. All field names and step codes are proposed, not an implemented API.

## Deterministic fixture-content hash

Parse JSON while rejecting duplicate object keys and non-finite constants.
Serialize with Python json.dumps(value, sort_keys=True, separators=(',', ':'),
ensure_ascii=False, allow_nan=False), encode as UTF-8, with no trailing newline,
then SHA-256 those bytes. Object keys are sorted recursively; array order is
preserved. This is this package's exact Python serialization convention, not
RFC 8785/JCS or a claim of cross-language canonicalization. No Unicode
normalization is performed. The pretty fixture file ends with a newline, so its
file-byte hash differs from its parsed-content hash. Source-file hashes cover
their exact bytes separately. Content hashes identify supplied artifacts; they
do not establish authenticity or independent collection.

## Limits

This checks only internal consistency of caller-supplied synthetic expected
records/readbacks and modeled coverage. Coordinated edits to both oracle and
readback cannot be detected as historical tampering without an external prior
artifact/hash. It is not a general schema validator or production client.
The fixture does not prove collector completeness, operator independence,
actual append-only storage, restart durability, idempotency, concurrent event
sequencing, metadata screening, live integration or a completed Commons trial.
e3 is an explicit simulated operator fix note; its false account-action flag is
not independence evidence. e6 completes only a synthetic probe.

DeliveryCheck boundary: supplied expected records and destination readbacks
with explicit coverage; honest, complete and correctly mapped collector
evidence remains an input assumption.
