# x402 Route Decisions for the Seven MCP-Only Gated Agents

The five existing HTTP routes remain the only x402/Bazaar allowlist:
Regulatory Radar, TaxCredit, GHG Ledger, Quantity Takeoff, and Disclosure
Compiler. No new route is published merely to increase inventory.

| Agent | Decision | Required before reconsideration |
|---|---|---|
| SmartScale | **Hold route; candidate after 0.9.4 release gates.** | Current offsite backup, production restore drill, snapshot compatibility, 0.9.4 deploy/coherence, and a retry replay smoke proving one logical charge. |
| ProtoGen | **Hold route.** | Converge 0.3.1 versions/manifests, regenerate schemas with `request_id`, finish structured-output migration, and prove bounded design/workspace snapshots restore. |
| Narrative Engine | **Hold route.** | Converge 0.1.1 versions/manifests, define a buyer-verifiable output contract and claims, migrate structured output, and add retry replay evidence. |
| Verified Relay | **Deliberately MCP-only for now.** | Its outbound-service/receipt workflow needs a dedicated SSRF and buyer-auth contract review; a generic single HTTP action would misrepresent the product. |
| Verdigraph | **Hold route.** | Publish coherent manifests/tool schemas, define the paid build action and output contract, migrate structured output, and pass snapshot compatibility. |
| Neurogenesis | **Deliberately MCP-only for now.** | The product is a stateful multi-step lifecycle; a one-shot x402 route is not a truthful sales contract without an account/session design. |
| Green Router | **Hold route.** | Separate routing estimates from certification claims, prove retirement/finalization behavior, migrate structured output, and pass bounded-state restore tests. |

“Hold” means no route entry in `X402_HTTP_TOOLS`, no Bazaar metadata, and no
registry sales claim. A route is added only in the same reviewed change that
closes its listed contract gates and adds route-specific settle/replay tests.
