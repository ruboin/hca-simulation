"""Unified compute pipeline: golden parity with the legacy model + rest-pool logic.

The canonical grouped scenario is ONE explicit group (NE 1) plus the automatic
rest pool (NE 2) — it must reproduce the goldens captured from the old
hardcoded-2-group implementation exactly.
"""
import pytest

import sankey.heizkosten as hk
from sankey.heizkosten import GroupConfig, NEConfig, ScenarioConfig

approx = pytest.approx

HZ_KWH = 34320.0
WW_KWH = 9680.0


def std_groups(leistung="beide"):
    """One explicit group holding NE 1; NE 2 lands in the automatic rest pool."""
    return [GroupConfig(id=1, members=[1], leistung=leistung,
                        hz_kwh=0.4 * HZ_KWH, ww_kwh=0.3 * WW_KWH,
                        verteilung_hz_pct=40, verteilung_ww_pct=30)]


def make_scenario(**over) -> ScenarioConfig:
    base = dict(
        brennstoff_kwh=44000.0,
        brennstoff_eur=5280.0,
        weitere_kosten_eur=980.0,
        geraetemiete_ww_eur=345.0,
        geraetemiete_hz_eur=265.0,
        co2_aktiv=True,
        co2_modus="manuell",
        co2_kosten_eur=320.0,
        co2_anteil_vermieter_pct=40,
        ww_modus="manuell",
        ww_kwh_manuell=WW_KWH,
        verteilung_ww_pct=30,
        verteilung_hz_pct=40,
        vorverteilung_ww_pct=30,
        vorverteilung_hz_pct=40,
        rest_verteilung_hz_pct=40,
        rest_verteilung_ww_pct=30,
        nutzeinheiten=[
            NEConfig(id=1, flaeche=68.0, ww_m3=18.0, hz_wert=1850.0),
            NEConfig(id=2, flaeche=90.0, ww_m3=23.5, hz_wert=2450.0),
        ],
        groups=[],
    )
    base.update(over)
    return ScenarioConfig(**base)


class TestSystemParity:
    def test_system_matches_legacy(self):
        res = hk.compute_all(make_scenario())
        assert res.co2.vermieter_eur == approx(128.0)
        assert res.system.brennstoff_gesamt_eur == approx(6132.0)
        assert res.system.warmwasser_eur == approx(1694.04)
        assert res.system.heizung_eur == approx(5047.96)

    def test_base_ne_match_legacy(self):
        res = hk.compute_all(make_scenario())
        ne1, ne2 = res.ne_results
        assert ne1.total == approx(2905.1531332891177)
        assert ne2.total == approx(3836.8468667108828)
        assert ne1.ww_gk == approx(218.7241518987342)
        assert ne1.groups_hz == [] and ne1.groups_ww == []


class TestArt1Parity:
    def test_grouped(self):
        res = hk.compute_all(make_scenario(ng_art="art1", groups=std_groups()))
        g1, g2 = res.hz.groups
        assert (g1.group_id, g2.group_id) == (1, 2)
        assert g1.eur == approx(2019.184)
        assert g2.eur == approx(3028.776)
        assert g1.gk == approx(807.6736)
        assert g2.vk == approx(1817.2656)
        w1, w2 = res.ww.groups
        assert w1.eur == approx(508.212)
        assert w1.gk == approx(152.4636)
        assert w2.vk == approx(830.0796)
        ne1, ne2 = res.ne_results
        assert ne1.total == approx(2527.396)
        assert ne2.total == approx(4214.604)
        assert ne1.groups_hz == [1] and ne1.groups_ww == [1]
        assert ne2.groups_hz == [2] and ne2.groups_ww == [2]   # automatic rest pool

    def test_hz_only_group_leaves_ww_shared(self):
        res = hk.compute_all(make_scenario(ng_art="art1", groups=std_groups("hz")))
        assert not res.ww.grouped
        assert res.ww.shared_gk == approx(508.212)
        base = hk.compute_all(make_scenario())
        for n, b in zip(res.ne_results, base.ne_results):
            assert n.ww_gk == approx(b.ww_gk)
            assert n.ww_vk == approx(b.ww_vk)
            assert n.groups_ww == []
        assert res.ne_results[0].groups_hz == [1]


class TestKreuzbergParity:
    def test_grouped(self):
        res = hk.compute_all(make_scenario(ng_art="kreuzberg", groups=std_groups()))
        assert res.hz.gk_pre == approx(2019.184)
        assert res.hz.vk_pre == approx(3028.776)
        g1 = res.hz.group(1)
        assert g1.eur == approx(2080.526298734177)
        assert g1.from_gk == approx(869.0158987341773)
        assert g1.area_fraction == approx(68.0 / 158.0)
        w1, w2 = res.ww.groups
        assert w1.eur == approx(574.4725518987342)
        assert w2.gk == approx(335.8702344303797)
        ne1, ne2 = res.ne_results
        assert ne1.total == approx(2654.998850632911)
        assert ne2.total == approx(4087.001149367088)

    def test_hz_only_group_leaves_ww_shared(self):
        res = hk.compute_all(make_scenario(ng_art="kreuzberg", groups=std_groups("hz")))
        base = hk.compute_all(make_scenario())
        for n, b in zip(res.ne_results, base.ne_results):
            assert n.ww_gk == approx(b.ww_gk)
            assert n.ww_vk == approx(b.ww_vk)


class TestRestPool:
    def test_rest_membership_is_complement(self):
        pools = hk.assemble_pools(make_scenario(groups=std_groups()), "hz")
        assert len(pools) == 2
        assert pools[0].members == [1] and not pools[0].is_rest
        assert pools[1].members == [2] and pools[1].is_rest
        assert pools[1].display_id == 2
        assert pools[1].kwh is None

    def test_rest_verteilung_comes_from_scenario_fields(self):
        s = make_scenario(groups=std_groups(), rest_verteilung_hz_pct=50,
                          rest_verteilung_ww_pct=50)
        assert hk.assemble_pools(s, "hz")[-1].verteilung_pct == 50
        assert hk.assemble_pools(s, "ww")[-1].verteilung_pct == 50
        res = hk.compute_all(s)
        rest = res.hz.group(2)
        assert rest.verteilung == approx(0.50)

    def test_full_coverage_has_no_rest(self):
        groups = [GroupConfig(id=1, members=[1, 2], leistung="beide",
                              hz_kwh=10000.0, ww_kwh=3000.0)]
        pools = hk.assemble_pools(make_scenario(groups=groups), "hz")
        assert len(pools) == 1
        assert not pools[0].is_rest
        assert pools[0].kwh is None   # last explicit pool becomes the remainder

    def test_ww_only_group_leaves_hz_shared(self):
        res = hk.compute_all(make_scenario(groups=std_groups("ww")))
        assert not res.hz.grouped and res.ww.grouped
        assert res.ne_results[0].groups_hz == []
        assert res.ne_results[0].groups_ww == [1]

    def test_ne_in_different_groups_per_gewerk(self):
        groups = [
            GroupConfig(id=1, members=[1], leistung="hz", hz_kwh=10000.0),
            GroupConfig(id=2, members=[2], leistung="ww", ww_kwh=3000.0),
        ]
        res = hk.compute_all(make_scenario(groups=groups))
        ne1, ne2 = res.ne_results
        # Hz: NE1 in pool 1, NE2 in rest (pool 2); WW: NE2 in pool 1, NE1 in rest
        assert (ne1.groups_hz, ne1.groups_ww) == ([1], [2])
        assert (ne2.groups_hz, ne2.groups_ww) == ([2], [1])
        assert sum(n.total for n in res.ne_results) == approx(
            res.system.warmwasser_eur + res.system.heizung_eur
        )

    def test_overlapping_membership_kept_in_both_pools(self):
        groups = [
            GroupConfig(id=1, members=[1], leistung="beide", hz_kwh=10000.0, ww_kwh=3000.0),
            GroupConfig(id=2, members=[1, 2], leistung="beide", hz_kwh=None, ww_kwh=None),
        ]
        pools = hk.assemble_pools(make_scenario(groups=groups), "hz")
        assert pools[0].members == [1]
        assert pools[1].members == [1, 2]
        assert len(pools) == 2   # union covers all NEs -> no rest pool


class TestOverlap:
    """Non-exclusive groups: an NE in several pools gets one share per pool."""

    def overlap_scenario(self, ng_art="art1"):
        # Pool 1 = [NE1], pool 2 = [NE1, NE2] — full coverage, pool 2 = remainder
        return make_scenario(ng_art=ng_art, groups=[
            GroupConfig(id=1, members=[1], leistung="hz", hz_kwh=10000.0,
                        verteilung_hz_pct=40),
            GroupConfig(id=2, members=[1, 2], leistung="hz", hz_kwh=None,
                        verteilung_hz_pct=40),
        ])

    def test_parts_match_pool_shares(self):
        s = self.overlap_scenario()
        res = hk.compute_all(s)
        ne1, ne2 = res.ne_results
        p1, p2 = res.hz.group(1), res.hz.group(2)

        assert ne1.groups_hz == [1, 2]
        assert ne2.groups_hz == [2]
        # Pool 1 has a single member -> NE1 receives it completely
        assert ne1.hz_parts[1][0] == approx(p1.gk)
        assert ne1.hz_parts[1][1] == approx(p1.vk)
        # Pool 2 distributes by Fläche (GK) and hz_wert (VK) over [NE1, NE2]
        assert ne1.hz_parts[2][0] == approx(68.0 / 158.0 * p2.gk)
        assert ne2.hz_parts[2][0] == approx(90.0 / 158.0 * p2.gk)
        assert ne1.hz_parts[2][1] == approx(1850.0 / 4300.0 * p2.vk)
        # Totals are the sums of the parts
        assert ne1.hz_gk == approx(p1.gk + 68.0 / 158.0 * p2.gk)
        assert ne1.hz_vk == approx(p1.vk + 1850.0 / 4300.0 * p2.vk)

    @pytest.mark.parametrize("ng_art", ["art1", "kreuzberg"])
    def test_conservation_under_overlap(self, ng_art):
        res = hk.compute_all(self.overlap_scenario(ng_art))
        assert sum(n.total for n in res.ne_results) == approx(
            res.system.warmwasser_eur + res.system.heizung_eur
        )

    def test_kreuzberg_area_fractions_normalized(self):
        """Σ pool areas > building area under overlap — fractions must sum to 1."""
        res = hk.compute_all(self.overlap_scenario("kreuzberg"))
        fracs = [gc.area_fraction for gc in res.hz.groups]
        assert sum(fracs) == approx(1.0)
        # pool areas: 68 and 158 -> normalized by 226, not by 158
        assert fracs[0] == approx(68.0 / 226.0)
        assert fracs[1] == approx(158.0 / 226.0)
        assert all(f >= 0 for f in fracs)

    def test_overlap_with_rest_pool(self):
        """Overlapping groups that do NOT cover everything still leave a rest pool."""
        s = make_scenario(
            nutzeinheiten=[
                NEConfig(id=1, flaeche=68.0, ww_m3=18.0, hz_wert=1850.0),
                NEConfig(id=2, flaeche=90.0, ww_m3=23.5, hz_wert=2450.0),
                NEConfig(id=3, flaeche=50.0, ww_m3=10.0, hz_wert=1200.0),
            ],
            groups=[
                GroupConfig(id=1, members=[1, 2], leistung="hz", hz_kwh=10000.0),
                GroupConfig(id=2, members=[2], leistung="hz", hz_kwh=8000.0),
            ],
        )
        pools = hk.assemble_pools(s, "hz")
        assert [p.members for p in pools] == [[1, 2], [2], [3]]
        assert pools[2].is_rest
        res = hk.compute_all(s)
        assert res.ne_results[1].groups_hz == [1, 2]
        assert res.ne_results[2].groups_hz == [3]
        assert sum(n.total for n in res.ne_results) == approx(
            res.system.warmwasser_eur + res.system.heizung_eur
        )


class TestConservation:
    @pytest.mark.parametrize("ng_art", ["art1", "kreuzberg"])
    @pytest.mark.parametrize("leistung", ["beide", "hz", "ww"])
    def test_ne_totals(self, ng_art, leistung):
        res = hk.compute_all(make_scenario(ng_art=ng_art, groups=std_groups(leistung)))
        assert sum(n.total for n in res.ne_results) == approx(
            res.system.warmwasser_eur + res.system.heizung_eur
        )


class TestWWEnergie:
    def test_formel(self):
        s = make_scenario(ww_modus="formel", ww_volumen_m3=41.5, ww_temp_c=60.0)
        e = hk.compute_ww_energie(s)
        assert e.kwh == approx(2.5 * 41.5 * 50.0)
        assert not e.gekappt
        assert "§9 Abs. 2 Formel" in e.beschreibung

    def test_formel_volumen_defaults_to_ne_sum(self):
        s = make_scenario(ww_modus="formel", ww_volumen_m3=None)
        e = hk.compute_ww_energie(s)
        assert e.kwh == approx(2.5 * (18.0 + 23.5) * 50.0)

    def test_pauschale(self):
        s = make_scenario(ww_modus="pauschale", ww_flaeche_m2=None)
        e = hk.compute_ww_energie(s)
        assert e.kwh == approx(32.0 * 158.0)
        assert "Pauschale" in e.beschreibung

    def test_clamped_to_brennstoff(self):
        s = make_scenario(ww_modus="formel", ww_volumen_m3=1e6)
        e = hk.compute_ww_energie(s)
        assert e.kwh == approx(s.brennstoff_kwh)
        assert e.gekappt


class TestCO2Modes:
    def test_stufen(self):
        s = make_scenario(co2_modus="stufen", co2_emission_kg=38.5 * 158.0, co2_flaeche_m2=None)
        c = hk.compute_co2(s)
        assert c.spez_kg_m2 == approx(38.5)
        assert c.stufe == 7
        assert c.anteil_vermieter == approx(0.60)
        assert c.vermieter_eur == approx(320.0 * 0.60)

    def test_inactive(self):
        c = hk.compute_co2(make_scenario(co2_aktiv=False))
        assert not c.aktiv and c.vermieter_eur == 0.0

    def test_cap(self):
        s = make_scenario(co2_kosten_eur=9000.0)
        c = hk.compute_co2(s)
        assert c.gekappt
        assert c.vermieter_eur == approx(5280.0 * 0.40)


class TestDeriveGroupKwh:
    def test_explicit_plus_remainder(self):
        s = make_scenario(groups=std_groups())
        pools = hk.assemble_pools(s, "hz")
        kwh = hk.derive_group_kwh(s.nutzeinheiten, pools, "hz", HZ_KWH)
        assert kwh == approx([0.4 * HZ_KWH, 0.6 * HZ_KWH])

    def test_wmz_group_is_meter_sum(self):
        s = make_scenario(groups=std_groups())
        s.nutzeinheiten[0].messtechnik = "wmz"
        s.nutzeinheiten[0].hz_wert = 12400.0
        s.groups[0].hz_kwh = None
        pools = hk.assemble_pools(s, "hz")
        kwh = hk.derive_group_kwh(s.nutzeinheiten, pools, "hz", HZ_KWH)
        assert kwh[0] == approx(12400.0)
        assert kwh[1] == approx(HZ_KWH - 12400.0)
