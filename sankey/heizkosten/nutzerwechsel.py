"""Nutzerwechsel-Aufteilung nach §9b HeizkostenV.

Splits a Nutzeinheit's annual cost components onto its user periods:
Grundkosten (Hz + WW) and Verbrauchskosten Warmwasser zeitanteilig (days),
Verbrauchskosten Heizung nach Gradtagszahlen (standard 1000-Promille table,
see ``GRADTAGSZAHLEN_PROMILLE``). Without a Zwischenablesung this is the
prescribed estimation method.
"""

import calendar
from datetime import date, timedelta
from typing import List, Optional, Tuple

from .constants import GRADTAGSZAHLEN_PROMILLE, SOMMER_PROMILLE, SOMMER_TAGE
from .model import NEConfig, NEResult, NutzerConfig, NutzerResult


def promille_pro_tag(year: int, month: int) -> float:
    """Gradtag-Promille of one day in the given month."""
    if month in (6, 7, 8):
        return SOMMER_PROMILLE / SOMMER_TAGE
    return GRADTAGSZAHLEN_PROMILLE[month] / calendar.monthrange(year, month)[1]


def gradtag_gewicht(von: date, bis: date) -> float:
    """Gradtag-Promille weight of a date span (inclusive on both ends)."""
    if bis < von:
        return 0.0
    gewicht = 0.0
    cursor = date(von.year, von.month, 1)
    while cursor <= bis:
        month_days = calendar.monthrange(cursor.year, cursor.month)[1]
        month_end = date(cursor.year, cursor.month, month_days)
        overlap_start = max(von, cursor)
        overlap_end = min(bis, month_end)
        days = (overlap_end - overlap_start).days + 1
        if days > 0:
            gewicht += days * promille_pro_tag(cursor.year, cursor.month)
        cursor = month_end + timedelta(days=1)
    return gewicht


def nutzer_perioden(
    zeitraum_von: date,
    zeitraum_bis: date,
    nutzer: List[NutzerConfig],
) -> List[Tuple[int, NutzerConfig, date, date]]:
    """
    Resolve the user periods of one NE: (idx, NutzerConfig, von, bis) — both
    inclusive. Convention: a Wechsel-Datum is the FIRST day of the new user;
    the previous user ends the day before. Dates are clamped into the
    Abrechnungszeitraum; users are ordered chronologically (the first user
    keeps position 1 regardless of its von=None).
    """
    first, rest = nutzer[0], nutzer[1:]
    rest = sorted(rest, key=lambda n: n.von or zeitraum_von)

    starts = [zeitraum_von]
    for n in rest:
        start = n.von or zeitraum_von
        start = max(zeitraum_von, min(start, zeitraum_bis))
        starts.append(start)

    ordered = [first] + rest
    perioden = []
    for i, (n, start) in enumerate(zip(ordered, starts)):
        end = (starts[i + 1] - timedelta(days=1)) if i + 1 < len(starts) else zeitraum_bis
        perioden.append((i + 1, n, start, end))
    return perioden


def _anteile(weights: List[float]) -> List[float]:
    """Normalize weights to fractions; the last entry absorbs rounding."""
    total = sum(weights)
    if total <= 0:
        n = len(weights)
        return [1.0 / n] * n if n else []
    fracs = [w / total for w in weights[:-1]]
    return fracs + [1.0 - sum(fracs)]


def split_ne_nutzer(
    ne: NEConfig,
    res: NEResult,
    zeitraum_von: Optional[date],
    zeitraum_bis: Optional[date],
) -> List[NutzerResult]:
    """§9b split of the NE's four cost components onto its user periods.

    Days-based shares for ww_gk, ww_vk, hz_gk; Gradtag shares for hz_vk.
    Falls back to equal shares when the Zeitraum is missing/invalid (validation
    raises an error for that configuration; compute must not crash).
    """
    n = len(ne.nutzer)
    valid = (zeitraum_von is not None and zeitraum_bis is not None
             and zeitraum_von < zeitraum_bis)

    if not valid:
        equal = [1.0 / n] * n
        return [
            NutzerResult(
                idx=i + 1, bezeichnung=nu.bezeichnung, von=None, bis=None,
                tage=0, tage_anteil=anteil, gradtag_anteil=anteil,
                ww_gk=res.ww_gk * anteil, ww_vk=res.ww_vk * anteil,
                hz_gk=res.hz_gk * anteil, hz_vk=res.hz_vk * anteil,
                vorauszahlung_eur=nu.vorauszahlung_eur,
            )
            for i, (nu, anteil) in enumerate(zip(ne.nutzer, equal))
        ]

    perioden = nutzer_perioden(zeitraum_von, zeitraum_bis, ne.nutzer)
    tage = [max(0, (bis - von).days + 1) for _, _, von, bis in perioden]
    tage_anteile = _anteile([float(t) for t in tage])
    gradtag_anteile = _anteile([
        gradtag_gewicht(von, bis) if bis >= von else 0.0
        for _, _, von, bis in perioden
    ])

    results = []
    for (idx, nu, von, bis), t, ta, ga in zip(perioden, tage, tage_anteile,
                                              gradtag_anteile):
        results.append(NutzerResult(
            idx=idx, bezeichnung=nu.bezeichnung, von=von, bis=bis,
            tage=t, tage_anteil=ta, gradtag_anteil=ga,
            ww_gk=res.ww_gk * ta, ww_vk=res.ww_vk * ta,
            hz_gk=res.hz_gk * ta, hz_vk=res.hz_vk * ga,
            vorauszahlung_eur=nu.vorauszahlung_eur,
        ))

    # Last user absorbs rounding so the user components sum exactly to the NE's
    if results:
        last = results[-1]
        last.ww_gk = res.ww_gk - sum(r.ww_gk for r in results[:-1])
        last.ww_vk = res.ww_vk - sum(r.ww_vk for r in results[:-1])
        last.hz_gk = res.hz_gk - sum(r.hz_gk for r in results[:-1])
        last.hz_vk = res.hz_vk - sum(r.hz_vk for r in results[:-1])
    return results
