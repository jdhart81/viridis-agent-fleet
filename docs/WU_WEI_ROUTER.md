# Wu Wei Workload Router

$1 USDC per routing plan for up to 20 route profiles and 50 workload groups. Supply recent representative evaluation counts, declared total cost per task and task requirements. Receive eligible route recommendations and modeled savings after our fee. A plan can conclude that savings do not cover its fee.

MCP: https://mcp.viridisconservation.com/wu-wei-router/mcp

Paid HTTP: https://mcp.viridisconservation.com/x402/wu-wei-router/plan_workload

Inspect the input schema and example in https://mcp.viridisconservation.com/x402/catalog; an unsigned POST returns an unpaid quote. `describe_agent` is free. Buyer-authorized payment is required for execution through the fleet. The standalone core is a computation library and must not be exposed outside the fleet payment gate.

This service makes recommendations only. It does not execute workloads, independently validate supplied evaluations, guarantee quality, measure energy or establish realized savings. Uses a Wilson lower-bound eligibility heuristic, not the research's unproven universal rate threshold. Adaptive learning is a later benchmarked upgrade.
