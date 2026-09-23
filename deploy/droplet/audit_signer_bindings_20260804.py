#!/usr/bin/env python3
"""Report signer variable names and derived public addresses without secrets."""

from __future__ import annotations

import json
import os
import re


NAME_PATTERN = re.compile(r"(?:PRIVATE_KEY|WALLET_KEY|SIGNER_KEY)$", re.IGNORECASE)
HEX_KEY = re.compile(r"^(?:0x)?[0-9a-fA-F]{64}$")


def main() -> None:
    try:
        from eth_account import Account
    except Exception:
        Account = None

    bindings = []
    for name, value in sorted(os.environ.items()):
        if not NAME_PATTERN.search(name):
            continue
        record = {"variable": name, "present": bool(value), "public_address": None}
        if value and HEX_KEY.fullmatch(value) and Account is not None:
            try:
                record["public_address"] = Account.from_key(value).address
            except Exception:
                record["derivation_status"] = "failed_without_secret_output"
        elif value:
            record["derivation_status"] = (
                "address_library_unavailable" if Account is None else "not_a_raw_hex_signer"
            )
        bindings.append(record)
    print(json.dumps({"signer_bindings": bindings}, sort_keys=True))


if __name__ == "__main__":
    main()
