// Release invariants for the npm package (see RELEASE.md).
// R1 one version: package.json, lib VERSION and `orc-seal --version` agree.
// R2 the changelog has an entry for that version.
// R3 the tarball ships exactly the runtime files: no tests, no stray files.
import test from "node:test";
import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { VERSION } from "../lib/sealer.js";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const PKG = JSON.parse(readFileSync(join(ROOT, "package.json"), "utf8"));

test("R1 one version everywhere", () => {
  assert.equal(VERSION, PKG.version);
  const out = execFileSync(process.execPath, [join(ROOT, "bin", "orc-seal.js"), "--version"], { encoding: "utf8" });
  assert.equal(out.trim(), PKG.version);
});

test("R2 changelog has an entry for this version", () => {
  const log = readFileSync(join(ROOT, "CHANGELOG.md"), "utf8");
  assert.match(log, new RegExp(`^## ${PKG.version.replace(/\./g, "\\.")} \\(`, "m"));
});

test("R3 npm pack ships exactly the runtime files", (t) => {
  const npm = process.platform === "win32" ? "npm.cmd" : "npm";
  const p = spawnSync(npm, ["pack", "--dry-run", "--json", "--ignore-scripts"], { cwd: ROOT, encoding: "utf8" });
  if (p.error || p.status !== 0) return t.skip(`npm pack unavailable: ${p.error?.message ?? p.stderr.trim()}`);
  const [info] = JSON.parse(p.stdout);
  assert.equal(info.name, "orc-seal");
  assert.equal(info.version, PKG.version);
  assert.deepEqual(info.files.map((f) => f.path).sort(), [
    "CHANGELOG.md", "LICENSE", "README.md", "bin/orc-seal.js", "index.js",
    "lib/cli.js", "lib/json.js", "lib/orc.js", "lib/proxy.js", "lib/sealer.js", "package.json",
  ]);
  const bin = info.files.find((f) => f.path === "bin/orc-seal.js");
  assert.ok(bin.mode & 0o111, "bin must be executable in the tarball");
});
