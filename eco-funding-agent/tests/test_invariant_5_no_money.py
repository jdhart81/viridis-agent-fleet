"""Invariant 5 - No money movement anywhere in the codebase: no payment SDKs, private
keys, wallet code or token minting. This test scans the repository and fails on any hit.

Layers:
* every Python file in the repository (not only ``src/``) is parsed, and any import of a
  payment, crypto-wallet or signing SDK fails, whatever the import form or alias;
* every text file is grepped for key material, payment-API hosts and endpoints,
  dependency pins and ``pip install`` lines naming such SDKs, and payment env variables;
* code and configuration files additionally get wallet / mint / transfer / payout
  patterns (prose may state the boundary, e.g. "no wallets", so it gets the narrower set);
* dependency manifests and source imports are checked directly.

The scanners are themselves tested: known bypass attempts are injected into a temporary
copy of the repository and must be caught (``test_scanner_catches_injected_violations``).
A grep can never be complete; the read-only layer (Invariant 6) independently blocks
any write-capable network code in ``src/``.
"""

from __future__ import annotations

import ast
import re
import shutil
import sys
import tomllib
from pathlib import Path

import pytest
from conftest import ROOT

SELF_NAME = Path(__file__).name
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", "build", "dist",
             ".ipynb_checkpoints", "htmlcov", "_to_delete"}
SKIP_SUFFIXES = {".png", ".jpg", ".pdf", ".pyc", ".whl", ".gz", ".zip", ".bundle"}
SKIP_NAMES = {"LICENSE", ".coverage"}

PAYMENT_SDKS = sorted({
    "stripe", "paypalrestsdk", "paypal", "paypalhttp", "braintree", "adyen", "squareup", "square",
    "plaid", "dwolla", "dwollav2", "wise", "coinbase", "coinbase_commerce", "web3", "eth_account",
    "eth_keys", "ethers", "solana", "solders", "anchorpy", "bitcoinlib", "bit", "pycoin", "monero",
    "algosdk", "xrpl", "stellar_sdk", "brownie", "ape", "hdwallet", "bip_utils", "mnemonic",
    "nacl", "pynacl", "ecdsa", "coincurve", "secp256k1", "cryptography", "Crypto", "Cryptodome",
    "jwt", "jose", "authlib", "mangopay", "gocardless_pro", "razorpay", "mollie", "checkout_sdk",
    "venmo", "cashapp", "lightning", "lnd", "pyln",
})
DIST_NAMES = PAYMENT_SDKS + ["eth-account", "stellar-sdk", "paypal-checkout-serversdk",
                             "coinbase-commerce", "checkout-sdk", "pycryptodome", "pyjwt",
                             "python-jose", "gocardless-pro", "web3py"]
_DIST = "|".join(re.escape(n) for n in sorted(DIST_NAMES, key=len, reverse=True))

KEY_MATERIAL = [
    r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED |PGP )?PRIVATE KEY",
    r"\b0x[0-9a-fA-F]{64}\b",                         # raw 256-bit hex key
    r"\b(?:sk|rk|pk)_(?:live|test)_[0-9A-Za-z]{10,}",  # payment-processor keys
    r"\b[5KL][1-9A-HJ-NP-Za-km-z]{50,51}\b",          # WIF private keys
    r"\b[xt]prv[1-9A-HJ-NP-Za-km-z]{100,}",           # extended private keys
]
EVERYWHERE = KEY_MATERIAL + [
    r"\b(?:api|api-m|api\.sandbox|connect|checkout|payments?)\.(?:stripe|paypal|braintreegateway|"
    r"squareup|adyen|plaid|wise|coinbase|gocardless|razorpay|mollie)\.com\b",
    r"\b(?:mainnet|sepolia|goerli|polygon-mainnet)\.infura\.io\b", r"\balchemy(?:api)?\.io\b",
    r"\b(?:api\.)?etherscan\.io\b", r"\brpc\.ankr\.com\b", r"\bapi\.mainnet-beta\.solana\.com\b",
    r"/v1/(?:charges|transfers|payouts|payment_intents|refunds|customers/\w+/sources)\b",
    r"\b(?:STRIPE|PAYPAL|BRAINTREE|PLAID|COINBASE|SQUARE|ADYEN|WALLET|MNEMONIC|INFURA|ALCHEMY)_\w+",
    rf"\bpip3?\s+install\b[^\n]*?(?<![\w.-])(?:{_DIST})(?![\w.-])",
    rf"(?m)^\s*[\"']?(?:{_DIST})\s*(?:[<>=!~]=?|\[|[\"']?\s*,?\s*$)",   # requirements / deps lines
]
CODE_ONLY = [
    r"\bprivate[_ ]?key\b", r"\bprivkey\b", r"\bsecret[_ ]?key\b", r"\bseed[_ ]?phrase\b",
    r"\bwallets?\w*\s*[=(]", r"\bmint\w*\s*\(", r"\bERC-?(?:20|721|1155)\b",
    r"\b(?:send|sign)_?(?:raw_?)?transaction\b", r"\btransfer(?:From)?\s*\(", r"\bpayouts?\w*\s*\(",
    r"\bcharges?\.create\b", r"\bPaymentIntent\b", r"\bcheckout\b",
]
CODE_SUFFIXES = {".py", ".toml", ".cfg", ".ini", ".json", ".yml", ".yaml", ".js", ".mjs", ".ts",
                 ".sh", ".bash", ".zsh", ".ipynb", ".txt", ".lock", ".env", ".in"}
PROSE_SUFFIXES = {".md", ".cff", ".rst"}


def repo_files(root: Path):
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == SELF_NAME:
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        if path.suffix in SKIP_SUFFIXES or path.name in SKIP_NAMES:
            continue
        yield path


def _import_roots(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.lineno, node.module.split(".")[0]
        elif (isinstance(node, ast.Call) and getattr(node.func, "attr", getattr(node.func, "id", ""))
              in {"import_module", "__import__"} and node.args and isinstance(node.args[0], ast.Constant)):
            yield node.lineno, str(node.args[0].value).split(".")[0]


def scan_money(root: Path) -> list[str]:
    hits = []
    sdk_set = set(PAYMENT_SDKS)
    for path in repo_files(root):
        rel = path.relative_to(root)
        text = path.read_text(encoding="utf-8", errors="replace")
        if path.suffix == ".py":
            try:
                tree = ast.parse(text)
            except SyntaxError:
                hits.append(f"{rel}: unparsable Python")
                tree = None
            if tree is not None:
                for line, root_name in _import_roots(tree):
                    if root_name in sdk_set:
                        hits.append(f"{rel}:{line}: imports {root_name}")
        is_code = path.suffix in CODE_SUFFIXES or path.name in {"Dockerfile", "Makefile", "Procfile"} \
            or path.name.startswith("requirements")
        patterns = EVERYWHERE + (CODE_ONLY if is_code else [])
        for pattern in patterns:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                line = text.count("\n", 0, match.start()) + 1
                hits.append(f"{rel}:{line}: {match.group(0).strip()!r}")
    return hits


def test_scan_covers_the_code():
    names = {p.relative_to(ROOT).as_posix() for p in repo_files(ROOT)}
    for required in ("src/viridis_eco_funding/pool/simulator.py", "src/viridis_eco_funding/mcp_server.py",
                     "pyproject.toml", "examples/woodland_valuation.ipynb", "tests/conftest.py"):
        assert required in names


def test_no_money_patterns_in_repository():
    hits = scan_money(ROOT)
    assert not hits, "money-movement patterns found:\n" + "\n".join(hits)


INJECTIONS = [
    ("tools/payout.py", "import json, stripe\nstripe.api_key = KEY\n"),
    ("tools/alias.py", "import importlib\nlib = importlib.import_module('web3')\n"),
    ("tools/from_import.py", "from eth_account import Account as A\n"),
    ("requirements.txt", "stripe==9.0.0\n"),
    ("requirements-dev.txt", "web3\n"),
    ("scripts/setup.sh", "pip install stripe web3\n"),
    ("src/viridis_eco_funding/sneaky.py",
     "from urllib.request import urlopen as _fetch\n"
     "_fetch('https://api.stripe.com/v1/transfers', body)\n"),
    ("src/viridis_eco_funding/env.py", "import os\nKEY = os.environ['STRIPE_SECRET']\n"),
    # Bait strings are assembled at runtime so secret scanners (gitleaks, the fleet's
    # open-core boundary) never see a key-shaped literal in this file.
    ("docs/notes.md", "-----BEGIN EC " + "PRIVATE KEY-----\nabc\n"),
    ("pool_extra.py", "def mint_tokens(n): pass\nmint_tokens(5)\n"),
    ("wallet.py", "wallet = load()\n"),
    ("cfg.json", '{"key": "' + "sk_" + "live_" + 'abcdefghijklmnop"}'),
]


@pytest.mark.parametrize("relative, content", INJECTIONS, ids=[i[0] for i in INJECTIONS])
def test_scanner_catches_injected_violations(tmp_path, relative, content):
    copy = tmp_path / "repo"
    shutil.copytree(ROOT, copy, ignore=shutil.ignore_patterns(*SKIP_DIRS))
    assert scan_money(copy) == []
    target = copy / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    assert scan_money(copy), f"scanner missed {relative}"


def test_no_payment_dependencies():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    deps = list(project.get("dependencies", []))
    for extra in project.get("optional-dependencies", {}).values():
        deps.extend(extra)
    names = {re.split(r"[<>=!~\[ ;]", d, maxsplit=1)[0].lower() for d in deps}
    assert names.isdisjoint({s.lower() for s in DIST_NAMES}), names
    assert project.get("dependencies") == [], "the core must stay standard-library only"


def test_source_imports_are_stdlib_or_mcp():
    # fleet_utils: the fleet's isError helper (contract C4), present only inside fleet trees
    allowed_third_party = {"mcp", "uvicorn", "fleet_utils"}
    stdlib = set(sys.stdlib_module_names)
    for path in list((ROOT / "src").rglob("*.py")) + list((ROOT / "adapters").rglob("*.py")):
        for _, root in _import_roots(ast.parse(path.read_text(encoding="utf-8"))):
            assert root in stdlib or root in allowed_third_party or root == "viridis_eco_funding", \
                f"{path.relative_to(ROOT)} imports {root}"
            if root in allowed_third_party:
                assert path.name == "mcp_server.py", f"{path.name} must not import {root}"
