"""Session-state management: single source of truth for every widget default.

All widgets in the app are created with `key=` only — `init_state()` seeds each
key once per session, so defaults live exclusively in the dicts below.

Nutzergruppen use dynamic keys `ng_{g}_bezeichnung / _leistung / _members /
_hz_kwh / _ww_kwh / _vhz / _vww` with the explicit group ids tracked in
`ng_group_ids` (0 to MAX_EXPLICIT_NG groups). Unassigned NEs form an automatic
rest pool per Gewerk whose Verteilschlüssel live in `rest_vhz` / `rest_vww`.

Nutzer (§9b Nutzerwechsel) use `ne_{id}_nutzer_{k}_bez / _von / _vz` with the
per-NE user ids tracked in `ne_{id}_nutzer_ids` (first user = Beginn des
Abrechnungszeitraums, no date).
"""
from datetime import date, timedelta

import streamlit as st

import sankey.heizkosten as hk
from sankey.heizkosten import MAX_EXPLICIT_NG, MAX_NE

# Default fractions used to derive dependent defaults
DEFAULT_WW_KWH_FRACTION = 0.22   # share of fuel energy attributed to Warmwasser
DEFAULT_NG1_WW_FRACTION = 0.30   # NG 1 share of the WW consumption pool
DEFAULT_NG1_HZ_FRACTION = 0.40   # NG 1 share of the Hz consumption pool

_DEFAULT_BRENNSTOFF_KWH = 44000.0
_DEFAULT_WW_KWH = round(_DEFAULT_BRENNSTOFF_KWH * DEFAULT_WW_KWH_FRACTION)  # 9680
_DEFAULT_HZ_KWH = _DEFAULT_BRENNSTOFF_KWH - _DEFAULT_WW_KWH                 # 34320

_LAST_YEAR = date.today().year - 1

DEFAULTS = {
    # Abrechnung
    "objekt": "",
    "zeitraum_von": date(_LAST_YEAR, 1, 1),
    "zeitraum_bis": date(_LAST_YEAR, 12, 31),
    # Kosten
    "bkwh": _DEFAULT_BRENNSTOFF_KWH,
    "beur": 5280.0,
    "wk":   980.0,
    "gww":  345.0,
    "ghz":  265.0,
    # CO2
    "co2_aktiv":    False,
    "co2_modus":    "Stufenmodell",
    "co2_kosten":   320.0,
    "co2_emission": 4000.0,
    "co2_v_anteil": 40,
    # Warmwasser-Energie (§9 Abs. 2)
    "ww_modus": "Manuell",
    "vwwh": float(_DEFAULT_WW_KWH),
    "ww_volumen_auto": True,
    "ww_volumen": 40.0,
    "ww_temp": 60.0,
    "ww_flaeche_auto": True,
    "ww_flaeche": 150.0,
    "co2_flaeche_auto": True,
    "co2_flaeche": 150.0,
    # Verteilung (shared / base mode)
    "vww": 30,
    "vhz": 40,
    # Nutzergruppen
    "ng_type": "Abrechnungsart 1",
    "vorv_ww": 30,
    "vorv_hz": 40,
    "rest_vhz": 40,
    "rest_vww": 30,
}

INITIAL_NE_LIST = [
    {"id": 1, "flaeche": 68.0, "ww_m3": 18.0, "hz_wert": 1850.0, "messtechnik": "HKV"},
    {"id": 2, "flaeche": 90.0, "ww_m3": 23.5, "hz_wert": 2450.0, "messtechnik": "HKV"},
]
NE_DEFAULTS = {"flaeche": 55.0, "ww_m3": 15.0, "hz_wert": 1500.0, "messtechnik": "HKV"}
NE_KEY_SUFFIXES = tuple(NE_DEFAULTS)   # widget-key suffixes per Nutzeinheit
NUTZER_KEY_SUFFIXES = ("bez", "von", "vz")   # per Nutzer of a Nutzeinheit
NG_DEFAULTS = {"vhz": 40, "vww": 30, "leistung": "Heizung", "bezeichnung": ""}
LEISTUNG_MAP = {"Heizung": "hz", "Warmwasser": "ww", "Beide": "beide"}
LEISTUNG_INVERSE = {v: k for k, v in LEISTUNG_MAP.items()}

# Widget display label ↔ internal model value
WW_MODUS_MAP = {
    "Manuell": "manuell",
    "Formel (§9 Abs. 2)": "formel",
    "Pauschale (32 kWh/m²)": "pauschale",
}
CO2_MODUS_MAP = {"Stufenmodell": "stufen", "Manuell": "manuell"}
WW_MODUS_INVERSE = {v: k for k, v in WW_MODUS_MAP.items()}
CO2_MODUS_INVERSE = {v: k for k, v in CO2_MODUS_MAP.items()}
NG_ART_MAP = {"Abrechnungsart 1": "art1", "Kreuzberg": "kreuzberg"}
NG_ART_INVERSE = {v: k for k, v in NG_ART_MAP.items()}

def default_wechsel_datum() -> date:
    """Midpoint of the current Abrechnungszeitraum (sensible Wechsel default)."""
    von = sget("zeitraum_von") or DEFAULTS["zeitraum_von"]
    bis = sget("zeitraum_bis") or DEFAULTS["zeitraum_bis"]
    if von >= bis:
        return von
    return von + timedelta(days=(bis - von).days // 2)


def _seed_nutzer_keys(ne_id: int, k: int) -> None:
    st.session_state.setdefault(f"ne_{ne_id}_nutzer_{k}_bez", "")
    st.session_state.setdefault(f"ne_{ne_id}_nutzer_{k}_von", default_wechsel_datum())
    st.session_state.setdefault(f"ne_{ne_id}_nutzer_{k}_vz", 0.0)


def _seed_ne_keys(ne: dict) -> None:
    for suffix in NE_KEY_SUFFIXES:
        st.session_state.setdefault(f"ne_{ne['id']}_{suffix}", ne.get(suffix, NE_DEFAULTS[suffix]))
    st.session_state.setdefault(f"ne_{ne['id']}_nutzer_ids", [1])
    for k in st.session_state[f"ne_{ne['id']}_nutzer_ids"]:
        _seed_nutzer_keys(ne["id"], k)


def _seed_group_keys(g: int) -> None:
    st.session_state.setdefault(f"ng_{g}_bezeichnung", NG_DEFAULTS["bezeichnung"])
    st.session_state.setdefault(f"ng_{g}_leistung", NG_DEFAULTS["leistung"])
    st.session_state.setdefault(f"ng_{g}_members", [])
    st.session_state.setdefault(f"ng_{g}_hz_kwh", _DEFAULT_HZ_KWH * DEFAULT_NG1_HZ_FRACTION)
    st.session_state.setdefault(f"ng_{g}_ww_kwh", _DEFAULT_WW_KWH * DEFAULT_NG1_WW_FRACTION)
    st.session_state.setdefault(f"ng_{g}_vhz", NG_DEFAULTS["vhz"])
    st.session_state.setdefault(f"ng_{g}_vww", NG_DEFAULTS["vww"])


def group_ids() -> list:
    return st.session_state.ng_group_ids


def init_state() -> None:
    """Seed every widget key exactly once per session; idempotent."""
    if "ne_list" not in st.session_state:
        st.session_state.ne_list = [dict(ne) for ne in INITIAL_NE_LIST]
    for ne in st.session_state.ne_list:
        _seed_ne_keys(ne)
    for key, val in DEFAULTS.items():
        st.session_state.setdefault(key, val)

    labels = [hk.ne_node_name(ne["id"]) for ne in st.session_state.ne_list]
    st.session_state.setdefault("ng_group_ids", [])   # no groups = base mode
    for g in st.session_state.ng_group_ids:
        _seed_group_keys(g)
    st.session_state.setdefault("sankey_ne_filter", labels[:2])


def sget(key: str):
    """Read a state value, falling back to its canonical default."""
    return st.session_state.get(key, DEFAULTS.get(key))


def clamp_state(key: str, lo: float, hi: float) -> None:
    """Clamp a stored numeric value into [lo, hi] before its widget renders."""
    val = st.session_state.get(key, DEFAULTS.get(key, lo))
    st.session_state[key] = min(max(val, lo), hi)


# ── Nutzeinheiten ─────────────────────────────────────────────────────────────

def add_ne() -> None:
    if len(st.session_state.ne_list) >= MAX_NE:
        return
    new_id = max(ne["id"] for ne in st.session_state.ne_list) + 1
    ne = {"id": new_id, **NE_DEFAULTS}
    st.session_state.ne_list.append(ne)
    _seed_ne_keys(ne)


def remove_ne(ne_id: int) -> None:
    label = hk.ne_node_name(ne_id)
    st.session_state.ne_list = [ne for ne in st.session_state.ne_list if ne["id"] != ne_id]
    for suffix in NE_KEY_SUFFIXES:
        st.session_state.pop(f"ne_{ne_id}_{suffix}", None)
    for k in st.session_state.pop(f"ne_{ne_id}_nutzer_ids", []):
        for suffix in NUTZER_KEY_SUFFIXES:
            st.session_state.pop(f"ne_{ne_id}_nutzer_{k}_{suffix}", None)
    member_keys = [f"ng_{g}_members" for g in st.session_state.get("ng_group_ids", [])]
    for key in member_keys + ["sankey_ne_filter"]:
        if key in st.session_state:
            st.session_state[key] = [l for l in st.session_state[key] if l != label]


# ── Nutzer (Nutzerwechsel) ────────────────────────────────────────────────────

def add_nutzer(ne_id: int) -> None:
    ids = st.session_state.get(f"ne_{ne_id}_nutzer_ids", [1])
    if len(ids) >= hk.MAX_NUTZER_JE_NE:
        return
    new_id = max(ids) + 1
    ids.append(new_id)
    st.session_state[f"ne_{ne_id}_nutzer_ids"] = ids
    _seed_nutzer_keys(ne_id, new_id)


def remove_nutzer(ne_id: int, k: int) -> None:
    ids = st.session_state.get(f"ne_{ne_id}_nutzer_ids", [])
    if k not in ids or len(ids) <= 1:
        return
    ids.remove(k)
    for suffix in NUTZER_KEY_SUFFIXES:
        st.session_state.pop(f"ne_{ne_id}_nutzer_{k}_{suffix}", None)


# ── Nutzergruppen ─────────────────────────────────────────────────────────────

def add_group() -> None:
    ids = st.session_state.ng_group_ids
    if len(ids) >= MAX_EXPLICIT_NG:
        return
    new_id = max(ids) + 1 if ids else 1
    ids.append(new_id)
    _seed_group_keys(new_id)


def remove_group(g: int) -> None:
    ids = st.session_state.ng_group_ids
    if g not in ids:
        return
    ids.remove(g)
    for suffix in ("leistung", "members", "hz_kwh", "ww_kwh", "vhz", "vww"):
        st.session_state.pop(f"ng_{g}_{suffix}", None)


def derive_groups_from_messtechnik() -> None:
    """Rebuild the Nutzergruppen as ONE explicit Heizung group holding the WMZ
    Nutzeinheiten — the HKV Nutzeinheiten form the automatic rest pool, whose
    consumption is the remainder; no sliders are needed at all."""
    ne_list = st.session_state.ne_list
    wmz = [hk.ne_node_name(ne["id"]) for ne in ne_list if ne.get("messtechnik") == "WMZ"]
    hkv = [hk.ne_node_name(ne["id"]) for ne in ne_list if ne.get("messtechnik") != "WMZ"]
    if not wmz or not hkv:
        return

    for g in st.session_state.get("ng_group_ids", []):
        for suffix in ("leistung", "members", "hz_kwh", "ww_kwh", "vhz", "vww"):
            st.session_state.pop(f"ng_{g}_{suffix}", None)
    st.session_state.ng_group_ids = [1]
    _seed_group_keys(1)
    st.session_state["ng_1_leistung"] = "Heizung"
    st.session_state["ng_1_members"] = wmz
