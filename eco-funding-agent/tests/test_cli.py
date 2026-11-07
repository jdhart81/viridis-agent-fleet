from __future__ import annotations

import json

from conftest import DATA

from viridis_eco_funding.cli import main


def run(capsys, *args):
    code = main(list(args))
    out = capsys.readouterr()
    return code, out.out, out.err


def test_value_receipt_verify_simulate_describe(capsys, tmp_path):
    site = str(DATA / "woodland_site.json")
    code, out, _ = run(capsys, "value", site)
    assert code == 0 and json.loads(out)["site_id"].startswith("mad-river")
    code, out, _ = run(capsys, "explain", site)
    assert code == 0 and json.loads(out)["steps"]
    code, receipt_text, _ = run(capsys, "receipt", site)
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(receipt_text)
    code, out, _ = run(capsys, "verify", str(receipt_path))
    assert code == 0 and json.loads(out)["valid"] is True
    obs = tmp_path / "obs.json"
    obs.write_text(json.dumps([{"period": 0, "receipt": json.loads(receipt_text)}]))
    code, out, _ = run(capsys, "simulate", str(DATA / "woodland_pool.json"), str(obs))
    assert code == 0 and json.loads(out)["simulation_only"] is True
    code, out, _ = run(capsys, "describe")
    assert code == 0 and "conjecture" in json.loads(out)["explanation"]


def test_errors_and_invalid_receipt(capsys, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"site_id": "x"}')
    code, _, err = run(capsys, "value", str(bad))
    assert code == 2 and "biodiversity" in err
    bad.write_text('{"receipt_version": "x"}')
    code, out, _ = run(capsys, "verify", str(bad))
    assert code == 1 and json.loads(out)["valid"] is False
