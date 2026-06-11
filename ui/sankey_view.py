"""Sankey rendering: topology → graph → layout → tighten → HTML/SVG."""
from typing import List

from sankey import (
    build_graph,
    layout_graph,
    place_node_after,
    render_html,
    render_static_svg,
    resort_links_by_position,
    tighten_merge_layer,
    tighten_split_layer,
)
import sankey.heizkosten as hk
from sankey.heizkosten import ComputedResults, ScenarioConfig
from sankey.heizkosten.topology import build_topology


def build_sankey_graph(
    scenario: ScenarioConfig,
    results: ComputedResults,
    selected_ne_ids: List[int],
) -> dict:
    topo = build_topology(scenario, results, selected_ne_ids)
    graph = build_graph(topo.flows, node_styles=topo.node_styles, default_padding=10)
    layout_graph(graph, node_sort_key=topo.sort_key, **hk.LAYOUT)

    for spec in topo.tighten_specs:
        if spec.kind == "merge":
            tighten_merge_layer(graph, parent_layer=spec.parent_layer,
                                child_layer=spec.child_layer, child_to_parents=spec.mapping)
        else:
            gap = spec.group_gap
            if gap is None:
                gap = 6 if len(spec.mapping) > 2 else 0
            tighten_split_layer(graph, parent_layer=spec.parent_layer,
                                child_layer=spec.child_layer, parent_to_children=spec.mapping,
                                group_gap=gap)

    # Equalize WEITERE↔GERAETE gap with the WW↔HZ gap (tighten_merge_layer collapses
    # the BRENNSTOFF↔WEITERE gap onto the WEITERE→GERAETE side, making it too wide)
    by_name = {n["name"]: n for n in graph["nodes"]}
    if hk.N_WW in by_name and hk.N_HZ in by_name:
        ref_gap = by_name[hk.N_HZ]["x0"] - by_name[hk.N_WW]["x1"]
        place_node_after(graph, hk.L_INPUTS, hk.N_GERAETE, hk.N_WEITERE, ref_gap)

    resort_links_by_position(graph)
    return graph


def sankey_html(graph: dict, embed: bool = True) -> str:
    """Interactive HTML for a laid-out graph (embedded iframe or standalone)."""
    return render_html(
        graph,
        title="" if embed else "Heizkostenabrechnung",
        theme="dark",
        embed=embed,
        transparent=embed,
        value_unit="€",
        locale="de",
        fit_container=embed,
    )


def sankey_report_svg(scenario: ScenarioConfig, results: ComputedResults) -> str:
    """Static (print-safe) SVG over ALL Nutzeinheiten for the report."""
    graph = build_sankey_graph(scenario, results,
                               [ne.id for ne in scenario.nutzeinheiten])
    return render_static_svg(graph, value_unit="€", locale="de", background="#1a212b")
