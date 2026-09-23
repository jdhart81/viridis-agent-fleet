# SmartScale Agent

SmartScale is a deterministic CR80 pixel-geometry scaling MCP.

It converts caller-supplied reference-card and object pixel geometry to
millimetres. The production MCP does not receive images, detect cards, or
locate objects.

## Supported contract

The caller supplies:

- a caller-defined source identifier;
- the pixel width of a standard CR80-size card (85.60 mm);
- optionally, the card pixel height for a distortion check;
- 1–200 coplanar objects with finite, bounded pixel width and height;
- optionally, area, perimeter, an upstream input-confidence value, and a
  retry-safe `request_id`.

SmartScale returns deterministic dimensions, explicit assumptions, and:

- a warning above 8% reference width/height scale disagreement;
- a refusal without dimensions above 15% disagreement.

The result is for non-safety-critical 2D scaling only. It is not legal
metrology, a fabrication-tolerance guarantee, or a substitute for verified
onsite measurement.

## Public MCP

Endpoint:

`https://mcp.viridisconservation.com/smartscale/mcp`

Public tools:

- `credit_card_photo_instructions`
- `scale_objects_from_credit_card`
- `describe`
- `health`

The first published allowance of state-changing calls is free. Calls beyond
that allowance are $0.50 each through the shared Viridis payment gate.
`describe` and `health` do not consume quota.

Example arguments:

```json
{
  "image_id": "source-001",
  "credit_card_pixel_width": 856.0,
  "credit_card_pixel_height": 539.8,
  "objects": [
    {
      "label": "part",
      "pixel_width": 428.0,
      "pixel_height": 214.0
    }
  ],
  "request_id": "buyer-order-001"
}
```

With a 10 px/mm reference, the object is 42.8 × 21.4 mm.

## Safe reference guidance

Only the CR80 outer dimensions matter. Prefer:

1. a blank CR80 calibration card;
2. an expired or non-payment card;
3. a fully masked card.

Never expose a PAN, expiry date, CVV, signature, or cardholder name. The image
stays with the caller or upstream pixel-picking system.

## Local verification

```bash
python3 -m pytest smartscale-agent/tests -q
python3 -m pytest deploy/gateway/test_payment_gate.py -q
python3 deploy/gateway/gateway_smoke.py
```

## Production architecture

The canonical runtime is:

```text
Caddy → shared Viridis MCP gateway → PaymentGate → StateStore → SmartScaleCore
```

SmartScale runs in the existing gateway process and uses the shared durable
SQLite state volume. The standalone `Dockerfile`, `docker-compose.yml`,
`adapters/fastapi_server.py`, `src/vision.py`, `src/measurement.py`, and
`src/agent/` are legacy or experimental surfaces. They are not the production
service and do not prove image-measurement capability.

## Paid-beta launch gates

Do not charge an external customer until:

- public descriptions and manifests match this contract;
- request-id replay consumes exactly one unit;
- non-finite and oversized inputs fail closed;
- the state database has an off-droplet backup less than 25 hours old; and
- a restore into a scratch database has passed integrity and marker-state
  verification.

## License

MIT
