"""Global CSS (dark theme) and small style helpers."""
import streamlit as st

from sankey.heizkosten import rgba, NE_COLORS

GLOBAL_CSS = """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@300;400;600&display=swap');

    /* ── Root palette ── */
    :root {
        --bg:             #0d0f12;
        --surface:        #13171d;
        --border:         #1e2530;
        --accent:         #d7dce1;
        --text:           #d4dce8;
        --text-muted:     #5a6a7e;
        --text-secondary: #8a9bb0;
        --accent-blue:    #5b82a0;
        --color-ww:       #c25454;
        --color-hz:       #cf7b48;
        --font-sans:      'IBM Plex Sans', sans-serif;
        --font-mono:      'IBM Plex Mono', monospace;
    }

    /* ── App shell ── */
    html, body, [class*="css"] {
        background-color: var(--bg) !important;
        color: var(--text) !important;
        font-family: var(--font-sans) !important;
    }
    .main .block-container {
        background-color: var(--bg);
        padding-top: 0.5rem;
        padding-bottom: 3rem;
    }

    /* ── Sidebar ── */
    section[data-testid="stSidebar"] {
        background-color: var(--surface) !important;
        border-right: 1px solid var(--border);
    }
    section[data-testid="stSidebar"] * {
        color: var(--text) !important;
    }

    /* ── Headings ── */
    h1, h2, h3, h4 {
        font-family: var(--font-sans) !important;
        font-weight: 600 !important;
        letter-spacing: -0.02em;
    }
    h1 { color: var(--text) !important; font-size: 1.6rem !important; }
    h2 { color: var(--accent) !important; font-size: 1.05rem !important;
         text-transform: uppercase; letter-spacing: 0.08em !important; }
    h3 { color: var(--text) !important; font-size: 0.95rem !important; }

    /* ── Sidebar section labels ── */
    .sidebar-section {
        display: flex;
        justify-content: space-between;
        align-items: baseline;
        gap: 0.5rem;
        font-family: var(--font-mono);
        font-size: 0.65rem;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: var(--text-muted);
        margin: 1.4rem 0 0.4rem 0;
        padding-bottom: 0.3rem;
        border-bottom: 1px solid var(--border);
    }
    .sidebar-section .summary {
        text-transform: none;
        letter-spacing: 0.02em;
        color: var(--text-secondary);
        text-align: right;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    /* ── Sidebar expanders / popover: match the section look ── */
    section[data-testid="stSidebar"] details[data-testid="stExpander"] {
        border: 1px solid var(--border) !important;
        border-radius: 4px !important;
        background: transparent !important;
        margin-bottom: 0.4rem;
    }
    section[data-testid="stSidebar"] details[data-testid="stExpander"] summary p {
        font-family: var(--font-mono) !important;
        font-size: 0.7rem !important;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        color: var(--text-secondary) !important;
    }
    section[data-testid="stSidebar"] [data-testid="stPopover"] button p {
        font-family: var(--font-mono) !important;
        font-size: 0.7rem !important;
        letter-spacing: 0.06em;
        text-transform: uppercase;
    }
    .sidebar-subsection {
        font-family: var(--font-mono);
        font-size: 0.6rem;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        color: var(--text-muted);
        margin: 1rem 0 0.25rem 0;
    }

    /* ── Inputs ── */
    input[type="number"], .stNumberInput input {
        background-color: var(--bg) !important;
        border: 1px solid var(--border) !important;
        color: var(--text) !important;
        border-radius: 4px !important;
        font-family: var(--font-mono) !important;
    }
    input[type="number"]:focus, .stNumberInput input:focus {
        border-color: var(--accent-blue) !important;
        box-shadow: 0 0 0 2px rgba(91, 130, 160, 0.18) !important;
    }

    /* ── Slider ── */
    .stSlider > div > div > div > div {
        background-color: var(--accent) !important;
    }
    .stSlider [data-baseweb="slider"] div[role="slider"] {
        background-color: var(--accent) !important;
        border-color: var(--accent) !important;
    }

    /* ── Metric cards ── */
    .metric-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        gap: 12px;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 6px;
        padding: 1rem 1.2rem;
    }
    .metric-card .label {
        font-family: var(--font-mono);
        font-size: 0.6rem;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        color: var(--text-muted);
        margin-bottom: 0.35rem;
    }
    .metric-card .value {
        font-family: var(--font-mono);
        font-size: 1.35rem;
        font-weight: 600;
        color: var(--accent);
    }
    .metric-card .sub {
        font-size: 0.7rem;
        color: var(--text-muted);
        margin-top: 0.2rem;
    }
    .metric-card.ww .value  { color: var(--color-ww); }
    .metric-card.hz .value  { color: var(--color-hz); }
    .metric-card.co2 .value { color: rgba(110, 122, 140, 1); }

    /* ── Divider ── */
    hr {
        border-color: var(--border) !important;
        margin: 0.5rem 0 !important;
    }

    /* ── Distribution hint text ── */
    .dist-hint {
        font-family: var(--font-mono);
        font-size: 0.7rem;
        color: var(--text-muted);
        margin-top: -0.6rem;
        margin-bottom: 0.8rem;
        line-height: 1.5;
    }

    /* ── Title bar ── */
    .title-bar {
        display: flex;
        align-items: baseline;
        gap: 1rem;
        margin-bottom: 0.25rem;
    }
    .title-bar h1 { margin: 0 !important; }
    .title-badge {
        font-family: var(--font-mono);
        font-size: 0.65rem;
        background: var(--border);
        color: var(--text-muted);
        padding: 2px 8px;
        border-radius: 20px;
        letter-spacing: 0.06em;
        text-transform: uppercase;
    }

    /* ── Streamlit element overrides ── */
    .stMarkdown p { color: var(--text); }
    div[data-testid="stNumberInput"] label,
    div[data-testid="stSlider"] label {
        color: var(--text-muted) !important;
        font-size: 0.8rem !important;
        font-family: var(--font-sans) !important;
    }

    /* ── Multiselect tags — dark theme ── */
    [data-testid="stMultiSelect"] [data-baseweb="tag"] {
        background-color: var(--border) !important;
        border-color: var(--border) !important;
    }
    [data-testid="stMultiSelect"] [data-baseweb="tag"] span {
        color: var(--text) !important;
    }
    [data-testid="stMultiSelect"] [data-baseweb="tag"] [role="presentation"] {
        color: var(--text-muted) !important;
    }

    /* ── Multiselect dropdown: "No results" → deutsch ── */
    [data-testid="stMultiSelect"] [data-baseweb="menu"] ul li:only-child {
        font-size: 0 !important;
        line-height: 0 !important;
    }
    [data-testid="stMultiSelect"] [data-baseweb="menu"] ul li:only-child::after {
        content: "Keine Ergebnisse";
        font-size: 0.84rem;
        line-height: 1.5;
        color: var(--text-muted);
        display: block;
        padding: 8px 16px;
    }

    /* ── Sankey chart panel ── */
    iframe[data-testid="stIFrame"] {
        display: block !important;
        background: transparent !important;
        border: none !important;
        border-radius: 6px !important;
        margin-bottom: 1.5rem !important;
    }
    </style>
"""


def ne_color(ne_id: int, alpha: float = 1.0) -> str:
    """Solid display color for a Nutzeinheit (palette cycles after 10)."""
    return rgba(NE_COLORS[(ne_id - 1) % len(NE_COLORS)], a=alpha)


def inject_css() -> None:
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)
    ne_css = "".join(
        f".metric-card.ne{i} .value {{ color: {ne_color(i)}; }}"
        f".metric-card.ne{i} {{ border-left: 3px solid {ne_color(i)}; }}"
        for i in range(1, 11)
    )
    st.markdown(f"<style>{ne_css}</style>", unsafe_allow_html=True)


def section(label: str, summary: str = "") -> None:
    right = f'<span class="summary">{summary}</span>' if summary else ""
    st.markdown(f'<div class="sidebar-section"><span>{label}</span>{right}</div>',
                unsafe_allow_html=True)


def subsection(label: str) -> None:
    st.markdown(f'<div class="sidebar-subsection">{label}</div>', unsafe_allow_html=True)


def dist_hint(pct: int) -> None:
    st.markdown(
        f'<div class="dist-hint">{pct}% Grundkosten &nbsp;·&nbsp; {100 - pct}% Verbrauchskosten</div>',
        unsafe_allow_html=True,
    )
