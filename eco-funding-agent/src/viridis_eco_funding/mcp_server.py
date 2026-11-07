"""MCP server: five read-only tools over stdio or Streamable HTTP.

    vef-mcp                                   # stdio (default)
    vef-mcp --transport streamable-http --host 127.0.0.1 --port 8765   # POST /mcp

Tools: value_site, explain_valuation, verify_receipt, simulate_pool, describe_method.
All are read-only (Invariant 6): they compute, and at most read VergeCommon's public API
with GET when the caller asks for a provenance binding. None writes anywhere, holds
state between calls, or moves money (Invariant 5).
"""

from __future__ import annotations

import argparse
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from . import __version__
from .canonical import to_canonical_data, to_plain_json
from .explain import describe_method as _describe_method
from .explain import explain_valuation as _explain_valuation
from .inputs import SiteInputError, normalize_site_inputs
from .pool import LEGAL_NOTICE, PoolSpecError
from .pool import simulate_pool as _simulate_pool
from .receipt import make_receipt
from .receipt import verify_receipt as _verify_receipt
from .fleet import INSTRUCTIONS
from .vergecommon import ReadOnlyVergeCommonClient, VergeCommonError, fetch_and_bind

TOOL_NAMES = ("value_site", "explain_valuation", "verify_receipt", "simulate_pool",
              "describe_method")

PURE = ToolAnnotations(title=None, read_only_hint=True, destructive_hint=False,
                       idempotent_hint=True, open_world_hint=False)
PUBLIC_READ = ToolAnnotations(title=None, read_only_hint=True, destructive_hint=False,
                              idempotent_hint=True, open_world_hint=True)


class ToolInputError(ToolError):
    """Bad tool input: reaches the MCP client as an is_error result with this message."""


def _client_factory() -> ReadOnlyVergeCommonClient:
    return ReadOnlyVergeCommonClient()


def build_server(client_factory: Any = _client_factory) -> MCPServer:
    server = MCPServer(name="viridis-eco-funding", version=__version__, instructions=INSTRUCTIONS,
                       website_url="https://viridisconservation.com")

    @server.tool(
        name="value_site",
        description=(
            "Value a site's ecological complexity from site inputs (schema vef-site/0.1: D-Score "
            "components, habitat patches and links, optional GSIP soil indicators, optional NPP and "
            "temperature). Produces a sealed, reproducible receipt with every quantity's formula, "
            "units, inputs and uncertainty. Set bind_vergecommon=true to read the named VergeCommon "
            "public project (GET only) and bind it as provenance. Quantities derived from the "
            "intelligence bound are labelled 'conjecture'. Not a price."),
        annotations=PUBLIC_READ)
    def value_site(site: dict[str, Any], bind_vergecommon: bool = False) -> dict[str, Any]:
        try:
            source = None
            if bind_vergecommon:
                normalized = normalize_site_inputs(site)
                source = fetch_and_bind(normalized, client_factory())
            receipt = make_receipt(site, source=source)
        except (SiteInputError, VergeCommonError) as exc:
            raise ToolInputError(str(exc)) from exc
        result = receipt["result"]
        return to_plain_json({
            "headline": result["headline"],
            "explanation": result["explanation"],
            "labels": result["labels"],
            "warnings": result["warnings"],
            "receipt_seal": receipt["seal"]["digest"],
            "receipt": receipt,
        })

    @server.tool(
        name="explain_valuation",
        description=(
            "Explain a valuation step by step: each quantity's formula, inputs, value, units, "
            "uncertainty and status (published method, v0.1 convention, input, or conjecture), plus "
            "the main limits. Accepts either a valuation result (receipt.result) or raw site inputs."),
        annotations=PURE)
    def explain_valuation(valuation_or_site: dict[str, Any]) -> dict[str, Any]:
        try:
            return to_plain_json(_explain_valuation(valuation_or_site))
        except SiteInputError as exc:
            raise ToolInputError(str(exc)) from exc

    @server.tool(
        name="verify_receipt",
        description=(
            "Re-run a valuation receipt offline and check its input, result and seal digests. "
            "Reports valid=true only if the result is reproduced byte for byte. With "
            "refetch_source=true, also reads the bound VergeCommon public record (GET only) and "
            "reports whether it changed. Verification shows reproducibility, not that inputs are true."),
        annotations=PUBLIC_READ)
    def verify_receipt(receipt: dict[str, Any], refetch_source: bool = False) -> dict[str, Any]:
        record = None
        if refetch_source:
            source = receipt.get("source") if isinstance(receipt, dict) else None
            if not isinstance(source, dict) or source.get("kind") != "vergecommon-public-api":
                raise ToolInputError("receipt has no VergeCommon source to refetch")
            try:
                record = client_factory().get_public_coop(str(source.get("coop_id")))["record"]
            except VergeCommonError as exc:
                raise ToolInputError(str(exc)) from exc
        return to_plain_json(_verify_receipt(receipt, source_record=record))

    @server.tool(
        name="simulate_pool",
        description=(
            "Simulate a pledge pool (schema vef-pool/0.1) under milestone and outcome-linked release "
            "rules, given per-period observations (receipts, or hypothetical metric readings). "
            "Integer accounting: releases plus remaining balance always equal pledges, and nothing "
            "is released without a met rule. SIMULATION ONLY: no funds are held or moved. "
            + LEGAL_NOTICE),
        annotations=PURE)
    def simulate_pool(pool: dict[str, Any],
                      observations: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        try:
            return to_plain_json(_simulate_pool(pool, observations))
        except PoolSpecError as exc:
            raise ToolInputError(str(exc)) from exc

    @server.tool(
        name="describe_method",
        description=(
            "Describe the valuation method: formulas, constants, declared defaults, statuses, the "
            "seven invariants, citations and limits. Call this first."),
        annotations=PURE)
    def describe_method() -> dict[str, Any]:
        return to_plain_json(to_canonical_data(_describe_method()))

    return server


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="vef-mcp", description=__doc__.splitlines()[0])
    parser.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    server = build_server()
    if args.transport == "stdio":
        server.run("stdio")
    else:
        server.run("streamable-http", host=args.host, port=args.port, stateless_http=True,
                   json_response=True)


if __name__ == "__main__":  # pragma: no cover
    main()
