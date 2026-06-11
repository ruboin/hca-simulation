"""Characterization tests: system-level cost split, base NE allocation, CO2 Stufen."""
import pytest

import sankey.heizkosten as hk
from sankey.heizkosten import NEConfig, ScenarioConfig
from conftest import SYSTEM_INPUTS, CO2_VERMIETER_EUR

approx = pytest.approx


class TestSystemCosts:
    def test_golden_values(self, sc):
        assert sc.brennstoff_gesamt_eur == approx(6132.0)
        assert sc.brennstoff_mieter_eur == approx(5152.0)
        assert sc.co2_vermieter_eur == approx(128.0)
        assert sc.warmwasser_kwh == approx(9680.0)
        assert sc.heizung_kwh == approx(34320.0)
        assert sc.warmwasser_eur == approx(1694.04)
        assert sc.heizung_eur == approx(5047.96)
        assert sc.warmwasser_grundkosten_eur == approx(508.212)
        assert sc.warmwasser_verbrauchskosten_eur == approx(1185.828)
        assert sc.heizung_grundkosten_eur == approx(2019.184)
        assert sc.heizung_verbrauchskosten_eur == approx(3028.776)

    def test_pools_sum_to_total(self, sc):
        geraete = SYSTEM_INPUTS["geraetemiete_ww_eur"] + SYSTEM_INPUTS["geraetemiete_hz_eur"]
        assert sc.warmwasser_eur + sc.heizung_eur == approx(
            sc.brennstoff_gesamt_eur + geraete
        )

    def test_gk_vk_split_per_gewerk(self, sc):
        assert sc.warmwasser_grundkosten_eur + sc.warmwasser_verbrauchskosten_eur == approx(
            sc.warmwasser_eur
        )
        assert sc.heizung_grundkosten_eur + sc.heizung_verbrauchskosten_eur == approx(
            sc.heizung_eur
        )
        assert sc.warmwasser_grundkosten_eur == approx(0.30 * sc.warmwasser_eur)
        assert sc.heizung_grundkosten_eur == approx(0.40 * sc.heizung_eur)

    def test_co2_reduces_mieter_share(self, sc):
        assert sc.brennstoff_mieter_eur == approx(
            SYSTEM_INPUTS["brennstoff_eur"] - CO2_VERMIETER_EUR
        )

    def test_zero_kwh_falls_back_to_geraetemieten(self):
        inputs = dict(SYSTEM_INPUTS, brennstoff_kwh=0.0, warmwasser_kwh=0.0)
        sc = hk.compute_system_costs(**inputs, co2_vermieter_eur=0.0)
        assert sc.warmwasser_eur == approx(inputs["geraetemiete_ww_eur"])
        assert sc.heizung_eur == approx(inputs["geraetemiete_hz_eur"])


def base_scenario() -> ScenarioConfig:
    """Default building (ScenarioConfig defaults) + manual CO2 = legacy goldens."""
    return ScenarioConfig(
        co2_aktiv=True,
        co2_modus="manuell",
        co2_kosten_eur=320.0,
        co2_anteil_vermieter_pct=40,
        nutzeinheiten=[
            NEConfig(id=1, flaeche=68.0, ww_m3=18.0, hz_wert=1850.0),
            NEConfig(id=2, flaeche=90.0, ww_m3=23.5, hz_wert=2450.0),
        ],
    )


class TestBaseNECosts:
    def test_golden_values(self):
        ne1, ne2 = hk.compute_all(base_scenario()).ne_results
        assert ne1.ww_gk == approx(218.7241518987342)
        assert ne1.ww_vk == approx(514.3350361445783)
        assert ne1.hz_gk == approx(869.0158987341773)
        assert ne1.hz_vk == approx(1303.0780465116277)
        assert ne1.total == approx(2905.1531332891177)
        assert ne2.total == approx(3836.8468667108828)

    def test_conservation(self):
        res = hk.compute_all(base_scenario())
        assert sum(r.total for r in res.ne_results) == approx(
            res.system.warmwasser_eur + res.system.heizung_eur
        )
        assert sum(r.ww_gk for r in res.ne_results) == approx(
            res.system.warmwasser_grundkosten_eur
        )
        assert sum(r.hz_vk for r in res.ne_results) == approx(
            res.system.heizung_verbrauchskosten_eur
        )


class TestCO2Stufen:
    @pytest.mark.parametrize(
        "spez, stufe, anteil",
        [
            (0.0, 1, 0.00),
            (11.99, 1, 0.00),
            (12.0, 2, 0.10),
            (16.99, 2, 0.10),
            (32.0, 6, 0.50),
            (38.5, 7, 0.60),
            (51.99, 9, 0.80),
            (52.0, 10, 0.95),
            (200.0, 10, 0.95),
        ],
    )
    def test_boundaries(self, spez, stufe, anteil):
        assert hk.co2_vermieteranteil(spez) == (stufe, anteil)


def test_sdiv():
    assert hk.sdiv(10.0, 2.0) == 5.0
    assert hk.sdiv(10.0, 0.0) == 0.0
