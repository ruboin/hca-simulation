"""Main-area output: title, hinweise, metric cards, NE filter, breakdown, exports."""
import csv
import io
from typing import List

import streamlit as st

from sankey.heizkosten import ComputedResults, Hinweis, NEResult, ScenarioConfig, fmt

from ui import presets
from ui.sankey_view import sankey_html
from ui.styles import ne_color


def render_hinweise(hinweise: List[Hinweis]) -> None:
    renderer = {"error": st.error, "warning": st.warning, "info": st.info}
    for h in hinweise:
        renderer[h.level](h.text)


def render_title() -> None:
    st.markdown(
        """
        <div class="title-bar">
          <h1>Heizkostenabrechnung</h1>
          <span class="title-badge">Simulation</span>
        </div>
        <p style="color:var(--text-muted);font-size:0.82rem;margin-top:0;margin-bottom:1.5rem;font-family:var(--font-mono);">
          Interaktive Verteilung der Heiz- und Warmwasserkosten
        </p>
        """,
        unsafe_allow_html=True,
    )


def _fmt_groups(groups: List[int]) -> str:
    return "+".join(str(g) for g in groups)


def _ne_badge(r: NEResult) -> str:
    hz, ww = r.groups_hz, r.groups_ww
    if not hz and not ww:
        return ""
    if hz == ww:
        text = f"NG {_fmt_groups(hz)}"
    else:
        parts = []
        if hz:
            parts.append(f"Hz NG {_fmt_groups(hz)}")
        if ww:
            parts.append(f"WW NG {_fmt_groups(ww)}")
        text = " · ".join(parts)
    return (f' &nbsp;<span style="font-size:0.6rem;background:var(--border);'
            f'border-radius:3px;padding:1px 5px;">{text}</span>')


def render_metric_cards(results: ComputedResults) -> None:
    system, co2 = results.system, results.co2

    def _ne_sub(r: NEResult) -> str:
        nutzer = f" · {len(r.nutzer)} Nutzer" if len(r.nutzer) >= 2 else ""
        return f"{fmt.m2(r.flaeche)}{nutzer}{_ne_badge(r)}"

    ne_cards = "".join(
        f'<div class="metric-card ne{r.id}">'
        f'<div class="label">{r.display_label}</div>'
        f'<div class="value">{fmt.eur(r.total)}</div>'
        f'<div class="sub">{_ne_sub(r)}</div>'
        f'</div>'
        for r in results.ne_results
    )
    co2_card = ""
    if co2.aktiv and co2.kosten_eur > 0:
        stufe = f" · Stufe {co2.stufe}" if co2.stufe is not None else ""
        co2_card = (
            f'<div class="metric-card co2">'
            f'<div class="label">CO2-Kosten (CO2KostAufG)</div>'
            f'<div class="value">{fmt.eur(co2.kosten_eur)}</div>'
            f'<div class="sub">Vermieter {co2.anteil_vermieter:.0%} · {fmt.eur(co2.vermieter_eur)}'
            f' / Mieter {fmt.eur(co2.mieter_eur)}{stufe}</div>'
            f'</div>'
        )
    st.markdown(
        f"""
        <div class="metric-grid">
          <div class="metric-card">
            <div class="label">Kosten für Heizung &amp; Wassererwärmung</div>
            <div class="value">{fmt.eur(system.brennstoff_gesamt_eur)}</div>
            <div class="sub">Brennstoff + Weitere Kosten</div>
          </div>
          <div class="metric-card ww">
            <div class="label">Kosten Warmwasser</div>
            <div class="value">{fmt.eur(system.warmwasser_eur)}</div>
            <div class="sub">{fmt.kwh(system.warmwasser_kwh)} Anteil</div>
          </div>
          <div class="metric-card hz">
            <div class="label">Kosten Heizung</div>
            <div class="value">{fmt.eur(system.heizung_eur)}</div>
            <div class="sub">{fmt.kwh(system.heizung_kwh)} Anteil</div>
          </div>
          {co2_card}
          {ne_cards}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_ne_filter(results: ComputedResults) -> List[int]:
    """Colored legend + multiselect; returns the selected 1-based NE ids."""
    all_labels = [r.label for r in results.ne_results]
    label_to_id = {r.label: r.id for r in results.ne_results}

    legend_items = "".join(
        f'<span style="display:inline-flex;align-items:center;gap:5px;margin-right:12px;'
        f'font-family:var(--font-mono);font-size:0.72rem;color:var(--text-muted);">'
        f'<span style="width:9px;height:9px;border-radius:2px;flex-shrink:0;'
        f'background:{ne_color(r.id)};"></span>'
        f'{r.label}</span>'
        for r in results.ne_results
    )
    st.markdown(
        f'<div style="display:flex;flex-wrap:wrap;align-items:center;'
        f'margin-bottom:4px;margin-top:0.5rem;">{legend_items}</div>',
        unsafe_allow_html=True,
    )

    st.session_state["sankey_ne_filter"] = [
        l for l in st.session_state["sankey_ne_filter"] if l in all_labels
    ]
    selected_labels = st.multiselect(
        "Nutzeinheiten im Sankey anzeigen",
        options=all_labels,
        key="sankey_ne_filter",
        placeholder="Nutzeinheiten auswählen …",
        help="Wähle die Nutzeinheiten aus, die im Sankey-Diagramm dargestellt werden sollen.",
    )
    selected = [label_to_id[l] for l in selected_labels if l in label_to_id]
    if not selected:
        selected = [r.id for r in results.ne_results[:2]]
    return selected


_TD_LABEL = "padding:6px 4px;color:var(--text-secondary);"
_TD_TOTAL = "padding:8px 4px;font-weight:600;color:var(--text);"
_TR_DIVIDER = "border-bottom:1px solid var(--border);"
_TR_TOTAL = "border-top:2px solid var(--accent-blue);"
_TABLE_BASE = ("width:100%;border-collapse:collapse;"
               "font-family:IBM Plex Mono,monospace;font-size:0.78rem;")
_CHUNK_SIZE = 3  # NE tables per row


def _csv_num(value: float, decimals: int = 2) -> str:
    """Plain comma-decimal number (no grouping) for German-Excel CSV."""
    return f"{value:.{decimals}f}".replace(".", ",")


def breakdown_csv(results: ComputedResults) -> str:
    """Per-user breakdown (one row per Nutzer) as semicolon CSV (German Excel)."""
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";", lineterminator="\n")
    writer.writerow([
        "id", "label", "nutzer", "von", "bis", "gruppe_hz", "gruppe_ww",
        "messtechnik", "flaeche_m2", "ww_gk_eur", "ww_vk_eur", "hz_gk_eur",
        "hz_vk_eur", "gesamt_eur", "vorauszahlung_eur", "saldo_eur",
    ])
    for r in results.ne_results:
        for nu in r.nutzer:
            writer.writerow([
                r.id, r.label, nu.display_label,
                nu.von.isoformat() if nu.von else "",
                nu.bis.isoformat() if nu.bis else "",
                _fmt_groups(r.groups_hz),
                _fmt_groups(r.groups_ww),
                r.messtechnik.upper(), _csv_num(r.flaeche, 1),
                _csv_num(nu.ww_gk), _csv_num(nu.ww_vk),
                _csv_num(nu.hz_gk), _csv_num(nu.hz_vk), _csv_num(nu.total),
                _csv_num(nu.vorauszahlung_eur), _csv_num(nu.saldo),
            ])
    return buf.getvalue()


def render_exports(
    scenario: ScenarioConfig,
    results: ComputedResults,
    graph: dict,
    report_html: str,
) -> None:
    cols = st.columns(4)
    cols[0].download_button(
        "⬇ Bericht (HTML)",
        data=report_html,
        file_name="heizkosten_abrechnung.html",
        mime="text/html",
        key="btn_export_report",
    )
    cols[1].download_button(
        "⬇ Aufschlüsselung (CSV)",
        data=breakdown_csv(results),
        file_name="heizkosten_aufschluesselung.csv",
        mime="text/csv",
        key="btn_export_csv",
    )
    cols[2].download_button(
        "⬇ Sankey (HTML)",
        data=sankey_html(graph, embed=False),
        file_name="heizkosten_sankey.html",
        mime="text/html",
        key="btn_export_html",
    )
    cols[3].download_button(
        "⬇ Szenario (JSON)",
        data=presets.scenario_to_json(scenario),
        file_name="heizkosten_szenario.json",
        mime="application/json",
        key="btn_export_json",
    )


def render_breakdown(results: ComputedResults, selected_ne_ids: List[int]) -> None:
    st.markdown("---")
    with st.expander("Kostenaufschlüsselung", expanded=True):
        selected = [r for r in results.ne_results if r.id in selected_ne_ids]
        if not selected:
            return
        for i in range(0, len(selected), _CHUNK_SIZE):
            chunk = selected[i:i + _CHUNK_SIZE]
            cols = st.columns(len(chunk), gap="large")
            for col, res in zip(cols, chunk):
                color = ne_color(res.id)
                td_val = f"padding:6px 4px;text-align:right;color:{color};"
                td_total_val = f"padding:8px 4px;text-align:right;font-weight:600;color:{color};"
                rows = [
                    ("WW — Grundkosten",      res.ww_gk),
                    ("WW — Verbrauchskosten", res.ww_vk),
                    ("Hz — Grundkosten",      res.hz_gk),
                    ("Hz — Verbrauchskosten", res.hz_vk),
                ]
                with col:
                    st.markdown(f"### {res.label}")
                    table = f'<table style="{_TABLE_BASE}">'
                    for lbl, val in rows:
                        table += (
                            f'<tr style="{_TR_DIVIDER}"><td style="{_TD_LABEL}">{lbl}</td>'
                            f'<td style="{td_val}">{fmt.eur(val)}</td></tr>'
                        )
                    table += (
                        f'<tr style="{_TR_TOTAL}"><td style="{_TD_TOTAL}">Gesamt</td>'
                        f'<td style="{td_total_val}">{fmt.eur(res.total)}</td></tr></table>'
                    )
                    st.markdown(table, unsafe_allow_html=True)
