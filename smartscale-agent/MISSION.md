# SmartScale Mission

SmartScale is the deterministic geometry-scaling primitive in the Viridis
measure → takeoff → CAD workflow.

## Product boundary

The production MCP does one job:

> Given caller-supplied pixel geometry for a standard CR80-size reference and
> coplanar objects, return deterministic dimensions in millimetres with
> explicit assumptions and distortion warning/refusal semantics.

The production MCP does not:

- receive, store, decode, or inspect images;
- detect a card, object, edge, or bounding box;
- infer depth or measure non-planar objects;
- provide calibrated measurement confidence;
- provide legal metrology, safety certification, or fabrication tolerances.

A human picker, UI, or upstream vision system must supply the pixel geometry.

## Customer promise

SmartScale may be sold as a no-SLA deterministic beta for non-safety-critical
2D scaling after the launch gates below pass. The supported claim is:

> Given the pixel width of a CR80-size card and pixel boxes for coplanar
> objects in the same source image, SmartScale deterministically returns their
> dimensions in millimetres and warns or refuses when the supplied card aspect
> indicates excessive distortion.

The price is $0.50 per state-changing scaling call after the published free
allowance. Revenue exists only when an external customer pays and settlement
and tool-result evidence agree.

## Production invariants

1. The CR80 width constant is 85.60 mm.
2. All numeric inputs are finite and bounded.
3. A call contains at most 200 objects and labels contain at most 128 characters.
4. The same caller and `request_id` with the same logical input returns the
   original persisted result without a second quota or credit consumption.
5. Reusing a `request_id` for different input fails closed.
6. Read-only `describe` and `health` calls never consume quota.
7. Card aspect disagreement above 8% warns; above 15% refuses without dimensions.
8. Every result states its assumptions, including rectangle-derived area or
   perimeter when the caller omits those fields.
9. State is durably persisted before acknowledgment.
10. Production is not ready for paid use until an off-droplet backup and
    performed restore drill are proven.

## Direction

Keep the deterministic scaler inside the shared Viridis gateway for the pilot.
Do not build automatic image measurement until:

- at least three distinct external callers have paid for the deterministic
  scaler; and
- at least one has explicitly requested automatic pixel extraction.

If that trigger occurs, image decoding and computer vision must run in an
isolated worker with a ground-truth benchmark. The existing simulated image
path is not product evidence.

## Success and stop conditions

Success is the first independently verified external paid call followed by
repeat use without billing or measurement disputes.

If the truthful listing and a discoverable buyer route produce zero external
paid SmartScale calls after 30 days, stop investing in SmartScale as a
standalone product. Keep it as a free or bundled primitive for Quantity
Takeoff and ProtoGen.
