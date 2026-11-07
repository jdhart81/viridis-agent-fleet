"""Habitat connectivity: Equivalent Connected Area (ECA) over verified habitat.

    PC numerator  = sum_i sum_j a_i a_j p*_ij        (Saura & Pascual-Hortal 2007)
    ECA           = sqrt(PC numerator)               (Saura et al. 2011)   [ha]

a_i is the patch attribute (verified area x condition, ha). p*_ij is the maximum product
probability over all paths from i to j (p*_ii = 1). Link probabilities come from one of:

* an explicit probability in (0, 1];
* a gap distance through HDFM's movement kernel p = exp(-alpha d / s)
  (jdhart81/hdfm-framework, hdfm/entropy.py; defaults alpha = 2, s = 1000 m);
* ``hdfm_linked: true``, a minimum-width corridor confirmed by the dfm-core corridor
  check, treated as structurally contiguous (p = 1).

Only patches flagged ``verified`` enter the calculation, and a link counts only when both
of its ends are verified. Unverified habitat and its links are reported, never scored.

Monotonicity (Invariant 2): adding a verified patch, enlarging one, adding a link or
raising a link probability can only add terms or improve paths, so ECA never falls.
Because decimal rounding is monotone, this holds for the computed numbers too, not only
for exact arithmetic (tests/test_invariant_2_monotonicity.py).
"""

from __future__ import annotations

import heapq
from decimal import Decimal
from typing import Any

from ._decimal import ONE, ZERO, exp, pinned, sqrt


@pinned
def link_probability(link: dict[str, Any], kernel: dict[str, Decimal]) -> Decimal:
    if link["mode"] == "probability":
        return link["probability"]
    if link["mode"] == "hdfm_linked":
        return ONE
    return exp(-kernel["alpha"] * link["distance_m"] / kernel["scale_m"])


@pinned
def best_path_probabilities(nodes: list[str], adjacency: dict[str, list[tuple[str, Decimal]]],
                            source: str) -> dict[str, Decimal]:
    """Max-product Dijkstra from ``source``. Deterministic: neighbours are pre-sorted and
    heap ties break on node id."""
    best = {source: ONE}
    heap: list[tuple[Decimal, str]] = [(-ONE, source)]
    while heap:
        negative, node = heapq.heappop(heap)
        prob = -negative
        if prob < best[node]:
            continue
        for neighbour, weight in adjacency[node]:
            candidate = prob * weight
            if candidate > best.get(neighbour, ZERO):
                best[neighbour] = candidate
                heapq.heappush(heap, (-candidate, neighbour))
    return best


@pinned
def equivalent_connected_area(habitat: dict[str, Any]) -> dict[str, Any]:
    patches = habitat["patches"]
    verified = [p for p in patches if p["verified"]]
    verified_ids = {p["id"] for p in verified}
    attribute = {p["id"]: p["area_ha"] * p["condition"] for p in verified}
    nodes = sorted(verified_ids)

    adjacency: dict[str, list[tuple[str, Decimal]]] = {node: [] for node in nodes}
    used_links: list[dict[str, Any]] = []
    ignored_links: list[dict[str, Any]] = []
    for link in habitat["links"]:
        if link["from"] in verified_ids and link["to"] in verified_ids:
            p = link_probability(link, habitat["kernel"])
            adjacency[link["from"]].append((link["to"], p))
            adjacency[link["to"]].append((link["from"], p))
            used_links.append({"from": link["from"], "to": link["to"], "mode": link["mode"],
                               "probability": p})
        else:
            ignored_links.append({"from": link["from"], "to": link["to"],
                                  "reason": "an endpoint is not verified habitat"})
    for node in nodes:
        adjacency[node].sort()

    numerator = ZERO
    for source in nodes:
        best = best_path_probabilities(nodes, adjacency, source)
        for target in nodes:
            p_star = best.get(target, ZERO)
            if p_star:
                numerator += attribute[source] * attribute[target] * p_star
    eca = sqrt(numerator)
    verified_area = sum((p["area_ha"] for p in verified), ZERO)
    attribute_area = sum(attribute.values(), ZERO)
    return {
        "eca_ha": eca,
        "pc_numerator_ha2": numerator,
        "verified_area_ha": verified_area,
        "attribute_area_ha": attribute_area,
        "verified_patch_ids": nodes,
        "unverified_patch_ids": sorted(p["id"] for p in patches if not p["verified"]),
        "links_used": used_links,
        "links_ignored": ignored_links,
    }
