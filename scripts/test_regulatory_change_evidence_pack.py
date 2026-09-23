import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "regulatory_change_evidence_pack.py"
SPEC = importlib.util.spec_from_file_location("evidence_pack_cli", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_markdown_preserves_proof_boundaries():
    pack = {
        "generated_at": "2026-08-14T12:00:00Z",
        "jurisdiction": "eu",
        "company_profile": {"company_name": "Example Co"},
        "live_source_monitoring": {
            "selected_source_count": 1,
            "retrieved_source_count": 1,
            "changed_count": 0,
            "baseline_count": 1,
            "unchanged_count": 0,
            "failed_count": 0,
            "sources": [{
                "authority": "European Commission",
                "change_status": "baseline_created",
                "retrieved_at": "2026-08-14T12:00:00Z",
                "sha256": "a" * 64,
                "source_url": "https://finance.ec.europa.eu/example",
                "title": "Example source",
                "published_on": "2026-07-03",
                "screening_summary": "The authority published a revised standard.",
                "review_focus": "Confirm scope and timing.",
                "diff_excerpt": [],
            }],
        },
        "curated_deadline_calendar": {
            "alert_level": "low", "change_count": 0, "changes": [],
        },
        "recommended_actions": [],
        "applicability_posture": {"notice": "Screening only."},
        "delivery_receipt": {"pack_sha256": "b" * 64},
    }
    rendered = MODULE.render_markdown(pack)
    assert "baseline is not presented as a detected regulatory change" in rendered
    assert "not evidence of buyer delivery" in rendered
    assert "Example Co" in rendered
