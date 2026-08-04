#!/usr/bin/env node

const DEFAULT_BASE_URL = "https://payanagent.com";
const DEFAULT_MAX_USD = 0.01;
const DEFAULT_EXCLUDED_SELLER = "j5778erynrcpbmxpd9y5bj3t998btdbk";
const EXECUTION_TOKEN = "I_ACCEPT_ONE_X402_PAYMENT";

export function parseToolResult(result) {
  if (!result || result.isError) {
    throw new Error("MCP tool returned an error");
  }
  const text = (result.content ?? [])
    .filter((item) => item?.type === "text" && typeof item.text === "string")
    .map((item) => item.text)
    .join("\n");
  if (!text) throw new Error("MCP tool returned no text payload");
  try {
    return JSON.parse(text);
  } catch (error) {
    throw new Error(`MCP tool returned invalid JSON: ${error.message}`);
  }
}

function priceUsd(offer) {
  const exact = Number(offer?.priceUsd);
  if (Number.isFinite(exact)) return exact;
  const cents = Number(offer?.priceCents);
  return Number.isFinite(cents) ? cents / 100 : Number.NaN;
}

export function chooseOffer(
  discovery,
  {
    maxUsd = DEFAULT_MAX_USD,
    preferredOfferId,
    excludeSellerId = DEFAULT_EXCLUDED_SELLER,
  } = {},
) {
  if (!Number.isFinite(maxUsd) || maxUsd <= 0) {
    throw new Error("maxUsd must be a positive finite number");
  }
  const candidates = (Array.isArray(discovery?.offers) ? discovery.offers : [])
    .filter((offer) => typeof offer?._id === "string" && offer._id)
    .filter((offer) => offer.isActive !== false)
    .filter((offer) => !excludeSellerId || offer.sellerId !== excludeSellerId)
    .map((offer) => ({ ...offer, _exactPriceUsd: priceUsd(offer) }))
    .filter(
      (offer) =>
        Number.isFinite(offer._exactPriceUsd) &&
        offer._exactPriceUsd > 0 &&
        offer._exactPriceUsd <= maxUsd,
    )
    .sort(
      (left, right) =>
        left._exactPriceUsd - right._exactPriceUsd ||
        left._id.localeCompare(right._id),
    );

  if (preferredOfferId) {
    const preferred = candidates.find((offer) => offer._id === preferredOfferId);
    if (!preferred) {
      throw new Error(
        "preferred offer is absent, inactive, self-owned, or above the price cap",
      );
    }
    return preferred;
  }
  if (!candidates.length) {
    throw new Error("discovery returned no eligible live offer under the price cap");
  }
  return candidates[0];
}

function requiredEnv(name) {
  const value = process.env[name];
  if (!value) throw new Error(`${name} is required`);
  return value;
}

function parseInputJson(raw) {
  try {
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      throw new Error("input must be a JSON object");
    }
    return parsed;
  } catch (error) {
    throw new Error(`PAYANAGENT_INPUT_JSON is invalid: ${error.message}`);
  }
}

function safeProcessEnv() {
  return Object.fromEntries(
    Object.entries(process.env).filter(([, value]) => typeof value === "string"),
  );
}

export async function run() {
  const dryRun = process.env.PAYANAGENT_DRY_RUN === "1";
  if (!dryRun && process.env.PAYANAGENT_EXECUTE !== EXECUTION_TOKEN) {
    throw new Error(
      `refusing to pay: set PAYANAGENT_EXECUTE=${EXECUTION_TOKEN} after reviewing the cap`,
    );
  }
  const privateKey = dryRun ? "" : requiredEnv("PAYANAGENT_WALLET_PRIVATE_KEY");
  if (!dryRun && !/^0x[0-9a-fA-F]{64}$/.test(privateKey)) {
    throw new Error("PAYANAGENT_WALLET_PRIVATE_KEY must be one 0x-prefixed EVM key");
  }
  const query = requiredEnv("PAYANAGENT_QUERY");
  const input = dryRun
    ? parseInputJson(process.env.PAYANAGENT_INPUT_JSON ?? "{}")
    : parseInputJson(requiredEnv("PAYANAGENT_INPUT_JSON"));
  const maxUsd = Number(process.env.PAYANAGENT_MAX_USD ?? DEFAULT_MAX_USD);
  if (!Number.isFinite(maxUsd) || maxUsd <= 0 || maxUsd > DEFAULT_MAX_USD) {
    throw new Error(`PAYANAGENT_MAX_USD must be greater than 0 and at most ${DEFAULT_MAX_USD}`);
  }

  const [{ Client }, { StdioClientTransport }] = await Promise.all([
    import("@modelcontextprotocol/sdk/client/index.js"),
    import("@modelcontextprotocol/sdk/client/stdio.js"),
  ]);
  const childEnv = {
    ...safeProcessEnv(),
    PAYANAGENT_BASE_URL: DEFAULT_BASE_URL,
  };
  if (!dryRun) childEnv.PAYANAGENT_WALLET_PRIVATE_KEY = privateKey;
  const transport = new StdioClientTransport({
    command: "npx",
    args: ["-y", "@payanagent/mcp@0.4.1"],
    env: childEnv,
    stderr: "inherit",
  });
  const client = new Client(
    { name: "viridis-payanagent-example", version: "1.0.0" },
    { capabilities: {} },
  );

  try {
    await client.connect(transport);
    const discovery = parseToolResult(
      await client.callTool({
        name: "payanagent_discover",
        arguments: {
          query,
          maxPriceCents: Math.ceil(maxUsd * 100),
          offerType: "api",
          limit: 50,
        },
      }),
    );
    const offer = chooseOffer(discovery, {
      maxUsd,
      preferredOfferId: process.env.PAYANAGENT_OFFER_ID,
      excludeSellerId:
        process.env.PAYANAGENT_EXCLUDE_SELLER_ID ?? DEFAULT_EXCLUDED_SELLER,
    });
    process.stderr.write(
      `Selected ${offer._id} at $${offer._exactPriceUsd.toFixed(6)}; input schema: ${offer.inputSchema ?? "unspecified"}\n`,
    );
    if (dryRun) {
      console.log(
        JSON.stringify(
          {
            dryRun: true,
            offerId: offer._id,
            priceUsd: offer._exactPriceUsd,
            inputSchema: offer.inputSchema ?? null,
            nextAction: "Set PAYANAGENT_INPUT_JSON from this schema, review the cap, and explicitly enable one payment.",
          },
          null,
          2,
        ),
      );
      return;
    }

    const purchase = parseToolResult(
      await client.callTool({
        name: "payanagent_buy",
        arguments: { offerId: offer._id, input },
      }),
    );
    if (purchase.paymentRequired) {
      throw new Error("configured wallet payment was not accepted");
    }
    if (!/^kn[0-9a-z]+$/.test(purchase.receiptId ?? "")) {
      throw new Error("purchase returned no valid Payan receipt id");
    }
    if (!/^0x[0-9a-fA-F]{64}$/.test(purchase.txHash ?? "")) {
      throw new Error("purchase returned no valid transaction hash");
    }

    const receiptResponse = await fetch(
      `${DEFAULT_BASE_URL}/api/v1/receipts/${purchase.receiptId}`,
      { headers: { Accept: "application/json" } },
    );
    if (!receiptResponse.ok) {
      throw new Error(`public receipt lookup failed with HTTP ${receiptResponse.status}`);
    }
    const receipt = await receiptResponse.json();
    const receiptText = JSON.stringify(receipt).toLowerCase();
    if (
      !receiptText.includes(purchase.receiptId.toLowerCase()) ||
      !receiptText.includes(purchase.txHash.toLowerCase())
    ) {
      throw new Error("public receipt does not bind the returned receipt id and tx hash");
    }

    console.log(
      JSON.stringify(
        {
          offerId: offer._id,
          priceUsd: offer._exactPriceUsd,
          output: purchase.output,
          receiptId: purchase.receiptId,
          txHash: purchase.txHash,
          receiptVerified: true,
        },
        null,
        2,
      ),
    );
  } finally {
    await client.close().catch(() => {});
  }
}

if (import.meta.url === new URL(`file://${process.argv[1]}`).href) {
  run().catch((error) => {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  });
}
