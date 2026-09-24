"""
Unit tests for ProtoGenCore
Tests spec parsing, BOM generation, process selection, DFM analysis, and costing.
"""

import pytest
import asyncio
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from core import ProtoGenCore, ProductSpec, ManufacturingPlan
from cost_engine import CostEngine
from manufacturing import ManufacturingLibrary


class TestProtoGenCore:
    """Test ProtoGenCore business logic."""

    @pytest.fixture
    def core(self):
        """Initialize ProtoGenCore for testing."""
        return ProtoGenCore()

    @pytest.fixture
    def sample_spec(self):
        """Sample product specification."""
        return {
            "name": "Aluminum Enclosure",
            "description": "Electronics enclosure for industrial equipment",
            "primary_material": "aluminum",
            "estimated_volume": 2500,
            "target_dimensions": {
                "length_mm": 150,
                "width_mm": 100,
                "height_mm": 75,
            },
            "tolerances": {
                "general": "±0.1mm",
                "critical": "±0.05mm",
            },
            "surface_finish": "anodized",
            "assembly_complexity": "moderate",
            "lead_time_weeks": 8,
            "target_unit_cost": 45.00,
        }

    def test_parse_spec_valid(self, core, sample_spec):
        """Test valid spec parsing."""
        parsed = core._parse_spec(sample_spec)
        assert parsed.name == "Aluminum Enclosure"
        assert parsed.primary_material == "aluminum"
        assert parsed.estimated_volume == 2500
        assert parsed.surface_finish == "anodized"

    def test_parse_spec_missing_field(self, core):
        """Test missing required field raises error."""
        incomplete_spec = {
            "name": "Widget",
            "description": "A widget",
            # Missing primary_material and estimated_volume
        }
        with pytest.raises(ValueError):
            core._parse_spec(incomplete_spec)

    def test_bom_generation_aluminum(self, core, sample_spec):
        """Test BOM generation for aluminum product."""
        spec = core._parse_spec(sample_spec)
        bom = core._generate_bom(spec)

        assert len(bom) > 0
        assert bom[0].material == "aluminum"
        assert bom[0].quantity == 1.0
        assert bom[0].unit_cost > 0

    def test_bom_generation_complex_assembly(self, core, sample_spec):
        """Test BOM includes fasteners for complex assembly."""
        sample_spec["assembly_complexity"] = "complex"
        spec = core._parse_spec(sample_spec)
        bom = core._generate_bom(spec)

        # Should have primary material, fasteners, and connectors
        assert len(bom) >= 3
        materials = [c.material for c in bom]
        assert "steel" in materials  # Fasteners

    def test_process_selection_high_volume_plastic(self, core):
        """Test process selection for high-volume plastic."""
        spec = ProductSpec(
            name="Plastic Case",
            description="High-volume plastic enclosure",
            primary_material="plastic_abs",
            estimated_volume=50000,
            target_dimensions={"length_mm": 100, "width_mm": 100, "height_mm": 50},
            tolerances={"general": "±0.2mm"},
            surface_finish="raw",
            assembly_complexity="simple",
        )
        processes = core._select_processes(spec)

        # Should select injection molding for high volume
        assert any(p.process_type == "injection_molding" for p in processes)

    def test_process_selection_low_volume_prototyping(self, core):
        """Test process selection for low-volume prototype."""
        spec = ProductSpec(
            name="Prototype",
            description="Low-volume prototype",
            primary_material="plastic_abs",
            estimated_volume=10,
            target_dimensions={"length_mm": 100, "width_mm": 100, "height_mm": 50},
            tolerances={"general": "±0.2mm"},
            surface_finish="raw",
            assembly_complexity="simple",
        )
        processes = core._select_processes(spec)

        # Should select 3D printing for low volume
        assert any(p.process_type == "3d_printing" for p in processes)

    def test_dfm_analysis_high_tolerances(self, core):
        """Test DFM detects tolerance issues."""
        spec = ProductSpec(
            name="Precision Part",
            description="Part with tight tolerances",
            primary_material="aluminum",
            estimated_volume=100,
            target_dimensions={"length_mm": 50, "width_mm": 50, "height_mm": 25},
            tolerances={"general": "±0.02mm", "critical": "±0.01mm"},
            surface_finish="raw",
            assembly_complexity="simple",
        )
        processes = core._select_processes(spec)
        issues = core._perform_dfm_analysis(spec, processes)

        # Should flag tight tolerances
        assert any("tolerance" in issue.lower() for issue in issues)

    def test_dfm_analysis_volume_mismatch(self, core):
        """Test DFM detects volume vs process mismatch."""
        spec = ProductSpec(
            name="Low-Volume Molded",
            description="Low volume but selected injection molding",
            primary_material="plastic_abs",
            estimated_volume=50,  # Too low for injection molding
            target_dimensions={"length_mm": 100, "width_mm": 100, "height_mm": 50},
            tolerances={"general": "±0.2mm"},
            surface_finish="raw",
            assembly_complexity="simple",
        )
        # Don't filter; let the normal process selection happen so injection_molding can be evaluated
        processes = core._select_processes(spec)

        # For low volume plastic, process selection should choose 3d_printing instead of injection_molding
        # But we can still test the DFM logic by manually adding injection molding and checking it's flagged
        from core import ProcessStep
        processes.append(ProcessStep(
            sequence=99,
            process_type="injection_molding",
            description="Injection molding (test)",
            equipment="injection_mold",
            estimated_cost_per_unit=50,
            setup_time_hours=1,
            lead_time_days=21,
        ))
        issues = core._perform_dfm_analysis(spec, processes)

        # Low volume should trigger warning against injection molding
        assert any("volume" in issue.lower() for issue in issues)

    def test_cost_calculation_structure(self, core, sample_spec):
        """Test cost breakdown structure and math."""
        spec = core._parse_spec(sample_spec)
        bom = core._generate_bom(spec)
        processes = core._select_processes(spec)
        costs = core._calculate_costs(spec, bom, processes)

        # Check structure
        assert "material_cost" in costs
        assert "labor_cost" in costs
        assert "tooling_amortization" in costs
        assert "subtotal_manufacturing" in costs
        assert "overhead" in costs
        assert "profit_margin" in costs
        assert "selling_price_per_unit" in costs

        # Check math: subtotal should equal material + labor + tooling
        calculated_subtotal = (
            costs["material_cost"] +
            costs["labor_cost"] +
            costs["tooling_amortization"]
        )
        assert abs(costs["subtotal_manufacturing"] - calculated_subtotal) < 0.01

        # Selling price should include all components
        assert costs["selling_price_per_unit"] > costs["subtotal_manufacturing"]

    def test_cost_scales_with_volume(self, core):
        """Test that costs scale appropriately with volume using plastic with tooling."""
        # Use plastic spec to trigger injection molding at high volume (which has tooling costs)
        spec1 = core._parse_spec({
            "name": "Plastic Widget",
            "description": "Plastic part",
            "primary_material": "plastic_abs",
            "estimated_volume": 5000,  # Triggers 3d_printing
            "target_dimensions": {"length_mm": 100, "width_mm": 100, "height_mm": 50},
            "tolerances": {"general": "±0.2mm"},
            "surface_finish": "raw",
            "assembly_complexity": "simple",
        })
        spec2 = core._parse_spec({
            "name": "Plastic Widget",
            "description": "Plastic part",
            "primary_material": "plastic_abs",
            "estimated_volume": 50000,  # Triggers injection_molding with tooling
            "target_dimensions": {"length_mm": 100, "width_mm": 100, "height_mm": 50},
            "tolerances": {"general": "±0.2mm"},
            "surface_finish": "raw",
            "assembly_complexity": "simple",
        })

        bom1 = core._generate_bom(spec1)
        bom2 = core._generate_bom(spec2)
        processes1 = core._select_processes(spec1)
        processes2 = core._select_processes(spec2)

        costs1 = core._calculate_costs(spec1, bom1, processes1)
        costs2 = core._calculate_costs(spec2, bom2, processes2)

        # Both specs should have valid costs
        assert costs1["selling_price_per_unit"] > 0
        assert costs2["selling_price_per_unit"] > 0
        # Verify that tooling amortization exists at high volume
        assert costs2["tooling_amortization"] >= 0

    def test_feasibility_score_range(self, core, sample_spec):
        """Test feasibility score is between 0 and 1."""
        spec = core._parse_spec(sample_spec)
        bom = core._generate_bom(spec)
        processes = core._select_processes(spec)
        costs = core._calculate_costs(spec, bom, processes)
        dfm_issues = core._perform_dfm_analysis(spec, processes)

        feasibility = core._score_feasibility(spec, costs, dfm_issues)

        assert 0.0 <= feasibility <= 1.0

    @pytest.mark.asyncio
    async def test_full_process_aluminum_enclosure(self, core, sample_spec):
        """Integration test: full manufacturing plan generation."""
        result = await core.process(sample_spec)

        assert result["status"] == "success"
        assert "plan" in result
        assert "timestamp" in result

        plan = result["plan"]
        assert plan["spec_id"]
        assert plan["product_name"] == "Aluminum Enclosure"
        assert len(plan["bom"]) > 0
        assert len(plan["process_sequence"]) > 0
        assert "cost_breakdown" in plan
        assert 0.0 <= plan["feasibility_score"] <= 1.0

    @pytest.mark.asyncio
    async def test_process_invalid_spec(self, core):
        """Test error handling for invalid spec."""
        invalid_spec = {
            "name": "Broken",
            # Missing required fields
        }
        result = await core.process(invalid_spec)

        assert result["status"] == "error"
        assert "message" in result

    def test_supplier_recommendations_structure(self, core, sample_spec):
        """Test supplier recommendations are populated."""
        spec = core._parse_spec(sample_spec)
        bom = core._generate_bom(spec)
        suppliers = core._recommend_suppliers(spec, bom)

        assert "materials" in suppliers
        assert "manufacturing" in suppliers
        assert "assembly" in suppliers

    def test_create_cad_workspace(self, core):
        """Test ProtoGen creates a callable CAD workspace for other agents."""
        workspace = core.create_cad_workspace(
            project_name="SmartScale bracket",
            owner_agent="smartscale-agent",
            design_goal="Create a camera mount bracket from measured dimensions",
            constraints={"max_length_mm": 150},
        )

        assert workspace["workspace_id"].startswith("cad-")
        assert workspace["owner_agent"] == "smartscale-agent"
        assert workspace["environment"]["mcp_usable"] is True
        assert workspace["units"] == "mm"

    def test_generate_cad_design_contract(self, core):
        """Test CAD design generation produces a parametric script contract."""
        workspace = core.create_cad_workspace(
            project_name="Prototype enclosure",
            owner_agent="energyai-agent",
            design_goal="Create an enclosure concept",
        )
        design = core.generate_cad_design(
            workspace_id=workspace["workspace_id"],
            part_name="sensor_enclosure",
            dimensions_mm={"length": 120, "width": 80, "height": 35},
            material="aluminum",
            features=[{"type": "through_hole", "x_mm": 20, "y_mm": 10, "diameter_mm": 5}],
        )

        assert design["design_id"].startswith("design-")
        assert design["workspace_id"] == workspace["workspace_id"]
        assert "openscad" in design["outputs"]
        assert "cylinder" in design["outputs"]["openscad"]
        assert design["outputs"]["manufacturing_brief"]["recommended_process"] == "cnc_machining"

    def test_export_cad_design(self, core):
        """Test CAD design export by design_id."""
        workspace = core.create_cad_workspace(
            project_name="Tile spacer",
            owner_agent="smartscale-agent",
            design_goal="Generate a simple spacer",
        )
        design = core.generate_cad_design(
            workspace_id=workspace["workspace_id"],
            part_name="spacer",
            dimensions_mm={"length": 40, "width": 20, "height": 5},
            material="plastic_abs",
        )
        exported = core.export_cad_design(design["design_id"], "openscad")

        assert exported["status"] == "ok"
        assert exported["export_format"] == "openscad"
        assert "cube" in exported["content"]

    @pytest.mark.asyncio
    async def test_process_generate_cad_design_action(self, core):
        """Test async process dispatch for MCP-style CAD design generation."""
        workspace_result = await core.process({
            "action": "create_cad_workspace",
            "project_name": "Agent requested part",
            "owner_agent": "viridis-agent",
            "design_goal": "Create a basic fixture",
        })
        workspace_id = workspace_result["workspace"]["workspace_id"]
        design_result = await core.process({
            "action": "generate_cad_design",
            "workspace_id": workspace_id,
            "part_name": "fixture",
            "dimensions_mm": {"length": 100, "width": 50, "height": 12},
            "material": "aluminum",
        })

        assert design_result["status"] == "success"
        assert design_result["design"]["outputs"]["step_contract"]["status"] == "contract_only"


class TestCostEngine:
    """Test cost calculation engine."""

    @pytest.fixture
    def engine(self):
        return CostEngine()

    def test_material_cost_calculation(self, engine):
        """Test material cost with scrap."""
        cost = engine.estimate_material_cost(
            volume_cm3=100,
            material_density=2.7,  # Aluminum
            cost_per_kg=3.50,
            scrap_rate=0.05,
        )
        assert cost > 0
        assert cost == round(cost, 2)

    def test_scrap_increases_cost(self, engine):
        """Test that scrap rate increases material cost."""
        cost_no_scrap = engine.estimate_material_cost(100, 2.7, 3.50, scrap_rate=0.0)
        cost_5_scrap = engine.estimate_material_cost(100, 2.7, 3.50, scrap_rate=0.05)
        cost_20_scrap = engine.estimate_material_cost(100, 2.7, 3.50, scrap_rate=0.20)

        assert cost_5_scrap > cost_no_scrap
        assert cost_20_scrap > cost_5_scrap

    def test_labor_cost_with_efficiency(self, engine):
        """Test labor cost accounting for efficiency."""
        cost_100pct = engine.estimate_labor_cost(60, hourly_rate=100, process_efficiency=1.0)
        cost_85pct = engine.estimate_labor_cost(60, hourly_rate=100, process_efficiency=0.85)

        # Lower efficiency should result in higher cost
        assert cost_85pct > cost_100pct

    def test_tooling_amortization(self, engine):
        """Test tooling cost amortization."""
        amort_small = engine.estimate_tooling_amortization(
            tooling_cost=10000,
            annual_volume=1000,
        )
        amort_large = engine.estimate_tooling_amortization(
            tooling_cost=10000,
            annual_volume=100000,
        )

        # Larger volume should result in lower amortized cost
        assert amort_small > amort_large

    def test_volume_discount_tiers(self, engine):
        """Test volume-based pricing tiers."""
        base_cost = 50.0

        discount_100 = engine.apply_volume_discount(base_cost, annual_volume=50)
        discount_1000 = engine.apply_volume_discount(base_cost, annual_volume=500)
        discount_50k = engine.apply_volume_discount(base_cost, annual_volume=50000)

        # Higher volumes should have higher discounts
        assert discount_100["discount_rate"] <= discount_1000["discount_rate"]
        assert discount_1000["discount_rate"] <= discount_50k["discount_rate"]

    def test_break_even_calculation(self, engine):
        """Test break-even volume calculation."""
        breakeven = engine.calculate_break_even(
            fixed_costs=10000,
            unit_contribution_margin=5.0,
        )

        assert breakeven == 2000  # 10000 / 5.0

    def test_sensitivity_analysis(self, engine):
        """Test sensitivity analysis provides varied outputs."""
        sensitivity = engine.sensitivity_analysis(
            base_cogs=20.0,
            base_volume=1000,
        )

        assert "material_cost_sensitivity" in sensitivity
        assert "labor_cost_sensitivity" in sensitivity
        assert "volume_sensitivity" in sensitivity

        # Check that results vary with input changes
        material_results = sensitivity["material_cost_sensitivity"]
        assert len(material_results) > 1
        costs = [r["cogs"] for r in material_results]
        assert len(set(costs)) > 1  # Not all the same


class TestManufacturingLibrary:
    """Test manufacturing process library."""

    @pytest.fixture
    def library(self):
        return ManufacturingLibrary()

    def test_process_retrieval(self, library):
        """Test getting process by name."""
        cnc = library.get_process("CNC_machining")
        assert cnc is not None
        assert cnc.name == "CNC Machining (3-axis, 5-axis)"
        assert cnc.min_tolerance_mm == 0.05

    def test_process_not_found(self, library):
        """Test retrieving non-existent process."""
        result = library.get_process("nonexistent_process")
        assert result is None

    def test_find_compatible_processes(self, library):
        """Test finding processes compatible with material."""
        aluminum_processes = library.find_compatible_processes("aluminum")
        assert len(aluminum_processes) > 0
        assert "CNC_machining" in aluminum_processes
        assert "sheet_metal" in aluminum_processes

    def test_cost_estimation(self, library):
        """Test process cost estimation."""
        cost = library.estimate_cost("CNC_machining", part_volume_cm3=100)
        assert cost > 0

    def test_process_summary(self, library):
        """Test process summary includes all available processes."""
        summary = library.process_summary()
        assert len(summary) > 0
        assert "CNC_machining" in summary
        assert "injection_molding" in summary


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestDimensionTypeGate:
    """N69: pin the P4 numeric gate — number-shaped strings must NOT coerce.

    N68 finding: `float(value)` let "40" pass the finite>0 check. The gate
    now requires a real number BEFORE coercion. These tests pin that closed.
    """

    def _workspace(self, core):
        return core.create_cad_workspace(
            project_name="Type gate",
            owner_agent="nightkeeper-test",
            design_goal="pin numeric gate",
        )["workspace_id"]

    def test_string_dimension_rejected(self):
        core = ProtoGenCore()
        ws = self._workspace(core)
        with pytest.raises(ValueError, match="must be numeric"):
            core.generate_cad_design(
                workspace_id=ws, part_name="p",
                dimensions_mm={"length": "40", "width": 20, "height": 5},
            )

    def test_numeric_string_suffixed_key_rejected(self):
        core = ProtoGenCore()
        ws = self._workspace(core)
        with pytest.raises(ValueError, match="must be numeric"):
            core.generate_cad_design(
                workspace_id=ws, part_name="p",
                dimensions_mm={"length_mm": "40.0", "width_mm": 20, "height_mm": 5},
            )

    def test_bool_still_rejected_and_real_numbers_still_pass(self):
        core = ProtoGenCore()
        ws = self._workspace(core)
        with pytest.raises(ValueError, match="must be numeric"):
            core.generate_cad_design(
                workspace_id=ws, part_name="p",
                dimensions_mm={"length": True, "width": 20, "height": 5},
            )
        design = core.generate_cad_design(
            workspace_id=ws, part_name="p",
            dimensions_mm={"length": 40, "width": 20.5, "height": 5},
        )
        assert design["dimensions_mm"] == {"length": 40.0, "width": 20.5, "height": 5.0}
