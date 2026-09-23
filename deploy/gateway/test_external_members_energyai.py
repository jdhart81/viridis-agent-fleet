import viridis_mcp_gateway as gateway


EXPECTED_FREE_TOOLS = [
    "check_incentives",
    "estimate_production",
    "get_node_score",
    "get_quote_link",
    "get_power_passport_link",
    "get_power_service_quote",
    "route_lead",
    "list_guides",
    "get_guide",
    "find_local_installers",
    "create_builder_key",
    "get_builder_upgrade_link",
]


def test_energyai_discovery_copy_matches_live_free_tool_contract():
    energyai = next(
        member
        for member in gateway.EXTERNAL_MEMBERS
        if member["identifier"] == "urn:air:viridis:energyai"
    )

    assert energyai["capabilities"] == EXPECTED_FREE_TOOLS + ["review_installer_quote", "record_quote_review_outcome"]
    assert energyai["version"] == "1.3.0"
    assert energyai["metadata"]["officialRegistryVersion"] == "1.3.0"
    assert energyai["metadata"]["builderActivation"]["firstCommercialTool"] == "review_installer_quote"
    assert energyai["metadata"]["builderActivation"]["activationUrl"] == "https://energyaisolution.com/agents/activate"
    assert energyai["metadata"]["quoteGuardianReferral"]["referralCreditPercent"] == 20
    assert energyai["metadata"]["quoteGuardianReferral"]["creditType"] == "non_cash_energyai_tool_credit"


def test_energyai_installer_copy_disclaims_vetting_and_partnership():
    energyai = next(
        member
        for member in gateway.EXTERNAL_MEMBERS
        if member["identifier"] == "urn:air:viridis:energyai"
    )
    description = energyai["description"].lower()

    assert "public reputation data" in description
    assert "listingstatus" in description
    assert "disclosure" in description
    assert "not vetted, endorsed, or partnered" in description


def test_energyai_commercial_contract_preserves_budget_and_claim_boundaries():
    member = next(m for m in gateway.EXTERNAL_MEMBERS if m["identifier"] == "urn:air:viridis:energyai")
    service = member["metadata"]["commercialService"]
    assert service["maxPriceField"] == "maxPriceCents"
    assert service["retryIdentityField"] == "toolCallId"
    assert service["humanReviewed"] is False
    assert service["externalAdoptionProven"] is False
    assert member["metadata"]["relationship"] == "COMMON_CONTROL_RELATED"


def test_energyai_job_discovery_is_free_and_distinct_from_execution():
    member = next(m for m in gateway.EXTERNAL_MEMBERS if m["identifier"] == "urn:air:viridis:energyai")
    discovery = member["metadata"]["capabilityMap"]
    assert discovery["url"] == "https://api.energyaisolution.com/api/v1/agent/capabilities"
    assert discovery["mcpResource"] == "energyai://capabilities"
    assert discovery["discoveryFree"] is True
    assert discovery["createsAccount"] is False
    assert discovery["executesJob"] is False
    assert set(discovery["workflows"]) == {"solar", "weatherization", "ev-charging", "battery", "heat-pump"}
