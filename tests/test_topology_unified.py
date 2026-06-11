"""Topology builder tests: flow balance, layer derivation, node order, tighten specs."""
from datetime import date

import pytest

import sankey.heizkosten as hk
from sankey.heizkosten import GroupConfig, NEConfig, NutzerConfig
from sankey.heizkosten.topology import build_topology
from conftest import assert_flows_balanced
from test_unified_compute import make_scenario, std_groups

SELECTED = [1, 2]


def NG(gw, g):
    return hk.ng_node(gw, g)


def GK(gw, g=None):
    return hk.gkvk_node(gw, "gk", g)


def VK(gw, g=None):
    return hk.gkvk_node(gw, "vk", g)


# mode → (ng_art or None, leistung of the explicit group)
MODES = [
    ("base", None), ("art1", "beide"), ("art1", "hz"),
    ("kreuzberg", "beide"), ("kreuzberg", "hz"),
]
MODE_IDS = ["base", "art1_grouped", "art1_hz_only", "k2_grouped", "k2_hz_only"]


def unified(mode, leistung, co2_aktiv=True):
    scenario = make_scenario(
        ng_art="kreuzberg" if mode == "kreuzberg" else "art1",
        groups=std_groups(leistung) if mode != "base" else [],
        co2_aktiv=co2_aktiv,
    )
    results = hk.compute_all(scenario)
    return scenario, results, build_topology(scenario, results, SELECTED)


@pytest.mark.parametrize("mode,leistung", MODES, ids=MODE_IDS)
def test_flows_balanced(mode, leistung):
    _, results, topo = unified(mode, leistung)
    assert_flows_balanced(topo.flows)
    ne_names = {hk.ne_node_name(i) for i in SELECTED}
    sink_total = sum(f["weight"] for f in topo.flows if f["target"] in ne_names)
    assert sink_total == pytest.approx(
        results.system.warmwasser_eur + results.system.heizung_eur
    )


@pytest.mark.parametrize("mode,leistung,expected_ne_layer", [
    ("base", None, 4), ("art1", "beide", 5), ("art1", "hz", 5),
    ("kreuzberg", "beide", 6), ("kreuzberg", "hz", 6),
], ids=MODE_IDS)
def test_ne_layer_derivation(mode, leistung, expected_ne_layer):
    _, _, topo = unified(mode, leistung)
    assert topo.ne_layer == expected_ne_layer
    assert topo.node_order[topo.ne_layer] == [hk.ne_node_name(i) for i in SELECTED]


def test_node_order_base():
    _, _, topo = unified("base", None)
    assert topo.node_order == {
        0: [hk.N_BRENNSTOFF, hk.N_WEITERE, hk.N_GERAETE],
        1: [hk.N_GESAMT],
        2: [hk.N_WW, hk.N_HZ, hk.N_CO2_VERMIETER],
        3: [GK("ww"), VK("ww"), GK("hz"), VK("hz")],
        4: [hk.ne_node_name(i) for i in SELECTED],
    }


def test_node_order_art1_grouped():
    _, _, topo = unified("art1", "beide")
    assert topo.node_order[3] == [NG("ww", 1), NG("ww", 2), NG("hz", 1), NG("hz", 2)]
    assert topo.node_order[4] == [
        GK("ww", 1), VK("ww", 1), GK("ww", 2), VK("ww", 2),
        GK("hz", 1), VK("hz", 1), GK("hz", 2), VK("hz", 2),
    ]


def test_node_order_art1_hz_only():
    _, _, topo = unified("art1", "hz")
    assert topo.node_order[3] == [GK("ww"), VK("ww"), NG("hz", 1), NG("hz", 2)]
    assert topo.node_order[4] == [
        GK("hz", 1), VK("hz", 1), GK("hz", 2), VK("hz", 2),
    ]


def test_node_order_kreuzberg():
    _, _, topo = unified("kreuzberg", "beide")
    assert topo.node_order[3] == [GK("ww"), VK("ww"), GK("hz"), VK("hz")]
    assert topo.node_order[4] == [NG("ww", 1), NG("ww", 2), NG("hz", 1), NG("hz", 2)]
    assert topo.node_order[5] == [
        GK("ww", 1), VK("ww", 1), GK("ww", 2), VK("ww", 2),
        GK("hz", 1), VK("hz", 1), GK("hz", 2), VK("hz", 2),
    ]


def test_shared_ww_jumps_to_ne_layer():
    """With an hz-only group the shared WW GK/VK flows skip intermediate layers."""
    _, _, topo = unified("kreuzberg", "hz")
    ww_ne_flows = [f for f in topo.flows
                   if f["source"] in (GK("ww"), VK("ww"))
                   and f["target"].startswith("Nutzeinheit")]
    assert ww_ne_flows, "expected shared WW → NE flows"
    for f in ww_ne_flows:
        assert f["layer"] == 3
        assert f["target_layer"] == 6


def test_tighten_specs_base():
    _, _, topo = unified("base", None)
    kinds = [(s.kind, s.parent_layer, s.child_layer) for s in topo.tighten_specs]
    assert kinds == [("merge", 0, 1), ("split", 2, 3)]
    assert topo.tighten_specs[0].mapping == {hk.N_GESAMT: [hk.N_BRENNSTOFF, hk.N_WEITERE]}
    assert topo.tighten_specs[1].mapping == {
        hk.N_WW: [GK("ww"), VK("ww")],
        hk.N_HZ: [GK("hz"), VK("hz")],
    }


def test_tighten_specs_art1_hz_only():
    _, _, topo = unified("art1", "hz")
    kinds = [(s.kind, s.parent_layer, s.child_layer) for s in topo.tighten_specs]
    assert kinds == [("merge", 0, 1), ("split", 2, 3), ("split", 3, 4)]
    assert topo.tighten_specs[1].mapping == {hk.N_WW: [GK("ww"), VK("ww")]}
    assert topo.tighten_specs[2].mapping == {
        NG("hz", 1): [GK("hz", 1), VK("hz", 1)],
        NG("hz", 2): [GK("hz", 2), VK("hz", 2)],
    }


def test_tighten_specs_kreuzberg():
    _, _, topo = unified("kreuzberg", "beide")
    kinds = [(s.kind, s.parent_layer, s.child_layer) for s in topo.tighten_specs]
    assert kinds == [("merge", 0, 1), ("split", 2, 3), ("split", 4, 5)]
    assert topo.tighten_specs[2].mapping == {
        NG("ww", 1): [GK("ww", 1), VK("ww", 1)],
        NG("ww", 2): [GK("ww", 2), VK("ww", 2)],
        NG("hz", 1): [GK("hz", 1), VK("hz", 1)],
        NG("hz", 2): [GK("hz", 2), VK("hz", 2)],
    }


def test_styles_cover_all_nodes():
    for mode, leistung in MODES:
        scenario, results, topo = unified(mode, leistung)
        node_names = {f["source"] for f in topo.flows} | {f["target"] for f in topo.flows}
        missing = node_names - set(topo.node_styles)
        assert not missing, f"{mode}: unstyled nodes {missing}"


def test_co2_off_removes_node():
    _, _, topo = unified("base", None, co2_aktiv=False)
    node_names = {f["source"] for f in topo.flows} | {f["target"] for f in topo.flows}
    assert hk.N_CO2_VERMIETER not in node_names


def test_per_gewerk_routing():
    """An NE in different hz/ww groups routes each Gewerk's final hop separately."""
    scenario = make_scenario(groups=[
        GroupConfig(id=1, members=[1], leistung="hz", hz_kwh=10000.0),
        GroupConfig(id=2, members=[2], leistung="ww", ww_kwh=3000.0),
    ])
    results = hk.compute_all(scenario)
    topo = build_topology(scenario, results, SELECTED)
    assert_flows_balanced(topo.flows)
    ne1 = hk.ne_node_name(1)
    # NE1: Hz from pool 1, WW from rest pool (display 2)
    hz_srcs = {f["source"] for f in topo.flows
               if f["target"] == ne1 and "Hz" in f["source"]}
    ww_srcs = {f["source"] for f in topo.flows
               if f["target"] == ne1 and "WW" in f["source"]}
    assert hz_srcs == {hk.gkvk_node("hz", "gk", 1), hk.gkvk_node("hz", "vk", 1)}
    assert ww_srcs == {hk.gkvk_node("ww", "gk", 2), hk.gkvk_node("ww", "vk", 2)}


# ── N pools (3 and 4 = MAX_EXPLICIT_NG + rest) ───────────────────────────────

def n_pool_scenario(n_explicit, ng_art, leistung):
    nes = [NEConfig(id=i, flaeche=50.0 + 10 * i, ww_m3=10.0 + 2 * i, hz_wert=1000.0 + 200 * i)
           for i in range(1, n_explicit + 3)]   # 2 extra NEs land in the rest pool
    groups = [
        GroupConfig(id=g, members=[g], leistung=leistung,
                    hz_kwh=4000.0 + 1000 * g, ww_kwh=1200.0 + 200 * g,
                    verteilung_hz_pct=40, verteilung_ww_pct=30)
        for g in range(1, n_explicit + 1)
    ]
    return make_scenario(ng_art=ng_art, nutzeinheiten=nes, groups=groups)


@pytest.mark.parametrize("n_explicit", [2, 3])
@pytest.mark.parametrize("ng_art", ["art1", "kreuzberg"])
@pytest.mark.parametrize("leistung", ["beide", "hz"], ids=["beide", "hz_only"])
def test_n_pools_balanced(n_explicit, ng_art, leistung):
    scenario = n_pool_scenario(n_explicit, ng_art, leistung)
    results = hk.compute_all(scenario)
    selected = [ne.id for ne in scenario.nutzeinheiten]
    topo = build_topology(scenario, results, selected)
    assert_flows_balanced(topo.flows)
    ne_names = {hk.ne_node_name(i) for i in selected}
    sink_total = sum(f["weight"] for f in topo.flows if f["target"] in ne_names)
    assert sink_total == pytest.approx(
        results.system.warmwasser_eur + results.system.heizung_eur
    )
    # explicit pools 1..n + rest pool n+1 all appear as Heizung NG nodes
    hz_ng_nodes = {f["target"] for f in topo.flows if f["target"].startswith("NG ")}
    for d in range(1, n_explicit + 2):
        assert hk.ng_node("hz", d) in hz_ng_nodes


def test_n_pools_unique_shades():
    for gw in ("ww", "hz"):
        for kind in (None, "gk", "vk"):
            shades = [hk.group_shade(gw, g, kind) for g in range(1, hk.MAX_NG + 1)]
            assert len(set(shades)) == len(shades), (gw, kind, shades)


@pytest.mark.parametrize("ng_art", ["art1", "kreuzberg"])
def test_overlap_multi_pool_routing(ng_art):
    """An NE in two pools of one Gewerk receives GK/VK ribbons from BOTH pools."""
    scenario = make_scenario(ng_art=ng_art, groups=[
        GroupConfig(id=1, members=[1], leistung="hz", hz_kwh=10000.0),
        GroupConfig(id=2, members=[1, 2], leistung="hz", hz_kwh=None),
    ])
    results = hk.compute_all(scenario)
    topo = build_topology(scenario, results, SELECTED)
    assert_flows_balanced(topo.flows)
    ne1 = hk.ne_node_name(1)
    hz_srcs = {f["source"] for f in topo.flows
               if f["target"] == ne1 and "Hz" in f["source"]}
    assert hz_srcs == {
        hk.gkvk_node("hz", "gk", 1), hk.gkvk_node("hz", "vk", 1),
        hk.gkvk_node("hz", "gk", 2), hk.gkvk_node("hz", "vk", 2),
    }
    # NE1's incoming Hz weights equal its part sums
    ne1_res = results.ne_results[0]
    hz_in = sum(f["weight"] for f in topo.flows
                if f["target"] == ne1 and "Hz" in f["source"])
    assert hz_in == pytest.approx(ne1_res.hz_gk + ne1_res.hz_vk)


# ── Nutzer layer (§9b Nutzerwechsel) ─────────────────────────────────────────

def wechsel_scenario(bez=("Fam. Alt", "Fam. Neu")):
    s = make_scenario()
    s.zeitraum_von = date(2025, 1, 1)
    s.zeitraum_bis = date(2025, 12, 31)
    s.nutzeinheiten[0].nutzer = [
        NutzerConfig(bez[0]),
        NutzerConfig(bez[1], von=date(2025, 7, 1)),
    ]
    return s


class TestNutzerLayer:
    def test_layer_flows_and_order(self):
        s = wechsel_scenario()
        results = hk.compute_all(s)
        topo = build_topology(s, results, SELECTED)
        assert_flows_balanced(topo.flows)
        nutzer_layer = topo.ne_layer + 1
        assert topo.node_order[nutzer_layer] == ["Fam. Alt", "Fam. Neu"]
        # NE 1 outflows = its user totals; NE 2 stays terminal
        ne1 = hk.ne_node_name(1)
        out1 = [f for f in topo.flows if f["source"] == ne1]
        assert sum(f["weight"] for f in out1) == pytest.approx(
            results.ne_results[0].total)
        assert all(f["label"].startswith("Zeitraum") for f in out1)
        assert not [f for f in topo.flows if f["source"] == hk.ne_node_name(2)]

    def test_tighten_spec_flush_with_zero_gap(self):
        s = wechsel_scenario()
        results = hk.compute_all(s)
        topo = build_topology(s, results, SELECTED)
        spec = topo.tighten_specs[-1]
        assert (spec.kind, spec.parent_layer, spec.child_layer) == (
            "split", topo.ne_layer, topo.ne_layer + 1)
        assert spec.group_gap == 0
        assert spec.mapping == {hk.ne_node_name(1): ["Fam. Alt", "Fam. Neu"]}

    def test_user_nodes_share_ne_color_and_style(self):
        s = wechsel_scenario()
        results = hk.compute_all(s)
        topo = build_topology(s, results, SELECTED)
        ne_color = topo.node_styles[hk.ne_node_name(1)]["color"]
        assert topo.node_styles["Fam. Alt"]["color"] == ne_color
        assert topo.node_styles["Fam. Neu"]["color"] == ne_color

    def test_no_layer_without_wechsel(self):
        s = make_scenario()
        results = hk.compute_all(s)
        topo = build_topology(s, results, SELECTED)
        assert topo.ne_layer + 1 not in topo.node_order

    def test_unfiltered_ne_gets_no_user_nodes(self):
        s = wechsel_scenario()
        results = hk.compute_all(s)
        topo = build_topology(s, results, [2])   # NE 1 not selected
        assert topo.ne_layer + 1 not in topo.node_order

    def test_duplicate_names_are_disambiguated(self):
        s = wechsel_scenario(bez=("", ""))   # both fall back to "Nutzer i"
        s.nutzeinheiten[1].nutzer = [
            NutzerConfig(""), NutzerConfig("", von=date(2025, 4, 1))]
        results = hk.compute_all(s)
        topo = build_topology(s, results, SELECTED)
        names = topo.node_order[topo.ne_layer + 1]
        assert len(names) == len(set(names)) == 4
        assert_flows_balanced(topo.flows)


def test_display_renumbering_for_noncontiguous_ids():
    """Sidebar group ids [2, 3] map to display pool numbers [1, 2]."""
    scenario = make_scenario(groups=[
        GroupConfig(id=2, members=[1], leistung="beide", hz_kwh=10000.0, ww_kwh=2000.0,
                    verteilung_hz_pct=40, verteilung_ww_pct=30),
        GroupConfig(id=3, members=[2], leistung="beide", hz_kwh=None, ww_kwh=None,
                    verteilung_hz_pct=40, verteilung_ww_pct=30),
    ])
    results = hk.compute_all(scenario)
    assert [gc.group_id for gc in results.hz.groups] == [1, 2]
    assert sum(n.total for n in results.ne_results) == pytest.approx(
        results.system.warmwasser_eur + results.system.heizung_eur
    )
    topo = build_topology(scenario, results, SELECTED)
    assert_flows_balanced(topo.flows)
    node_names = {f["source"] for f in topo.flows} | {f["target"] for f in topo.flows}
    assert hk.ng_node("hz", 1) in node_names
    assert hk.ng_node("hz", 3) not in node_names