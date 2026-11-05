# Releasing orc-seal to npm

This package is kept `"private": true` so that nothing publishes by accident. A release needs an owner's yes and an npm account that can publish the `orc-seal` name (the first publish claims it). Never commit an npm token, and never paste one into an issue, PR or chat.

## Ready (checked on the release-prep branch)

- [x] Name `orc-seal` is free on registry.npmjs.org (checked 2026-11-05).
- [x] Version `0.1.0` in `package.json`, `lib/sealer.js` (`VERSION`) and the CLI's `--version`; a test keeps them equal.
- [x] `package.json` has description, licence, author, homepage, repository, bugs, keywords, `engines`, `bin` and `publishConfig.access = public`.
- [x] `CHANGELOG.md` has a `0.1.0` entry.
- [x] `npm pack --dry-run` ships exactly: `LICENSE`, `README.md`, `CHANGELOG.md`, `package.json`, `index.js`, `bin/orc-seal.js`, `lib/{cli,json,orc,proxy,sealer}.js`. No tests. A test asserts this list.
- [x] JS tests and the Python parity tests pass.

## Release (the owner's step)

From a clean checkout of `main` after the PR that adds this file is merged:

```bash
cd products/orc-seal-js
npm test
npm pack --dry-run          # confirm the 11 files above
npm login                   # or an automation token in ~/.npmrc, never in the repo
```

1. Delete the line `"private": true,` from `package.json`.
2. In `CHANGELOG.md`, change `## 0.1.0 (unreleased)` to `## 0.1.0 (YYYY-MM-DD)`.
3. Commit both changes: `Release orc-seal (npm) 0.1.0`.
4. Publish and tag:

```bash
npm publish                 # publishConfig makes it public
git tag orc-seal-js-v0.1.0  # not orc-seal-v*: that prefix triggers the PyPI workflow
git push origin main orc-seal-js-v0.1.0
```

5. Check from a fresh shell:

```bash
npm view orc-seal version           # 0.1.0
npx -y orc-seal@0.1.0 --version     # 0.1.0
npx -y orc-seal badge
```

If something is wrong within 72 hours, `npm unpublish orc-seal@0.1.0` is possible, but the version number can never be reused. Prefer `npm deprecate` and a 0.1.1.

## Later, optional

A tag-triggered GitHub workflow with npm trusted publishing (OIDC) would publish with provenance and no stored token, like `publish-orc-seal.yml` does for PyPI. It changes CI, so it needs the owner's yes first.
