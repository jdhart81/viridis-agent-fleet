"""Canonical JSON: the byte form that receipts are hashed over.

Rules (stable across versions of this package; changing them is a method-version bump):

* Objects: keys must be strings, emitted sorted by Unicode code point.
* No insignificant whitespace; separators are ``,`` and ``:``.
* Strings: JSON-escaped with ``ensure_ascii=True`` so the bytes are pure ASCII.
* Integers: plain base-10.
* Decimals: normalized (no trailing zeros). Plain notation when the decimal exponent of
  the leading digit is in [-7, 21); otherwise ``d.dddE+n`` scientific notation.
* Binary floats are rejected inside the core (they are converted at the boundary), so a
  float can never leak platform-dependent formatting into a hash.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from decimal import Decimal
from typing import Any

from ._decimal import CONTEXT, pinned, to_decimal


def format_decimal(value: Decimal) -> str:
    if not value.is_finite():
        raise ValueError("non-finite number cannot be serialized")
    if value.is_zero():
        return "0"
    # Context-free formatting: only the pinned CONTEXT is used (for normalize), never the
    # caller's thread-local context, so the bytes cannot depend on the caller's settings.
    normalized = value.normalize(CONTEXT)
    sign, digits, exponent = normalized.as_tuple()
    adjusted = normalized.adjusted()
    text_digits = "".join(str(d) for d in digits)
    prefix = "-" if sign else ""
    if -7 <= adjusted < 21:
        if exponent >= 0:
            return prefix + text_digits + "0" * exponent
        point = len(text_digits) + exponent
        if point > 0:
            return prefix + text_digits[:point] + "." + text_digits[point:]
        return prefix + "0." + "0" * (-point) + text_digits
    mantissa = text_digits[0] + ("." + text_digits[1:] if len(text_digits) > 1 else "")
    return f"{prefix}{mantissa}E{adjusted:+d}"


def _encode(obj: Any, out: list[str]) -> None:
    if obj is None:
        out.append("null")
    elif obj is True:
        out.append("true")
    elif obj is False:
        out.append("false")
    elif isinstance(obj, int):
        out.append(str(obj))
    elif isinstance(obj, Decimal):
        out.append(format_decimal(obj))
    elif isinstance(obj, float):
        raise TypeError("binary float in canonical data; convert with to_decimal() first")
    elif isinstance(obj, str):
        out.append(json.dumps(obj, ensure_ascii=True))
    elif isinstance(obj, dict):
        keys = list(obj.keys())
        for key in keys:
            if not isinstance(key, str):
                raise TypeError(f"object key must be str, got {type(key).__name__}")
        out.append("{")
        for index, key in enumerate(sorted(keys)):
            if index:
                out.append(",")
            out.append(json.dumps(key, ensure_ascii=True))
            out.append(":")
            _encode(obj[key], out)
        out.append("}")
    elif isinstance(obj, (list, tuple)):
        out.append("[")
        for index, item in enumerate(obj):
            if index:
                out.append(",")
            _encode(item, out)
        out.append("]")
    else:
        raise TypeError(f"cannot canonicalize {type(obj).__name__}")


@pinned
def canonical_dumps(obj: Any) -> str:
    out: list[str] = []
    _encode(obj, out)
    return "".join(out)


def canonical_bytes(obj: Any) -> bytes:
    return canonical_dumps(obj).encode("ascii")


def sha256_hex(obj: Any) -> str:
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


def loads_decimal(text: str | bytes) -> Any:
    """Parse JSON with every non-integer number as Decimal (no binary floats)."""
    return json.loads(text, parse_float=Decimal, parse_constant=_reject_constant)


def _reject_constant(name: str) -> Any:
    raise ValueError(f"JSON constant {name} is not allowed")


def to_canonical_data(obj: Any) -> Any:
    """Deep-convert user data (which may contain floats) into canonical-safe data.

    Strings are NFC-normalized so visually identical text gives identical bytes."""
    if isinstance(obj, str):
        return unicodedata.normalize("NFC", obj)
    if isinstance(obj, bool) or obj is None or isinstance(obj, (int, Decimal)):
        return obj
    if isinstance(obj, float):
        return to_decimal(obj)
    if isinstance(obj, dict):
        return {unicodedata.normalize("NFC", str(k)): to_canonical_data(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_canonical_data(v) for v in obj]
    raise TypeError(f"unsupported type {type(obj).__name__}")


def to_plain_json(obj: Any) -> Any:
    """Canonical data -> plain JSON types (floats) for transports such as MCP."""
    return json.loads(canonical_dumps(obj))
