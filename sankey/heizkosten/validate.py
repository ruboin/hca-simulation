"""Scenario validation: Messtechnik rules, §12-Kürzungsrecht, plausibility checks.

Returns ``Hinweis`` records; level "error" means the configuration cannot be
calculated meaningfully (the UI skips the Sankey/breakdown), "warning" flags
implausible inputs, "info" carries legal hints (§12 HeizkostenV).
"""

from typing import List, Optional

from .compute import assemble_pools, derive_group_kwh
from .model import ComputedResults, Hinweis, ScenarioConfig

# Legal range §7 Abs. 1 HeizkostenV: 50–70 % nach Verbrauch
VERBRAUCHSANTEIL_MIN = 50
VERBRAUCHSANTEIL_MAX = 70


def _pool_name(pool) -> str:
    if pool.is_rest:
        return f"Die automatische Restgruppe (NG {pool.display_id})"
    return f"Nutzergruppe {pool.display_id}"


def _messtechnik_hinweise(scenario: ScenarioConfig) -> List[Hinweis]:
    hinweise: List[Hinweis] = []
    techniken = {ne.messtechnik for ne in scenario.nutzeinheiten}
    hz_pools = assemble_pools(scenario, "hz")
    if len(techniken) > 1 and not hz_pools:
        hinweise.append(Hinweis(
            "error", "MESSTECHNIK_MIXED_NO_NG",
            "Gemischte Messtechnik (HKV + WMZ) erfordert Nutzergruppen für die "
            "Heizung: kWh aus Wärmemengenzählern und Verbrauchseinheiten aus "
            "Heizkostenverteilern können nicht in einem Verteilungspool gemischt "
            "werden (§5 Abs. 2 HeizkostenV).",
        ))
        return hinweise

    ne_by_id = {ne.id: ne for ne in scenario.nutzeinheiten}
    for pool in hz_pools:
        members = [ne_by_id[i] for i in pool.members if i in ne_by_id]
        if len({ne.messtechnik for ne in members}) > 1:
            hinweise.append(Hinweis(
                "error", "MESSTECHNIK_MIXED_GROUP",
                f"{_pool_name(pool)} mischt HKV- und WMZ-Nutzeinheiten "
                f"— jeder Heizungs-Pool muss einheitlich gemessen sein "
                f"(§5 Abs. 2 HeizkostenV).",
            ))
    return hinweise


def _gruppen_hinweise(scenario: ScenarioConfig, results: ComputedResults) -> List[Hinweis]:
    hinweise: List[Hinweis] = []
    if not scenario.groups:
        return hinweise

    for pos, grp in enumerate(scenario.groups, start=1):
        if not grp.members:
            hinweise.append(Hinweis(
                "warning", "GROUP_EMPTY",
                f"Nutzergruppe {pos} hat keine Nutzeinheiten — ihre Kosten "
                f"erreichen keine Nutzeinheit.",
            ))

    hz_pools = assemble_pools(scenario, "hz")
    if hz_pools:
        hz_kwh = derive_group_kwh(scenario.nutzeinheiten, hz_pools, "hz",
                                  results.system.heizung_kwh)
        if hz_kwh and hz_kwh[-1] < 0:
            hinweise.append(Hinweis(
                "warning", "GROUP_KWH_SUM_MISMATCH",
                f"Die Heizungs-Verbräuche der Nutzergruppen übersteigen den "
                f"Gebäudeverbrauch um {-hz_kwh[-1]:,.0f} kWh — der letzte Pool "
                f"erhält einen negativen Rest.",
            ))

    wmz_sum = sum(ne.hz_wert for ne in scenario.nutzeinheiten if ne.messtechnik == "wmz")
    if wmz_sum > results.system.heizung_kwh > 0:
        hinweise.append(Hinweis(
            "warning", "WMZ_SUM_EXCEEDS_POOL",
            f"Die Summe der WMZ-Messwerte ({wmz_sum:,.0f} kWh) übersteigt den "
            f"Heizungsanteil des Gebäudes ({results.system.heizung_kwh:,.0f} kWh).",
        ))

    multi = _multi_pool_hinweis(scenario)
    if multi:
        hinweise.append(multi)
    return hinweise


def _multi_pool_hinweis(scenario: ScenarioConfig) -> Optional[Hinweis]:
    """Info when NEs belong to several pools of one Gewerk (non-exclusive groups)."""
    from .constants import GEWERK_LABEL, ne_node_name

    parts = []
    for gewerk in ("hz", "ww"):
        pools = assemble_pools(scenario, gewerk)
        counts: dict = {}
        for pool in pools:
            for ne_id in pool.members:
                counts[ne_id] = counts.get(ne_id, 0) + 1
        shared = sorted(i for i, c in counts.items() if c > 1)
        if shared:
            labels = ", ".join(ne_node_name(i) for i in shared)
            parts.append(f"{GEWERK_LABEL[gewerk]}: {labels}")
    if not parts:
        return None
    return Hinweis(
        "info", "NE_MULTI_POOL",
        "Nutzeinheiten in mehreren Pools (" + " · ".join(parts) + ") — "
        "Fläche und Verbrauch zählen in jedem Pool voll; die Kosten der "
        "Nutzeinheit sind die Summe ihrer Pool-Anteile.",
    )


def _zeitraum_hinweis(scenario: ScenarioConfig) -> Optional[Hinweis]:
    """Abrechnungszeitraum: pflicht für eine formell vollständige Abrechnung."""
    von, bis = scenario.zeitraum_von, scenario.zeitraum_bis
    if von is None or bis is None:
        return Hinweis(
            "info", "ZEITRAUM_MISSING",
            "Kein Abrechnungszeitraum angegeben — eine formell wirksame Abrechnung "
            "muss den Zeitraum ausweisen.",
        )
    if von >= bis:
        return Hinweis(
            "warning", "ZEITRAUM_INVALID",
            "Der Abrechnungszeitraum ist ungültig: das Enddatum liegt nicht nach "
            "dem Anfangsdatum.",
        )
    days = (bis - von).days + 1
    if days > 366:
        return Hinweis(
            "warning", "ZEITRAUM_GT_12M",
            f"Der Abrechnungszeitraum umfasst {days} Tage — er darf höchstens "
            f"12 Monate betragen (§556 Abs. 3 BGB, jährliche Abrechnung).",
        )
    if days < 360:
        return Hinweis(
            "info", "ZEITRAUM_RUMPF",
            f"Rumpfabrechnungszeitraum von {days} Tagen — zulässig z. B. bei "
            f"Nutzerwechsel oder Umstellung des Abrechnungsjahres.",
        )
    return None


def _nutzerwechsel_hinweise(scenario: ScenarioConfig) -> List[Hinweis]:
    """§9b checks: Wechsel need a valid Zeitraum; dates inside it; no empty periods."""
    from .nutzerwechsel import nutzer_perioden

    hinweise: List[Hinweis] = []
    multi = [ne for ne in scenario.nutzeinheiten if len(ne.nutzer) >= 2]
    if not multi:
        return hinweise

    von, bis = scenario.zeitraum_von, scenario.zeitraum_bis
    if von is None or bis is None or von >= bis:
        hinweise.append(Hinweis(
            "error", "NUTZERWECHSEL_OHNE_ZEITRAUM",
            "Nutzerwechsel erfordern einen gültigen Abrechnungszeitraum — die "
            "Aufteilung nach Tagen und Gradtagszahlen (§9b HeizkostenV) ist "
            "sonst nicht möglich.",
        ))
        return hinweise

    ausserhalb: List[str] = []
    leer: List[str] = []
    for ne in multi:
        for nu in ne.nutzer[1:]:
            if nu.von is not None and not (von < nu.von <= bis):
                ausserhalb.append(f"{ne.label} ({nu.von.strftime('%d.%m.%Y')})")
        for _, _, p_von, p_bis in nutzer_perioden(von, bis, ne.nutzer):
            if p_bis < p_von:
                leer.append(ne.label)
                break
    if ausserhalb:
        hinweise.append(Hinweis(
            "warning", "NUTZERWECHSEL_DATUM",
            "Nutzerwechsel-Datum außerhalb des Abrechnungszeitraums — es wird "
            "auf den Zeitraum begrenzt: " + ", ".join(ausserhalb) + ".",
        ))
    if leer:
        hinweise.append(Hinweis(
            "warning", "NUTZER_PERIODE_LEER",
            "Nutzerperioden ohne einen einzigen Tag (gleiche Wechseldaten) in: "
            + ", ".join(leer) + " — diese Nutzer erhalten keine Kosten.",
        ))
    return hinweise


def _paragraph12_hinweis(scenario: ScenarioConfig, results: ComputedResults) -> Optional[Hinweis]:
    """§12 HeizkostenV: 15 % Kürzungsrecht bei nicht verbrauchsabhängiger Abrechnung."""
    reasons: List[str] = []

    hz_pools = assemble_pools(scenario, "hz")
    if hz_pools:
        active_hz_pcts = [p.verteilung_pct for p in hz_pools]
        if scenario.ng_art == "kreuzberg":
            active_hz_pcts.append(scenario.vorverteilung_hz_pct)
    else:
        active_hz_pcts = [scenario.verteilung_hz_pct]
    for pct in active_hz_pcts:
        verbrauchsanteil = 100 - pct
        if not (VERBRAUCHSANTEIL_MIN <= verbrauchsanteil <= VERBRAUCHSANTEIL_MAX):
            reasons.append(
                f"Heizungs-Verbrauchsanteil {verbrauchsanteil} % liegt außerhalb "
                f"der zulässigen 50–70 % (§7 Abs. 1)"
            )
            break

    if results.system.heizung_kwh <= 0 and results.system.heizung_eur > 0:
        reasons.append("kein erfasster Heizungsverbrauch")

    if scenario.ww_modus == "pauschale":
        reasons.append("Warmwasser-Energie nur pauschal nach §9 Abs. 2 Satz 4 ermittelt")

    if not reasons:
        return None
    return Hinweis(
        "info", "PARAGRAPH_12",
        "Hinweis §12 HeizkostenV: Die Konfiguration deutet auf nicht "
        "verbrauchsabhängige Abrechnung hin — Nutzer können eine Kürzung von "
        "15 % geltend machen. (Grund: " + "; ".join(reasons) + ")",
    )


def validate_scenario(scenario: ScenarioConfig, results: ComputedResults) -> List[Hinweis]:
    hinweise = _messtechnik_hinweise(scenario)
    hinweise += _gruppen_hinweise(scenario, results)
    hinweise += _nutzerwechsel_hinweise(scenario)

    if results.co2.gekappt:
        hinweise.append(Hinweis(
            "warning", "CO2_GT_BRENNSTOFF",
            "CO2-Kosten übersteigen die Brennstoffkosten – der Vermieteranteil "
            "wird auf Basis der Brennstoffkosten begrenzt.",
        ))
    if results.ww_energie.gekappt:
        hinweise.append(Hinweis(
            "warning", "WW_KWH_GT_BRENNSTOFF",
            f"Die ermittelte Warmwasser-Energie übersteigt die Brennstoffenergie "
            f"({scenario.brennstoff_kwh:,.0f} kWh) und wurde gekappt.",
        ))
    if scenario.nutzeinheiten and all(ne.hz_wert <= 0 for ne in scenario.nutzeinheiten):
        hinweise.append(Hinweis(
            "warning", "NE_ALL_ZERO",
            "Alle Nutzeinheiten haben einen Heizungsverbrauch von 0 — die "
            "Verbrauchskosten Heizung können nicht verteilt werden.",
        ))

    for extra in (_zeitraum_hinweis(scenario), _paragraph12_hinweis(scenario, results)):
        if extra:
            hinweise.append(extra)
    return hinweise


def has_errors(hinweise: List[Hinweis]) -> bool:
    return any(h.level == "error" for h in hinweise)
