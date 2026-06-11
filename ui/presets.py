"""Scenario presets: versioned semantic JSON (save/load) + built-in examples.

The schema is semantic (model field names), NOT widget keys, so saved files
survive UI refactors. ``apply_preset`` translates a dict into widget keys.
"""
import json
from datetime import date
from typing import Any, Dict, Optional

import streamlit as st

import sankey.heizkosten as hk
from sankey.heizkosten import GroupConfig, NEConfig, NutzerConfig, ScenarioConfig

from ui import state

SCHEMA_VERSION = 4


def _date_to_iso(d: Optional[date]) -> Optional[str]:
    return d.isoformat() if d else None


def _date_from_iso(s: Optional[str]) -> Optional[date]:
    return date.fromisoformat(s) if s else None


def scenario_to_dict(s: ScenarioConfig) -> Dict[str, Any]:
    return {
        "version": SCHEMA_VERSION,
        "abrechnung": {
            "objekt": s.objekt,
            "zeitraum_von": _date_to_iso(s.zeitraum_von),
            "zeitraum_bis": _date_to_iso(s.zeitraum_bis),
        },
        "gebaeude": {
            "brennstoff_kwh": s.brennstoff_kwh,
            "brennstoff_eur": s.brennstoff_eur,
            "weitere_kosten_eur": s.weitere_kosten_eur,
            "geraetemiete_ww_eur": s.geraetemiete_ww_eur,
            "geraetemiete_hz_eur": s.geraetemiete_hz_eur,
        },
        "co2": {
            "aktiv": s.co2_aktiv,
            "modus": s.co2_modus,
            "kosten_eur": s.co2_kosten_eur,
            "emission_kg": s.co2_emission_kg,
            "flaeche_m2": s.co2_flaeche_m2,
            "anteil_vermieter_pct": s.co2_anteil_vermieter_pct,
        },
        "warmwasser": {
            "modus": s.ww_modus,
            "kwh_manuell": s.ww_kwh_manuell,
            "volumen_m3": s.ww_volumen_m3,
            "temperatur_c": s.ww_temp_c,
            "flaeche_m2": s.ww_flaeche_m2,
        },
        "verteilung": {
            "vww_pct": s.verteilung_ww_pct,
            "vhz_pct": s.verteilung_hz_pct,
        },
        "nutzergruppen": {
            "art": s.ng_art,
            "vorverteilung_ww_pct": s.vorverteilung_ww_pct,
            "vorverteilung_hz_pct": s.vorverteilung_hz_pct,
            "rest_verteilung_hz_pct": s.rest_verteilung_hz_pct,
            "rest_verteilung_ww_pct": s.rest_verteilung_ww_pct,
            "gruppen": [
                {
                    "id": g.id,
                    "bezeichnung": g.bezeichnung,
                    "leistung": g.leistung,
                    "mitglieder": list(g.members),
                    "hz_kwh": g.hz_kwh,
                    "ww_kwh": g.ww_kwh,
                    "verteilung_hz_pct": g.verteilung_hz_pct,
                    "verteilung_ww_pct": g.verteilung_ww_pct,
                }
                for g in s.groups
            ],
        },
        "nutzeinheiten": [
            {"id": ne.id, "flaeche": ne.flaeche, "ww_m3": ne.ww_m3,
             "messtechnik": ne.messtechnik, "hz_wert": ne.hz_wert,
             "nutzer": [
                 {"bezeichnung": nu.bezeichnung, "von": _date_to_iso(nu.von),
                  "vorauszahlung_eur": nu.vorauszahlung_eur}
                 for nu in ne.nutzer
             ]}
            for ne in s.nutzeinheiten
        ],
    }


def _upgrade_v1(d: Dict[str, Any]) -> Dict[str, Any]:
    """v1 → v2: the old last group becomes the automatic rest pool; remaining
    groups get the Leistung implied by ww_by_group; NEs in no old group are
    folded into the first group (old compute defaulted them to group 1)."""
    d = json.loads(json.dumps(d))  # deep copy
    ng = d["nutzergruppen"]
    aktiv = ng.pop("aktiv", False)
    ww_by_group = ng.pop("ww_by_group", False)
    gruppen = ng.get("gruppen", [])
    ng.setdefault("rest_verteilung_hz_pct", 40)
    ng.setdefault("rest_verteilung_ww_pct", 30)

    if not aktiv or not gruppen:
        ng["gruppen"] = []
    else:
        last = gruppen[-1]
        ng["rest_verteilung_hz_pct"] = last.get("verteilung_hz_pct", 40)
        ng["rest_verteilung_ww_pct"] = last.get("verteilung_ww_pct", 30)
        assigned = {i for g in gruppen for i in g.get("mitglieder", [])}
        gruppen = gruppen[:-1]
        for g in gruppen:
            g["leistung"] = "beide" if ww_by_group else "hz"
        if gruppen:
            unassigned = [ne["id"] for ne in d.get("nutzeinheiten", [])
                          if ne["id"] not in assigned]
            gruppen[0]["mitglieder"] = list(gruppen[0].get("mitglieder", [])) + unassigned
        ng["gruppen"] = gruppen

    d["version"] = 2
    return d


def _upgrade_v2(d: Dict[str, Any]) -> Dict[str, Any]:
    """v2 → v3: add the Abrechnung header block and per-NE billing fields."""
    d = json.loads(json.dumps(d))  # deep copy
    d.setdefault("abrechnung", {"objekt": "", "zeitraum_von": None, "zeitraum_bis": None})
    for ne in d.get("nutzeinheiten", []):
        ne.setdefault("bezeichnung", "")
        ne.setdefault("vorauszahlung_eur", 0.0)
    d["version"] = 3
    return d


def _upgrade_v3(d: Dict[str, Any]) -> Dict[str, Any]:
    """v3 → v4: per-NE billing fields become the (single) first Nutzer;
    Nutzergruppen gain a Bezeichnung."""
    d = json.loads(json.dumps(d))  # deep copy
    for ne in d.get("nutzeinheiten", []):
        ne["nutzer"] = [{
            "bezeichnung": ne.pop("bezeichnung", ""),
            "von": None,
            "vorauszahlung_eur": ne.pop("vorauszahlung_eur", 0.0),
        }]
    for g in d.get("nutzergruppen", {}).get("gruppen", []):
        g.setdefault("bezeichnung", "")
    d["version"] = SCHEMA_VERSION
    return d


def scenario_from_dict(d: Dict[str, Any]) -> ScenarioConfig:
    if d.get("version") == 1:
        d = _upgrade_v1(d)
    if d.get("version") == 2:
        d = _upgrade_v2(d)
    if d.get("version") == 3:
        d = _upgrade_v3(d)
    if d.get("version") != SCHEMA_VERSION:
        raise ValueError(f"Unbekannte Szenario-Version: {d.get('version')!r}")
    abr = d["abrechnung"]
    geb, co2, ww = d["gebaeude"], d["co2"], d["warmwasser"]
    vert, ng = d["verteilung"], d["nutzergruppen"]
    return ScenarioConfig(
        objekt=abr.get("objekt", ""),
        zeitraum_von=_date_from_iso(abr.get("zeitraum_von")),
        zeitraum_bis=_date_from_iso(abr.get("zeitraum_bis")),
        brennstoff_kwh=geb["brennstoff_kwh"],
        brennstoff_eur=geb["brennstoff_eur"],
        weitere_kosten_eur=geb["weitere_kosten_eur"],
        geraetemiete_ww_eur=geb["geraetemiete_ww_eur"],
        geraetemiete_hz_eur=geb["geraetemiete_hz_eur"],
        co2_aktiv=co2["aktiv"],
        co2_modus=co2["modus"],
        co2_kosten_eur=co2["kosten_eur"],
        co2_emission_kg=co2["emission_kg"],
        co2_flaeche_m2=co2["flaeche_m2"],
        co2_anteil_vermieter_pct=co2["anteil_vermieter_pct"],
        ww_modus=ww["modus"],
        ww_kwh_manuell=ww["kwh_manuell"],
        ww_volumen_m3=ww["volumen_m3"],
        ww_temp_c=ww["temperatur_c"],
        ww_flaeche_m2=ww["flaeche_m2"],
        verteilung_ww_pct=vert["vww_pct"],
        verteilung_hz_pct=vert["vhz_pct"],
        ng_art=ng["art"],
        vorverteilung_ww_pct=ng["vorverteilung_ww_pct"],
        vorverteilung_hz_pct=ng["vorverteilung_hz_pct"],
        rest_verteilung_hz_pct=ng.get("rest_verteilung_hz_pct", 40),
        rest_verteilung_ww_pct=ng.get("rest_verteilung_ww_pct", 30),
        groups=[
            GroupConfig(
                id=g["id"], members=list(g["mitglieder"]),
                bezeichnung=g.get("bezeichnung", ""),
                leistung=g.get("leistung", "beide"),
                hz_kwh=g["hz_kwh"], ww_kwh=g["ww_kwh"],
                verteilung_hz_pct=g["verteilung_hz_pct"],
                verteilung_ww_pct=g["verteilung_ww_pct"],
            )
            for g in ng["gruppen"]
        ],
        nutzeinheiten=[
            NEConfig(id=ne["id"], flaeche=ne["flaeche"], ww_m3=ne["ww_m3"],
                     messtechnik=ne["messtechnik"], hz_wert=ne["hz_wert"],
                     nutzer=[
                         NutzerConfig(
                             bezeichnung=nu.get("bezeichnung", ""),
                             von=_date_from_iso(nu.get("von")),
                             vorauszahlung_eur=nu.get("vorauszahlung_eur", 0.0),
                         )
                         for nu in ne.get("nutzer", [])
                     ])
            for ne in d["nutzeinheiten"]
        ],
    )


def scenario_to_json(s: ScenarioConfig) -> str:
    return json.dumps(scenario_to_dict(s), indent=2, ensure_ascii=False)


def apply_preset(d: Dict[str, Any]) -> None:
    """Write a scenario dict into widget keys. Must run before those widgets render."""
    scenario = scenario_from_dict(d)  # validates structure & version

    # Drop all dynamic keys from the previous configuration
    stale = [k for k in st.session_state if k.startswith(("ne_", "ng_"))]
    for k in stale:
        del st.session_state[k]

    ss = st.session_state
    ss["objekt"] = scenario.objekt
    ss["zeitraum_von"] = scenario.zeitraum_von or state.DEFAULTS["zeitraum_von"]
    ss["zeitraum_bis"] = scenario.zeitraum_bis or state.DEFAULTS["zeitraum_bis"]
    ss["bkwh"] = scenario.brennstoff_kwh
    ss["beur"] = scenario.brennstoff_eur
    ss["wk"] = scenario.weitere_kosten_eur
    ss["gww"] = scenario.geraetemiete_ww_eur
    ss["ghz"] = scenario.geraetemiete_hz_eur

    ss["co2_aktiv"] = scenario.co2_aktiv
    ss["co2_modus"] = state.CO2_MODUS_INVERSE[scenario.co2_modus]
    ss["co2_kosten"] = scenario.co2_kosten_eur
    ss["co2_emission"] = scenario.co2_emission_kg or state.DEFAULTS["co2_emission"]
    ss["co2_flaeche_auto"] = scenario.co2_flaeche_m2 is None
    ss["co2_flaeche"] = scenario.co2_flaeche_m2 or state.DEFAULTS["co2_flaeche"]
    ss["co2_v_anteil"] = scenario.co2_anteil_vermieter_pct

    ss["ww_modus"] = state.WW_MODUS_INVERSE[scenario.ww_modus]
    ss["vwwh"] = scenario.ww_kwh_manuell
    ss["ww_volumen_auto"] = scenario.ww_volumen_m3 is None
    ss["ww_volumen"] = scenario.ww_volumen_m3 or state.DEFAULTS["ww_volumen"]
    ss["ww_temp"] = scenario.ww_temp_c
    ss["ww_flaeche_auto"] = scenario.ww_flaeche_m2 is None
    ss["ww_flaeche"] = scenario.ww_flaeche_m2 or state.DEFAULTS["ww_flaeche"]

    ss["vww"] = scenario.verteilung_ww_pct
    ss["vhz"] = scenario.verteilung_hz_pct

    ss["ng_type"] = state.NG_ART_INVERSE[scenario.ng_art]
    ss["vorv_ww"] = scenario.vorverteilung_ww_pct
    ss["vorv_hz"] = scenario.vorverteilung_hz_pct
    ss["rest_vhz"] = scenario.rest_verteilung_hz_pct
    ss["rest_vww"] = scenario.rest_verteilung_ww_pct

    ss["ne_list"] = [
        {"id": ne.id, "flaeche": ne.flaeche, "ww_m3": ne.ww_m3,
         "hz_wert": ne.hz_wert, "messtechnik": ne.messtechnik.upper()}
        for ne in scenario.nutzeinheiten
    ]
    for ne in ss["ne_list"]:
        for suffix in state.NE_KEY_SUFFIXES:
            ss[f"ne_{ne['id']}_{suffix}"] = ne[suffix]
    for ne in scenario.nutzeinheiten:
        ss[f"ne_{ne.id}_nutzer_ids"] = list(range(1, len(ne.nutzer) + 1))
        for k, nu in enumerate(ne.nutzer, start=1):
            ss[f"ne_{ne.id}_nutzer_{k}_bez"] = nu.bezeichnung
            ss[f"ne_{ne.id}_nutzer_{k}_vz"] = nu.vorauszahlung_eur
            ss[f"ne_{ne.id}_nutzer_{k}_von"] = nu.von or state.default_wechsel_datum()

    ss["ng_group_ids"] = [g.id for g in scenario.groups]
    labels = {ne.id: ne.label for ne in scenario.nutzeinheiten}
    for g in scenario.groups:
        ss[f"ng_{g.id}_bezeichnung"] = g.bezeichnung
        ss[f"ng_{g.id}_leistung"] = state.LEISTUNG_INVERSE[g.leistung]
        ss[f"ng_{g.id}_members"] = [labels[i] for i in g.members if i in labels]
        ss[f"ng_{g.id}_vhz"] = g.verteilung_hz_pct
        ss[f"ng_{g.id}_vww"] = g.verteilung_ww_pct
        if g.hz_kwh is not None:
            ss[f"ng_{g.id}_hz_kwh"] = g.hz_kwh
        if g.ww_kwh is not None:
            ss[f"ng_{g.id}_ww_kwh"] = g.ww_kwh

    ss["sankey_ne_filter"] = [labels[ne.id] for ne in scenario.nutzeinheiten][:2]


# ── Built-in example presets ──────────────────────────────────────────────────

_STANDARD = ScenarioConfig(
    nutzeinheiten=[
        NEConfig(id=1, flaeche=68.0, ww_m3=18.0, hz_wert=1850.0),
        NEConfig(id=2, flaeche=90.0, ww_m3=23.5, hz_wert=2450.0),
    ],
)

_LAST_YEAR = date.today().year - 1

_KREUZBERG_GEMISCHT = ScenarioConfig(
    objekt="MFH Beispielstraße 12, 10999 Berlin",
    zeitraum_von=date(_LAST_YEAR, 1, 1),
    zeitraum_bis=date(_LAST_YEAR, 12, 31),
    co2_aktiv=True,
    co2_modus="stufen",
    co2_emission_kg=5400.0,
    ww_modus="formel",
    ng_art="kreuzberg",
    nutzeinheiten=[
        NEConfig(id=1, flaeche=68.0, ww_m3=18.0, hz_wert=11500.0, messtechnik="wmz",
                 nutzer=[NutzerConfig("Whg. 1 · EG links", vorauszahlung_eur=2200.0)]),
        NEConfig(id=2, flaeche=55.0, ww_m3=14.0, hz_wert=9200.0, messtechnik="wmz",
                 nutzer=[NutzerConfig("Whg. 2 · EG rechts", vorauszahlung_eur=1700.0)]),
        # Whg. 3 demonstrates a Nutzerwechsel (§9b) mid-period
        NEConfig(id=3, flaeche=90.0, ww_m3=23.5, hz_wert=2450.0, messtechnik="hkv",
                 nutzer=[
                     NutzerConfig("Fam. Alt (Whg. 3)", vorauszahlung_eur=900.0),
                     NutzerConfig("Fam. Neumann (Whg. 3)",
                                  von=date(_LAST_YEAR, 7, 1),
                                  vorauszahlung_eur=700.0),
                 ]),
        NEConfig(id=4, flaeche=75.0, ww_m3=19.0, hz_wert=2100.0, messtechnik="hkv",
                 nutzer=[NutzerConfig("Whg. 4 · DG", vorauszahlung_eur=1200.0)]),
    ],
    groups=[
        # One explicit Hz group with the WMZ flats; the HKV flats form the
        # automatic rest pool (consumption = remainder, no sliders needed).
        GroupConfig(id=1, bezeichnung="WMZ-Wohnungen EG", members=[1, 2], leistung="hz",
                    hz_kwh=None, ww_kwh=None,
                    verteilung_hz_pct=40, verteilung_ww_pct=30),
    ],
)

BUILTIN_PRESETS = {
    "Standard (2 Wohnungen)": scenario_to_dict(_STANDARD),
    "Kreuzberg gemischt WMZ/HKV": scenario_to_dict(_KREUZBERG_GEMISCHT),
}


def load_builtin(name: str) -> None:
    apply_preset(BUILTIN_PRESETS[name])
