from typing import Dict, Any, List
import re

STANDARD_DB = [
    {"name":"credit card (CR80)", "width_mm":85.60, "height_mm":53.98, "thickness_mm":0.76},
    {"name":"US Letter", "width_mm":215.9, "height_mm":279.4},
    {"name":"A4", "width_mm":210.0, "height_mm":297.0},
    {"name":"2x4 lumber (US actual)", "width_mm":38.1, "height_mm":88.9},
]

class SpecsService:
    def __init__(self, abo_index_path: str = None):
        self.abo_index_path = abo_index_path
        self.cache = {}

    def search(self, query: str) -> Dict[str, Any]:
        q = query.lower().strip()
        hits: List[Dict[str, Any]] = []

        # 1) Local standard DB
        for row in STANDARD_DB:
            if any(tok in row["name"].lower() for tok in re.findall(r"[\w]+", q)):
                hits.append({"source":"standard", **row})

        # 2) Optional ABO JSON (if you provide a path to predownloaded metadata)
        if self.abo_index_path and "abo_loaded" not in self.cache:
            try:
                import json
                with open(self.abo_index_path, "r") as f:
                    self.cache["abo"] = json.load(f)
                self.cache["abo_loaded"] = True
            except Exception:
                self.cache["abo"] = []
                self.cache["abo_loaded"] = True

        if self.cache.get("abo"):
            for item in self.cache["abo"][:1000]:  # limit scan in demo
                title = " ".join([n.get("value","") for n in item.get("item_name", [])])
                if any(tok in title.lower() for tok in re.findall(r"[\w]+", q)):
                    dims = item.get("item_dimensions", {})
                    if dims:
                        hits.append({
                            "source":"ABO",
                            "item_id": item.get("item_id"),
                            "title": title,
                            "dimensions": dims
                        })

        return {"query": query, "hits": hits}
