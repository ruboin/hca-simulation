"""Heizkostenabrechnung Sankey dashboard — orchestrator.

Pipeline: init state → sidebar (ScenarioConfig) → compute_all → render
(Diagramm-Tab, Bericht-Tab, Exporte).
"""
import streamlit as st

import sankey.heizkosten as hk
from ui import state
from ui.results import (
    render_breakdown,
    render_exports,
    render_hinweise,
    render_metric_cards,
    render_ne_filter,
    render_title,
)
from ui.sankey_view import build_sankey_graph, sankey_html, sankey_report_svg
from ui.sidebar import render_sidebar
from ui.styles import inject_css

st.set_page_config(
    page_title="Heizkostenabrechnung - Sankey",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_css()
state.init_state()

scenario = render_sidebar()
results = hk.compute_all(scenario)
hinweise = hk.validate_scenario(scenario, results)

render_title()
render_hinweise(hinweise)
if hk.has_errors(hinweise):
    if any(h.code.startswith("MESSTECHNIK") for h in hinweise):
        st.button(
            "Gruppen automatisch nach Messtechnik bilden",
            on_click=state.derive_groups_from_messtechnik,
            key="btn_derive_groups",
            type="primary",
        )
    st.stop()

render_metric_cards(results)

tab_diagramm, tab_bericht = st.tabs(["Diagramm", "Bericht"])

with tab_diagramm:
    selected_ne_ids = render_ne_filter(results)
    graph = build_sankey_graph(scenario, results, selected_ne_ids)
    st.iframe(sankey_html(graph), height="content")
    render_breakdown(results, selected_ne_ids)

with tab_bericht:
    report_html = hk.build_report_html(
        scenario, results, hinweise,
        sankey_svg=sankey_report_svg(scenario, results),
    )
    # Fixed-height viewer pane: height="content" can only ever grow (Streamlit
    # measures documentElement.scrollHeight, which is floored at the iframe
    # height), leaving dead whitespace under the report after any reflow.
    st.iframe(report_html, height=1000)

render_exports(scenario, results, graph, report_html)
