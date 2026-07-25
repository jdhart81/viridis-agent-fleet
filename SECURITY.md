# Security Policy

## Supported code

Security fixes target the current `main` branch and the live services linked
from the repository README. Historical tags, superseded manifests, and retired
deployment targets may not receive fixes.

## Report a vulnerability privately

Use GitHub's private vulnerability reporting form:

<https://github.com/jdhart81/viridis-agent-fleet/security/advisories/new>

Do not open a public issue for a suspected vulnerability. Never include private
keys, wallet seed phrases, payment signatures, API tokens, customer data, or
other secrets in a report.

Please include:

- the affected endpoint, file, commit, or manifest;
- the security impact and the boundary an attacker could cross;
- minimal reproduction steps using test data;
- sanitized evidence such as response codes, hashes, or redacted logs; and
- a suggested fix or mitigation, when available.

For payment, identity, escrow, or agent-authority findings, stop after the
minimum safe proof. Do not move real funds, access another party's data,
degrade the live service, or test destructive behavior.

## What happens next

Viridis will triage the private report, preserve the reporter conversation,
and coordinate remediation and disclosure through the GitHub advisory. A
report is not a promise of a bounty or payment.

Security evidence is scoped: a successful review or attestation covers only
the named version and tests. It is never represented as a guarantee that an
agent or service is vulnerability-free.
