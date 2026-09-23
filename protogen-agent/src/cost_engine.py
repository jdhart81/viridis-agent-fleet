"""
Cost Estimation Engine for ProtoGen
Advanced cost models: material, labor, tooling, overhead, economies of scale.
"""

import logging
import math
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class CostFactors:
    """Cost parameters for estimation."""
    material_density: float  # kg/cm³
    material_cost_per_kg: float  # $/kg
    scrap_rate: float  # 0.05 = 5% scrap
    process_hourly_rate: float  # $/hour
    process_efficiency: float  # 0.0-1.0, accounts for downtime
    labor_rate: float  # $/hour for assembly/finishing
    overhead_multiplier: float  # 1.15 = 15% overhead


class CostEngine:
    """Production cost estimation with volume scaling."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def estimate_material_cost(
        self,
        volume_cm3: float,
        material_density: float,
        cost_per_kg: float,
        scrap_rate: float = 0.05,
    ) -> float:
        """Calculate raw material cost per unit."""
        mass_kg = (volume_cm3 / 1000) * material_density
        # Account for scrap/yield loss
        mass_with_scrap = mass_kg / (1 - scrap_rate)
        cost = mass_with_scrap * cost_per_kg
        return round(cost, 2)

    def estimate_labor_cost(
        self,
        process_time_minutes: float,
        hourly_rate: float,
        process_efficiency: float = 0.85,
    ) -> float:
        """Calculate labor cost accounting for efficiency."""
        effective_time = process_time_minutes / (60 * process_efficiency)
        cost = (effective_time / 60) * hourly_rate
        return round(cost, 2)

    def estimate_tooling_amortization(
        self,
        tooling_cost: float,
        annual_volume: int,
        tool_lifespan_units: int = 100000,
    ) -> float:
        """Amortize one-time tooling cost over lifetime production."""
        effective_volume = min(annual_volume, tool_lifespan_units)
        amortization = tooling_cost / effective_volume if effective_volume > 0 else 0
        return round(amortization, 2)

    def calculate_per_unit_cost(
        self,
        material_cost: float,
        labor_cost: float,
        process_cost: float,
        tooling_amortization: float,
        overhead_rate: float = 0.15,
        contingency_rate: float = 0.05,
    ) -> dict:
        """Calculate comprehensive per-unit manufacturing cost."""
        subtotal = material_cost + labor_cost + process_cost + tooling_amortization
        overhead = subtotal * overhead_rate
        contingency = subtotal * contingency_rate
        total_cost = subtotal + overhead + contingency

        return {
            "material_cost": round(material_cost, 2),
            "labor_cost": round(labor_cost, 2),
            "process_cost": round(process_cost, 2),
            "tooling_amortization": round(tooling_amortization, 2),
            "subtotal_direct": round(subtotal, 2),
            "overhead": round(overhead, 2),
            "contingency": round(contingency, 2),
            "total_cogs": round(total_cost, 2),
        }

    def apply_volume_discount(
        self,
        unit_cost: float,
        annual_volume: int,
        discount_tiers: Optional[dict] = None,
    ) -> dict:
        """Apply volume discounts and calculate net cost."""
        if discount_tiers is None:
            # Default discount structure
            discount_tiers = {
                100: 0.0,      # 0% discount for <100 units
                500: 0.05,     # 5% for 100-500
                1000: 0.10,    # 10% for 500-1000
                5000: 0.15,    # 15% for 1000-5000
                10000: 0.20,   # 20% for 5000-10000
                50000: 0.25,   # 25% for 10000-50000
                float('inf'): 0.30,  # 30% for 50000+
            }

        discount_rate = 0.0
        for tier_volume, tier_discount in sorted(discount_tiers.items()):
            if annual_volume < tier_volume:
                discount_rate = tier_discount
                break

        discounted_cost = unit_cost * (1 - discount_rate)
        savings = unit_cost - discounted_cost

        return {
            "unit_cost_before_discount": round(unit_cost, 2),
            "volume_tier": annual_volume,
            "discount_rate": discount_rate,
            "unit_cost_after_discount": round(discounted_cost, 2),
            "savings_per_unit": round(savings, 2),
        }

    def calculate_selling_price(
        self,
        cogs: float,
        gross_margin_target: float = 0.40,
        currency: str = "USD",
    ) -> dict:
        """Calculate selling price from COGS and margin target."""
        gross_profit = cogs * (gross_margin_target / (1 - gross_margin_target))
        selling_price = cogs + gross_profit

        return {
            "cogs": round(cogs, 2),
            "gross_profit": round(gross_profit, 2),
            "selling_price": round(selling_price, 2),
            "gross_margin_pct": round(gross_margin_target * 100, 1),
            "currency": currency,
        }

    def calculate_break_even(
        self,
        fixed_costs: float,
        unit_contribution_margin: float,
    ) -> int:
        """Calculate break-even volume."""
        if unit_contribution_margin <= 0:
            return 0
        return math.ceil(fixed_costs / unit_contribution_margin)

    def lifetime_cost_analysis(
        self,
        unit_cogs: float,
        annual_volume: int,
        annual_growth_rate: float = 0.1,
        years: int = 5,
        fixed_costs: float = 0.0,
    ) -> dict:
        """Project 5-year cost and profitability."""
        projections = []
        cumulative_volume = 0
        cumulative_profit = 0

        for year in range(1, years + 1):
            year_volume = int(annual_volume * ((1 + annual_growth_rate) ** (year - 1)))
            year_cogs = unit_cogs * year_volume
            year_revenue = self.calculate_selling_price(unit_cogs)["selling_price"] * year_volume
            year_profit = year_revenue - year_cogs - fixed_costs

            cumulative_volume += year_volume
            cumulative_profit += year_profit

            projections.append({
                "year": year,
                "annual_volume": year_volume,
                "cogs_total": round(year_cogs, 2),
                "revenue_total": round(year_revenue, 2),
                "profit": round(year_profit, 2),
                "cumulative_volume": cumulative_volume,
                "cumulative_profit": round(cumulative_profit, 2),
            })

        return {
            "scenario": f"{years}-year projection at {annual_growth_rate*100:.0f}% annual growth",
            "projections": projections,
            "total_volume": cumulative_volume,
            "total_profit": round(cumulative_profit, 2),
        }

    def sensitivity_analysis(
        self,
        base_cogs: float,
        base_volume: int,
        variables: Optional[dict] = None,
    ) -> dict:
        """Analyze cost sensitivity to parameter changes."""
        if variables is None:
            variables = {
                "material_cost": [-20, -10, 0, 10, 20],
                "labor_cost": [-20, -10, 0, 10, 20],
                "volume": [-30, -15, 0, 15, 30],
            }

        results = {}

        # Material sensitivity
        material_changes = variables.get("material_cost", [])
        material_results = []
        for pct_change in material_changes:
            adjusted_cogs = base_cogs * (1 + pct_change / 100)
            price = self.calculate_selling_price(adjusted_cogs)["selling_price"]
            material_results.append({
                "change_pct": pct_change,
                "cogs": round(adjusted_cogs, 2),
                "selling_price": round(price, 2),
            })
        results["material_cost_sensitivity"] = material_results

        # Labor sensitivity
        labor_changes = variables.get("labor_cost", [])
        labor_results = []
        for pct_change in labor_changes:
            adjusted_cogs = base_cogs * (1 + pct_change / 100)
            price = self.calculate_selling_price(adjusted_cogs)["selling_price"]
            labor_results.append({
                "change_pct": pct_change,
                "cogs": round(adjusted_cogs, 2),
                "selling_price": round(price, 2),
            })
        results["labor_cost_sensitivity"] = labor_results

        # Volume sensitivity
        volume_changes = variables.get("volume", [])
        volume_results = []
        for pct_change in volume_changes:
            adj_volume = int(base_volume * (1 + pct_change / 100))
            # Simplified: assume 10% cost reduction per 2x volume
            volume_multiplier = (adj_volume / base_volume) if base_volume > 0 else 1.0
            cost_reduction = 1 - (0.05 * math.log2(volume_multiplier))
            adjusted_cogs = base_cogs * cost_reduction
            price = self.calculate_selling_price(adjusted_cogs)["selling_price"]
            volume_results.append({
                "change_pct": pct_change,
                "volume": adj_volume,
                "cogs": round(adjusted_cogs, 2),
                "selling_price": round(price, 2),
            })
        results["volume_sensitivity"] = volume_results

        return results
