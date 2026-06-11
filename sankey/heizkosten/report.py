"""Printable Heizkostenabrechnung report (standalone HTML, A4 print CSS).

``build_report_html`` documents the complete calculation chain — Gesamtkosten →
CO2-Aufteilung → §9-Trennung → Verteilschlüssel → Einzelabrechnung je
Nutzeinheit → Kontrollsummen — with the legal references (HeizkostenV,
CO2KostAufG) next to every step. Pure function: no Streamlit, no third-party
dependencies; print to PDF via the browser.
"""

from datetime import date
from html import escape
from typing import Dict, List, Optional, Tuple

from . import fmt
from .compute import GewerkPool, assemble_pools, derive_group_kwh
from .constants import GEWERK_LABEL
from .model import (
    ComputedResults,
    GewerkResult,
    Hinweis,
    NEConfig,
    NEResult,
    ScenarioConfig,
)

_HINWEIS_LABEL = {"error": "Fehler", "warning": "Warnung", "info": "Hinweis"}

_CSS = """
  :root {
    --ink: #1c2430; --muted: #5a6a7e; --line: #d7dce3; --soft: #f3f5f8;
    --accent: #35506b; --ok: #2e7d4f; --warn: #9a6b00; --err: #b3372f;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 28px 34px; color: var(--ink); background: #fff;
    font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    font-size: 13px; line-height: 1.45;
  }
  header.kopf { border-bottom: 2px solid var(--ink); padding-bottom: 10px; margin-bottom: 18px; }
  header.kopf h1 { margin: 0 0 2px 0; font-size: 21px; letter-spacing: -0.01em; }
  header.kopf .meta { color: var(--muted); font-size: 12px; }
  header.kopf .meta b { color: var(--ink); font-weight: 600; }
  .badge {
    display: inline-block; font-size: 10px; letter-spacing: 0.08em; text-transform: uppercase;
    border: 1px solid var(--line); border-radius: 10px; padding: 1px 8px;
    color: var(--muted); margin-left: 8px; vertical-align: 2px;
  }
  section.block { margin-bottom: 22px; page-break-inside: avoid; }
  section.block h2 {
    font-size: 14px; margin: 0 0 2px 0; color: var(--accent);
  }
  section.block h2 .cite { font-weight: 400; font-size: 11px; color: var(--muted); margin-left: 6px; }
  section.block .lead { color: var(--muted); font-size: 12px; margin: 0 0 8px 0; }
  table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
  th, td { padding: 4px 8px; text-align: left; vertical-align: top; }
  thead th {
    font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.06em;
    color: var(--muted); border-bottom: 1px solid var(--ink); font-weight: 600;
  }
  tbody tr { border-bottom: 1px solid var(--line); }
  td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
  td.formel { color: var(--muted); font-size: 12px; }
  tr.sum td { border-top: 1.5px solid var(--ink); border-bottom: none; font-weight: 600; }
  tr.saldo td { font-weight: 700; }
  tr.saldo.nachzahlung td.num { color: var(--err); }
  tr.saldo.guthaben td.num { color: var(--ok); }
  .ne-block { border: 1px solid var(--line); border-radius: 6px; padding: 12px 14px; margin-bottom: 12px; page-break-inside: avoid; }
  .ne-block h3 { margin: 0 0 1px 0; font-size: 13.5px; }
  .ne-block .meta { color: var(--muted); font-size: 11.5px; margin-bottom: 8px; }
  .ne-block h4 { margin: 12px 0 4px 0; font-size: 12px; color: var(--accent); }
  .nutzer-block { border-left: 3px solid var(--line); background: var(--soft);
                  border-radius: 0 4px 4px 0; padding: 8px 12px; margin-top: 8px;
                  page-break-inside: avoid; }
  .nutzer-block h5 { margin: 0 0 1px 0; font-size: 12.5px; }
  .nutzer-block .meta { color: var(--muted); font-size: 11px; margin-bottom: 6px; }
  .hinweis { border-left: 3px solid var(--line); background: var(--soft); padding: 6px 10px; margin-bottom: 6px; font-size: 12px; }
  .hinweis.warning { border-left-color: var(--warn); }
  .hinweis.error { border-left-color: var(--err); }
  .kontroll-ok { color: var(--ok); font-weight: 600; }
  .kontroll-fail { color: var(--err); font-weight: 600; }
  footer { margin-top: 26px; padding-top: 10px; border-top: 1px solid var(--line); color: var(--muted); font-size: 11px; }
  .sankey { margin-top: 6px; border: 1px solid var(--line); border-radius: 6px; overflow: hidden; }
  @page { size: A4; margin: 13mm; }
  @media print {
    body { padding: 0; font-size: 11.5px; }
    .sankey { page-break-before: auto; }
  }
"""


def _fmt_date(d: Optional[date]) -> str:
    return d.strftime("%d.%m.%Y") if d else "—"


def _hz_unit(messtechnik: str) -> str:
    return "kWh" if messtechnik == "wmz" else "VE"


def _section(title: str, cite: str, body: str, lead: str = "") -> str:
    lead_html = f'<p class="lead">{lead}</p>' if lead else ""
    return (f'<section class="block"><h2>{escape(title)}'
            f'<span class="cite">{escape(cite)}</span></h2>{lead_html}{body}</section>')


def _table(head: List[Tuple[str, bool]], rows: List[str]) -> str:
    ths = "".join(f'<th{" class=num" if num else ""}>{escape(h)}</th>' for h, num in head)
    return f"<table><thead><tr>{ths}</tr></thead><tbody>{''.join(rows)}</tbody></table>"


# ── Kopf & Gesamtkosten ───────────────────────────────────────────────────────

def _kopf(scenario: ScenarioConfig) -> str:
    objekt = escape(scenario.objekt) if scenario.objekt else "—"
    return f"""
<header class="kopf">
  <h1>Heizkostenabrechnung<span class="badge">Simulation</span></h1>
  <div class="meta">
    Objekt: <b>{objekt}</b> &nbsp;·&nbsp;
    Abrechnungszeitraum: <b>{_fmt_date(scenario.zeitraum_von)} – {_fmt_date(scenario.zeitraum_bis)}</b> &nbsp;·&nbsp;
    Erstellt am: <b>{_fmt_date(date.today())}</b>
  </div>
</header>"""


def _gesamtkosten(scenario: ScenarioConfig) -> str:
    summe = (scenario.brennstoff_eur + scenario.weitere_kosten_eur
             + scenario.geraetemiete_ww_eur + scenario.geraetemiete_hz_eur)
    rows = [
        f'<tr><td>Brennstoffkosten</td><td class="formel">{fmt.kwh(scenario.brennstoff_kwh)}</td>'
        f'<td class="num">{fmt.eur(scenario.brennstoff_eur)}</td></tr>',
        f'<tr><td>Weitere Heizungsbetriebskosten</td>'
        f'<td class="formel">Betriebsstrom, Wartung, Messdienst u. a. (§7 Abs. 2)</td>'
        f'<td class="num">{fmt.eur(scenario.weitere_kosten_eur)}</td></tr>',
        f'<tr><td>Gerätemiete Warmwasser</td><td class="formel">Anmietung der Erfassungsgeräte</td>'
        f'<td class="num">{fmt.eur(scenario.geraetemiete_ww_eur)}</td></tr>',
        f'<tr><td>Gerätemiete Heizung</td><td class="formel">Anmietung der Erfassungsgeräte</td>'
        f'<td class="num">{fmt.eur(scenario.geraetemiete_hz_eur)}</td></tr>',
        f'<tr class="sum"><td>Gesamtkosten</td><td></td><td class="num">{fmt.eur(summe)}</td></tr>',
    ]
    return _section(
        "A · Gesamtkosten der Abrechnungseinheit", "§7 Abs. 2, §8 Abs. 2 HeizkostenV",
        _table([("Kostenart", False), ("Erläuterung", False), ("Betrag", True)], rows),
        lead="Zusammenstellung der im Abrechnungszeitraum angefallenen Kosten des Betriebs "
             "der zentralen Heizungs- und Warmwasserversorgungsanlage.",
    )


def _co2_block(results: ComputedResults, scenario: ScenarioConfig) -> str:
    co2 = results.co2
    if not co2.aktiv:
        return _section(
            "B · CO2-Kostenaufteilung", "CO2KostAufG",
            '<p class="lead">Nicht aktiviert — die CO2-Kosten verbleiben vollständig '
            "in den umlagefähigen Brennstoffkosten.</p>",
        )
    rows = []
    if co2.modus == "stufen":
        rows.append(f'<tr><td>CO2-Ausstoß des Gebäudes</td><td class="formel"></td>'
                    f'<td class="num">{fmt.num(scenario.co2_emission_kg or 0.0, 0)} kg/a</td></tr>')
        rows.append(f'<tr><td>Spezifischer Ausstoß</td>'
                    f'<td class="formel">Ausstoß ÷ Wohnfläche</td>'
                    f'<td class="num">{fmt.num(co2.spez_kg_m2 or 0.0, 1)} kg CO2/m²·a</td></tr>')
        rows.append(f'<tr><td>Einstufung (10-Stufen-Modell, §7 CO2KostAufG)</td>'
                    f'<td class="formel"></td><td class="num">Stufe {co2.stufe}</td></tr>')
    rows += [
        f'<tr><td>CO2-Kosten gesamt</td><td class="formel"></td>'
        f'<td class="num">{fmt.eur(co2.kosten_eur)}</td></tr>',
        f'<tr><td>Anteil Vermieter ({fmt.pct(co2.anteil_vermieter)})</td>'
        f'<td class="formel">wird von den umlagefähigen Brennstoffkosten abgezogen</td>'
        f'<td class="num">−{fmt.eur(co2.vermieter_eur)}</td></tr>',
        f'<tr class="sum"><td>Anteil Mieter</td><td></td>'
        f'<td class="num">{fmt.eur(co2.mieter_eur)}</td></tr>',
    ]
    lead = ("Aufteilung der Kohlendioxidkosten zwischen Vermieter und Mieter nach dem "
            "Kohlendioxidkostenaufteilungsgesetz (CO2KostAufG)."
            + (" Die CO2-Kosten wurden auf die Brennstoffkosten begrenzt." if co2.gekappt else ""))
    return _section("B · CO2-Kostenaufteilung", "CO2KostAufG", _table(
        [("Schritt", False), ("Erläuterung", False), ("Wert", True)], rows), lead=lead)


def _trennung(results: ComputedResults, scenario: ScenarioConfig) -> str:
    sys = results.system
    www = results.ww_energie
    rows = [
        f'<tr><td>Warmwasser-Energieanteil</td>'
        f'<td class="formel">{escape(www.beschreibung)}</td>'
        f'<td class="num">{fmt.kwh(sys.warmwasser_kwh)}</td></tr>',
        f'<tr><td>Heizungs-Energieanteil</td>'
        f'<td class="formel">{fmt.kwh(scenario.brennstoff_kwh)} − {fmt.kwh(sys.warmwasser_kwh)}</td>'
        f'<td class="num">{fmt.kwh(sys.heizung_kwh)}</td></tr>',
        f'<tr><td>Umlagefähige Kosten</td>'
        f'<td class="formel">Brennstoff (nach CO2-Abzug) {fmt.eur(sys.brennstoff_mieter_eur)} '
        f'+ Weitere Kosten {fmt.eur(scenario.weitere_kosten_eur)}</td>'
        f'<td class="num">{fmt.eur(sys.brennstoff_gesamt_eur)}</td></tr>',
        f'<tr><td>Kosten Warmwasser</td>'
        f'<td class="formel">{fmt.kwh(sys.warmwasser_kwh)} / {fmt.kwh(scenario.brennstoff_kwh)} × '
        f'{fmt.eur(sys.brennstoff_gesamt_eur)} + Gerätemiete {fmt.eur(scenario.geraetemiete_ww_eur)}</td>'
        f'<td class="num">{fmt.eur(sys.warmwasser_eur)}</td></tr>',
        f'<tr><td>Kosten Heizung</td>'
        f'<td class="formel">{fmt.kwh(sys.heizung_kwh)} / {fmt.kwh(scenario.brennstoff_kwh)} × '
        f'{fmt.eur(sys.brennstoff_gesamt_eur)} + Gerätemiete {fmt.eur(scenario.geraetemiete_hz_eur)}</td>'
        f'<td class="num">{fmt.eur(sys.heizung_eur)}</td></tr>',
        f'<tr class="sum"><td>Summe der Kostenpools</td><td></td>'
        f'<td class="num">{fmt.eur(sys.warmwasser_eur + sys.heizung_eur)}</td></tr>',
    ]
    return _section(
        "C · Trennung Warmwasser / Heizung", "§9 HeizkostenV",
        _table([("Schritt", False), ("Berechnung", False), ("Ergebnis", True)], rows),
        lead="Der auf die zentrale Warmwasserversorgung entfallende Energie- und "
             "Kostenanteil wird nach §9 Abs. 2 HeizkostenV bestimmt; die Gerätemieten "
             "werden dem jeweiligen Gewerk direkt zugeordnet.",
    )


# ── Verteilschlüssel (per Gewerk) ─────────────────────────────────────────────

def _pool_label(pool: GewerkPool, scenario: ScenarioConfig) -> str:
    if pool.is_rest:
        return f"Rest (NG {pool.display_id})"
    grp = next((g for g in scenario.groups if g.id == pool.source_group_id), None)
    if grp is not None and grp.bezeichnung.strip():
        return f"NG {pool.display_id} „{grp.bezeichnung.strip()}“"
    return f"NG {pool.display_id}"


def _member_names(pool: GewerkPool, by_id: Dict[int, NEConfig]) -> str:
    return ", ".join(by_id[i].display_label for i in pool.members if i in by_id)


def _verteilung_gewerk(gewerk: str, gres: GewerkResult, scenario: ScenarioConfig,
                       results: ComputedResults) -> str:
    name = GEWERK_LABEL[gewerk]
    if not gres.grouped:
        v = gres.shared_verteilung
        rows = [
            f'<tr><td>Grundkosten ({fmt.pct(v)})</td>'
            f'<td class="formel">Verteilung nach Wohnfläche</td>'
            f'<td class="num">{fmt.eur(gres.shared_gk)}</td></tr>',
            f'<tr><td>Verbrauchskosten ({fmt.pct(1 - v)})</td>'
            f'<td class="formel">Verteilung nach erfasstem Verbrauch</td>'
            f'<td class="num">{fmt.eur(gres.shared_vk)}</td></tr>',
            f'<tr class="sum"><td>Kosten {escape(name)}</td><td></td>'
            f'<td class="num">{fmt.eur(gres.eur)}</td></tr>',
        ]
        return _table([("Anteil", False), ("Maßstab", False), ("Betrag", True)], rows)

    by_id = {ne.id: ne for ne in scenario.nutzeinheiten}
    pools = assemble_pools(scenario, gewerk)
    pool_kwh = (results.system.heizung_kwh if gewerk == "hz"
                else results.system.warmwasser_kwh)
    kwhs = derive_group_kwh(scenario.nutzeinheiten, pools, gewerk, pool_kwh)

    pre = ""
    if gres.kreuzberg:
        pre = (f'<p class="lead">Vorverteilung („Kreuzberger Schlüssel“): '
               f'{fmt.pct(gres.vorverteilung)} Grundkostenanteil ({fmt.eur(gres.gk_pre)}, '
               f'auf die Pools nach Fläche) / {fmt.pct(1 - gres.vorverteilung)} '
               f'Verbrauchskostenanteil ({fmt.eur(gres.vk_pre)}, nach Verbrauch).</p>')

    rows = []
    for pool, kwh in zip(pools, kwhs):
        gc = gres.group(pool.display_id)
        if gres.kreuzberg:
            herkunft = (f'aus GK-Anteil {fmt.pct(gc.area_fraction, 1)} = {fmt.eur(gc.from_gk)} '
                        f'+ aus VK-Anteil {fmt.pct(gc.fraction, 1)} = {fmt.eur(gc.from_vk)}')
        else:
            herkunft = f'Verbrauchsanteil {fmt.pct(gc.fraction, 1)}'
        rows.append(
            f'<tr><td>{escape(_pool_label(pool, scenario))}</td>'
            f'<td class="formel">{escape(_member_names(pool, by_id))}</td>'
            f'<td class="num">{fmt.kwh(kwh)}</td>'
            f'<td class="formel">{herkunft}</td>'
            f'<td class="num">{fmt.eur(gc.eur)}</td>'
            f'<td class="num">{fmt.pct(gc.verteilung)} → {fmt.eur(gc.gk)}</td>'
            f'<td class="num">{fmt.pct(1 - gc.verteilung)} → {fmt.eur(gc.vk)}</td></tr>'
        )
    rows.append(f'<tr class="sum"><td>Kosten {escape(name)}</td><td></td>'
                f'<td class="num">{fmt.kwh(pool_kwh)}</td><td></td>'
                f'<td class="num">{fmt.eur(gres.eur)}</td><td></td><td></td></tr>')
    return pre + _table(
        [("Pool", False), ("Nutzeinheiten", False), ("Verbrauch", True),
         ("Zuteilung", False), ("Kosten", True), ("Grundkosten", True),
         ("Verbrauchskosten", True)],
        rows,
    )


def _verteilung(results: ComputedResults, scenario: ScenarioConfig) -> str:
    body = ""
    for gewerk, gres in (("ww", results.ww), ("hz", results.hz)):
        body += f"<h3>{escape(GEWERK_LABEL[gewerk])}</h3>"
        body += _verteilung_gewerk(gewerk, gres, scenario, results)
    return _section(
        "D · Verteilschlüssel", "§7 Abs. 1, §8 Abs. 1, §5 Abs. 2 HeizkostenV",
        body,
        lead="Die Kosten jedes Gewerks werden in Grundkosten (nach Wohnfläche) und "
             "Verbrauchskosten (nach erfasstem Verbrauch) zerlegt; bei Nutzergruppen "
             "(§5 Abs. 2 Vorerfassung) zunächst je Gruppe vorverteilt.",
    )


# ── Einzelabrechnungen ────────────────────────────────────────────────────────

def _ne_rows(ne: NEConfig, scenario: ScenarioConfig, results: ComputedResults,
             gewerk: str) -> List[str]:
    """Formula rows for one NE and one Gewerk (per pool when grouped)."""
    gres = results.ww if gewerk == "ww" else results.hz
    res = next(r for r in results.ne_results if r.id == ne.id)
    name = GEWERK_LABEL[gewerk]
    by_id = {n.id: n for n in scenario.nutzeinheiten}

    def cons(n: NEConfig) -> float:
        return n.ww_m3 if gewerk == "ww" else n.hz_wert

    def cons_unit(n: NEConfig) -> str:
        return "m³" if gewerk == "ww" else _hz_unit(n.messtechnik)

    def row(label: str, formel: str, value: float) -> str:
        return (f'<tr><td>{escape(label)}</td><td class="formel">{escape(formel)}</td>'
                f'<td class="num">{fmt.eur(value)}</td></tr>')

    rows: List[str] = []
    if not gres.grouped:
        flaeche_total = scenario.total_flaeche()
        cons_total = sum(cons(n) for n in scenario.nutzeinheiten)
        gk, vk = (res.ww_gk, res.ww_vk) if gewerk == "ww" else (res.hz_gk, res.hz_vk)
        rows.append(row(
            f"{name} — Grundkosten",
            f"{fmt.m2(ne.flaeche)} / {fmt.m2(flaeche_total)} × {fmt.eur(gres.shared_gk)}",
            gk,
        ))
        unit = cons_unit(ne)
        rows.append(row(
            f"{name} — Verbrauchskosten",
            f"{fmt.num(cons(ne), 1)} {unit} / {fmt.num(cons_total, 1)} {unit} × "
            f"{fmt.eur(gres.shared_vk)}",
            vk,
        ))
        return rows

    pools = {p.display_id: p for p in assemble_pools(scenario, gewerk)}
    parts = res.ww_parts if gewerk == "ww" else res.hz_parts
    for display_id in sorted(parts):
        pool = pools[display_id]
        gc = gres.group(display_id)
        members = [by_id[i] for i in pool.members if i in by_id]
        pool_flaeche = sum(n.flaeche for n in members)
        pool_cons = sum(cons(n) for n in members)
        gk_w, vk_w = parts[display_id]
        suffix = f" ({_pool_label(pool, scenario)})" if len(parts) > 1 or len(pools) > 1 else ""
        unit = cons_unit(ne)
        rows.append(row(
            f"{name} — Grundkosten{suffix}",
            f"{fmt.m2(ne.flaeche)} / {fmt.m2(pool_flaeche)} × {fmt.eur(gc.gk)}",
            gk_w,
        ))
        rows.append(row(
            f"{name} — Verbrauchskosten{suffix}",
            f"{fmt.num(cons(ne), 1)} {unit} / {fmt.num(pool_cons, 1)} {unit} × {fmt.eur(gc.vk)}",
            vk_w,
        ))
    return rows


def _saldo_rows(total: float, vorauszahlung: float) -> List[str]:
    saldo = total - vorauszahlung
    cls, label = (("nachzahlung", "Nachzahlung") if saldo >= 0
                  else ("guthaben", "Guthaben"))
    return [
        f'<tr><td>abzüglich Vorauszahlungen</td><td></td>'
        f'<td class="num">−{fmt.eur(vorauszahlung)}</td></tr>',
        f'<tr class="saldo {cls}"><td>{label}</td><td></td>'
        f'<td class="num">{fmt.eur(abs(saldo))}</td></tr>',
    ]


def _nutzerwechsel_block(res: NEResult) -> str:
    """§9b split table + one sub-block per user (own Vorauszahlung & Saldo)."""
    split_rows = [
        f'<tr><td>{escape(nu.display_label)}</td>'
        f'<td class="formel">{nu.zeitraum_text}</td>'
        f'<td class="num">{nu.tage}</td>'
        f'<td class="num">{fmt.pct(nu.tage_anteil, 1)}</td>'
        f'<td class="num">{fmt.pct(nu.gradtag_anteil, 1)}</td></tr>'
        for nu in res.nutzer
    ]
    html = ('<h4>Aufteilung bei Nutzerwechsel (§9b Abs. 2 HeizkostenV)</h4>'
            '<p class="lead">Grundkosten und Verbrauchskosten Warmwasser zeitanteilig '
            '(nach Tagen), Verbrauchskosten Heizung nach Gradtagszahlen '
            '(Promille-Tabelle, Summe 1000 ‰/Jahr).</p>'
            + _table([("Nutzer", False), ("Zeitraum", False), ("Tage", True),
                      ("Anteil Tage", True), ("Anteil Gradtage", True)], split_rows))

    for nu in res.nutzer:
        rows = [
            f'<tr><td>Warmwasser — Grundkosten</td>'
            f'<td class="formel">Tage-Anteil {fmt.pct(nu.tage_anteil, 1)} × {fmt.eur(res.ww_gk)}</td>'
            f'<td class="num">{fmt.eur(nu.ww_gk)}</td></tr>',
            f'<tr><td>Warmwasser — Verbrauchskosten</td>'
            f'<td class="formel">Tage-Anteil {fmt.pct(nu.tage_anteil, 1)} × {fmt.eur(res.ww_vk)}</td>'
            f'<td class="num">{fmt.eur(nu.ww_vk)}</td></tr>',
            f'<tr><td>Heizung — Grundkosten</td>'
            f'<td class="formel">Tage-Anteil {fmt.pct(nu.tage_anteil, 1)} × {fmt.eur(res.hz_gk)}</td>'
            f'<td class="num">{fmt.eur(nu.hz_gk)}</td></tr>',
            f'<tr><td>Heizung — Verbrauchskosten</td>'
            f'<td class="formel">Gradtag-Anteil {fmt.pct(nu.gradtag_anteil, 1)} × {fmt.eur(res.hz_vk)}</td>'
            f'<td class="num">{fmt.eur(nu.hz_vk)}</td></tr>',
            f'<tr class="sum"><td>Summe {escape(nu.display_label)}</td><td></td>'
            f'<td class="num">{fmt.eur(nu.total)}</td></tr>',
        ] + _saldo_rows(nu.total, nu.vorauszahlung_eur)
        html += (
            f'<div class="nutzer-block"><h5>{escape(nu.display_label)}</h5>'
            f'<div class="meta">Nutzungszeitraum {nu.zeitraum_text} · {nu.tage} Tage</div>'
            + _table([("Kostenanteil", False), ("Berechnung", False), ("Betrag", True)], rows)
            + "</div>"
        )
    return html


def _einzelabrechnungen(scenario: ScenarioConfig, results: ComputedResults) -> str:
    blocks = []
    for ne in scenario.nutzeinheiten:
        res = next(r for r in results.ne_results if r.id == ne.id)
        multi = len(res.nutzer) >= 2
        rows = _ne_rows(ne, scenario, results, "ww") + _ne_rows(ne, scenario, results, "hz")
        rows.append(f'<tr class="sum"><td>Summe Heiz- und Warmwasserkosten</td><td></td>'
                    f'<td class="num">{fmt.eur(res.total)}</td></tr>')
        if not multi:
            rows += _saldo_rows(res.total, res.vorauszahlung_eur)

        title = ne.label if not res.bezeichnung else f"{ne.label} — {res.bezeichnung}"
        meta = (f"Wohnfläche {fmt.m2(ne.flaeche)} · Warmwasser {fmt.num(ne.ww_m3, 1)} m³ · "
                f"Heizung {fmt.num(ne.hz_wert, 0)} {_hz_unit(ne.messtechnik)} "
                f"({'Wärmemengenzähler' if ne.messtechnik == 'wmz' else 'Heizkostenverteiler'})")
        body = _table([("Kostenanteil", False), ("Berechnung", False), ("Betrag", True)], rows)
        if multi:
            body += _nutzerwechsel_block(res)
        blocks.append(
            f'<div class="ne-block"><h3>{escape(title)}</h3>'
            f'<div class="meta">{escape(meta)}</div>{body}</div>'
        )
    return _section(
        "E · Einzelabrechnungen der Nutzeinheiten", "§6, §7 Abs. 1, §8 Abs. 1, §9b HeizkostenV",
        "".join(blocks),
        lead="Jeder Kostenanteil ist mit seinem Rechenweg ausgewiesen: Grundkosten nach "
             "Wohnflächenanteil, Verbrauchskosten nach Anteil am erfassten Verbrauch des "
             "jeweiligen Verteilungspools; bei Nutzerwechsel anschließend Aufteilung "
             "nach §9b HeizkostenV auf die Nutzer.",
    )


# ── Gesamtübersicht & Kontrollsummen ──────────────────────────────────────────

def _uebersicht(scenario: ScenarioConfig, results: ComputedResults) -> str:
    rows = []
    s = {"ww_gk": 0.0, "ww_vk": 0.0, "hz_gk": 0.0, "hz_vk": 0.0,
         "total": 0.0, "vz": 0.0, "saldo": 0.0}
    for r in results.ne_results:
        multi = len(r.nutzer) >= 2
        for nu in r.nutzer:
            s["ww_gk"] += nu.ww_gk; s["ww_vk"] += nu.ww_vk
            s["hz_gk"] += nu.hz_gk; s["hz_vk"] += nu.hz_vk
            s["total"] += nu.total; s["vz"] += nu.vorauszahlung_eur
            s["saldo"] += nu.saldo
            label = (f"{r.label} · {nu.display_label}" if multi
                     else r.display_label)
            rows.append(
                f'<tr><td>{escape(label)}</td>'
                f'<td class="formel">{nu.zeitraum_text}</td>'
                f'<td class="num">{fmt.eur(nu.ww_gk)}</td><td class="num">{fmt.eur(nu.ww_vk)}</td>'
                f'<td class="num">{fmt.eur(nu.hz_gk)}</td><td class="num">{fmt.eur(nu.hz_vk)}</td>'
                f'<td class="num">{fmt.eur(nu.total)}</td>'
                f'<td class="num">{fmt.eur(nu.vorauszahlung_eur)}</td>'
                f'<td class="num">{fmt.eur(nu.saldo)}</td></tr>'
            )
    rows.append(
        f'<tr class="sum"><td>Summe</td><td></td>'
        f'<td class="num">{fmt.eur(s["ww_gk"])}</td><td class="num">{fmt.eur(s["ww_vk"])}</td>'
        f'<td class="num">{fmt.eur(s["hz_gk"])}</td><td class="num">{fmt.eur(s["hz_vk"])}</td>'
        f'<td class="num">{fmt.eur(s["total"])}</td>'
        f'<td class="num">{fmt.eur(s["vz"])}</td>'
        f'<td class="num">{fmt.eur(s["saldo"])}</td></tr>'
    )
    table = _table(
        [("Nutzer", False), ("Zeitraum", False), ("WW Grund", True), ("WW Verbrauch", True),
         ("Hz Grund", True), ("Hz Verbrauch", True), ("Gesamt", True),
         ("Vorauszahlung", True), ("Saldo", True)],
        rows,
    )

    pools_total = results.system.warmwasser_eur + results.system.heizung_eur
    diff = s["total"] - pools_total
    ok = abs(diff) < 0.005
    mark = ('<span class="kontroll-ok">✓ vollständig verteilt</span>' if ok else
            f'<span class="kontroll-fail">✗ Differenz {fmt.eur(diff)}</span>')
    kontrolle = (
        f'<p class="lead" style="margin-top:8px">Kontrollsumme: Summe aller Nutzeinheiten '
        f'{fmt.eur(s["total"])} = Kosten Warmwasser {fmt.eur(results.system.warmwasser_eur)} '
        f'+ Kosten Heizung {fmt.eur(results.system.heizung_eur)} '
        f'= {fmt.eur(pools_total)} &nbsp;{mark}</p>'
    )
    return _section("F · Gesamtübersicht & Kontrollsummen", "Vollständigkeitsnachweis",
                    table + kontrolle)


# ── Hinweise & Fuß ────────────────────────────────────────────────────────────

def _hinweise_block(hinweise: List[Hinweis]) -> str:
    items = "".join(
        f'<div class="hinweis {h.level}"><b>{_HINWEIS_LABEL[h.level]}:</b> {escape(h.text)}</div>'
        for h in hinweise
    )
    if not items:
        items = '<p class="lead">Keine Auffälligkeiten — alle Plausibilitätsprüfungen bestanden.</p>'
    return _section("G · Hinweise & Plausibilität", "u. a. §12 HeizkostenV", items)


def _footer() -> str:
    return (
        '<footer>Diese Auswertung ist eine <b>Simulation</b> zur Veranschaulichung der '
        'Kostenverteilung nach der Verordnung über Heizkostenabrechnung (HeizkostenV) und dem '
        'Kohlendioxidkostenaufteilungsgesetz (CO2KostAufG). Sie ersetzt keine rechtsverbindliche '
        'Abrechnung durch den Gebäudeeigentümer bzw. Messdienstleister. Angewandte Maßstäbe: '
        'Grundkosten nach Wohnfläche, Verbrauchskosten nach erfasstem Verbrauch '
        '(§§7, 8 HeizkostenV); Warmwasser-Energieanteil nach §9 Abs. 2 HeizkostenV; bei '
        'Nutzerwechsel Aufteilung nach §9b HeizkostenV — Grundkosten und Warmwasser-'
        'Verbrauchskosten zeitanteilig, Heizungs-Verbrauchskosten nach der '
        'Gradtagszahlen-Tabelle (1000 ‰ je Abrechnungsjahr).</footer>'
    )


# ── Entry point ───────────────────────────────────────────────────────────────

def build_report_html(
    scenario: ScenarioConfig,
    results: ComputedResults,
    hinweise: List[Hinweis],
    sankey_svg: Optional[str] = None,
) -> str:
    """Self-contained printable Heizkostenabrechnung (HTML, A4)."""
    sankey_block = ""
    if sankey_svg:
        sankey_block = _section(
            "H · Kostenfluss-Diagramm", "Sankey-Darstellung",
            f'<div class="sankey">{sankey_svg}</div>',
            lead="Visualisierung des vollständigen Kostenflusses von den Gesamtkosten "
                 "bis zu den Nutzeinheiten.",
        )
    title = "Heizkostenabrechnung" + (f" — {scenario.objekt}" if scenario.objekt else "")
    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{escape(title)}</title>
<style>{_CSS}</style>
</head>
<body>
{_kopf(scenario)}
{_gesamtkosten(scenario)}
{_co2_block(results, scenario)}
{_trennung(results, scenario)}
{_verteilung(results, scenario)}
{_einzelabrechnungen(scenario, results)}
{_uebersicht(scenario, results)}
{_hinweise_block(hinweise)}
{sankey_block}
{_footer()}
</body>
</html>"""
