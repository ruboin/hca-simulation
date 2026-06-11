"""Shared constants: node names, layers, colors, limits, legal tables."""

from typing import List, Optional

# ── Limits & options ──────────────────────────────────────────────────────────
MAX_NE = 10
MAX_EXPLICIT_NG = 3   # user-defined groups; + automatic rest pool = MAX_NG pools
MAX_NG = 4            # max pools per Gewerk (also the color-shade range)
MAX_NUTZER_JE_NE = 4  # max users per Nutzeinheit (1 + 3 Nutzerwechsel)
VERTEILSCHLUESSEL_OPTIONS = (0, 30, 40, 50, 100)  # GK share %; 0/100 = keine verbrauchsabh. Abrechnung

# ── §9b HeizkostenV — Gradtagszahlen (Promille je Monat, Summe = 1000) ────────
# Standard table used by Messdienste (ista u. a.) for Nutzerwechsel. Juni, Juli
# und August teilen sich zusammen 40 ‰ gleichmäßig über ihre 92 Tage.
GRADTAGSZAHLEN_PROMILLE = {
    1: 170.0, 2: 150.0, 3: 130.0, 4: 80.0, 5: 40.0,
    9: 30.0, 10: 80.0, 11: 120.0, 12: 160.0,
}
SOMMER_PROMILLE = 40.0        # Juni + Juli + August zusammen
SOMMER_TAGE = 92.0            # 30 + 31 + 31

# Default layout dimensions for the Sankey canvas
LAYOUT = dict(width=1100, height=660, node_width=28, node_padding=10,
              margin_top=12, margin_bottom=24)

# ── §9 Abs. 2 HeizkostenV — Warmwasser-Energie ───────────────────────────────
WW_FORMEL_FAKTOR = 2.5        # kWh/(m³·K)
WW_KALTWASSER_C = 10.0        # °C reference cold-water temperature
WW_TEMP_DEFAULT_C = 60.0      # °C default warm-water temperature
WW_PAUSCHALE_KWH_M2 = 32.0    # kWh per m² Wohnfläche (Satz 4 fallback)

# ── CO2KostAufG Stufenmodell ─────────────────────────────────────────────────
# (upper bound kg CO2/m²·a, Vermieteranteil)
CO2_STUFEN = [
    (12.0, 0.00), (17.0, 0.10), (22.0, 0.20), (27.0, 0.30), (32.0, 0.40),
    (37.0, 0.50), (42.0, 0.60), (47.0, 0.70), (52.0, 0.80), (float("inf"), 0.95),
]

# ── Gewerke ──────────────────────────────────────────────────────────────────
GEWERKE = ("ww", "hz")
GEWERK_LABEL = {"ww": "Warmwasser", "hz": "Heizung"}
GEWERK_ABBR = {"ww": "WW", "hz": "Hz"}
KIND_LABEL = {"gk": "Grundkosten", "vk": "Verbrauchskosten"}

# ── Node display names (fixed) ───────────────────────────────────────────────
N_BRENNSTOFF = "Brennstoffkosten"
N_WEITERE = "Weitere Kosten"
N_GERAETE = "Gerätemieten"
N_GESAMT = "Kosten Heizung & Wassererwärmung"
N_CO2_VERMIETER = "CO2-Anteil Vermieter"
N_WW = "Kosten Warmwasser"
N_HZ = "Kosten Heizung"


def ne_node_name(i: int) -> str:
    """Display name for the i-th Nutzeinheit (1-based)."""
    return f"Nutzeinheit {i}"


def gewerk_node(gewerk: str) -> str:
    return f"Kosten {GEWERK_LABEL[gewerk]}"


def ng_node(gewerk: str, g: int) -> str:
    """Nutzergruppen-level node, e.g. 'NG 1 – Warmwasser'."""
    return f"NG {g} – {GEWERK_LABEL[gewerk]}"


def gkvk_node(gewerk: str, kind: str, g: Optional[int] = None) -> str:
    """GK/VK node, e.g. 'Grundkosten WW' or 'Verbrauchskosten Hz NG 2'."""
    base = f"{KIND_LABEL[kind]} {GEWERK_ABBR[gewerk]}"
    return base if g is None else f"{base} NG {g}"


# ── Layer indices (top → bottom); layers below L_SYSTEM are derived per mode ──
L_INPUTS = 0
L_GESAMT = 1
L_SYSTEM = 2   # WW / Hz

# ── Colors (balanced palette for dark backgrounds) ───────────────────────────
NODE_ALPHA = 0.84

SLATE_CO2 = "rgba(110, 122, 140, {a})"
YELLOW_BRENNSTOFF = "rgba(203, 170, 75, {a})"
YELLOW_WEITERE    = "rgba(184, 153, 69, {a})"
YELLOW_GESAMT     = "rgba(220, 195, 107, {a})"
GREEN_GERAETE     = "rgba(85, 158, 120, {a})"
RED_BASE          = "rgba(194, 84, 84, {a})"
RED_LIGHT1        = "rgba(203, 114, 106, {a})"
RED_LIGHT2        = "rgba(211, 141, 129, {a})"
ORANGE_BASE       = "rgba(207, 123, 72, {a})"
ORANGE_LIGHT1     = "rgba(211, 152, 107, {a})"
ORANGE_LIGHT2     = "rgba(217, 176, 138, {a})"

# NG2-specific shades (NG1 reuses RED_BASE/ORANGE_BASE and their LIGHT variants)
RED_NG2_WW       = "rgba(210, 90, 90, {a})"
ORANGE_NG2_HZ    = "rgba(220, 140, 85, {a})"
RED_NG2_WW_GK    = "rgba(215, 120, 112, {a})"
RED_NG2_WW_VK    = "rgba(222, 147, 135, {a})"
ORANGE_NG2_HZ_GK = "rgba(220, 158, 115, {a})"
ORANGE_NG2_HZ_VK = "rgba(225, 182, 146, {a})"

# 10-slot palette: linear gradient violet → cerulean (evenly spaced)
NE_COLORS: List[str] = [
    "rgba(168, 141, 208, {a})",  # NE1  violet
    "rgba(152, 141, 209, {a})",  # NE2
    "rgba(136, 141, 209, {a})",  # NE3
    "rgba(120, 148, 210, {a})",  # NE4
    "rgba(104, 155, 210, {a})",  # NE5
    "rgba( 88, 155, 210, {a})",  # NE6
    "rgba( 88, 162, 211, {a})",  # NE7
    "rgba( 80, 163, 211, {a})",  # NE8
    "rgba( 76, 163, 211, {a})",  # NE9
    "rgba( 73, 163, 210, {a})",  # NE10 cerulean
]


def rgba(token: str, a: float = NODE_ALPHA) -> str:
    return token.format(a=a)


# ── Programmatic group shades ────────────────────────────────────────────────
_GEWERK_RGB = {"ww": (194, 84, 84), "hz": (207, 123, 72)}

# Hand-calibrated legacy shades for groups 1/2 (visual parity with the old palette)
_LEGACY_GROUP_SHADES = {
    ("ww", 1, None): RED_BASE,        ("ww", 2, None): RED_NG2_WW,
    ("hz", 1, None): ORANGE_BASE,     ("hz", 2, None): ORANGE_NG2_HZ,
    ("ww", 1, "gk"): RED_LIGHT1,      ("ww", 1, "vk"): RED_LIGHT2,
    ("ww", 2, "gk"): RED_NG2_WW_GK,   ("ww", 2, "vk"): RED_NG2_WW_VK,
    ("hz", 1, "gk"): ORANGE_LIGHT1,   ("hz", 1, "vk"): ORANGE_LIGHT2,
    ("hz", 2, "gk"): ORANGE_NG2_HZ_GK, ("hz", 2, "vk"): ORANGE_NG2_HZ_VK,
}


def shade(rgb: tuple, lighten: float) -> str:
    """Mix an RGB color toward white by `lighten` (0..1); returns an {a} template."""
    r, g, b = (round(c + (255 - c) * lighten) for c in rgb)
    return f"rgba({r}, {g}, {b}, {{a}})"


def group_shade(gewerk: str, g: int, kind: Optional[str] = None) -> str:
    """Color template for an NG node (kind=None) or its GK/VK child node."""
    legacy = _LEGACY_GROUP_SHADES.get((gewerk, g, kind))
    if legacy is not None:
        return legacy
    lighten = 0.10 * (g - 1)
    if kind == "gk":
        lighten += 0.12
    elif kind == "vk":
        lighten += 0.24
    return shade(_GEWERK_RGB[gewerk], min(lighten, 0.7))
