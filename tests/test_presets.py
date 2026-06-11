"""Preset serialization: v4 round-trip, v1–v3 upgrades (incl. numeric parity), built-ins."""
import json
from datetime import date

import pytest

import sankey.heizkosten as hk
from sankey.heizkosten import GroupConfig
from ui.presets import (
    BUILTIN_PRESETS,
    scenario_from_dict,
    scenario_to_dict,
    scenario_to_json,
)
from test_unified_compute import HZ_KWH, WW_KWH, make_scenario, std_groups


@pytest.mark.parametrize("over", [
    dict(),
    dict(ng_art="art1", groups=std_groups("beide")),
    dict(ng_art="kreuzberg", groups=std_groups("hz"),
         co2_aktiv=True, co2_modus="stufen", co2_emission_kg=5000.0,
         ww_modus="formel", ww_volumen_m3=41.5,
         rest_verteilung_hz_pct=50),
], ids=["base", "art1_beide", "kreuzberg_hz_stufen_formel"])
def test_round_trip(over):
    scenario = make_scenario(**over)
    scenario.nutzeinheiten[0].messtechnik = "wmz"
    restored = scenario_from_dict(scenario_to_dict(scenario))
    assert restored == scenario


def test_round_trip_mixed_leistung():
    scenario = make_scenario(groups=[
        GroupConfig(id=1, members=[1], leistung="hz", hz_kwh=10000.0),
        GroupConfig(id=2, members=[2], leistung="ww", ww_kwh=3000.0),
    ])
    restored = scenario_from_dict(scenario_to_dict(scenario))
    assert restored == scenario


def test_json_round_trip():
    scenario = make_scenario(groups=std_groups())
    restored = scenario_from_dict(json.loads(scenario_to_json(scenario)))
    assert restored == scenario


def test_round_trip_with_abrechnung_fields():
    scenario = make_scenario()
    scenario.objekt = "MFH Teststraße 5"
    scenario.zeitraum_von = date(2025, 1, 1)
    scenario.zeitraum_bis = date(2025, 12, 31)
    scenario.nutzeinheiten[0].nutzer = [
        hk.NutzerConfig("Whg. 1 links", vorauszahlung_eur=1200.0),
        hk.NutzerConfig("Fam. Neu", von=date(2025, 7, 1), vorauszahlung_eur=800.0),
    ]
    restored = scenario_from_dict(json.loads(scenario_to_json(scenario)))
    assert restored == scenario
    assert restored.nutzeinheiten[0].nutzer[1].von == date(2025, 7, 1)


def test_round_trip_group_bezeichnung():
    scenario = make_scenario(groups=std_groups())
    scenario.groups[0].bezeichnung = "Vorderhaus"
    restored = scenario_from_dict(scenario_to_dict(scenario))
    assert restored == scenario
    assert restored.groups[0].bezeichnung == "Vorderhaus"


def test_unknown_version_rejected():
    d = scenario_to_dict(make_scenario())
    d["version"] = 99
    with pytest.raises(ValueError):
        scenario_from_dict(d)


def make_v2_dict():
    """A schema-v2 file as the old code wrote it (no Abrechnung block, flat
    per-NE billing fields, no group Bezeichnung)."""
    d = scenario_to_dict(make_scenario(groups=std_groups()))
    del d["abrechnung"]
    for ne in d["nutzeinheiten"]:
        del ne["nutzer"]
    for g in d["nutzergruppen"]["gruppen"]:
        del g["bezeichnung"]
    d["version"] = 2
    return d


def make_v3_dict():
    """A schema-v3 file: flat bezeichnung/vorauszahlung per NE, no nutzer list."""
    d = scenario_to_dict(make_scenario(groups=std_groups()))
    d["abrechnung"] = {"objekt": "Altbestand", "zeitraum_von": "2025-01-01",
                       "zeitraum_bis": "2025-12-31"}
    for i, ne in enumerate(d["nutzeinheiten"], start=1):
        del ne["nutzer"]
        ne["bezeichnung"] = f"Whg. {i}"
        ne["vorauszahlung_eur"] = 1000.0 * i
    for g in d["nutzergruppen"]["gruppen"]:
        del g["bezeichnung"]
    d["version"] = 3
    return d


class TestV2Upgrade:
    def test_fills_defaults(self):
        s = scenario_from_dict(make_v2_dict())
        assert s.objekt == ""
        assert s.zeitraum_von is None and s.zeitraum_bis is None
        for ne in s.nutzeinheiten:
            assert len(ne.nutzer) == 1
            assert ne.nutzer[0].bezeichnung == ""
            assert ne.nutzer[0].vorauszahlung_eur == 0.0

    def test_numeric_parity(self):
        res = hk.compute_all(scenario_from_dict(make_v2_dict()))
        ne1, ne2 = res.ne_results
        assert ne1.total == pytest.approx(2527.396)
        assert ne2.total == pytest.approx(4214.604)


class TestV3Upgrade:
    def test_billing_fields_become_first_nutzer(self):
        s = scenario_from_dict(make_v3_dict())
        ne1 = s.nutzeinheiten[0]
        assert len(ne1.nutzer) == 1
        assert ne1.nutzer[0].bezeichnung == "Whg. 1"
        assert ne1.nutzer[0].vorauszahlung_eur == 1000.0
        assert ne1.nutzer[0].von is None
        assert all(g.bezeichnung == "" for g in s.groups)

    def test_numeric_parity(self):
        res = hk.compute_all(scenario_from_dict(make_v3_dict()))
        ne1, ne2 = res.ne_results
        assert ne1.total == pytest.approx(2527.396)
        assert ne2.total == pytest.approx(4214.604)
        assert res.ne_results[0].vorauszahlung_eur == 1000.0


def make_v1_dict(aktiv=True, ww_by_group=True):
    """A canonical schema-v1 file as the old code wrote it."""
    return {
        "version": 1,
        "gebaeude": {"brennstoff_kwh": 44000.0, "brennstoff_eur": 5280.0,
                     "weitere_kosten_eur": 980.0, "geraetemiete_ww_eur": 345.0,
                     "geraetemiete_hz_eur": 265.0},
        "co2": {"aktiv": True, "modus": "manuell", "kosten_eur": 320.0,
                "emission_kg": None, "flaeche_m2": None, "anteil_vermieter_pct": 40},
        "warmwasser": {"modus": "manuell", "kwh_manuell": WW_KWH, "volumen_m3": None,
                       "temperatur_c": 60.0, "flaeche_m2": None},
        "verteilung": {"vww_pct": 30, "vhz_pct": 40},
        "nutzergruppen": {
            "aktiv": aktiv, "art": "art1", "ww_by_group": ww_by_group,
            "vorverteilung_ww_pct": 30, "vorverteilung_hz_pct": 40,
            "gruppen": [
                {"id": 1, "mitglieder": [1], "hz_kwh": 0.4 * HZ_KWH,
                 "ww_kwh": 0.3 * WW_KWH, "verteilung_hz_pct": 40, "verteilung_ww_pct": 30},
                {"id": 2, "mitglieder": [2], "hz_kwh": None, "ww_kwh": None,
                 "verteilung_hz_pct": 40, "verteilung_ww_pct": 30},
            ],
        },
        "nutzeinheiten": [
            {"id": 1, "flaeche": 68.0, "ww_m3": 18.0, "messtechnik": "hkv", "hz_wert": 1850.0},
            {"id": 2, "flaeche": 90.0, "ww_m3": 23.5, "messtechnik": "hkv", "hz_wert": 2450.0},
        ],
    }


class TestV1Upgrade:
    def test_structure(self):
        s = scenario_from_dict(make_v1_dict(ww_by_group=True))
        assert len(s.groups) == 1                 # old last group dropped → rest
        assert s.groups[0].leistung == "beide"
        assert s.groups[0].members == [1]
        assert s.rest_verteilung_hz_pct == 40     # inherited from old group 2
        assert s.rest_verteilung_ww_pct == 30

    def test_only_heizung_maps_to_hz(self):
        s = scenario_from_dict(make_v1_dict(ww_by_group=False))
        assert s.groups[0].leistung == "hz"

    def test_inactive_drops_groups(self):
        s = scenario_from_dict(make_v1_dict(aktiv=False))
        assert s.groups == []

    def test_numeric_parity(self):
        """The upgraded canonical v1 file reproduces the legacy golden numbers."""
        res = hk.compute_all(scenario_from_dict(make_v1_dict(ww_by_group=True)))
        ne1, ne2 = res.ne_results
        assert ne1.total == pytest.approx(2527.396)
        assert ne2.total == pytest.approx(4214.604)

    def test_unassigned_nes_fold_into_first_group(self):
        d = make_v1_dict()
        d["nutzeinheiten"].append(
            {"id": 3, "flaeche": 50.0, "ww_m3": 10.0, "messtechnik": "hkv", "hz_wert": 1000.0})
        s = scenario_from_dict(d)
        assert 3 in s.groups[0].members


@pytest.mark.parametrize("name", list(BUILTIN_PRESETS))
def test_builtin_presets_compute_cleanly(name):
    scenario = scenario_from_dict(BUILTIN_PRESETS[name])
    results = hk.compute_all(scenario)
    hinweise = hk.validate_scenario(scenario, results)
    assert not hk.has_errors(hinweise), [h.text for h in hinweise]
    assert sum(n.total for n in results.ne_results) == pytest.approx(
        results.system.warmwasser_eur + results.system.heizung_eur
    )


def test_kreuzberg_builtin_uses_rest_pool():
    scenario = scenario_from_dict(BUILTIN_PRESETS["Kreuzberg gemischt WMZ/HKV"])
    assert len(scenario.groups) == 1
    assert scenario.groups[0].leistung == "hz"
    pools = hk.assemble_pools(scenario, "hz")
    assert len(pools) == 2
    assert pools[1].is_rest and pools[1].members == [3, 4]
    assert not hk.assemble_pools(scenario, "ww")   # WW ungrouped