# Contributing to Viridis Agent Fleet

Thanks for helping. For anything larger than a small fix, open an issue first so we can agree on the approach.

## Build and test

```bash
pip install -r requirements-dev.txt
python3 run_fleet_tests.py
```

Each agent keeps its tests in its own `tests/` folder. Add or update tests when you change behavior.

## What belongs here

This repository holds the open, Apache-2.0 agents. Code for the hosted service stays out of it: `scripts/public_boundary_guard.py` checks that in CI.

## Sign your commits (DCO)

Pull requests from forks need a `Signed-off-by` line on every commit, matching the commit author's email:

    Signed-off-by: Your Name <you@example.com>

`git commit -s` adds it, and `git rebase --signoff origin/main` fixes an existing branch. Signing off
certifies the Developer Certificate of Origin 1.1 (https://developercertificate.org): you wrote the
change, or you have the right to submit it under this repository's license. The DCO check blocks
unsigned commits.

## License of contributions

Contributions are licensed under the same license as the files they change (see `LICENSE`), with no
additional terms. Don't submit work you can't license that way.

## Never commit

Credentials, API keys, private keys, `.env` files, customer or partner data, or wallet files. The secret
scan blocks known key formats. If you find a leaked secret, report it privately as described in
`SECURITY.md`.

## Names and marks

The license does not cover Viridis names, logos or certification marks. See `TRADEMARKS.md`.
