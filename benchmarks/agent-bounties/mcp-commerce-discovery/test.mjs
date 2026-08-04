#!/usr/bin/env node

import assert from "node:assert/strict";
import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { spawnSync } from "node:child_process";

const workspace = resolve(process.argv[2] ?? ".");
const checker = join(workspace, "scripts", "check-mcp-commerce-discovery.mjs");
const extension = "https://github.com/google-a2a/a2a-x402/v0.1";

function route(agent, tool, amount) {
  return {
    agent,
    tool,
    endpoint: `https://mcp.example.test/x402/${agent}/${tool}`,
    mcp_endpoint: `https://mcp.example.test/${agent}/mcp`,
    methods: ["GET", "POST"],
    paid_execution_method: "POST",
    amount_atomic_usdc: amount,
    x402_version: 2,
    v2_enabled: true,
  };
}

const routes = [
  route("regulatory-radar", "scan_regulations", "250000"),
  route("regulatory-radar", "monitor_changes", "250000"),
  route("taxcredit-engine", "calculate_tax_credit", "2000000"),
  route("ghg-ledger", "calculate_inventory", "1000000"),
  route("quantity-takeoff", "calculate_takeoff", "500000"),
  route("disclosure-compiler", "compile_disclosure", "2000000"),
  route("hive", "solve", "5000000"),
  route("security-preflight", "security_preflight", "1000000"),
];

function validBundle() {
  return {
    "x402-catalog.json": {
      spec_version: "viridis-x402-catalog-v1",
      routes: structuredClone(routes),
    },
    "agent-card.json": {
      capabilities: {
        extensions: [{ uri: extension, required: true, params: { x402Version: 2 } }],
      },
      skills: routes.map((item) => ({
        id: `${item.agent}.${item.tool}`,
        metadata: {
          httpX402Endpoint: item.endpoint,
          amountAtomicUsdc: item.amount_atomic_usdc,
        },
      })),
    },
    "skills-index.json": {
      skills: [{ name: "viridis-paid-tools", files: ["SKILL.md"] }],
    },
  };
}

async function writeBundle(root, bundle) {
  await mkdir(root, { recursive: true });
  for (const [name, value] of Object.entries(bundle)) {
    const text = typeof value === "string" ? value : `${JSON.stringify(value)}\n`;
    await writeFile(join(root, name), text, "utf8");
  }
}

function run(args) {
  return spawnSync(process.execPath, [checker, ...args], {
    cwd: workspace,
    encoding: "utf8",
    env: { PATH: process.env.PATH ?? "" },
    timeout: 5_000,
    maxBuffer: 1_048_576,
  });
}

function expect(result, status, stdout, stderr) {
  assert.equal(result.error, undefined, result.error?.message);
  assert.equal(result.signal, null);
  assert.equal(result.status, status);
  assert.equal(result.stdout, stdout);
  assert.equal(result.stderr, stderr);
}

const temp = await mkdtemp(join(tmpdir(), "mcp-commerce-discovery-"));
try {
  expect(
    run([]),
    64,
    "",
    "usage: node scripts/check-mcp-commerce-discovery.mjs <bundle-directory>\n",
  );

  const valid = join(temp, "valid");
  await writeBundle(valid, validBundle());
  expect(
    run([valid]),
    0,
    '{"a2a_skills":8,"buyer_skills":1,"routes":8,"status":"ok"}\n',
    "",
  );

  const missing = join(temp, "missing");
  const missingBundle = validBundle();
  delete missingBundle["agent-card.json"];
  await writeBundle(missing, missingBundle);
  expect(
    run([missing]),
    2,
    "",
    '{"status":"error","code":"bundle_read_error","file":"agent-card.json","message":"required regular file is missing or unreadable"}\n',
  );

  const invalidJson = join(temp, "invalid-json");
  const invalidJsonBundle = validBundle();
  invalidJsonBundle["x402-catalog.json"] = "{not json}\n";
  await writeBundle(invalidJson, invalidJsonBundle);
  expect(
    run([invalidJson]),
    2,
    "",
    '{"status":"error","code":"invalid_json","file":"x402-catalog.json","message":"file is not valid JSON"}\n',
  );

  const catalog = join(temp, "catalog-contract");
  const catalogBundle = validBundle();
  catalogBundle["x402-catalog.json"].routes[0].amount_atomic_usdc = "0";
  await writeBundle(catalog, catalogBundle);
  expect(
    run([catalog]),
    1,
    "",
    '{"status":"error","code":"catalog_contract","file":"x402-catalog.json","message":"routes must satisfy the eight-route x402 v2 contract"}\n',
  );

  const card = join(temp, "card-contract");
  const cardBundle = validBundle();
  cardBundle["agent-card.json"].capabilities.extensions = [];
  await writeBundle(card, cardBundle);
  expect(
    run([card]),
    1,
    "",
    '{"status":"error","code":"card_contract","file":"agent-card.json","message":"card must expose eight unique skills and the required x402 extension"}\n',
  );

  const mismatch = join(temp, "surface-mismatch");
  const mismatchBundle = validBundle();
  mismatchBundle["agent-card.json"].skills[3].metadata.amountAtomicUsdc = "999";
  await writeBundle(mismatch, mismatchBundle);
  expect(
    run([mismatch]),
    1,
    "",
    '{"status":"error","code":"surface_mismatch","file":"agent-card.json","message":"A2A skill endpoints and amounts must match the x402 catalog"}\n',
  );

  const skillIndex = join(temp, "skill-index-contract");
  const skillIndexBundle = validBundle();
  skillIndexBundle["skills-index.json"].skills[0].files = ["README.md"];
  await writeBundle(skillIndex, skillIndexBundle);
  expect(
    run([skillIndex]),
    1,
    "",
    '{"status":"error","code":"skill_index_contract","file":"skills-index.json","message":"index must expose only viridis-paid-tools with SKILL.md"}\n',
  );

  process.stdout.write("benchmark ok\n");
} finally {
  await rm(temp, { recursive: true, force: true });
}
