"""Sidebar inputs; returns a fully-populated ScenarioConfig.

Layout: presets popover → Abrechnung → collapsible sections with live summary
labels (Kosten, CO2, Warmwasser-Energie, Verteilung) → Nutzergruppen →
Nutzeinheiten. Pool structure is derived from the domain (``assemble_pools``),
not re-implemented here.
"""
import hashlib
import json
from datetime import timedelta
from typing import Dict, List, Optional

import streamlit as st

import sankey.heizkosten as hk
from sankey.heizkosten import GroupConfig, NEConfig, NutzerConfig, ScenarioConfig, fmt

from ui import presets, state
from ui.state import sget
from ui.styles import dist_hint, section, subsection

VERTEIL_OPTIONS = list(hk.VERTEILSCHLUESSEL_OPTIONS)

WW_MODUS_MAP = state.WW_MODUS_MAP
CO2_MODUS_MAP = state.CO2_MODUS_MAP


# ── State → model helpers ─────────────────────────────────────────────────────

def _ne_state(ne_id: int, suffix: str):
    """Current widget value of a Nutzeinheit field (always fresh, key-based)."""
    return st.session_state.get(f"ne_{ne_id}_{suffix}", state.NE_DEFAULTS.get(suffix))


def _nutzer_from_state(ne_id: int) -> List[NutzerConfig]:
    ids = st.session_state.get(f"ne_{ne_id}_nutzer_ids", [1])
    return [
        NutzerConfig(
            bezeichnung=st.session_state.get(f"ne_{ne_id}_nutzer_{k}_bez", "") or "",
            von=(None if pos == 0
                 else st.session_state.get(f"ne_{ne_id}_nutzer_{k}_von")),
            vorauszahlung_eur=st.session_state.get(f"ne_{ne_id}_nutzer_{k}_vz", 0.0) or 0.0,
        )
        for pos, k in enumerate(ids)
    ]


def _nutzeinheiten_from_state() -> List[NEConfig]:
    return [
        NEConfig(
            id=ne["id"],
            flaeche=_ne_state(ne["id"], "flaeche"),
            ww_m3=_ne_state(ne["id"], "ww_m3"),
            hz_wert=_ne_state(ne["id"], "hz_wert"),
            messtechnik="wmz" if _ne_state(ne["id"], "messtechnik") == "WMZ" else "hkv",
            nutzer=_nutzer_from_state(ne["id"]),
        )
        for ne in st.session_state.ne_list
    ]


def _leistung(g: int) -> str:
    """Model value ('hz'/'ww'/'beide') of a group's Leistung widget."""
    return state.LEISTUNG_MAP[st.session_state.get(f"ng_{g}_leistung", "Heizung")]


def _skeleton_scenario(nutzeinheiten: List[NEConfig]) -> ScenarioConfig:
    """Members+Leistung-only scenario — enough to derive the pool structure."""
    label_to_id = {ne.label: ne.id for ne in nutzeinheiten}
    return ScenarioConfig(
        groups=[
            GroupConfig(
                id=g,
                members=[label_to_id[l]
                         for l in st.session_state.get(f"ng_{g}_members", [])
                         if l in label_to_id],
                leistung=_leistung(g),
            )
            for g in state.group_ids()
        ],
        nutzeinheiten=nutzeinheiten,
    )


def _pool_plan(skeleton: ScenarioConfig, gewerk: str) -> dict:
    """
    UI view of the domain pool structure (``assemble_pools``) for one Gewerk.

    Returns {} when the Gewerk is ungrouped, else:
      targeting:    ordered explicit group ids targeting the Gewerk
      display:      {g: display_number in the diagram}
      rest_members: labels of the automatic rest pool ([] if fully covered)
      rest_display: display number of the rest pool (None if no rest)
      derived:      explicit g without a consumption slider (WMZ-fixed/remainder)
      remainder_g:  explicit group acting as remainder (None if the rest does)
      wmz_kwh:      {g: meter sum} for WMZ-fixed explicit groups
      rest_wmz / rest_meter_kwh: rest pool fixed by meters + its sum
    """
    pools = hk.assemble_pools(skeleton, gewerk)
    if not pools:
        return {}
    nutzeinheiten = skeleton.nutzeinheiten
    ne_label = {ne.id: ne.label for ne in nutzeinheiten}
    explicit = [p for p in pools if not p.is_rest]
    rest = pools[-1] if pools[-1].is_rest else None
    wmz_kwh = {p.source_group_id: hk.pool_meter_sum(p, nutzeinheiten)
               for p in explicit if hk.pool_is_wmz_fixed(p, gewerk, nutzeinheiten)}

    derived = set(wmz_kwh)
    remainder_g: Optional[int] = None
    if rest is None:
        last_g = explicit[-1].source_group_id
        derived.add(last_g)
        if last_g not in wmz_kwh:
            remainder_g = last_g

    return {
        "targeting": [p.source_group_id for p in explicit],
        "display": {p.source_group_id: p.display_id for p in explicit},
        "rest_members": [ne_label[i] for i in rest.members] if rest else [],
        "rest_display": rest.display_id if rest else None,
        "derived": derived,
        "remainder_g": remainder_g,
        "wmz_kwh": wmz_kwh,
        "rest_wmz": rest is not None and hk.pool_is_wmz_fixed(rest, gewerk, nutzeinheiten),
        "rest_meter_kwh": hk.pool_meter_sum(rest, nutzeinheiten) if rest else 0.0,
    }


def _ww_fields() -> dict:
    return dict(
        ww_modus=WW_MODUS_MAP[sget("ww_modus")],
        ww_kwh_manuell=sget("vwwh"),
        ww_volumen_m3=None if sget("ww_volumen_auto") else sget("ww_volumen"),
        ww_temp_c=sget("ww_temp"),
        ww_flaeche_m2=None if sget("ww_flaeche_auto") else sget("ww_flaeche"),
    )


# ── Sections ──────────────────────────────────────────────────────────────────

def _szenario_inputs() -> None:
    """Preset load/save. Must render first: applying a preset rewrites widget
    keys, which is only allowed before those widgets are instantiated."""
    with st.popover("Vorlagen & Szenario", width="stretch"):
        st.selectbox("Vorlage", list(presets.BUILTIN_PRESETS), key="preset_choice")
        st.button(
            "Vorlage laden",
            on_click=lambda: presets.load_builtin(st.session_state["preset_choice"]),
            key="btn_load_preset",
            type="secondary",
        )

        uploaded = st.file_uploader("Szenario laden (JSON)", type="json", key="preset_upload")
        if uploaded is not None:
            raw = uploaded.getvalue()
            digest = hashlib.md5(raw).hexdigest()
            if st.session_state.get("_preset_hash") != digest:
                st.session_state["_preset_hash"] = digest
                try:
                    presets.apply_preset(json.loads(raw.decode("utf-8")))
                except (ValueError, KeyError, json.JSONDecodeError) as exc:
                    st.error(f"Szenario konnte nicht geladen werden: {exc}")
                else:
                    st.rerun()

        st.download_button(
            "Szenario speichern (JSON)",
            data=presets.scenario_to_json(scenario_from_state()),
            file_name="heizkosten_szenario.json",
            mime="application/json",
            key="btn_save_preset",
            type="secondary",
        )


def _abrechnung_inputs() -> None:
    section("Abrechnung")
    st.text_input("Objekt / Liegenschaft", key="objekt",
                  placeholder="z. B. MFH Musterstraße 1")
    cols = st.columns(2)
    cols[0].date_input("Zeitraum von", key="zeitraum_von", format="DD.MM.YYYY")
    cols[1].date_input("Zeitraum bis", key="zeitraum_bis", format="DD.MM.YYYY")


def _kosten_inputs() -> None:
    total = sget("beur") + sget("wk") + sget("gww") + sget("ghz")
    with st.expander(f"Kosten · {fmt.eur(total, 0)}", expanded=False):
        subsection("Brennstoff")
        st.number_input("kWh", step=100.0, format="%.0f", key="bkwh")
        st.number_input("€  (Brennstoff)", step=50.0, format="%.2f", key="beur")
        subsection("Weitere Kosten")
        st.number_input("€  (Weitere Kosten)", step=50.0, format="%.2f", key="wk")
        subsection("Gerätemieten")
        st.number_input("€  (Gerätemiete WW)", step=10.0, format="%.2f", key="gww")
        st.number_input("€  (Gerätemiete Hz)", step=10.0, format="%.2f", key="ghz")


def _co2_summary(nutzeinheiten: List[NEConfig]) -> str:
    if not sget("co2_aktiv"):
        return "CO2 · aus"
    if CO2_MODUS_MAP[sget("co2_modus")] == "stufen":
        flaeche = (sum(ne.flaeche for ne in nutzeinheiten)
                   if sget("co2_flaeche_auto") else sget("co2_flaeche"))
        stufe, anteil = hk.co2_vermieteranteil(hk.sdiv(sget("co2_emission"), flaeche))
        return f"CO2 · Stufe {stufe} · Vermieter {anteil:.0%}"
    return f"CO2 · Vermieter {sget('co2_v_anteil')}%"


def _co2_inputs(nutzeinheiten: List[NEConfig]) -> None:
    with st.expander(_co2_summary(nutzeinheiten), expanded=False):
        if not st.toggle("CO2-Aufteilung aktivieren", key="co2_aktiv"):
            return
        st.number_input("CO2-Kosten (€)", min_value=0.0, step=10.0, format="%.2f",
                        key="co2_kosten")
        st.radio("Aufteilung", list(CO2_MODUS_MAP), key="co2_modus", horizontal=True)
        if CO2_MODUS_MAP[sget("co2_modus")] == "stufen":
            st.number_input("CO2-Ausstoß (kg/Jahr)", min_value=0.0, step=100.0,
                            format="%.0f", key="co2_emission")
            st.checkbox("Wohnfläche = Summe der Nutzeinheiten", key="co2_flaeche_auto")
            if not sget("co2_flaeche_auto"):
                st.number_input("Wohnfläche (m²)", min_value=1.0, step=5.0,
                                format="%.1f", key="co2_flaeche")
            flaeche = (sum(ne.flaeche for ne in nutzeinheiten)
                       if sget("co2_flaeche_auto") else sget("co2_flaeche"))
            spez = hk.sdiv(sget("co2_emission"), flaeche)
            stufe, anteil = hk.co2_vermieteranteil(spez)
            st.markdown(
                f'<div class="dist-hint">{fmt.num(spez, 1)} kg CO2/m²·a → Stufe {stufe} → '
                f'Vermieter {anteil:.0%}</div>',
                unsafe_allow_html=True,
            )
        else:
            anteil_pct = st.slider("Anteil Vermieter (%)", 0, 100, step=10, key="co2_v_anteil")
            anteil = anteil_pct / 100
            st.markdown(
                f'<div class="dist-hint">Vermieter {anteil:.0%} · Mieter {1 - anteil:.0%}</div>',
                unsafe_allow_html=True,
            )


def _ww_energie_inputs(ww_energie: "hk.WWEnergieErgebnis") -> None:
    label = f"Warmwasser-Energie · {fmt.kwh(ww_energie.kwh)}"
    with st.expander(label, expanded=False):
        st.radio("Ermittlung (§9 Abs. 2)", list(WW_MODUS_MAP), key="ww_modus")
        modus = WW_MODUS_MAP[sget("ww_modus")]
        if modus == "manuell":
            brennstoff_kwh = sget("bkwh")
            state.clamp_state("vwwh", 0.0, float(brennstoff_kwh))
            st.slider(
                "Verbrauch Warmwasser (kWh)",
                min_value=0.0,
                max_value=float(brennstoff_kwh),
                step=50.0,
                key="vwwh",
            )
        elif modus == "formel":
            st.checkbox("Volumen = Summe der Nutzeinheiten", key="ww_volumen_auto")
            if not sget("ww_volumen_auto"):
                st.number_input("Warmwasser-Volumen (m³)", min_value=0.0, step=1.0,
                                format="%.1f", key="ww_volumen")
            st.number_input("Warmwassertemperatur (°C)", min_value=20.0, max_value=90.0,
                            step=1.0, format="%.0f", key="ww_temp")
        else:  # pauschale
            st.checkbox("Wohnfläche = Summe der Nutzeinheiten", key="ww_flaeche_auto")
            if not sget("ww_flaeche_auto"):
                st.number_input("Wohnfläche (m²)", min_value=1.0, step=5.0,
                                format="%.1f", key="ww_flaeche")
        st.markdown(f'<div class="dist-hint">→ {ww_energie.beschreibung}</div>',
                    unsafe_allow_html=True)


def _verteilschluessel(label: str, key: str, help_text: str) -> None:
    val = st.select_slider(label, options=VERTEIL_OPTIONS, key=key, help=help_text)
    dist_hint(val)


def _verteilung_inputs(plans: Dict[str, dict]) -> None:
    """Shared Verteilschlüssel — rendered per Gewerk that has no Nutzergruppen."""
    if plans["hz"] and plans["ww"]:
        return
    parts = []
    if not plans["ww"]:
        parts.append(f"WW {sget('vww')}/{100 - sget('vww')}")
    if not plans["hz"]:
        parts.append(f"Hz {sget('vhz')}/{100 - sget('vhz')}")
    with st.expander("Verteilung · " + " · ".join(parts), expanded=False):
        if not plans["ww"]:
            subsection("Warmwasser")
            _verteilschluessel("Verteilschlüssel Warmwasser", "vww",
                               "Anteil der Grundkosten — der Rest sind Verbrauchskosten")
        if not plans["hz"]:
            subsection("Heizung")
            _verteilschluessel("Verteilschlüssel Heizung", "vhz",
                               "Anteil der Grundkosten — der Rest sind Verbrauchskosten")


def _remainder_kwh(plan: dict, gewerk: str, pool_kwh: float) -> float:
    """Pool size minus all explicitly set / WMZ-derived consumptions."""
    rest = pool_kwh
    for g in plan["targeting"]:
        if g == plan["remainder_g"]:
            continue
        if g in plan["wmz_kwh"]:
            rest -= plan["wmz_kwh"][g]
        else:
            rest -= st.session_state.get(f"ng_{g}_{gewerk}_kwh", 0.0)
    return max(0.0, rest)


def _nutzergruppen_inputs(plans: Dict[str, dict], pools_kwh: Dict[str, float],
                          all_labels: List[str]) -> None:
    ids = state.group_ids()
    section("Nutzergruppen", f"{len(ids)} / {hk.MAX_EXPLICIT_NG}" if ids else "keine")

    if ids:
        st.selectbox("Abrechnungsart", ["Abrechnungsart 1", "Kreuzberg"], key="ng_type")
        if sget("ng_type") == "Kreuzberg":
            subsection("Vorverteilschlüssel")
            if plans["hz"]:
                _verteilschluessel("Vorverteilschlüssel Heizung", "vorv_hz",
                                   "Vorab-Aufteilung in Grundkosten / Verbrauchskosten (gilt für alle Pools)")
            if plans["ww"]:
                _verteilschluessel("Vorverteilschlüssel Warmwasser", "vorv_ww",
                                   "Vorab-Aufteilung in Grundkosten / Verbrauchskosten (gilt für alle Pools)")

    for idx, g in enumerate(ids, start=1):
        bez = (st.session_state.get(f"ng_{g}_bezeichnung", "") or "").strip()
        title = f"Nutzergruppe {idx}" + (f" · {bez}" if bez else "")
        with st.expander(title, expanded=True):
            st.text_input("Bezeichnung", key=f"ng_{g}_bezeichnung",
                          placeholder="z. B. Vorderhaus")
            st.selectbox("Leistung", list(state.LEISTUNG_MAP), key=f"ng_{g}_leistung",
                         help="Für welches Gewerk diese Gruppe gilt")
            # Groups are non-exclusive — a Nutzeinheit may be in several groups
            st.multiselect("Nutzeinheiten", options=all_labels, key=f"ng_{g}_members")

            for gw, gw_label in (("hz", "Hz"), ("ww", "WW")):
                plan = plans[gw]
                if not plan or g not in plan["targeting"]:
                    continue
                if g in plan["wmz_kwh"] and g != plan["remainder_g"]:
                    st.markdown(f'<div class="dist-hint">Verbrauch Hz: ∑ WMZ '
                                f'{fmt.kwh(plan["wmz_kwh"][g])}</div>',
                                unsafe_allow_html=True)
                elif g == plan["remainder_g"]:
                    rest = _remainder_kwh(plan, gw, pools_kwh[gw])
                    st.markdown(f'<div class="dist-hint">Verbrauch {gw_label} (Rest): '
                                f'{fmt.kwh(rest)}</div>', unsafe_allow_html=True)
                else:
                    key = f"ng_{g}_{gw}_kwh"
                    state.clamp_state(key, 0.0, pools_kwh[gw])
                    st.slider(f"Verbrauch {gw_label} (kWh)", min_value=0.0,
                              max_value=pools_kwh[gw], step=50.0, key=key)
                _verteilschluessel(
                    f"Verteilschlüssel {gw_label}", f"ng_{g}_v{gw}",
                    "Anteil der Grundkosten — der Rest sind Verbrauchskosten")

            display_parts = []
            for gw, gw_name in (("hz", "Heizung"), ("ww", "Warmwasser")):
                plan = plans[gw]
                if plan and g in plan["display"] and plan["display"][g] != idx:
                    display_parts.append(f"NG {plan['display'][g]} – {gw_name}")
            if display_parts:
                st.markdown(f'<div class="dist-hint">Im Diagramm: '
                            f'{" · ".join(display_parts)}</div>', unsafe_allow_html=True)

            st.button("Entfernen", key=f"del_ng_{g}", on_click=state.remove_group,
                      args=(g,), type="secondary")

    if len(ids) < hk.MAX_EXPLICIT_NG:
        st.button(f"+ Nutzergruppe hinzufügen  ({len(ids) + 1} / {hk.MAX_EXPLICIT_NG})",
                  on_click=state.add_group, key="btn_add_group", type="secondary")
    else:
        st.markdown(
            f'<div class="dist-hint">Maximum von {hk.MAX_EXPLICIT_NG} Nutzergruppen erreicht.</div>',
            unsafe_allow_html=True,
        )

    # Automatic rest pool per grouped Gewerk
    for gw, gw_name in (("hz", "Heizung"), ("ww", "Warmwasser")):
        plan = plans[gw]
        if not plan or not plan["rest_members"]:
            continue
        subsection(f"Rest – {gw_name} (NG {plan['rest_display']})")
        st.markdown(
            f'<div class="dist-hint">{", ".join(plan["rest_members"])}</div>',
            unsafe_allow_html=True,
        )
        if plan["rest_wmz"]:
            st.markdown(f'<div class="dist-hint">Verbrauch: ∑ WMZ '
                        f'{fmt.kwh(plan["rest_meter_kwh"])}</div>', unsafe_allow_html=True)
        else:
            rest = _remainder_kwh(plan, gw, pools_kwh[gw])
            st.markdown(f'<div class="dist-hint">Verbrauch (Rest): {fmt.kwh(rest)}</div>',
                        unsafe_allow_html=True)
        _verteilschluessel(f"Verteilschlüssel {gw_name} (Rest)", f"rest_v{gw}",
                           "Anteil der Grundkosten — der Rest sind Verbrauchskosten")


def _ne_title(ne_id: int) -> str:
    """Expander title: Bezeichnung (single user) or user count (Nutzerwechsel)."""
    ids = st.session_state.get(f"ne_{ne_id}_nutzer_ids", [1])
    base = hk.ne_node_name(ne_id)
    if len(ids) >= 2:
        return f"{base} · {len(ids)} Nutzer"
    bez = (st.session_state.get(f"ne_{ne_id}_nutzer_{ids[0]}_bez", "") or "").strip()
    return f"{base} · {bez}" if bez else base


def _nutzer_inputs(ne_id: int) -> None:
    """Per-user blocks: Bezeichnung + Vorauszahlung; users 2+ get a Wechsel-Datum."""
    ids = st.session_state[f"ne_{ne_id}_nutzer_ids"]
    zeitraum_von, zeitraum_bis = sget("zeitraum_von"), sget("zeitraum_bis")
    for pos, k in enumerate(ids, start=1):
        subsection(f"Nutzer {pos}" + ("" if pos == 1 else " (Nutzerwechsel)"))
        if pos > 1 and zeitraum_von and zeitraum_bis and zeitraum_von < zeitraum_bis:
            lo = zeitraum_von + timedelta(days=1)
            state.clamp_state(f"ne_{ne_id}_nutzer_{k}_von", lo, zeitraum_bis)
            st.date_input("Nutzerwechsel zum", key=f"ne_{ne_id}_nutzer_{k}_von",
                          min_value=lo, max_value=zeitraum_bis, format="DD.MM.YYYY",
                          help="Erster Tag des neuen Nutzers — der Vornutzer endet "
                               "am Vortag (§9b HeizkostenV).")
        st.text_input("Bezeichnung", key=f"ne_{ne_id}_nutzer_{k}_bez",
                      placeholder="z. B. Fam. Muster")
        st.number_input("Vorauszahlung (€)", min_value=0.0, step=50.0, format="%.2f",
                        key=f"ne_{ne_id}_nutzer_{k}_vz",
                        help="Vorauszahlungen dieses Nutzers — der Bericht weist "
                             "je Nutzer Nachzahlung/Guthaben aus.")
        if pos > 1:
            st.button("Nutzer entfernen", key=f"del_nutzer_{ne_id}_{k}",
                      on_click=state.remove_nutzer, args=(ne_id, k), type="secondary")
    if len(ids) < hk.MAX_NUTZER_JE_NE:
        st.button(f"+ Nutzerwechsel  ({len(ids)} / {hk.MAX_NUTZER_JE_NE} Nutzer)",
                  key=f"btn_add_nutzer_{ne_id}", on_click=state.add_nutzer,
                  args=(ne_id,), type="secondary")


def _nutzeinheiten_inputs(nutzeinheiten: List[NEConfig]) -> None:
    count = len(nutzeinheiten)
    total_m2 = sum(ne.flaeche for ne in nutzeinheiten)
    section("Nutzeinheiten", f"{count} · {fmt.m2(total_m2)}")
    for ne in st.session_state.ne_list:
        ne_id = ne["id"]
        with st.expander(_ne_title(ne_id), expanded=(ne_id <= 2)):
            ne["flaeche"] = st.number_input("Fläche (m²)", step=0.5, format="%.1f",
                                            key=f"ne_{ne_id}_flaeche")
            ne["ww_m3"] = st.number_input("Warmwasser (m³)", step=0.5, format="%.1f",
                                          key=f"ne_{ne_id}_ww_m3")
            ne["messtechnik"] = st.radio(
                "Messtechnik Heizung", ["HKV", "WMZ"], horizontal=True,
                key=f"ne_{ne_id}_messtechnik",
                help="HKV: Heizkostenverteiler (Verbrauchseinheiten) · "
                     "WMZ: Wärmemengenzähler (kWh)",
            )
            if ne["messtechnik"] == "WMZ":
                ne["hz_wert"] = st.number_input("Heizung (kWh)", step=10.0,
                                                format="%.0f", key=f"ne_{ne_id}_hz_wert")
            else:
                ne["hz_wert"] = st.number_input("Heizung (Verbrauchseinheiten)", step=1.0,
                                                format="%.0f", key=f"ne_{ne_id}_hz_wert")
            _nutzer_inputs(ne_id)
            if ne_id > 2:
                st.button("Entfernen", key=f"del_{ne_id}", on_click=state.remove_ne,
                          args=(ne_id,), type="secondary")

    if count < state.MAX_NE:
        st.button(f"+ Nutzeinheit hinzufügen  ({count + 1} / {state.MAX_NE})",
                  on_click=state.add_ne, key="btn_add_ne", type="secondary")
    else:
        st.markdown(
            f'<div class="dist-hint">Maximum von {state.MAX_NE} Nutzeinheiten erreicht.</div>',
            unsafe_allow_html=True,
        )


# ── Scenario assembly ─────────────────────────────────────────────────────────

def scenario_from_state() -> ScenarioConfig:
    """Assemble the typed scenario from session state (single source of truth)."""
    nutzeinheiten = _nutzeinheiten_from_state()
    skeleton = _skeleton_scenario(nutzeinheiten)
    plans = {gw: _pool_plan(skeleton, gw) for gw in ("hz", "ww")}

    def consumption(g: int, gw: str):
        """Slider value, or None when derived (WMZ sum / remainder / not targeted)."""
        plan = plans[gw]
        if not plan or g not in plan["targeting"]:
            return None
        if g in plan["derived"] or g == plan["remainder_g"]:
            return None
        return st.session_state.get(f"ng_{g}_{gw}_kwh")

    groups = [
        GroupConfig(
            id=grp.id,
            bezeichnung=st.session_state.get(f"ng_{grp.id}_bezeichnung", "") or "",
            members=grp.members,
            leistung=grp.leistung,
            hz_kwh=consumption(grp.id, "hz"),
            ww_kwh=consumption(grp.id, "ww"),
            verteilung_hz_pct=st.session_state.get(f"ng_{grp.id}_vhz", 40),
            verteilung_ww_pct=st.session_state.get(f"ng_{grp.id}_vww", 30),
        )
        for grp in skeleton.groups
    ]
    return ScenarioConfig(
        objekt=sget("objekt") or "",
        zeitraum_von=sget("zeitraum_von"),
        zeitraum_bis=sget("zeitraum_bis"),
        brennstoff_kwh=sget("bkwh"),
        brennstoff_eur=sget("beur"),
        weitere_kosten_eur=sget("wk"),
        geraetemiete_ww_eur=sget("gww"),
        geraetemiete_hz_eur=sget("ghz"),
        co2_aktiv=sget("co2_aktiv"),
        co2_modus=CO2_MODUS_MAP[sget("co2_modus")],
        co2_kosten_eur=sget("co2_kosten"),
        co2_emission_kg=sget("co2_emission"),
        co2_flaeche_m2=None if sget("co2_flaeche_auto") else sget("co2_flaeche"),
        co2_anteil_vermieter_pct=sget("co2_v_anteil"),
        verteilung_ww_pct=sget("vww"),
        verteilung_hz_pct=sget("vhz"),
        ng_art="kreuzberg" if sget("ng_type") == "Kreuzberg" else "art1",
        vorverteilung_ww_pct=sget("vorv_ww"),
        vorverteilung_hz_pct=sget("vorv_hz"),
        rest_verteilung_hz_pct=sget("rest_vhz"),
        rest_verteilung_ww_pct=sget("rest_vww"),
        groups=groups,
        nutzeinheiten=nutzeinheiten,
        **_ww_fields(),
    )


def render_sidebar() -> ScenarioConfig:
    with st.sidebar:
        _szenario_inputs()
        _abrechnung_inputs()

        nutzeinheiten = _nutzeinheiten_from_state()
        skeleton = _skeleton_scenario(nutzeinheiten)
        plans = {gw: _pool_plan(skeleton, gw) for gw in ("hz", "ww")}
        ww_energie = hk.compute_ww_energie(ScenarioConfig(
            brennstoff_kwh=sget("bkwh"), nutzeinheiten=nutzeinheiten, **_ww_fields()))
        pools_kwh = {"ww": max(0.01, float(ww_energie.kwh)),
                     "hz": max(0.01, float(sget("bkwh") - ww_energie.kwh))}

        _kosten_inputs()
        _co2_inputs(nutzeinheiten)
        _ww_energie_inputs(ww_energie)
        _verteilung_inputs(plans)
        _nutzergruppen_inputs(plans, pools_kwh, [ne.label for ne in nutzeinheiten])
        _nutzeinheiten_inputs(nutzeinheiten)
    return scenario_from_state()
