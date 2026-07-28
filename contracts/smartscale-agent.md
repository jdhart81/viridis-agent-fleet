# SmartScale Agent Contract

Version: `0.9.4`  
Status: conditional deterministic beta  
Endpoint: `https://mcp.viridisconservation.com/smartscale/mcp`

## What the service does

SmartScale deterministically converts caller-supplied pixel geometry to
millimetres using the standard CR80 width of 85.60 mm.

The caller supplies:

- a caller-defined source identifier;
- CR80 card pixel width;
- optional CR80 card pixel height;
- 1–200 coplanar object pixel boxes; and
- an optional retry-safe `request_id`.

The service returns scaled 2D dimensions, explicit assumptions, and
distortion warning/refusal semantics.

## What the service does not do

The public MCP does not receive images, detect the reference card, locate
objects, infer depth, or provide calibrated measurement confidence. It is not
legal metrology, safety certification, or a fabrication-tolerance guarantee.

A human picker, UI, or upstream vision system must supply the pixel geometry.

## Billing and retry contract

The first ten state-changing calls per caller per UTC day are free, subject to
the documented aggregate anonymous-pool cap. Additional calls cost $0.50.

When `request_id` is supplied:

- the key is scoped to the server-derived caller identity;
- the same key and logical input return the original persisted result;
- replay consumes no second quota, credit, subscription unit, escrow, x402
  settlement, or metering event; and
- reusing a key for different logical input fails closed.

`describe` and `health` are always read-only and unmetered.

## Input guards

- every number must be finite;
- dimension values must be between `1e-3` and `1e7` pixels;
- at most 200 objects are accepted;
- labels are at most 128 characters;
- supplied confidence is treated only as upstream `input_confidence`;
- reference aspect disagreement above 8% warns; and
- disagreement above 15% refuses without dimensions.

## Commercial status

The payment rail is mechanically implemented. Commercial validation remains
absent until an external paid SmartScale call is independently verified.

Do not claim automatic image measurement or real-photo accuracy. Do not claim
revenue based on a live endpoint, free calls, or internal tests.
