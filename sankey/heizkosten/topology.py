"""Unified Sankey topology builder.

One ``build_topology()`` covers every mode — base (no Nutzergruppen),
Abrechnungsart 1, Kreuzberg, per-Gewerk grouping ("nur für Heizung"), any
number of groups — by deriving layers per Gewerk instead of hardcoding the
historical 5/6/7-layer variants:

    depth(gewerk) = 2  ungrouped    SYSTEM → GK/VK → NE
                  = 3  art1         SYSTEM → NG_g → GK/VK_g → NE
                  = 4  kreuzberg    SYSTEM → GK/VK_pre → NG_g → GK/VK_g → NE
    L_NE = L_SYSTEM + max(depth(ww), depth(hz))

The shallower Gewerk's flows jump to L_NE via ``target_layer``.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .constants import (
    GREEN_GERAETE,
    L_GESAMT,
    L_INPUTS,
    L_SYSTEM,
    N_BRENNSTOFF,
    N_CO2_VERMIETER,
    N_GERAETE,
    N_GESAMT,
    NE_COLORS,
    ORANGE_BASE,
    ORANGE_LIGHT1,
    ORANGE_LIGHT2,
    RED_BASE,
    RED_LIGHT1,
    RED_LIGHT2,
    SLATE_CO2,
    YELLOW_BRENNSTOFF,
    YELLOW_GESAMT,
    YELLOW_WEITERE,
    N_WEITERE,
    gewerk_node,
    gkvk_node,
    group_shade,
    ne_node_name,
    ng_node,
    rgba,
)
from .model import ComputedResults, GewerkResult, ScenarioConfig


@dataclass
class TightenSpec:
    kind: str                       # "merge" | "split"
    parent_layer: int
    child_layer: int
    mapping: Dict[str, List[str]]
    group_gap: Optional[int] = None  # None => renderer heuristic


@dataclass
class Topology:
    flows: List[Dict[str, Any]]
    node_order: Dict[int, List[str]]
    node_styles: Dict[str, Dict[str, Any]]
    tighten_specs: List[TightenSpec]
    ne_layer: int

    @property
    def sort_key(self) -> Callable[[Dict[str, Any]], Any]:
        return _make_sort_key(self.node_order)


def _make_sort_key(node_order: Dict[int, List[str]]) -> Callable[[Dict[str, Any]], Any]:
    def _sort_key(node: Dict[str, Any]) -> Any:
        layer = node.get("layer", 0)
        order = node_order.get(layer)
        if order:
            name = node.get("name", "")
            try:
                return order.index(name)
            except ValueError:
                return len(order)
        return node.get("name", "")
    return _sort_key


def _flow(
    source: str,
    layer: int,
    target: str,
    weight: float,
    label: str = "",
    target_layer: Optional[int] = None,
    flow_color: str = "gradient",
) -> Dict[str, Any]:
    row = {
        "source": source,
        "layer": layer,
        "target": target,
        "weight": weight,
        "label": label or f"{weight:,.2f} €",
        "flow_color": flow_color,
    }
    if target_layer is not None:
        row["target_layer"] = target_layer
    return row


def gewerk_depth(gres: GewerkResult) -> int:
    if not gres.grouped:
        return 2
    return 4 if gres.kreuzberg else 3


_GEWERK_BASE = {"ww": RED_BASE, "hz": ORANGE_BASE}
_GEWERK_LIGHT = {"ww": (RED_LIGHT1, RED_LIGHT2), "hz": (ORANGE_LIGHT1, ORANGE_LIGHT2)}


def build_node_styles(
    scenario: ScenarioConfig,
    results: ComputedResults,
) -> Dict[str, Dict[str, Any]]:
    """Style dict for all nodes of this scenario (pool display ids per Gewerk)."""
    styles: Dict[str, Dict[str, Any]] = {
        N_BRENNSTOFF:    {"color": rgba(YELLOW_BRENNSTOFF), "padding": 14},
        N_WEITERE:       {"color": rgba(YELLOW_WEITERE),    "padding": 14},
        N_GERAETE:       {"color": rgba(GREEN_GERAETE),     "padding": 14},
        N_GESAMT:        {"color": rgba(YELLOW_GESAMT),     "padding": 12},
        N_CO2_VERMIETER: {"color": rgba(SLATE_CO2, 0.85),   "padding": 12},
    }
    for gw, gres in (("ww", results.ww), ("hz", results.hz)):
        light1, light2 = _GEWERK_LIGHT[gw]
        styles[gewerk_node(gw)] = {"color": rgba(_GEWERK_BASE[gw]), "padding": 12}
        styles[gkvk_node(gw, "gk")] = {"color": rgba(light1), "padding": 10}
        styles[gkvk_node(gw, "vk")] = {"color": rgba(light2), "padding": 10}
        for gc in gres.groups:
            g = gc.group_id
            styles[ng_node(gw, g)] = {"color": rgba(group_shade(gw, g)), "padding": 10}
            for kind in ("gk", "vk"):
                styles[gkvk_node(gw, kind, g)] = {
                    "color": rgba(group_shade(gw, g, kind)), "padding": 8,
                }
    for ne in scenario.nutzeinheiten:
        color = NE_COLORS[(ne.id - 1) % len(NE_COLORS)]
        styles[ne.label] = {"color": rgba(color), "padding": 12}
    return styles


def build_topology(
    scenario: ScenarioConfig,
    results: ComputedResults,
    selected_ne_ids: List[int],
) -> Topology:
    system = results.system
    ww, hz = results.ww, results.hz
    ne_layer = L_SYSTEM + max(gewerk_depth(ww), gewerk_depth(hz))

    flows: List[Dict[str, Any]] = []
    order: Dict[int, List[str]] = {
        L_INPUTS: [N_BRENNSTOFF, N_WEITERE, N_GERAETE],
        L_GESAMT: [N_GESAMT],
        L_SYSTEM: [],
    }
    for layer in range(L_SYSTEM + 1, ne_layer):
        order[layer] = []
    order[ne_layer] = [ne_node_name(i) for i in selected_ne_ids]

    splits: Dict[tuple, Dict[str, List[str]]] = {}

    def add_split(parent_layer: int, parent: str, children: List[str]) -> None:
        splits.setdefault((parent_layer, parent_layer + 1), {})[parent] = children

    # ── Common head ───────────────────────────────────────────────────────────
    geraete = {"ww": scenario.geraetemiete_ww_eur, "hz": scenario.geraetemiete_hz_eur}
    flows += [
        _flow(N_BRENNSTOFF, L_INPUTS, N_GESAMT, scenario.brennstoff_eur),
        _flow(N_GESAMT, L_GESAMT, N_CO2_VERMIETER, results.co2.vermieter_eur,
              target_layer=L_SYSTEM, flow_color=rgba(SLATE_CO2, 0.5)),
        _flow(N_WEITERE, L_INPUTS, N_GESAMT, scenario.weitere_kosten_eur),
    ]
    for gw, gres in (("ww", ww), ("hz", hz)):
        sys_node = gewerk_node(gw)
        order[L_SYSTEM].append(sys_node)
        flows.append(_flow(N_GESAMT, L_GESAMT, sys_node, gres.eur - geraete[gw]))
        flows.append(_flow(N_GERAETE, L_INPUTS, sys_node, geraete[gw], target_layer=L_SYSTEM))
    order[L_SYSTEM].append(N_CO2_VERMIETER)

    # ── Per-Gewerk body; remembers each NE's source nodes for the final hop ──
    ne_sources: Dict[str, Callable[[int], tuple]] = {}

    def emit_gewerk(gw: str, gres: GewerkResult) -> None:
        sys_node = gewerk_node(gw)
        if not gres.grouped:
            gk_n, vk_n = gkvk_node(gw, "gk"), gkvk_node(gw, "vk")
            pos = L_SYSTEM + 1
            flows.append(_flow(sys_node, L_SYSTEM, gk_n, gres.shared_gk,
                               label=f"Grundkosten: {gres.shared_verteilung:.0%}"))
            flows.append(_flow(sys_node, L_SYSTEM, vk_n, gres.shared_vk,
                               label=f"Verbrauchskosten: {1 - gres.shared_verteilung:.0%}"))
            order[pos] += [gk_n, vk_n]
            add_split(L_SYSTEM, sys_node, [gk_n, vk_n])
            ne_sources[gw] = lambda g, gk_n=gk_n, vk_n=vk_n, pos=pos: (gk_n, vk_n, pos)
            return

        if gres.kreuzberg:
            gk_pre_n, vk_pre_n = gkvk_node(gw, "gk"), gkvk_node(gw, "vk")
            flows.append(_flow(sys_node, L_SYSTEM, gk_pre_n, gres.gk_pre,
                               label=f"Grundkostenanteil: {gres.vorverteilung:.0%}"))
            flows.append(_flow(sys_node, L_SYSTEM, vk_pre_n, gres.vk_pre,
                               label=f"Verbrauchskostenanteil: {1 - gres.vorverteilung:.0%}"))
            order[L_SYSTEM + 1] += [gk_pre_n, vk_pre_n]
            add_split(L_SYSTEM, sys_node, [gk_pre_n, vk_pre_n])
            ng_layer, split_layer = L_SYSTEM + 2, L_SYSTEM + 3
            for gc in gres.groups:
                ng_n = ng_node(gw, gc.group_id)
                flows.append(_flow(gk_pre_n, L_SYSTEM + 1, ng_n, gc.from_gk,
                                   label=f"nach Fläche: {gc.area_fraction:.1%}"))
                flows.append(_flow(vk_pre_n, L_SYSTEM + 1, ng_n, gc.from_vk,
                                   label=f"nach Verbrauch: {gc.fraction:.1%}"))
                order[ng_layer].append(ng_n)
        else:  # art1
            ng_layer, split_layer = L_SYSTEM + 1, L_SYSTEM + 2
            for gc in gres.groups:
                ng_n = ng_node(gw, gc.group_id)
                flows.append(_flow(sys_node, L_SYSTEM, ng_n, gc.eur,
                                   label=f"nach Verbrauch: {gc.fraction:.1%}"))
                order[ng_layer].append(ng_n)

        for gc in gres.groups:
            ng_n = ng_node(gw, gc.group_id)
            gk_n = gkvk_node(gw, "gk", gc.group_id)
            vk_n = gkvk_node(gw, "vk", gc.group_id)
            flows.append(_flow(ng_n, ng_layer, gk_n, gc.gk,
                               label=f"Grundkosten: {gc.verteilung:.0%}"))
            flows.append(_flow(ng_n, ng_layer, vk_n, gc.vk,
                               label=f"Verbrauchskosten: {1 - gc.verteilung:.0%}"))
            order[split_layer] += [gk_n, vk_n]
            add_split(ng_layer, ng_n, [gk_n, vk_n])
        ne_sources[gw] = lambda g, gw=gw, pos=split_layer: (
            gkvk_node(gw, "gk", g), gkvk_node(gw, "vk", g), pos
        )

    emit_gewerk("ww", ww)
    emit_gewerk("hz", hz)

    # ── Final hop: GK/VK → Nutzeinheiten ─────────────────────────────────────
    # Pools are non-exclusive: a grouped Gewerk contributes one GK + one VK
    # ribbon per pool the NE belongs to (weights from the per-pool parts).
    ne_by_id = {r.id: r for r in results.ne_results}
    for ne_id in selected_ne_ids:
        res = ne_by_id[ne_id]
        name = res.label
        for gw, gres, parts, gk_total, vk_total in (
            ("ww", ww, res.ww_parts, res.ww_gk, res.ww_vk),
            ("hz", hz, res.hz_parts, res.hz_gk, res.hz_vk),
        ):
            if gres.grouped:
                for display_id in sorted(parts):
                    gk_w, vk_w = parts[display_id]
                    gk_n, vk_n, pos = ne_sources[gw](display_id)
                    flows.append(_flow(gk_n, pos, name, gk_w, target_layer=ne_layer))
                    flows.append(_flow(vk_n, pos, name, vk_w, target_layer=ne_layer))
            else:
                gk_n, vk_n, pos = ne_sources[gw](1)
                flows.append(_flow(gk_n, pos, name, gk_total, target_layer=ne_layer))
                flows.append(_flow(vk_n, pos, name, vk_total, target_layer=ne_layer))

    # ── Nutzer layer (§9b): NEs with ≥2 users split into user nodes below ────
    styles = build_node_styles(scenario, results)
    nutzer_split: Dict[str, List[str]] = {}
    multi_user = [ne_by_id[i] for i in selected_ne_ids
                  if len(ne_by_id[i].nutzer) >= 2]
    if multi_user:
        nutzer_layer = ne_layer + 1
        order[nutzer_layer] = []
        taken = {f["source"] for f in flows} | {f["target"] for f in flows}
        for res in multi_user:
            ne_color = NE_COLORS[(res.id - 1) % len(NE_COLORS)]
            children = []
            for nu in res.nutzer:
                name = nu.display_label
                if name in taken:
                    name = f"{name} ({res.label})"
                while name in taken:
                    name = name + "·"
                taken.add(name)
                flows.append(_flow(res.label, ne_layer, name, nu.total,
                                   label=f"Zeitraum {nu.zeitraum_text}"))
                order[nutzer_layer].append(name)
                styles[name] = {"color": rgba(ne_color), "padding": 12}
                children.append(name)
            nutzer_split[res.label] = children

    flows = [f for f in flows if f["weight"] > 0]

    tighten_specs = [TightenSpec("merge", L_INPUTS, L_GESAMT,
                                 {N_GESAMT: [N_BRENNSTOFF, N_WEITERE]})]
    for (parent_layer, child_layer), mapping in sorted(splits.items()):
        tighten_specs.append(TightenSpec("split", parent_layer, child_layer, mapping))
    if nutzer_split:
        # Users sit flush below their NE with no horizontal gap between them
        tighten_specs.append(TightenSpec("split", ne_layer, ne_layer + 1,
                                         nutzer_split, group_gap=0))

    return Topology(
        flows=flows,
        node_order=order,
        node_styles=styles,
        tighten_specs=tighten_specs,
        ne_layer=ne_layer,
    )
