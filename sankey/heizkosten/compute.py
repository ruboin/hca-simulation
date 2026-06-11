"""Cost computations: system split, CO2, §9(2) WW energy, group split, per-NE allocation."""

from dataclasses import dataclass
from typing import Dict, List, Optional

from .constants import (
    CO2_STUFEN,
    WW_FORMEL_FAKTOR,
    WW_KALTWASSER_C,
    WW_PAUSCHALE_KWH_M2,
)
from .model import (
    CO2Ergebnis,
    ComputedResults,
    GewerkGroupCosts,
    GewerkResult,
    NEConfig,
    NEResult,
    ScenarioConfig,
    SystemCosts,
    WWEnergieErgebnis,
)


def sdiv(a: float, b: float) -> float:
    """Safe division — returns 0 when denominator is zero."""
    return a / b if b else 0.0


def co2_vermieteranteil(spez_ausstoss_kg_m2: float) -> tuple:
    """Return (Stufe 1..10, Vermieteranteil 0..0.95) for kg CO2/m²·a."""
    for i, (grenze, anteil) in enumerate(CO2_STUFEN, start=1):
        if spez_ausstoss_kg_m2 < grenze:
            return i, anteil
    return 10, 0.95


def compute_system_costs(
    brennstoff_kwh: float,
    brennstoff_eur: float,
    weitere_kosten_eur: float,
    geraetemiete_ww_eur: float,
    geraetemiete_hz_eur: float,
    warmwasser_kwh: float,
    verteilung_ww: float,
    verteilung_hz: float,
    co2_vermieter_eur: float = 0.0,
) -> SystemCosts:
    """System-level split: fuel + further costs → WW/Hz pools → GK/VK."""
    heizung_kwh = brennstoff_kwh - warmwasser_kwh
    brennstoff_mieter_eur = brennstoff_eur - co2_vermieter_eur
    brennstoff_gesamt_eur = brennstoff_mieter_eur + weitere_kosten_eur

    if brennstoff_kwh > 0:
        warmwasser_eur = brennstoff_gesamt_eur * (warmwasser_kwh / brennstoff_kwh) + geraetemiete_ww_eur
        heizung_eur    = brennstoff_gesamt_eur * (heizung_kwh    / brennstoff_kwh) + geraetemiete_hz_eur
    else:
        warmwasser_eur = geraetemiete_ww_eur
        heizung_eur    = geraetemiete_hz_eur

    return SystemCosts(
        brennstoff_gesamt_eur=brennstoff_gesamt_eur,
        brennstoff_mieter_eur=brennstoff_mieter_eur,
        co2_vermieter_eur=co2_vermieter_eur,
        warmwasser_kwh=warmwasser_kwh,
        heizung_kwh=heizung_kwh,
        warmwasser_eur=warmwasser_eur,
        heizung_eur=heizung_eur,
        warmwasser_grundkosten_eur=verteilung_ww * warmwasser_eur,
        warmwasser_verbrauchskosten_eur=(1 - verteilung_ww) * warmwasser_eur,
        heizung_grundkosten_eur=verteilung_hz * heizung_eur,
        heizung_verbrauchskosten_eur=(1 - verteilung_hz) * heizung_eur,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Unified pipeline (scenario → results)
# ══════════════════════════════════════════════════════════════════════════════

def compute_ww_energie(scenario: ScenarioConfig) -> WWEnergieErgebnis:
    """§9 Abs. 2 HeizkostenV — energy share of the central warm-water supply."""
    if scenario.ww_modus == "formel":
        volumen = scenario.ww_volumen_m3
        if volumen is None:
            volumen = scenario.total_ww_m3()
        delta_t = scenario.ww_temp_c - WW_KALTWASSER_C
        kwh = WW_FORMEL_FAKTOR * volumen * delta_t
        beschreibung = (
            f"Q = {WW_FORMEL_FAKTOR:g} × {volumen:,.1f} m³ × {delta_t:,.0f} K"
            f" = {kwh:,.0f} kWh (§9 Abs. 2 Formel)"
        )
    elif scenario.ww_modus == "pauschale":
        flaeche = scenario.ww_flaeche_m2
        if flaeche is None:
            flaeche = scenario.total_flaeche()
        kwh = WW_PAUSCHALE_KWH_M2 * flaeche
        beschreibung = (
            f"Q = {WW_PAUSCHALE_KWH_M2:g} kWh/m² × {flaeche:,.1f} m²"
            f" = {kwh:,.0f} kWh (§9 Abs. 2 Satz 4 Pauschale)"
        )
    else:
        kwh = scenario.ww_kwh_manuell
        beschreibung = f"{kwh:,.0f} kWh (manuell)"

    gekappt = kwh > scenario.brennstoff_kwh
    if gekappt:
        kwh = scenario.brennstoff_kwh
    return WWEnergieErgebnis(modus=scenario.ww_modus, kwh=kwh, gekappt=gekappt,
                             beschreibung=beschreibung)


def compute_co2(scenario: ScenarioConfig) -> CO2Ergebnis:
    """CO2KostAufG — landlord/tenant split, Stufenmodell or manual override."""
    if not scenario.co2_aktiv:
        return CO2Ergebnis(aktiv=False, modus=scenario.co2_modus)

    kosten = scenario.co2_kosten_eur
    basis = min(kosten, scenario.brennstoff_eur)
    gekappt = kosten > scenario.brennstoff_eur

    stufe: Optional[int] = None
    spez: Optional[float] = None
    if scenario.co2_modus == "stufen":
        flaeche = scenario.co2_flaeche_m2
        if flaeche is None:
            flaeche = scenario.total_flaeche()
        spez = sdiv(scenario.co2_emission_kg or 0.0, flaeche)
        stufe, anteil = co2_vermieteranteil(spez)
    else:
        anteil = scenario.co2_anteil_vermieter_pct / 100

    vermieter = basis * anteil
    return CO2Ergebnis(
        aktiv=True,
        modus=scenario.co2_modus,
        kosten_eur=kosten,
        anteil_vermieter=anteil,
        vermieter_eur=vermieter,
        mieter_eur=kosten - vermieter,
        stufe=stufe,
        spez_kg_m2=spez,
        gekappt=gekappt,
    )


@dataclass
class GewerkPool:
    """One allocation pool of a grouped Gewerk: an explicit group or the auto rest."""
    display_id: int                      # 1..k explicit (definition order), k+1 = rest
    members: List[int]                   # NE ids
    kwh: Optional[float]                 # None => derived (WMZ sum / remainder)
    verteilung_pct: int
    is_rest: bool = False
    source_group_id: Optional[int] = None  # sidebar group id; None for the rest pool


def assemble_pools(scenario: ScenarioConfig, gewerk: str) -> List[GewerkPool]:
    """
    Per-Gewerk pool list: explicit groups targeting the Gewerk (definition order,
    display ids 1..k) plus an automatic rest pool for uncovered NEs. Empty list
    means the Gewerk is not grouped. The remainder pool (kwh=None, last) is the
    rest pool — or the last explicit pool when explicit groups cover all NEs.

    Groups are NON-exclusive: an NE may be a member of several pools; each pool
    distributes its money independently among its full member list. The rest
    pool holds the NEs that are in no targeting group at all.
    """
    targeting = [grp for grp in scenario.groups if grp.targets(gewerk)]
    if not targeting:
        return []

    pools = []
    covered: set = set()
    for idx, grp in enumerate(targeting, start=1):
        covered.update(grp.members)
        pools.append(GewerkPool(
            display_id=idx,
            members=list(grp.members),
            kwh=grp.hz_kwh if gewerk == "hz" else grp.ww_kwh,
            verteilung_pct=grp.verteilung_hz_pct if gewerk == "hz" else grp.verteilung_ww_pct,
            source_group_id=grp.id,
        ))

    rest_members = [ne.id for ne in scenario.nutzeinheiten if ne.id not in covered]
    if rest_members:
        pools.append(GewerkPool(
            display_id=len(pools) + 1,
            members=rest_members,
            kwh=None,
            verteilung_pct=(scenario.rest_verteilung_hz_pct if gewerk == "hz"
                            else scenario.rest_verteilung_ww_pct),
            is_rest=True,
        ))
    else:
        pools[-1].kwh = None  # last explicit pool becomes the remainder
    return pools


def pool_is_wmz_fixed(pool: GewerkPool, gewerk: str, nutzeinheiten: List[NEConfig]) -> bool:
    """True when a Heizung pool's consumption is fixed by meters (all members WMZ)."""
    if gewerk != "hz":
        return False
    members = [ne for ne in nutzeinheiten if ne.id in pool.members]
    return bool(members) and all(ne.messtechnik == "wmz" for ne in members)


def pool_meter_sum(pool: GewerkPool, nutzeinheiten: List[NEConfig]) -> float:
    """Sum of the pool members' Heizung meter readings (kWh)."""
    return sum(ne.hz_wert for ne in nutzeinheiten if ne.id in pool.members)


def derive_group_kwh(
    nutzeinheiten: List[NEConfig],
    pools: List[GewerkPool],
    gewerk: str,
    pool_kwh: float,
) -> List[float]:
    """
    Resolve the per-pool consumption (kWh) for a gewerk.

    Heizung: an all-WMZ pool is fixed to the sum of its members' meter readings;
    explicit values (sliders) are taken as-is; the last unresolved pool receives
    the remainder so the column always sums to pool_kwh exactly.
    """
    resolved: List[Optional[float]] = []
    for pool in pools:
        if pool_is_wmz_fixed(pool, gewerk, nutzeinheiten):
            resolved.append(pool_meter_sum(pool, nutzeinheiten))
        else:
            resolved.append(pool.kwh)

    open_idx = [i for i, v in enumerate(resolved) if v is None]
    known = sum(v for v in resolved if v is not None)
    if open_idx:
        for i in open_idx[:-1]:
            resolved[i] = 0.0
        resolved[open_idx[-1]] = pool_kwh - known
    return [v if v is not None else 0.0 for v in resolved]


def _fractions(values: List[float], pool: float) -> List[float]:
    """Consumption fractions; the last group absorbs rounding so they sum to 1."""
    if not values:
        return []
    fracs = [sdiv(v, pool) for v in values[:-1]]
    return fracs + [1.0 - sum(fracs)]


def compute_gewerk(
    gewerk: str,
    pool_eur: float,
    grouped: bool,
    shared_verteilung: float,
    kreuzberg: bool = False,
    vorverteilung: float = 0.0,
    group_ids: Optional[List[int]] = None,
    fractions: Optional[List[float]] = None,
    verteilungen: Optional[List[float]] = None,
    area_fractions: Optional[List[float]] = None,
) -> GewerkResult:
    """Split one gewerk pool — shared, per-group (Art 1), or Kreuzberg pre-split."""
    if not grouped:
        return GewerkResult(
            gewerk=gewerk,
            eur=pool_eur,
            grouped=False,
            shared_verteilung=shared_verteilung,
            shared_gk=pool_eur * shared_verteilung,
            shared_vk=pool_eur * (1.0 - shared_verteilung),
        )

    result = GewerkResult(gewerk=gewerk, eur=pool_eur, grouped=True, kreuzberg=kreuzberg)
    if kreuzberg:
        result.vorverteilung = vorverteilung
        result.gk_pre = pool_eur * vorverteilung
        result.vk_pre = pool_eur * (1.0 - vorverteilung)
        for gid, frac, vert, af in zip(group_ids, fractions, verteilungen, area_fractions):
            from_gk = result.gk_pre * af
            from_vk = result.vk_pre * frac
            eur = from_gk + from_vk
            result.groups.append(GewerkGroupCosts(
                group_id=gid, eur=eur,
                gk=eur * vert, vk=eur * (1.0 - vert),
                fraction=frac, verteilung=vert,
                from_gk=from_gk, from_vk=from_vk, area_fraction=af,
            ))
    else:
        for gid, frac, vert in zip(group_ids, fractions, verteilungen):
            eur = pool_eur * frac
            result.groups.append(GewerkGroupCosts(
                group_id=gid, eur=eur,
                gk=eur * vert, vk=eur * (1.0 - vert),
                fraction=frac, verteilung=vert,
            ))
    return result


def compute_ne_results(
    nutzeinheiten: List[NEConfig],
    pools_ww: List[GewerkPool],
    pools_hz: List[GewerkPool],
    ww: GewerkResult,
    hz: GewerkResult,
) -> List[NEResult]:
    """Allocate both gewerk pools down to the Nutzeinheiten (unit-agnostic shares).

    Pools are non-exclusive: every pool distributes its GK by Fläche share and
    its VK by consumption share over its FULL member list, so an NE in several
    pools accumulates one (gk, vk) part per pool. Union(pools) covers all NEs
    by construction (assemble_pools adds the rest pool).
    """
    def consumption(ne: NEConfig, gewerk: str) -> float:
        return ne.ww_m3 if gewerk == "ww" else ne.hz_wert

    ne_by_id = {ne.id: ne for ne in nutzeinheiten}

    def pool_parts(gres: GewerkResult, pools: List[GewerkPool]) -> Dict[int, Dict[int, tuple]]:
        """ne_id → {pool display id → (gk, vk)}."""
        parts: Dict[int, Dict[int, tuple]] = {ne.id: {} for ne in nutzeinheiten}
        for pool in pools:
            members = [ne_by_id[i] for i in pool.members if i in ne_by_id]
            flaeche_total = sum(n.flaeche for n in members)
            cons_total = sum(consumption(n, gres.gewerk) for n in members)
            gc = gres.group(pool.display_id)
            for n in members:
                gk = sdiv(n.flaeche, flaeche_total) * gc.gk
                vk = sdiv(consumption(n, gres.gewerk), cons_total) * gc.vk
                parts[n.id][pool.display_id] = (gk, vk)
        return parts

    flaeche_total = sum(n.flaeche for n in nutzeinheiten)
    cons_totals = {gw: sum(consumption(n, gw) for n in nutzeinheiten) for gw in ("ww", "hz")}

    def shared_share(ne: NEConfig, gres: GewerkResult) -> tuple:
        gk = sdiv(ne.flaeche, flaeche_total) * gres.shared_gk
        vk = sdiv(consumption(ne, gres.gewerk), cons_totals[gres.gewerk]) * gres.shared_vk
        return gk, vk

    parts_ww = pool_parts(ww, pools_ww) if ww.grouped else {}
    parts_hz = pool_parts(hz, pools_hz) if hz.grouped else {}

    results = []
    for ne in nutzeinheiten:
        if ww.grouped:
            ne_ww = parts_ww[ne.id]
            ww_gk = sum(gk for gk, _ in ne_ww.values())
            ww_vk = sum(vk for _, vk in ne_ww.values())
        else:
            ne_ww = {}
            ww_gk, ww_vk = shared_share(ne, ww)
        if hz.grouped:
            ne_hz = parts_hz[ne.id]
            hz_gk = sum(gk for gk, _ in ne_hz.values())
            hz_vk = sum(vk for _, vk in ne_hz.values())
        else:
            ne_hz = {}
            hz_gk, hz_vk = shared_share(ne, hz)
        results.append(NEResult(
            id=ne.id, label=ne.label, flaeche=ne.flaeche, messtechnik=ne.messtechnik,
            ww_gk=ww_gk, ww_vk=ww_vk, hz_gk=hz_gk, hz_vk=hz_vk,
            ww_parts=ne_ww, hz_parts=ne_hz,
        ))
    return results


def _split_gewerk(
    scenario: ScenarioConfig,
    gewerk: str,
    pool_eur: float,
    pool_kwh: float,
) -> tuple:
    """Split one gewerk pool; returns (GewerkResult, List[GewerkPool])."""
    shared = (scenario.verteilung_hz_pct if gewerk == "hz"
              else scenario.verteilung_ww_pct) / 100
    pools = assemble_pools(scenario, gewerk)
    if not pools:
        return compute_gewerk(gewerk, pool_eur, grouped=False,
                              shared_verteilung=shared), []

    kwhs = derive_group_kwh(scenario.nutzeinheiten, pools, gewerk, pool_kwh)
    ne_by_id = {ne.id: ne for ne in scenario.nutzeinheiten}
    areas = [sum(ne_by_id[i].flaeche for i in p.members if i in ne_by_id) for p in pools]
    gres = compute_gewerk(
        gewerk, pool_eur,
        grouped=True,
        shared_verteilung=shared,
        kreuzberg=scenario.ng_art == "kreuzberg",
        vorverteilung=(scenario.vorverteilung_hz_pct if gewerk == "hz"
                       else scenario.vorverteilung_ww_pct) / 100,
        group_ids=[p.display_id for p in pools],
        fractions=_fractions(kwhs, pool_kwh),
        verteilungen=[p.verteilung_pct / 100 for p in pools],
        # Normalize by the pool-area sum: with non-exclusive groups an NE's
        # Fläche counts in every pool it belongs to, so the sum can exceed the
        # building area (identical to total_flaeche for a clean partition).
        area_fractions=_fractions(areas, sum(areas)),
    )
    return gres, pools


def compute_all(scenario: ScenarioConfig) -> ComputedResults:
    """Full pipeline: §9(2) WW energy → CO2 → system split → pools →
    Nutzeinheiten → Nutzer (§9b)."""
    from .nutzerwechsel import split_ne_nutzer

    ww_energie = compute_ww_energie(scenario)
    co2 = compute_co2(scenario)

    system = compute_system_costs(
        brennstoff_kwh=scenario.brennstoff_kwh,
        brennstoff_eur=scenario.brennstoff_eur,
        weitere_kosten_eur=scenario.weitere_kosten_eur,
        geraetemiete_ww_eur=scenario.geraetemiete_ww_eur,
        geraetemiete_hz_eur=scenario.geraetemiete_hz_eur,
        warmwasser_kwh=ww_energie.kwh,
        verteilung_ww=scenario.verteilung_ww_pct / 100,
        verteilung_hz=scenario.verteilung_hz_pct / 100,
        co2_vermieter_eur=co2.vermieter_eur,
    )

    hz, pools_hz = _split_gewerk(scenario, "hz", system.heizung_eur, system.heizung_kwh)
    ww, pools_ww = _split_gewerk(scenario, "ww", system.warmwasser_eur, system.warmwasser_kwh)

    ne_results = compute_ne_results(scenario.nutzeinheiten, pools_ww, pools_hz, ww, hz)
    ne_by_id = {ne.id: ne for ne in scenario.nutzeinheiten}
    for res in ne_results:
        ne = ne_by_id[res.id]
        res.nutzer = split_ne_nutzer(ne, res, scenario.zeitraum_von, scenario.zeitraum_bis)
        res.vorauszahlung_eur = sum(n.vorauszahlung_eur for n in res.nutzer)
        res.bezeichnung = ne.nutzer[0].bezeichnung if len(ne.nutzer) == 1 else ""
    return ComputedResults(
        ww_energie=ww_energie, co2=co2, system=system, ww=ww, hz=hz, ne_results=ne_results
    )
