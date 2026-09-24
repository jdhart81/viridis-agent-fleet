"""Thin programmatic adapter around the deterministic takeoff core."""

from __future__ import annotations

from typing import Any, Optional

from .core import QuantityTakeoffCore, build


class QuantityTakeoffAdapter:
    """Fleet-friendly action adapter; it contains no calculation logic."""

    def __init__(self, core: Optional[QuantityTakeoffCore] = None):
        self.core = core or build()

    async def calculate_takeoff(self, items: list[dict[str, Any]],
                                options: Optional[dict[str, Any]] = None) -> dict:
        return await self.core.process({"action": "calculate_takeoff", "items": items,
                                        "options": options or {}})

    async def list_assemblies(self) -> dict:
        return await self.core.process({"action": "list_assemblies"})

    async def get_assembly(self, assembly_type: str) -> dict:
        return await self.core.process({"action": "get_assembly",
                                        "assembly_type": assembly_type})

    async def list_material_pack(self) -> dict:
        return await self.core.process({"action": "list_material_pack"})

    async def get_material_pack(self) -> dict:
        return await self.core.process({"action": "get_material_pack"})

    async def verify_result(self, result: dict[str, Any]) -> dict:
        return await self.core.process({"action": "verify_result", "result": result})

    async def health(self) -> dict:
        return await self.core.health()

    def describe(self) -> dict:
        return self.core.describe()


def build_adapter(core: Optional[QuantityTakeoffCore] = None) -> QuantityTakeoffAdapter:
    return QuantityTakeoffAdapter(core)
