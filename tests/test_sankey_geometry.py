"""Geometry regression tests on the fully laid-out + tightened Sankey graph.

Regression: in Art 1 with an Hz-only group, the per-group Grund-/Verbrauchskosten
nodes were placed ABOVE the Nutzergruppen row because tighten_split_layer anchored
children to an arbitrary sample node of the parent layer (the raised shared WW
GK/VK) instead of their own parent.
"""
import pytest

import sankey.heizkosten as hk
from ui.sankey_view import build_sankey_graph
from test_unified_compute import make_scenario, std_groups

SELECTED = [1, 2]

N_WW_GK = hk.gkvk_node("ww", "gk")
N_WW_VK = hk.gkvk_node("ww", "vk")
N_HZ_GK = hk.gkvk_node("hz", "gk")
N_HZ_VK = hk.gkvk_node("hz", "vk")


def laid_out_graph(**scenario_over):
    scenario = make_scenario(**scenario_over)
    results = hk.compute_all(scenario)
    graph = build_sankey_graph(scenario, results, SELECTED)
    return {n["name"]: n for n in graph["nodes"]}


def assert_flush_below(nodes, parent_name, child_names):
    parent = nodes[parent_name]
    for child_name in child_names:
        child = nodes[child_name]
        assert child["y0"] == pytest.approx(parent["y1"]), (
            f"{child_name} (y0={child['y0']:.1f}) is not flush below "
            f"{parent_name} (y1={parent['y1']:.1f})"
        )


def test_art1_hz_only_group_children_below_ng_nodes():
    nodes = laid_out_graph(ng_art="art1", groups=std_groups("hz"))
    for g in (1, 2):
        assert_flush_below(nodes, hk.ng_node("hz", g),
                           [hk.gkvk_node("hz", "gk", g), hk.gkvk_node("hz", "vk", g)])
    # shared WW GK/VK flush below Kosten Warmwasser
    assert_flush_below(nodes, hk.N_WW, [N_WW_GK, N_WW_VK])


def test_art1_beide_children_below_ng_nodes():
    nodes = laid_out_graph(ng_art="art1", groups=std_groups("beide"))
    for gw in ("ww", "hz"):
        for g in (1, 2):
            assert_flush_below(nodes, hk.ng_node(gw, g),
                               [hk.gkvk_node(gw, "gk", g), hk.gkvk_node(gw, "vk", g)])


def test_kreuzberg_hz_only_children_below_ng_nodes():
    nodes = laid_out_graph(ng_art="kreuzberg", groups=std_groups("hz"))
    for g in (1, 2):
        assert_flush_below(nodes, hk.ng_node("hz", g),
                           [hk.gkvk_node("hz", "gk", g), hk.gkvk_node("hz", "vk", g)])
    assert_flush_below(nodes, hk.N_WW, [N_WW_GK, N_WW_VK])
    assert_flush_below(nodes, hk.N_HZ, [N_HZ_GK, N_HZ_VK])


def test_base_mode_children_below_system_nodes():
    nodes = laid_out_graph()
    assert_flush_below(nodes, hk.N_WW, [N_WW_GK, N_WW_VK])
    assert_flush_below(nodes, hk.N_HZ, [N_HZ_GK, N_HZ_VK])


def test_nutzer_nodes_flush_adjacent_and_span_ne_width():
    """§9b user nodes: flush below their NE, no horizontal gap between them,
    together exactly as wide as the NE bar; the single-user NE stays terminal."""
    from datetime import date
    from sankey.heizkosten import NutzerConfig

    scenario = make_scenario()
    scenario.zeitraum_von = date(2025, 1, 1)
    scenario.zeitraum_bis = date(2025, 12, 31)
    scenario.nutzeinheiten[0].nutzer = [
        NutzerConfig("Fam. Alt"),
        NutzerConfig("Fam. Neu", von=date(2025, 7, 1)),
    ]
    results = hk.compute_all(scenario)
    graph = build_sankey_graph(scenario, results, SELECTED)
    nodes = {n["name"]: n for n in graph["nodes"]}

    ne1 = nodes[hk.ne_node_name(1)]
    alt, neu = nodes["Fam. Alt"], nodes["Fam. Neu"]
    assert_flush_below(nodes, hk.ne_node_name(1), ["Fam. Alt", "Fam. Neu"])
    assert alt["x0"] == pytest.approx(ne1["x0"])
    assert neu["x0"] == pytest.approx(alt["x1"])          # adjacent, no gap
    assert neu["x1"] == pytest.approx(ne1["x1"])          # spans the NE bar
    assert "Nutzeinheit 2" in nodes                       # terminal, no children
