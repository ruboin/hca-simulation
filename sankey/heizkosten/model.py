"""Typed data model: scenario configuration and computed results."""

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Literal, Optional, Tuple

from .constants import ne_node_name

Messtechnik = Literal["hkv", "wmz"]   # HKV = Verbrauchseinheiten, WMZ = kWh
NgArt = Literal["art1", "kreuzberg"]
WwModus = Literal["manuell", "formel", "pauschale"]
Co2Modus = Literal["stufen", "manuell"]
Leistung = Literal["hz", "ww", "beide"]   # which Gewerk(e) a Nutzergruppe targets


# ── Configuration ─────────────────────────────────────────────────────────────

@dataclass
class NutzerConfig:
    """One user period of a Nutzeinheit. ``von`` is the first day of THIS user
    (the Nutzerwechsel date); None marks the first user (= zeitraum_von)."""
    bezeichnung: str = ""
    von: Optional[date] = None
    vorauszahlung_eur: float = 0.0


@dataclass
class NEConfig:
    id: int
    flaeche: float
    ww_m3: float
    hz_wert: float = 0.0                 # Verbrauchseinheiten (hkv) or kWh (wmz)
    messtechnik: Messtechnik = "hkv"
    nutzer: List[NutzerConfig] = field(default_factory=list)   # ≥1 after init

    def __post_init__(self) -> None:
        if not self.nutzer:
            self.nutzer = [NutzerConfig()]

    @property
    def label(self) -> str:
        return ne_node_name(self.id)

    @property
    def display_label(self) -> str:
        """Report/UI label: single user's Bezeichnung if set, else node name."""
        if len(self.nutzer) == 1 and self.nutzer[0].bezeichnung.strip():
            return self.nutzer[0].bezeichnung.strip()
        return self.label


@dataclass
class GroupConfig:
    id: int                              # 1-based, stable sidebar identity
    bezeichnung: str = ""                # e.g. "Vorderhaus"
    members: List[int] = field(default_factory=list)   # NE ids
    leistung: Leistung = "beide"
    hz_kwh: Optional[float] = None       # None => derived (WMZ sum / remainder)
    ww_kwh: Optional[float] = None
    verteilung_hz_pct: int = 40
    verteilung_ww_pct: int = 30

    def targets(self, gewerk: str) -> bool:
        return self.leistung in ("beide", gewerk)


@dataclass
class ScenarioConfig:
    # Abrechnung (report header)
    objekt: str = ""
    zeitraum_von: Optional[date] = None
    zeitraum_bis: Optional[date] = None
    # Gebäude & Brennstoff
    brennstoff_kwh: float = 44000.0
    brennstoff_eur: float = 5280.0
    weitere_kosten_eur: float = 980.0
    geraetemiete_ww_eur: float = 345.0
    geraetemiete_hz_eur: float = 265.0
    # CO2 (CO2KostAufG)
    co2_aktiv: bool = False
    co2_modus: Co2Modus = "stufen"
    co2_kosten_eur: float = 320.0
    co2_emission_kg: Optional[float] = None     # stufen mode
    co2_flaeche_m2: Optional[float] = None      # None => sum(NE flaeche)
    co2_anteil_vermieter_pct: int = 40          # manual mode
    # §9 Abs. 2 — Warmwasser-Energie
    ww_modus: WwModus = "manuell"
    ww_kwh_manuell: float = 9680.0
    ww_volumen_m3: Optional[float] = None       # None => sum(NE ww_m3)
    ww_temp_c: float = 60.0
    ww_flaeche_m2: Optional[float] = None       # pauschale; None => sum(NE flaeche)
    # Shared Verteilschlüssel (base mode / shared WW)
    verteilung_ww_pct: int = 30
    verteilung_hz_pct: int = 40
    # Nutzergruppen — a Gewerk is grouped iff ≥1 group targets it; NEs not in
    # any targeting group form an automatic rest pool per Gewerk
    ng_art: NgArt = "art1"
    vorverteilung_ww_pct: int = 30              # kreuzberg
    vorverteilung_hz_pct: int = 40
    rest_verteilung_hz_pct: int = 40            # Verteilschlüssel of the auto rest pool
    rest_verteilung_ww_pct: int = 30
    groups: List[GroupConfig] = field(default_factory=list)
    nutzeinheiten: List[NEConfig] = field(default_factory=list)

    def total_flaeche(self) -> float:
        return sum(ne.flaeche for ne in self.nutzeinheiten)

    def total_ww_m3(self) -> float:
        return sum(ne.ww_m3 for ne in self.nutzeinheiten)


# ── Results ───────────────────────────────────────────────────────────────────

@dataclass
class WWEnergieErgebnis:
    modus: WwModus
    kwh: float
    gekappt: bool = False
    beschreibung: str = ""


@dataclass
class CO2Ergebnis:
    aktiv: bool
    modus: Co2Modus
    kosten_eur: float = 0.0
    anteil_vermieter: float = 0.0
    vermieter_eur: float = 0.0
    mieter_eur: float = 0.0
    stufe: Optional[int] = None
    spez_kg_m2: Optional[float] = None
    gekappt: bool = False


@dataclass
class SystemCosts:
    brennstoff_gesamt_eur: float
    brennstoff_mieter_eur: float
    co2_vermieter_eur: float
    warmwasser_kwh: float
    heizung_kwh: float
    warmwasser_eur: float
    heizung_eur: float
    warmwasser_grundkosten_eur: float
    warmwasser_verbrauchskosten_eur: float
    heizung_grundkosten_eur: float
    heizung_verbrauchskosten_eur: float


@dataclass
class GewerkGroupCosts:
    group_id: int
    eur: float
    gk: float
    vk: float
    fraction: float                       # consumption fraction of the pool
    verteilung: float                     # GK share 0..1 within the group
    from_gk: float = 0.0                  # Kreuzberg: amount received from the GK pre-pool
    from_vk: float = 0.0                  # Kreuzberg: amount received from the VK pre-pool
    area_fraction: float = 0.0            # Kreuzberg: share of the GK pre-pool (by area)


@dataclass
class GewerkResult:
    gewerk: str                           # "ww" | "hz"
    eur: float                            # pool total
    grouped: bool
    kreuzberg: bool = False
    vorverteilung: float = 0.0            # kreuzberg GK pre-share
    gk_pre: float = 0.0
    vk_pre: float = 0.0
    groups: List[GewerkGroupCosts] = field(default_factory=list)
    shared_verteilung: float = 0.0        # ungrouped GK share
    shared_gk: float = 0.0
    shared_vk: float = 0.0

    def group(self, g: int) -> GewerkGroupCosts:
        return next(gc for gc in self.groups if gc.group_id == g)


@dataclass
class NutzerResult:
    """§9b split of one NE's costs onto one user period."""
    idx: int                              # 1-based within the NE
    bezeichnung: str
    von: Optional[date]
    bis: Optional[date]
    tage: int
    tage_anteil: float                    # share of the Abrechnungszeitraum (days)
    gradtag_anteil: float                 # share by Gradtagszahlen (§9b Abs. 2)
    ww_gk: float
    ww_vk: float
    hz_gk: float
    hz_vk: float
    vorauszahlung_eur: float = 0.0

    @property
    def total(self) -> float:
        return self.ww_gk + self.ww_vk + self.hz_gk + self.hz_vk

    @property
    def saldo(self) -> float:
        return self.total - self.vorauszahlung_eur

    @property
    def display_label(self) -> str:
        return self.bezeichnung.strip() or f"Nutzer {self.idx}"

    @property
    def zeitraum_text(self) -> str:
        if self.von is None or self.bis is None:
            return "—"
        return f"{self.von.strftime('%d.%m.%Y')} – {self.bis.strftime('%d.%m.%Y')}"


@dataclass
class NEResult:
    id: int
    label: str
    flaeche: float
    messtechnik: Messtechnik
    ww_gk: float
    ww_vk: float
    hz_gk: float
    hz_vk: float
    bezeichnung: str = ""                 # single user's Bezeichnung, else ""
    vorauszahlung_eur: float = 0.0        # Σ over the users
    nutzer: List[NutzerResult] = field(default_factory=list)
    # Pool display number → (gk, vk) share. Groups are non-exclusive: an NE may
    # receive shares from several pools per Gewerk; the fields above are the sums.
    # Empty when the Gewerk is not grouped (then the shared pool feeds the totals).
    hz_parts: Dict[int, Tuple[float, float]] = field(default_factory=dict)
    ww_parts: Dict[int, Tuple[float, float]] = field(default_factory=dict)

    @property
    def groups_hz(self) -> List[int]:
        return sorted(self.hz_parts)

    @property
    def groups_ww(self) -> List[int]:
        return sorted(self.ww_parts)

    @property
    def total(self) -> float:
        return self.ww_gk + self.ww_vk + self.hz_gk + self.hz_vk

    @property
    def saldo(self) -> float:
        """Total minus Vorauszahlung; > 0 = Nachzahlung, < 0 = Guthaben."""
        return self.total - self.vorauszahlung_eur

    @property
    def display_label(self) -> str:
        return self.bezeichnung.strip() or self.label


@dataclass
class Hinweis:
    level: Literal["error", "warning", "info"]
    code: str
    text: str


@dataclass
class ComputedResults:
    ww_energie: WWEnergieErgebnis
    co2: CO2Ergebnis
    system: SystemCosts
    ww: GewerkResult
    hz: GewerkResult
    ne_results: List[NEResult]
