# io.github.jdhart81/smartscale

Deterministic conversion of caller-supplied CR80 reference and coplanar object pixel geometry to millimetres

| | |
|---|---|
| Registry name | `io.github.jdhart81/smartscale` |
| Endpoint (Streamable HTTP) | `https://mcp.viridisconservation.com/smartscale/mcp` |
| Version | 0.9.4 |
| Tools | 4 |
| Source | [`smartscale-agent/`](../../smartscale-agent/) |

## Connect

No account, API key or OAuth is needed to connect, list tools or call free tools.

```json
{
  "mcpServers": {
    "viridis-smartscale": {
      "type": "http",
      "url": "https://mcp.viridisconservation.com/smartscale/mcp"
    }
  }
}
```

Claude Code: `claude mcp add --transport http viridis-smartscale https://mcp.viridisconservation.com/smartscale/mcp`

Claude, ChatGPT, VS Code, API and stdio-only clients: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#connect-a-client).

## Tools

### `credit_card_photo_instructions`

Return safe capture guidance for upstream CR80 pixel picking. The image stays with the caller or upstream vision system; SmartScale only receives numeric pixel geometry.

*changes records; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `measurement_goal` | string | no | Optional. What you want to measure. |
| `objects_to_measure` | array | no | Optional. The objects to measure. |

### `scale_objects_from_credit_card`

Scale object pixel dimensions using a standard CR80 credit card reference. Args: image_id: Caller-defined source identifier; no image is uploaded. credit_card_pixel_width: Caller-supplied pixel width of a CR80-size …

*changes records; structured output*

| Input | Type | Required | Description |
|---|---|---|---|
| `credit_card_pixel_height` | number | no | Optional. Height of the card in pixels, to check the scale. |
| `credit_card_pixel_width` | number | yes | Width of the CR80 card in the image, in pixels. |
| `image_id` | string | yes | Your id for the source image. The image itself is not uploaded. |
| `objects` | array of object | yes | Objects to scale, each with its pixel dimensions. |
| `payment_ref` | string | no | Optional. A paid credit or payment reference, used only after the free daily calls. Leave it out to use the free tier or a seat. |
| `request_id` | string | no | Optional. Your id for this call. Repeat it to retry safely: the same request_id is never charged twice. |

### `describe`

Return SmartScale capabilities and input contract.

*read-only; structured output*

No inputs.

### `health`

Return SmartScale health status.

*read-only; structured output*

No inputs.

## Example

Request (`tools/call`, captured from the live endpoint on 2026-11-15):

```json
{
  "name": "describe",
  "arguments": {}
}
```

Response (shortened):

```json
{
  "status": "ok",
  "data": {
    "name": "smartscale-agent",
    "version": "0.9.4",
    "description": "Deterministically converts caller-supplied CR80 reference and coplanar object pixel geometry into millimetres. The public MCP does not receive images or detect cards or objects.",
    "capabilities": [
      "deterministic_pixel_scaling",
      "cr80_reference_scaling",
      "perspective_sanity_check",
      "distortion_refusal"
    ],
    "inputs": {
      "measure_from_credit_card": {
        "image_id": "str — caller-defined source identifier",
        "credit_card_pixel_width": "finite float — caller-supplied CR80 card pixel width",
        "credit_card_pixel_height": "finite float (optional) — caller-supplied height for distortion check",
        "objects": "1..200 objects with bounded pixel_width and pixel_height",
        "request_id": "str (optional) — retry-safe idempotency key"
      }
    },
    "outputs": {
      "measure_from_credit_card": "Deterministic millimetre dimensions, explicit assumptions, and warning/refusal semantics"
    },
    "credit_card_reference": {
      "standard": "CR80",
      "width_mm": 85.6,
      "height_mm": 53.98
    },
    "claim_boundary": "Non-safety-critical 2D scaling only. No image ingestion, object detection, legal metrology, or fabrication tolerance guarantee.",
    "deploy_target": "remote_mcp_shared_gateway",
    "revenue_model": "$0.50 per state-changing scaling call after the free allowance"
  },
  "error": null
}
```

## Pricing and authentication

Read-only and verification tools are free. Paid tools include 10 free calls per caller per UTC day over MCP; after that a call returns `payment_required` with the exact price and ways to pay (card credits, a monthly seat, or x402 USDC on Base). Per-call prices shown above come from the live x402 catalog; a paid tool without one states its price in that `payment_required` answer. Nothing is charged without a separate, explicit payment. A call that cannot be attempted, or that determines nothing, is not charged. Details: [docs/HOSTED_MCP.md](../HOSTED_MCP.md#what-is-free-and-what-is-paid).

## Hosted service and this repository

This server's logic, MCP adapter and tests are open source (Apache-2.0) in [`smartscale-agent/`](../../smartscale-agent/); self-hosting gives the same results for the same inputs. The hosted gateway (payments, signing keys, receipt and usage storage, rate limits) is operated by Viridis and is not in this repository. The hosted service is operated by ViridisNorth LLC; the "Viridis" marks belong to Viridis LLC; both are owned by Justin Hart, who publishes as GitHub `jdhart81`. Contact: <justin@viridisconservation.com>.

*Generated by `scripts/server_docs.py` from the live endpoint (2026-11-15T23:15:45Z).*
