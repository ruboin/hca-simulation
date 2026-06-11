"""Tests for validate_scenario: Messtechnik per-pool rules, §12, Zeitraum, plausibility."""
from datetime import date

import pytest

import sankey.heizkosten as hk
from sankey.heizkosten import GroupConfig
from test_unified_compute import make_scenario, std_groups


def hinweis_codes(scenario):
    results = hk.compute_all(scenario)
    return {h.code: h for h in hk.validate_scenario(scenario, results)}


def test_clean_scenario_has_no_errors():
    codes = hinweis_codes(make_scenario())
    assert not any(h.level == "error" for h in codes.values())
    assert "PARAGRAPH_12" not in codes


class TestMesstechnik:
    def test_mixed_without_hz_groups_is_error(self):
        s = make_scenario()
        s.nutzeinheiten[0].messtechnik = "wmz"
        codes = hinweis_codes(s)
        assert "MESSTECHNIK_MIXED_NO_NG" in codes
        assert codes["MESSTECHNIK_MIXED_NO_NG"].level == "error"

    def test_ww_only_group_does_not_satisfy_mixed_technik(self):
        s = make_scenario(groups=std_groups("ww"))
        s.nutzeinheiten[0].messtechnik = "wmz"
        assert "MESSTECHNIK_MIXED_NO_NG" in hinweis_codes(s)

    def test_mixed_explicit_group_is_error(self):
        s = make_scenario(groups=[GroupConfig(id=1, members=[1, 2], leistung="hz",
                                              hz_kwh=None)])
        s.nutzeinheiten[0].messtechnik = "wmz"
        codes = hinweis_codes(s)
        assert "MESSTECHNIK_MIXED_GROUP" in codes

    def test_mixed_rest_pool_is_error(self):
        """Explicit WMZ group, but the rest pool mixes one WMZ and one HKV NE."""
        s = make_scenario(groups=[GroupConfig(id=1, members=[1], leistung="hz",
                                              hz_kwh=None)])
        s.nutzeinheiten.append(type(s.nutzeinheiten[0])(
            id=3, flaeche=50.0, ww_m3=10.0, hz_wert=8000.0, messtechnik="wmz"))
        s.nutzeinheiten[0].messtechnik = "wmz"
        codes = hinweis_codes(s)
        assert "MESSTECHNIK_MIXED_GROUP" in codes
        assert "Restgruppe" in codes["MESSTECHNIK_MIXED_GROUP"].text

    def test_homogeneous_pools_ok(self):
        s = make_scenario(groups=[GroupConfig(id=1, members=[1], leistung="hz",
                                              hz_kwh=None)])
        s.nutzeinheiten[0].messtechnik = "wmz"   # group [1] all-WMZ, rest [2] all-HKV
        codes = hinweis_codes(s)
        assert not any(h.level == "error" for h in codes.values())

    def test_uniform_wmz_without_groups_ok(self):
        s = make_scenario()
        for ne in s.nutzeinheiten:
            ne.messtechnik = "wmz"
        codes = hinweis_codes(s)
        assert not any(h.level == "error" for h in codes.values())

    def test_wmz_sum_exceeds_pool_warns(self):
        s = make_scenario(groups=[GroupConfig(id=1, members=[1], leistung="hz",
                                              hz_kwh=None)])
        s.nutzeinheiten[0].messtechnik = "wmz"
        s.nutzeinheiten[0].hz_wert = 99999.0
        assert "WMZ_SUM_EXCEEDS_POOL" in hinweis_codes(s)


class TestGruppen:
    def test_empty_group_warns(self):
        groups = std_groups()
        groups.append(GroupConfig(id=2, members=[], leistung="beide",
                                  hz_kwh=None, ww_kwh=None))
        assert "GROUP_EMPTY" in hinweis_codes(make_scenario(groups=groups))

    def test_negative_remainder_warns(self):
        groups = std_groups()
        groups[0].hz_kwh = 99999.0
        assert "GROUP_KWH_SUM_MISMATCH" in hinweis_codes(make_scenario(groups=groups))


class TestParagraph12:
    def test_verbrauchsanteil_below_50(self):
        codes = hinweis_codes(make_scenario(verteilung_hz_pct=100))
        assert "PARAGRAPH_12" in codes
        assert codes["PARAGRAPH_12"].level == "info"

    def test_verbrauchsanteil_above_70_base(self):
        assert "PARAGRAPH_12" in hinweis_codes(make_scenario(verteilung_hz_pct=0))

    def test_group_verteilung_triggers(self):
        groups = std_groups()
        groups[0].verteilung_hz_pct = 100
        assert "PARAGRAPH_12" in hinweis_codes(make_scenario(groups=groups))

    def test_rest_verteilung_triggers(self):
        s = make_scenario(groups=std_groups(), rest_verteilung_hz_pct=100)
        assert "PARAGRAPH_12" in hinweis_codes(s)

    def test_pauschale_triggers(self):
        assert "PARAGRAPH_12" in hinweis_codes(make_scenario(ww_modus="pauschale"))

    def test_legal_config_silent(self):
        assert "PARAGRAPH_12" not in hinweis_codes(make_scenario(groups=std_groups()))


class TestZeitraum:
    def zeitraum_scenario(self, von, bis):
        s = make_scenario()
        s.zeitraum_von, s.zeitraum_bis = von, bis
        return s

    def test_missing_is_info(self):
        codes = hinweis_codes(make_scenario())
        assert "ZEITRAUM_MISSING" in codes
        assert codes["ZEITRAUM_MISSING"].level == "info"

    def test_full_year_is_silent(self):
        s = self.zeitraum_scenario(date(2025, 1, 1), date(2025, 12, 31))
        codes = hinweis_codes(s)
        assert not any(c.startswith("ZEITRAUM") for c in codes)

    def test_inverted_warns(self):
        s = self.zeitraum_scenario(date(2025, 12, 31), date(2025, 1, 1))
        assert hinweis_codes(s)["ZEITRAUM_INVALID"].level == "warning"

    def test_longer_than_12_months_warns(self):
        s = self.zeitraum_scenario(date(2024, 1, 1), date(2025, 3, 31))
        assert hinweis_codes(s)["ZEITRAUM_GT_12M"].level == "warning"

    def test_rumpf_is_info(self):
        s = self.zeitraum_scenario(date(2025, 1, 1), date(2025, 6, 30))
        assert hinweis_codes(s)["ZEITRAUM_RUMPF"].level == "info"


class TestPlausibility:
    def test_co2_cap_warns(self):
        assert "CO2_GT_BRENNSTOFF" in hinweis_codes(make_scenario(co2_kosten_eur=99999.0))

    def test_ww_clamp_warns(self):
        codes = hinweis_codes(make_scenario(ww_modus="formel", ww_volumen_m3=1e6))
        assert "WW_KWH_GT_BRENNSTOFF" in codes

    def test_all_zero_hz_warns(self):
        s = make_scenario()
        for ne in s.nutzeinheiten:
            ne.hz_wert = 0.0
        assert "NE_ALL_ZERO" in hinweis_codes(s)


class TestOverlapHinweise:
    def overlap_groups(self):
        return [
            GroupConfig(id=1, members=[1], leistung="hz", hz_kwh=10000.0),
            GroupConfig(id=2, members=[1, 2], leistung="hz", hz_kwh=None),
        ]

    def test_multi_pool_info_shown(self):
        codes = hinweis_codes(make_scenario(groups=self.overlap_groups()))
        assert "NE_MULTI_POOL" in codes
        assert codes["NE_MULTI_POOL"].level == "info"
        assert "Nutzeinheit 1" in codes["NE_MULTI_POOL"].text

    def test_no_info_without_overlap(self):
        assert "NE_MULTI_POOL" not in hinweis_codes(make_scenario(groups=std_groups()))

    def test_homogeneous_overlap_passes(self):
        s = make_scenario(groups=self.overlap_groups())
        for ne in s.nutzeinheiten:
            ne.messtechnik = "wmz"
        codes = hinweis_codes(s)
        assert not any(h.level == "error" for h in codes.values())

    def test_overlap_making_pool_impure_is_error(self):
        """WMZ NE 1 shared into a pool with HKV NE 2 → that pool mixes technik."""
        s = make_scenario(groups=self.overlap_groups())
        s.nutzeinheiten[0].messtechnik = "wmz"
        codes = hinweis_codes(s)
        assert "MESSTECHNIK_MIXED_GROUP" in codes


def test_has_errors():
    s = make_scenario()
    s.nutzeinheiten[0].messtechnik = "wmz"
    results = hk.compute_all(s)
    assert hk.has_errors(hk.validate_scenario(s, results))
    assert not hk.has_errors([])
