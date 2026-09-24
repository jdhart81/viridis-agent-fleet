"""
Manufacturing Process Library
Real process models: tolerances, cost rates, capabilities, constraints.
"""

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ProcessCapabilities:
    """Defines a manufacturing process and its technical capabilities."""
    name: str  # e.g., "CNC_machining", "injection_molding"
    category: str  # "forming", "finishing", "assembly", "testing"
    min_tolerance_mm: float  # Smallest achievable tolerance
    surface_roughness_ra: float  # Ra in micrometers
    hourly_rate: float  # $/hour
    setup_time_hours: float
    min_batch_size: int
    max_batch_size: int
    lead_time_days: int
    compatible_materials: list[str]
    max_part_dimension_mm: float
    notes: str


class ManufacturingLibrary:
    """Curated library of real manufacturing processes."""

    def __init__(self):
        self.processes = self._init_processes()

    def _init_processes(self) -> dict[str, ProcessCapabilities]:
        """Initialize library with real process data."""
        return {
            "CNC_machining": ProcessCapabilities(
                name="CNC Machining (3-axis, 5-axis)",
                category="forming",
                min_tolerance_mm=0.05,
                surface_roughness_ra=1.6,
                hourly_rate=150,
                setup_time_hours=4,
                min_batch_size=1,
                max_batch_size=10000,
                lead_time_days=7,
                compatible_materials=[
                    "aluminum", "steel", "stainless_steel", "titanium",
                    "brass", "copper", "plastics"
                ],
                max_part_dimension_mm=500,
                notes="Subtractive, high precision, flexible batch sizes",
            ),

            "injection_molding": ProcessCapabilities(
                name="Injection Molding",
                category="forming",
                min_tolerance_mm=0.1,
                surface_roughness_ra=3.2,
                hourly_rate=120,
                setup_time_hours=8,
                min_batch_size=5000,
                max_batch_size=1000000,
                lead_time_days=21,
                compatible_materials=[
                    "plastic_abs", "plastic_petg", "polycarbonate",
                    "nylon", "polystyrene", "polyethylene"
                ],
                max_part_dimension_mm=300,
                notes="High volume only, high tooling cost ($5K-$50K), amortize >10K units",
            ),

            "3d_printing_fdm": ProcessCapabilities(
                name="3D Printing (FDM/FFF)",
                category="forming",
                min_tolerance_mm=0.2,
                surface_roughness_ra=6.3,
                hourly_rate=80,
                setup_time_hours=1,
                min_batch_size=1,
                max_batch_size=100,
                lead_time_days=3,
                compatible_materials=["pla", "abs", "petg", "nylon", "tpu"],
                max_part_dimension_mm=200,
                notes="Rapid prototyping, low volume, post-processing often needed",
            ),

            "3d_printing_sla": ProcessCapabilities(
                name="3D Printing (SLA/DLP Resin)",
                category="forming",
                min_tolerance_mm=0.1,
                surface_roughness_ra=3.2,
                hourly_rate=120,
                setup_time_hours=2,
                min_batch_size=1,
                max_batch_size=50,
                lead_time_days=4,
                compatible_materials=["castable_resin", "standard_resin", "tough_resin"],
                max_part_dimension_mm=150,
                notes="High precision prototyping, excellent surface finish",
            ),

            "sheet_metal": ProcessCapabilities(
                name="Sheet Metal Fabrication",
                category="forming",
                min_tolerance_mm=0.1,
                surface_roughness_ra=1.6,
                hourly_rate=100,
                setup_time_hours=3,
                min_batch_size=10,
                max_batch_size=50000,
                lead_time_days=7,
                compatible_materials=[
                    "steel", "aluminum", "stainless_steel", "copper", "brass"
                ],
                max_part_dimension_mm=1000,
                notes="Good for enclosures, brackets, panels. Stamping cost-effective >1K units",
            ),

            "die_casting": ProcessCapabilities(
                name="Die Casting (Aluminum, Zinc)",
                category="forming",
                min_tolerance_mm=0.2,
                surface_roughness_ra=3.2,
                hourly_rate=90,
                setup_time_hours=6,
                min_batch_size=1000,
                max_batch_size=100000,
                lead_time_days=14,
                compatible_materials=["aluminum", "zinc", "magnesium"],
                max_part_dimension_mm=400,
                notes="Medium-high volume, complex shapes, tooling $3K-$20K",
            ),

            "sand_casting": ProcessCapabilities(
                name="Sand Casting",
                category="forming",
                min_tolerance_mm=0.5,
                surface_roughness_ra=6.3,
                hourly_rate=60,
                setup_time_hours=2,
                min_batch_size=5,
                max_batch_size=10000,
                lead_time_days=14,
                compatible_materials=["aluminum", "steel", "iron", "copper"],
                max_part_dimension_mm=800,
                notes="Low tooling cost, loose tolerances, post-machining often needed",
            ),

            "powder_coating": ProcessCapabilities(
                name="Powder Coating",
                category="finishing",
                min_tolerance_mm=0.0,
                surface_roughness_ra=6.3,
                hourly_rate=80,
                setup_time_hours=1,
                min_batch_size=1,
                max_batch_size=100000,
                lead_time_days=5,
                compatible_materials=["steel", "aluminum", "stainless_steel"],
                max_part_dimension_mm=1000,
                notes="Excellent corrosion resistance, uniform coverage, no drips",
            ),

            "anodizing": ProcessCapabilities(
                name="Anodizing (Type II/III)",
                category="finishing",
                min_tolerance_mm=0.0,
                surface_roughness_ra=3.2,
                hourly_rate=70,
                setup_time_hours=1,
                min_batch_size=1,
                max_batch_size=50000,
                lead_time_days=7,
                compatible_materials=["aluminum"],
                max_part_dimension_mm=500,
                notes="Type II: decorative, Type III: hardcoat for wear",
            ),

            "electroplating": ProcessCapabilities(
                name="Electroplating (Ni, Cr, Cu, Zn)",
                category="finishing",
                min_tolerance_mm=0.0,
                surface_roughness_ra=0.4,
                hourly_rate=90,
                setup_time_hours=2,
                min_batch_size=10,
                max_batch_size=10000,
                lead_time_days=7,
                compatible_materials=["steel", "brass", "copper"],
                max_part_dimension_mm=300,
                notes="Precise deposit thickness, excellent surface finish",
            ),

            "passivation": ProcessCapabilities(
                name="Passivation (Stainless Steel)",
                category="finishing",
                min_tolerance_mm=0.0,
                surface_roughness_ra=0.0,
                hourly_rate=50,
                setup_time_hours=0.5,
                min_batch_size=1,
                max_batch_size=100000,
                lead_time_days=3,
                compatible_materials=["stainless_steel"],
                max_part_dimension_mm=1000,
                notes="Removes iron contamination, improves corrosion resistance",
            ),

            "assembly": ProcessCapabilities(
                name="Manual/Semi-Automated Assembly",
                category="assembly",
                min_tolerance_mm=0.5,
                surface_roughness_ra=0.0,
                hourly_rate=60,
                setup_time_hours=2,
                min_batch_size=1,
                max_batch_size=10000,
                lead_time_days=3,
                compatible_materials=[],
                max_part_dimension_mm=1000,
                notes="Labor cost scales with complexity; automation break-even ~5K units",
            ),

            "functional_testing": ProcessCapabilities(
                name="Functional Testing & QC",
                category="testing",
                min_tolerance_mm=0.0,
                surface_roughness_ra=0.0,
                hourly_rate=80,
                setup_time_hours=1,
                min_batch_size=1,
                max_batch_size=10000,
                lead_time_days=2,
                compatible_materials=[],
                max_part_dimension_mm=1000,
                notes="AQL sampling, 100% test, or statistical sampling",
            ),
        }

    def get_process(self, name: str) -> Optional[ProcessCapabilities]:
        """Retrieve process by name."""
        return self.processes.get(name)

    def find_compatible_processes(self, material: str) -> list[str]:
        """Find all processes compatible with given material."""
        compatible = []
        for name, proc in self.processes.items():
            if material in proc.compatible_materials:
                compatible.append(name)
        return compatible

    def estimate_cost(self, process_name: str, part_volume_cm3: float,
                      setup_hours: float = None) -> float:
        """Estimate cost for a process given part volume."""
        proc = self.get_process(process_name)
        if not proc:
            return 0.0

        # Rough estimate: hourly rate * (setup + production time)
        # Production time scales with part volume
        production_hours = max(0.25, part_volume_cm3 / 100)  # 100cm³ per hour baseline
        setup_h = setup_hours or proc.setup_time_hours

        return proc.hourly_rate * (setup_h + production_hours)

    def process_summary(self) -> dict:
        """Return summary of all available processes."""
        summary = {}
        for name, proc in self.processes.items():
            summary[name] = {
                "category": proc.category,
                "min_tolerance_mm": proc.min_tolerance_mm,
                "hourly_rate": proc.hourly_rate,
                "lead_time_days": proc.lead_time_days,
                "min_batch": proc.min_batch_size,
                "max_batch": proc.max_batch_size,
                "materials": proc.compatible_materials,
            }
        return summary
