"""§9b Nutzerwechsel: Gradtagszahlen, period splitting, per-user cost shares."""
from datetime import date

import pytest

import sankey.heizkosten as hk
from sankey.heizkosten import NutzerConfig
from sankey.heizkosten.nutzerwechsel import gradtag_gewicht, nutzer_perioden
from test_unified_compute import make_scenario

approx = pytest.approx


def scenario_with_wechsel(*wechsel, vz=(0.0, 0.0)):
    """Default scenario, NE 1 with user periods split at the given dates."""
    s = make_scenario()
    s.zeitraum_von = date(2025, 1, 1)
    s.zeitraum_bis = date(2025, 12, 31)
    nutzer = [NutzerConfig("Fam. Alt", vorauszahlung_eur=vz[0])]
    for i, w in enumerate(wechsel, start=1):
        nutzer.append(NutzerConfig(f"Fam. Neu {i}", von=w,
                                   vorauszahlung_eur=vz[i] if i < len(vz) else 0.0))
    s.nutzeinheiten[0].nutzer = nutzer
    return s


class TestGradtagGewicht:
    def test_full_calendar_year_is_1000(self):
        assert gradtag_gewicht(date(2025, 1, 1), date(2025, 12, 31)) == approx(1000.0)
        assert gradtag_gewicht(date(2024, 1, 1), date(2024, 12, 31)) == approx(1000.0)  # leap

    def test_january_is_170(self):
        assert gradtag_gewicht(date(2025, 1, 1), date(2025, 1, 31)) == approx(170.0)

    def test_summer_day_is_40_over_92(self):
        assert gradtag_gewicht(date(2025, 7, 15), date(2025, 7, 15)) == approx(40.0 / 92.0)
        assert gradtag_gewicht(date(2025, 6, 1), date(2025, 8, 31)) == approx(40.0)

    def test_february_leap_year_total_unchanged(self):
        assert gradtag_gewicht(date(2024, 2, 1), date(2024, 2, 29)) == approx(150.0)
        assert gradtag_gewicht(date(2025, 2, 1), date(2025, 2, 28)) == approx(150.0)

    def test_half_january(self):
        # 1.–15.1. = 15 days × 170/31
        assert gradtag_gewicht(date(2025, 1, 1), date(2025, 1, 15)) == approx(15 * 170.0 / 31)

    def test_cross_year_span(self):
        # Dez + Jan across the year boundary
        assert gradtag_gewicht(date(2024, 12, 1), date(2025, 1, 31)) == approx(160.0 + 170.0)

    def test_empty_span(self):
        assert gradtag_gewicht(date(2025, 5, 2), date(2025, 5, 1)) == 0.0


class TestPerioden:
    def test_wechsel_day_starts_new_user(self):
        nutzer = [NutzerConfig("A"), NutzerConfig("B", von=date(2025, 7, 1))]
        perioden = nutzer_perioden(date(2025, 1, 1), date(2025, 12, 31), nutzer)
        (i1, _, v1, b1), (i2, _, v2, b2) = perioden
        assert (i1, v1, b1) == (1, date(2025, 1, 1), date(2025, 6, 30))
        assert (i2, v2, b2) == (2, date(2025, 7, 1), date(2025, 12, 31))

    def test_unsorted_wechsel_dates_are_ordered(self):
        nutzer = [NutzerConfig("A"),
                  NutzerConfig("C", von=date(2025, 10, 1)),
                  NutzerConfig("B", von=date(2025, 4, 1))]
        perioden = nutzer_perioden(date(2025, 1, 1), date(2025, 12, 31), nutzer)
        assert [p[1].bezeichnung for p in perioden] == ["A", "B", "C"]
        assert perioden[1][2] == date(2025, 4, 1)
        assert perioden[1][3] == date(2025, 9, 30)

    def test_out_of_range_date_clamped(self):
        nutzer = [NutzerConfig("A"), NutzerConfig("B", von=date(2030, 1, 1))]
        perioden = nutzer_perioden(date(2025, 1, 1), date(2025, 12, 31), nutzer)
        assert perioden[1][2] == date(2025, 12, 31)   # clamped to zeitraum_bis
        assert perioden[0][3] == date(2025, 12, 30)

    def test_duplicate_dates_give_empty_period(self):
        nutzer = [NutzerConfig("A"),
                  NutzerConfig("B", von=date(2025, 7, 1)),
                  NutzerConfig("C", von=date(2025, 7, 1))]
        perioden = nutzer_perioden(date(2025, 1, 1), date(2025, 12, 31), nutzer)
        _, _, v2, b2 = perioden[1]
        assert b2 < v2   # empty period for the first of the duplicates


class TestSplit:
    def test_paragraph_9b_components(self):
        """Days for GK + WW-VK; Gradtage only for Hz-VK."""
        res = hk.compute_all(scenario_with_wechsel(date(2025, 7, 1)))
        ne1 = res.ne_results[0]
        alt, neu = ne1.nutzer
        tage_alt = 181 / 365
        gradtage_alt = gradtag_gewicht(date(2025, 1, 1), date(2025, 6, 30)) / 1000.0
        assert alt.tage_anteil == approx(tage_alt)
        assert alt.gradtag_anteil == approx(gradtage_alt)
        assert alt.ww_gk == approx(ne1.ww_gk * tage_alt)
        assert alt.ww_vk == approx(ne1.ww_vk * tage_alt)
        assert alt.hz_gk == approx(ne1.hz_gk * tage_alt)
        assert alt.hz_vk == approx(ne1.hz_vk * gradtage_alt)
        # winter-heavy first half gets MORE Hz-VK than its day share
        assert gradtage_alt > tage_alt

    @pytest.mark.parametrize("wechsel", [
        (date(2025, 7, 1),),
        (date(2025, 4, 1), date(2025, 10, 15)),
        (date(2025, 2, 1), date(2025, 2, 1)),   # duplicate → empty period
    ])
    def test_component_conservation(self, wechsel):
        res = hk.compute_all(scenario_with_wechsel(*wechsel))
        ne1 = res.ne_results[0]
        assert sum(n.ww_gk for n in ne1.nutzer) == approx(ne1.ww_gk)
        assert sum(n.ww_vk for n in ne1.nutzer) == approx(ne1.ww_vk)
        assert sum(n.hz_gk for n in ne1.nutzer) == approx(ne1.hz_gk)
        assert sum(n.hz_vk for n in ne1.nutzer) == approx(ne1.hz_vk)
        assert sum(n.total for n in ne1.nutzer) == approx(ne1.total)

    def test_rumpf_period_shares_sum_to_one(self):
        s = scenario_with_wechsel(date(2025, 5, 1))
        s.zeitraum_von = date(2025, 3, 1)
        s.zeitraum_bis = date(2025, 8, 31)
        res = hk.compute_all(s)
        ne1 = res.ne_results[0]
        assert sum(n.tage_anteil for n in ne1.nutzer) == approx(1.0)
        assert sum(n.gradtag_anteil for n in ne1.nutzer) == approx(1.0)

    def test_single_user_gets_everything(self):
        res = hk.compute_all(make_scenario())
        ne1 = res.ne_results[0]
        assert len(ne1.nutzer) == 1
        assert ne1.nutzer[0].tage_anteil == approx(1.0)
        assert ne1.nutzer[0].total == approx(ne1.total)

    def test_vorauszahlung_and_saldo_per_user(self):
        res = hk.compute_all(scenario_with_wechsel(date(2025, 7, 1), vz=(5000.0, 100.0)))
        ne1 = res.ne_results[0]
        alt, neu = ne1.nutzer
        assert alt.saldo == approx(alt.total - 5000.0)   # Guthaben
        assert neu.saldo == approx(neu.total - 100.0)    # Nachzahlung
        assert ne1.vorauszahlung_eur == approx(5100.0)

    def test_missing_zeitraum_falls_back_to_equal(self):
        s = scenario_with_wechsel(date(2025, 7, 1))
        s.zeitraum_von = None
        s.zeitraum_bis = None
        res = hk.compute_all(s)
        ne1 = res.ne_results[0]
        assert [n.tage_anteil for n in ne1.nutzer] == approx([0.5, 0.5])
        assert sum(n.total for n in ne1.nutzer) == approx(ne1.total)


class TestValidation:
    def hinweis_codes(self, s):
        res = hk.compute_all(s)
        return {h.code: h for h in hk.validate_scenario(s, res)}

    def test_wechsel_without_zeitraum_is_error(self):
        s = scenario_with_wechsel(date(2025, 7, 1))
        s.zeitraum_von = None
        s.zeitraum_bis = None
        codes = self.hinweis_codes(s)
        assert codes["NUTZERWECHSEL_OHNE_ZEITRAUM"].level == "error"

    def test_out_of_range_date_warns(self):
        codes = self.hinweis_codes(scenario_with_wechsel(date(2030, 1, 1)))
        assert codes["NUTZERWECHSEL_DATUM"].level == "warning"

    def test_duplicate_dates_warn_empty_period(self):
        codes = self.hinweis_codes(
            scenario_with_wechsel(date(2025, 7, 1), date(2025, 7, 1)))
        assert codes["NUTZER_PERIODE_LEER"].level == "warning"

    def test_clean_wechsel_is_silent(self):
        codes = self.hinweis_codes(scenario_with_wechsel(date(2025, 7, 1)))
        assert not any(c.startswith("NUTZER") for c in codes)
