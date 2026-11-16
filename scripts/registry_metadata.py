#!/usr/bin/env python3
"""Registry listing metadata for every MCP Registry entry (RM1-RM6).

Directories score listings on an icon, a title, a website and complete tool
docs (mcptry: icon +4, title +2, website +3). This script gives every entry
those fields and writes the icon images, in the style of the existing
assets/listing-logos tiles.

    python3 scripts/registry_metadata.py icons    # write missing icon PNGs
    python3 scripts/registry_metadata.py apply    # update server.json files
    python3 scripts/registry_metadata.py check    # fail if anything is stale

RM1 Every entry in PUBLISH has an icon (PNG, 400x400, served from this repo
    on GitHub), a title of at most 100 characters, and a websiteUrl pointing
    at its docs page (docs/servers/<name>.md).
RM2 The listing version is the hosted release: the agent's open-core release
    with the patch number raised by one (0.2.0 -> 0.2.1). The open-core
    release it builds on is recorded under _meta publisher-provided
    viridis.release. The hosted gateway reports the listing version as
    serverInfo.version exactly when its own release equals that record, so
    registry and server never disagree. (SemVer build metadata such as
    0.2.0+h1115 was tried first: it sorts equal to 0.2.0, so the registry kept
    the old listing as latest.) `latest-check` confirms each new version sorts
    above the registry's current latest before publishing.
RM3 Name, repository and remotes are never changed here. A description is
    replaced only where DESCRIPTIONS gives one: the registry caps descriptions
    at 100 characters and 18 had been cut off mid-word; each replacement is a
    complete sentence that restates the old text without new claims.
RM4 Entries in HOLD are left untouched, with the reason recorded.
RM5 Existing hand-made icons are kept; generated icons are deterministic.
RM6 apply is idempotent.
RM8 A SELF_VERSIONED server's listing version is its agent.yaml release
    exactly; it must sort above the registry's latest, so it changes only
    with a real release.
RM7 deploy/mcp-publish holds an older copy of the same registry names; a
    managed entry's copy there is kept identical, so no manifest in the
    repository disagrees with the version the server reports.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "deploy" / "mcp-publish-github"
MIRROR = ROOT / "deploy" / "mcp-publish"      # older copy of the same names
LOGOS = ROOT / "assets" / "listing-logos"
RAW = "https://raw.githubusercontent.com/jdhart81/viridis-agent-fleet/main/"
DOCS = "https://github.com/jdhart81/viridis-agent-fleet/blob/main/docs/servers/"
HOSTED_BUILD = "h1115b"         # names the publish tag: registry-meta-v<HOSTED_BUILD>
META_KEY = "io.modelcontextprotocol.registry/publisher-provided"

HOLD = {
    "security-preflight": "registry lists 1.3.1 while the code is 1.2.0, and GitHub review is in progress",
}
# Servers that run outside the hosted gateway and report their own release as
# serverInfo.version: the listing version is the release in agent.yaml (RM8).
SELF_VERSIONED = {"agent-market-network"}

# short name -> (title, glyph on the tile, existing logo file or None)
SERVERS = {
    "agent-arbitration": ("Agent Arbitration", "⚖", None),
    "agent-compute-ledger": ("Compute Ledger", "kWh", None),
    "agent-covenant": ("Agent Covenant", "§", None),
    "agent-erc8004-bridge": ("ERC-8004 Bridge", "8004", None),
    "agent-escrow": ("Agent Escrow", None, "viridis-agent-escrow-400.png"),
    "agent-hive-orchestrator": ("Hive Orchestrator", "⬡", None),
    "agent-identity-registry": ("Agent Identity", None, "viridis-agent-identity-400.png"),
    "agent-market-network": ("Agent Market", "⇄", None),
    "agent-metering": ("Agent Metering", "Σ", None),
    "agent-notary": ("Agent Notary", "#", None),
    "agent-offset-clearinghouse": ("Offset Clearinghouse", "tCO₂", None),
    "agent-provenance": ("Agent Provenance", "↳", None),
    "agent-surety": ("Agent Surety", "$", None),
    "agent-trust-oracle": ("Trust Oracle", "✓", None),
    "agent-verified-relay": ("Verified Relay", "↻", None),
    "disclosure-compiler": ("Disclosure Compiler", "SB", None),
    "eco-funding": ("Eco Funding", "ROI", None),
    "ghg-ledger": ("GHG Ledger", None, "viridis-ghg-ledger-400.png"),
    "green-router": ("Green Router", "gCO₂", None),
    "maxwell-defense": ("Maxwell Defense", "ΔS", None),
    "narrative-engine": ("Narrative Engine", "¶", None),
    "neurogenesis": ("Neurogenesis", "Ψ", None),
    "protogen": ("Protogen CAD", "CAD", None),
    "quantity-takeoff": ("Quantity Takeoff", "m³", None),
    "regulatory-radar": ("Regulatory Radar", None, "viridis-regulatory-radar-400.png"),
    "security-preflight": ("Security Preflight", "MCP", None),
    "settlement-engine": ("Settlement Engine", "∫", None),
    "smartscale": ("SmartScale", "1:n", None),
    "subscriptions": ("Subscriptions", "↺", None),
    "taxcredit-engine": ("Tax Credit Engine", "45Y", None),
    "verdigraph": ("Verdigraph", "◈", None),
    "viridisos": ("ViridisOS", "OS", None),
    "wavefunction-search": ("Wavefunction Search", "|ψ⟩", None),
    "wu-wei-router": ("Wu Wei Router", "無", None),
}

DESCRIPTIONS = {
    "agent-covenant": "Machine-checkable authority leases for agents: scoped, budgeted, expiring, revocable and audited.",
    "agent-erc8004-bridge": "MCP bridge to ERC-8004 on-chain agent identity, reputation and validation registries.",
    "agent-escrow": "Escrow and settlement for agent-to-agent jobs: exactly-once state machine, frozen fees, audit log.",
    "agent-hive-orchestrator": "Deterministic hive orchestration on the A2A rails: hire N solvers and cross-review their work.",
    "agent-identity-registry": "Verifiable agent identity with content-addressed DIDs, capability ads and capability search.",
    "agent-notary": "Verifiable delivery for agent jobs: commit-reveal notarization of delivered content.",
    "agent-offset-clearinghouse": "Matches verified conservation credits to agent compute emissions, with retirement records.",
    "agent-provenance": "Birth certificates, lineage and cascading recalls for agents.",
    "agent-surety": "Bonds behind agent promises: wronged parties are paid only on an arbitration ruling.",
    "agent-trust-oracle": "Decay-weighted agent reputation and tamper-evident trust attestations.",
    "agent-verified-relay": "Wraps any MCP server with tamper-evident delivery receipts, metered fees and disputes.",
    "green-router": "Free energy and carbon footprint quotes for agent compute, and greener backend ranking.",
    "narrative-engine": "Turns ecological and agent data into audience-tailored grant, investor and policy narratives.",
    "neurogenesis": "Developmental agents: create an agent from a digital genome, then evolve it by evaluation.",
    "protogen": "CAD workspaces, parametric CAD contracts and manufacturing briefs for design work.",
    "smartscale": "Deterministic CR80 card pixel-geometry scaler for caller-supplied card and object geometry.",
    "viridisos": "ViridisOS: theorem-backed conservation certification and the fleet's trust root.",
    "wavefunction-search": "Post a goal before you know who can do it: agents sense open work and earn scoped trust.",
}

FONT_BOLD = "/usr/share/fonts/opentype/inter/Inter-Bold.otf"
FONT_MED = "/usr/share/fonts/opentype/inter/Inter-Medium.otf"
FONT_FALLBACK = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
CJK = ("/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc",
       "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf")


def entries() -> list[dict]:
    out = []
    for path in sorted(REGISTRY.glob("*/server.json")):
        data = json.loads(path.read_text())
        short = data["name"].split("/")[-1]
        out.append({"path": path, "data": data, "short": short})
    return out


def logo_file(short: str) -> str:
    _, _, existing = SERVERS[short]
    return existing or f"viridis-{short}-400.png"


_CMAPS: dict = {}


def _has_glyph(path: str, ch: str) -> bool:
    """True when the font's character map covers ch (a missing glyph would
    render as the font's placeholder box)."""
    if path not in _CMAPS:
        from fontTools.ttLib import TTFont
        try:
            font = TTFont(path, fontNumber=0, lazy=True)
            _CMAPS[path] = set(font.getBestCmap() or {})
        except Exception:
            _CMAPS[path] = set()
    return ord(ch) in _CMAPS[path]


def _font(path: str, size: int, text: str):
    from PIL import ImageFont
    candidates = [path, FONT_FALLBACK]
    if any(ord(ch) > 0x2E80 for ch in text):
        candidates = list(CJK) + candidates
    for candidate in candidates:
        try:
            font = ImageFont.truetype(candidate, size)
        except OSError:
            continue
        if all(_has_glyph(candidate, ch) for ch in text if not ch.isspace()):
            return font
    raise SystemExit(f"RM5: no installed font draws {text!r}; pick another glyph")


def draw_icon(short: str, out: Path) -> None:
    from PIL import Image, ImageDraw
    title, glyph, _ = SERVERS[short]
    scale = 4                                         # supersample, then shrink
    size = 400 * scale
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=72 * scale, fill=(18, 61, 42, 255))
    ring = 40 * scale
    d.ellipse([250 * scale, -150 * scale, 550 * scale, 150 * scale],
              outline=(38, 128, 80, 255), width=ring)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=72 * scale, fill=255)
    img.putalpha(mask)
    d = ImageDraw.Draw(img)
    glyph_size = {1: 190, 2: 170, 3: 140, 4: 112}.get(len(glyph), 100) * scale
    font = _font(FONT_BOLD, glyph_size, glyph)
    box = d.textbbox((0, 0), glyph, font=font)
    gx = (size - (box[2] - box[0])) / 2 - box[0]
    gy = 205 * scale - (box[1] + box[3]) / 2
    d.text((gx, gy), glyph, font=font, fill=(224, 245, 233, 255))
    name_font = _font(FONT_MED, 30 * scale, title)
    box = d.textbbox((0, 0), title, font=name_font)
    d.text(((size - (box[2] - box[0])) / 2 - box[0], 300 * scale), title,
           font=name_font, fill=(126, 210, 160, 255))
    tag_font = _font(FONT_MED, 20 * scale, "VIRIDIS")
    box = d.textbbox((0, 0), "VIRIDIS", font=tag_font)
    d.text(((size - (box[2] - box[0])) / 2 - box[0], 348 * scale), "VIRIDIS",
           font=tag_font, fill=(102, 180, 135, 255))
    img = img.resize((400, 400), Image.LANCZOS)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, format="PNG", optimize=True)


def write_icons() -> list[str]:
    written = []
    for entry in entries():
        short = entry["short"]
        path = LOGOS / logo_file(short)
        if SERVERS[short][2] is None and not path.exists():          # RM5
            draw_icon(short, path)
            written.append(str(path.relative_to(ROOT)))
    return written


def release_of(data: dict) -> str:
    """The open-core release a listing builds on (RM2)."""
    recorded = ((data.get("_meta") or {}).get(META_KEY) or {}).get("viridis", {}).get("release")
    return recorded or str(data["version"]).split("+", 1)[0]


def _semver(version: str) -> tuple:
    core = version.split("+", 1)[0].split("-", 1)[0]
    return tuple(int(part) for part in core.split("."))


def agent_release(entry: dict) -> str:
    """The release in the server's agent.yaml (RM8)."""
    import re as _re
    text = (ROOT / entry["path"].parent.name / "agent.yaml").read_text()
    match = _re.search(r'^version:\s*"?([0-9][^"\s]*)"?', text, _re.M)
    if not match:
        raise SystemExit(f"RM8: no version in {entry['path'].parent.name}/agent.yaml")
    return match.group(1)


def hosted_version(release: str) -> str:
    major, minor, patch = _semver(release)
    return f"{major}.{minor}.{patch + 1}"


def wanted(entry: dict) -> dict:
    data = dict(entry["data"])
    short = entry["short"]
    title, _, _ = SERVERS[short]
    data["title"] = title
    if short in DESCRIPTIONS:                                           # RM3
        data["description"] = DESCRIPTIONS[short]
    data["websiteUrl"] = DOCS + f"{short}.md"
    data["icons"] = [{"src": RAW + "assets/listing-logos/" + logo_file(short),
                      "mimeType": "image/png", "sizes": ["400x400"]}]
    if short in SELF_VERSIONED:                                         # RM8
        release = agent_release(entry)
        data["version"] = release
    else:
        release = release_of(data)
        data["version"] = hosted_version(release)
    data["_meta"] = {META_KEY: {"viridis": {"release": release, "hostedBuild": HOSTED_BUILD}}}
    order = ["$schema", "name", "title", "description", "version", "websiteUrl",
             "icons", "repository", "remotes", "_meta"]
    return {k: data[k] for k in order if k in data} | {k: v for k, v in data.items() if k not in order}


def apply(write: bool = True) -> list[str]:
    stale = []
    for entry in entries():
        if entry["short"] in HOLD:                                      # RM4
            continue
        target = wanted(entry)
        for key in ("name", "repository", "remotes"):                   # RM3
            assert target.get(key) == entry["data"].get(key), (entry["short"], key)
        text = json.dumps(target, indent=2, ensure_ascii=False) + "\n"
        paths = [entry["path"]]
        mirror = MIRROR / entry["path"].parent.name / "server.json"     # RM7
        if mirror.exists():
            paths.append(mirror)
        for path in paths:
            if path.read_text() != text:
                stale.append(str(path.relative_to(ROOT)))
                if write:
                    path.write_text(text)
    return stale


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "check"
    if mode == "icons":
        print("\n".join(write_icons()) or "no new icons")
    elif mode == "apply":
        print("\n".join(apply()) or "up to date")
    elif mode in ("latest-check", "to-publish"):                       # RM2
        import urllib.parse
        import urllib.request
        behind, publish = [], []
        for entry in entries():
            if entry["short"] in HOLD:
                continue
            name = entry["data"]["name"]
            url = ("https://registry.modelcontextprotocol.io/v0/servers/"
                   + urllib.parse.quote(name, safe="") + "/versions/latest")
            try:
                latest = json.loads(urllib.request.urlopen(url, timeout=30).read())["server"]["version"]
            except Exception:
                latest = None                                 # never published
            mine = entry["data"]["version"]
            if latest is None or _semver(mine) > _semver(latest):
                publish.append(str(entry["path"]))
            elif _semver(mine) < _semver(latest):
                behind.append((name, mine, latest))
        if behind:
            raise SystemExit(f"would not become latest: {behind}")
        if mode == "to-publish":
            print(" ".join(publish))
        else:
            print(f"{len(publish)} listing(s) to publish; the rest are already latest")
    elif mode == "check":
        missing = [e["short"] for e in entries() if not (LOGOS / logo_file(e["short"])).exists()]
        stale = apply(write=False)
        if missing or stale:
            raise SystemExit(f"missing icons: {missing}; stale: {stale}")
        print("up to date")
    else:
        raise SystemExit(__doc__)
