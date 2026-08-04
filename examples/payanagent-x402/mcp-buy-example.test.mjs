import assert from "node:assert/strict";
import test from "node:test";

import { chooseOffer, parseToolResult } from "./mcp-buy-example.mjs";

test("parseToolResult decodes the MCP text payload", () => {
  assert.deepEqual(
    parseToolResult({ content: [{ type: "text", text: '{"offers":[]}' }] }),
    { offers: [] },
  );
});
test("chooseOffer selects the cheapest independent live offer under the cap", () => {
  const selected = chooseOffer(
    {
      offers: [
        { _id: "expensive", priceUsd: 0.02, isActive: true },
        { _id: "self", priceUsd: 0.001, isActive: true, sellerId: "viridis" },
        { _id: "dead", priceUsd: 0.002, isActive: false },
        { _id: "eligible-b", priceUsd: 0.004, isActive: true },
        { _id: "eligible-a", priceUsd: 0.004, isActive: true },
      ],
    },
    { maxUsd: 0.01, excludeSellerId: "viridis" },
  );
  assert.equal(selected._id, "eligible-a");
  assert.equal(selected._exactPriceUsd, 0.004);
});

test("chooseOffer fails closed when a preferred offer is ineligible", () => {
  assert.throws(
    () =>
      chooseOffer(
        { offers: [{ _id: "too-much", priceUsd: 0.02, isActive: true }] },
        { maxUsd: 0.01, preferredOfferId: "too-much" },
      ),
    /preferred offer/,
  );
});
