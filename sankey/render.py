"""Render layout graph to standalone interactive HTML (no third-party deps)."""

import json
from html import escape
from typing import Any, Dict, List


def link_path(link: Dict[str, Any], curvature: float = 0.5) -> str:
    """
    Ribbon from source bottom to target top (vertical flow).
    Control points mirror d3-sankey so both edges stay parallel (no S-curve
    when x jumps from right to left between layers).
    """
    y0 = link["source"]["y1"]
    y1 = link["target"]["y0"]
    dy = y1 - y0
    y2 = y0 + dy * curvature
    y3 = y0 + dy * (1.0 - curvature)
    xl0 = link["x0"] - link["width"] / 2
    xl1 = link["x1"] - link["width"] / 2
    xr0 = link["x0"] + link["width"] / 2
    xr1 = link["x1"] + link["width"] / 2
    # Left edge:  (xl0, y0) → (xl1, y1), controls share x with their endpoint
    # Right edge: (xr1, y1) → (xr0, y0), same rule on the return curve
    return (
        f"M{xl0},{y0}C{xl0},{y2} {xl1},{y3} {xl1},{y1}"
        f"L{xr1},{y1}C{xr1},{y3} {xr0},{y2} {xr0},{y0}Z"
    )


def _fmt_value(value: float, unit: str, locale: str) -> str:
    s = f"{value:,.2f}".rstrip("0").rstrip(".")
    if locale == "de":
        s = f"{value:,.2f}".translate(str.maketrans({",": ".", ".": ","}))
    return f"{s} {unit}".strip()


def render_static_svg(
    graph: Dict[str, Any],
    value_unit: str = "",
    locale: str = "en",
    background: str = "#ffffff",
) -> str:
    """JS-free SVG of a laid-out graph — for print/embedding (reports).

    Mirrors the interactive renderer's geometry: gradient ribbons via
    ``link_path`` and centered node labels; node values are printed on bars
    wide enough to hold a second line (no tooltips in static output).
    """
    nodes = graph["nodes"]
    links = graph["links"]
    w, h = graph["width"], graph["height"]

    defs: List[str] = []
    paths: List[str] = []
    for i, lk in enumerate(links):
        fc = lk.get("flow_color", "gradient")
        opacity = "0.55"
        if fc == "gradient":
            fill = f"url(#sgrad-{i})"
            defs.append(
                f'<linearGradient id="sgrad-{i}" gradientUnits="objectBoundingBox" '
                f'x1="0" y1="0" x2="0" y2="1">'
                f'<stop offset="0%" stop-color="{escape(lk["source"]["color"])}"/>'
                f'<stop offset="100%" stop-color="{escape(lk["target"]["color"])}"/>'
                f"</linearGradient>"
            )
        elif fc == "source":
            fill = lk["source"]["color"]
        elif fc == "target":
            fill = lk["target"]["color"]
        else:
            fill = fc
            opacity = "0.85"
        paths.append(
            f'<path d="{link_path(lk)}" fill="{escape(fill)}" fill-opacity="{opacity}"/>'
        )

    rects: List[str] = []
    labels: List[str] = []
    for n in nodes:
        bar_w = n["x1"] - n["x0"]
        rects.append(
            f'<rect x="{n["x0"]:.2f}" y="{n["y0"]:.2f}" width="{bar_w:.2f}" '
            f'height="{(n["y1"] - n["y0"]):.2f}" fill="{escape(n["color"])}" '
            f'stroke="rgba(0,0,0,0.15)" stroke-width="1"/>'
        )
        cx = (n["x0"] + n["x1"]) / 2
        cy = (n["y0"] + n["y1"]) / 2
        lines = str(n["name"]).split("\n")
        if bar_w > 110:
            lines = lines + [_fmt_value(n["value"], value_unit, locale)]
        spans = []
        line_height = 1.1
        for j, line in enumerate(lines):
            dy = f"{-(len(lines) - 1) * line_height / 2:.2f}em" if j == 0 else f"{line_height}em"
            size_attr = ' font-size="8.5"' if j and j == len(lines) - 1 and bar_w > 110 else ""
            spans.append(f'<tspan x="{cx:.2f}" dy="{dy}"{size_attr}>{escape(line)}</tspan>')
        labels.append(
            f'<text x="{cx:.2f}" y="{cy:.2f}" text-anchor="middle" '
            f'dominant-baseline="central" font-size="10" fill="#ffffff" '
            f'font-family="system-ui, sans-serif">{"".join(spans)}</text>'
        )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
        f'width="100%" style="background:{escape(background)};display:block;">'
        f"<defs>{''.join(defs)}</defs>"
        f"<g>{''.join(paths)}</g><g>{''.join(rects)}</g><g>{''.join(labels)}</g>"
        f"</svg>"
    )


_THEMES = {
    "light": {
        "bg": "#f6f7f9",
        "svg_bg": "#fff",
        "svg_shadow": "0 1px 4px rgba(0,0,0,.08)",
        "svg_radius": "8px",
        "label": "#222",
        "node_label": "#222",
        "node_stroke": "rgba(0,0,0,.15)",
        "node_highlight_stroke": "#333",
        "link_opacity": "0.45",
        "link_dim": "0.08",
        "link_highlight": "0.75",
        "font": "system-ui, -apple-system, Segoe UI, Roboto, sans-serif",
    },
    "dark": {
        "bg": "#0d0f12",
        "svg_bg": "#0d0f12",
        "svg_shadow": "none",
        "svg_radius": "0",
        "label": "#7a8a9e",
        "node_label": "#ffffff",
        "node_stroke": "rgba(0,0,0,0)",
        "node_highlight_stroke": "rgba(215, 220, 225, 0.55)",
        "link_opacity": "0.38",
        "link_dim": "0.05",
        "link_highlight": "0.72",
        "font": "'IBM Plex Mono', monospace",
    },
}

_I18N = {
    "en": {
        "total": "Total",
        "incoming": "Incoming",
        "outgoing": "Outgoing",
    },
    "de": {
        "total": "Gesamt",
        "incoming": "Eingehende Kosten",
        "outgoing": "Ausgehende Kosten",
    },
}


def render_html(
    graph: Dict[str, Any],
    title: str = "Cost flow",
    theme: str = "light",
    embed: bool = False,
    value_unit: str = "",
    transparent: bool = False,
    locale: str = "en",
    fit_container: bool = False,
) -> str:
    nodes = graph["nodes"]
    links = graph["links"]
    w = graph["width"]
    h = graph["height"]
    margin_top = float(graph.get("margin_top", 48))
    th = dict(_THEMES.get(theme, _THEMES["light"]))
    if transparent or embed:
        th["bg"] = "transparent"
        th["svg_bg"] = "transparent"
        th["svg_shadow"] = "none"
    unit = value_unit.replace("\\", "").replace("'", "")
    node_label_fill = th.get("node_label", th["label"])
    i18n = _I18N.get(locale, _I18N["en"])
    fit = fit_container or embed

    node_payload = []
    for n in nodes:
        node_payload.append(
            {
                "id": n["id"],
                "name": n["name"],
                "layer": n["layer"],
                "color": n["color"],
                "x0": n["x0"],
                "x1": n["x1"],
                "y0": n["y0"],
                "y1": n["y1"],
                "value": n["value"],
            }
        )

    link_payload = []
    for i, lk in enumerate(links):
        src = lk["source"]
        tgt = lk["target"]
        fc = lk.get("flow_color", "gradient")
        is_gradient = fc == "gradient"
        custom = False
        if fc == "source":
            fill = src["color"]
        elif fc == "target":
            fill = tgt["color"]
        elif is_gradient:
            fill = f"url(#grad-{i})"
        else:
            fill = fc
            custom = True
        link_payload.append(
            {
                "index": i,
                "path": link_path(lk),
                "fill": fill,
                "gradient": is_gradient,
                "custom": custom,
                "label": lk.get("label", ""),
                "value": lk["value"],
                "sourceId": src["id"],
                "targetId": tgt["id"],
                "sourceName": src["name"],
                "targetName": tgt["name"],
            }
        )

    data_json = json.dumps({"nodes": node_payload, "links": link_payload})

    gradients = []
    for i, lk in enumerate(links):
        if lk.get("flow_color", "gradient") == "gradient":
            src = lk["source"]
            tgt = lk["target"]
            gradients.append(
                f'<linearGradient id="grad-{i}" gradientUnits="objectBoundingBox" '
                f'x1="0" y1="0" x2="0" y2="1">'
                f'<stop offset="0%" stop-color="{escape(src["color"])}"/>'
                f'<stop offset="100%" stop-color="{escape(tgt["color"])}"/>'
                f"</linearGradient>"
            )

    header_html = ""
    if title and not embed:
        header_html = f"<header>{escape(title)}</header>"
    wrap_pad = "0" if embed else "16px"
    fit_css = ""
    svg_fit_attrs = f'width="{w}" height="{h}"'
    streamlit_resize_js = ""
    if fit:
        fit_css = """
  html, body {
    margin: 0;
    overflow: hidden;
  }
  #wrap {
    width: 100%;
    padding: 0;
    line-height: 0;
  }
"""
        svg_fit_attrs = f'viewBox="0 0 {w} {h}" width="100%" height="auto"'
        streamlit_resize_js = ""
    else:
        svg_fit_attrs = f'width="{w}" height="{h}" viewBox="0 0 {w} {h}"'

    return f"""<!DOCTYPE html>
<html lang="{escape(locale)}">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{escape(title or "Sankey")}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    font-family: {th["font"]};
    background: {th["bg"]};
    color: {th["label"]};
  }}
  header {{
    padding: 12px 20px;
    background: #fff;
    border-bottom: 1px solid #e2e4e8;
    font-weight: 600;
  }}
  #wrap {{
    padding: {wrap_pad};
    overflow: hidden;
  }}
{fit_css}
  svg {{
    display: block;
    width: 100%;
    height: auto;
    background: {th["svg_bg"]};
    border-radius: {th["svg_radius"]};
    box-shadow: {th["svg_shadow"]};
  }}
  .link {{
    fill-opacity: {th["link_opacity"]};
    stroke: none;
    cursor: pointer;
    transition: fill-opacity 0.15s, opacity 0.15s;
  }}
  .link.gradient {{ fill-opacity: 0.58; }}
  .link.custom {{ fill-opacity: 1; }}
  .link.dim {{ fill-opacity: {th["link_dim"]}; }}
  .link.dim.gradient {{ fill-opacity: 0.12; }}
  .link.dim.custom {{ opacity: 0.2; fill-opacity: 1; }}
  .link.highlight {{ fill-opacity: {th["link_highlight"]}; }}
  .link.highlight.gradient {{ fill-opacity: 0.78; }}
  .link.highlight.custom {{ opacity: 1; fill-opacity: 1; }}
  .node {{
    cursor: pointer;
    stroke: {th["node_stroke"]};
    stroke-width: 1;
    transition: opacity 0.15s;
  }}
  .node.dim {{ opacity: 0.4; }}
  .node.highlight {{ opacity: 1; stroke: {th["node_highlight_stroke"]}; stroke-width: 1.25; }}
  .node-label {{
    font-size: 10px;
    fill: {th.get("node_label", th["label"])};
    pointer-events: none;
    user-select: none;
  }}
  #tooltip {{
    position: fixed;
    pointer-events: none;
    background: rgba(20, 24, 32, 0.94);
    color: #f4f6fa;
    padding: 10px 12px;
    border-radius: 6px;
    font-size: 13px;
    line-height: 1.45;
    max-width: 280px;
    box-shadow: 0 4px 16px rgba(0,0,0,.2);
    opacity: 0;
    transition: opacity 0.12s;
    z-index: 1000;
  }}
  #tooltip.visible {{ opacity: 1; }}
  #tooltip .title {{ font-weight: 600; margin-bottom: 4px; }}
  #tooltip .row {{ color: #c8d0dc; }}
  #tooltip .num {{ color: #fff; font-variant-numeric: tabular-nums; }}
</style>
</head>
<body>
{header_html}
<div id="wrap">
<svg id="chart" {svg_fit_attrs}>
<defs>
{"".join(gradients)}
</defs>
<g id="links"></g>
<g id="nodes"></g>
<g id="labels"></g>
</svg>
</div>
<div id="tooltip"></div>
<script>
const DATA = {data_json};
const svg = document.getElementById('chart');
const gLinks = document.getElementById('links');
const gNodes = document.getElementById('nodes');
const gLabels = document.getElementById('labels');
const tip = document.getElementById('tooltip');

const VALUE_UNIT = {json.dumps(unit)};
const NODE_LABEL_FILL = {json.dumps(node_label_fill)};
const I18N = {json.dumps(i18n)};

function fmt(n) {{
  const s = Number(n).toLocaleString(undefined, {{ maximumFractionDigits: 2 }});
  return VALUE_UNIT ? s + ' ' + VALUE_UNIT : s;
}}

function showTip(html, x, y) {{
  tip.innerHTML = html;
  tip.classList.add('visible');
  const pad = 12;
  const rect = tip.getBoundingClientRect();
  let left = x + pad;
  let top = y + pad;
  if (left + rect.width > window.innerWidth - 8) left = x - rect.width - pad;
  if (top + rect.height > window.innerHeight - 8) top = y - rect.height - pad;
  tip.style.left = left + 'px';
  tip.style.top = top + 'px';
}}

function hideTip() {{
  tip.classList.remove('visible');
}}

function clearHighlight() {{
  gLinks.querySelectorAll('.link').forEach(el => {{
    el.classList.remove('dim', 'highlight');
  }});
  gNodes.querySelectorAll('.node').forEach(el => {{
    el.classList.remove('dim', 'highlight');
  }});
}}

function highlightNode(nodeId) {{
  const connected = new Set();
  DATA.links.forEach(lk => {{
    if (lk.sourceId === nodeId || lk.targetId === nodeId) {{
      connected.add(lk.index);
    }}
  }});
  gLinks.querySelectorAll('.link').forEach(el => {{
    const i = +el.dataset.index;
    if (connected.has(i)) el.classList.add('highlight');
    else el.classList.add('dim');
  }});
  gNodes.querySelectorAll('.node').forEach(el => {{
    if (el.dataset.id === nodeId) el.classList.add('highlight');
    else el.classList.add('dim');
  }});
}}

function highlightLink(index) {{
  gLinks.querySelectorAll('.link').forEach(el => {{
    if (+el.dataset.index === index) el.classList.add('highlight');
    else el.classList.add('dim');
  }});
  gNodes.querySelectorAll('.node').forEach(el => el.classList.add('dim'));
}}

DATA.links.forEach(lk => {{
  const p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  p.setAttribute('d', lk.path);
  p.setAttribute('fill', lk.fill);
  p.classList.add('link');
  if (lk.gradient) p.classList.add('gradient');
  if (lk.custom) p.classList.add('custom');
  p.dataset.index = lk.index;
  p.addEventListener('mouseenter', e => {{
    highlightLink(lk.index);
    const label = lk.label ? lk.label + '<br/>' : '';
    showTip(
      '<div class="title">' + lk.sourceName + ' → ' + lk.targetName + '</div>' +
      label +
      '<div class="row"><span class="num">' + fmt(lk.value) + '</span></div>',
      e.clientX, e.clientY
    );
  }});
  p.addEventListener('mousemove', e => {{
    const label = lk.label ? lk.label + '<br/>' : '';
    showTip(
      '<div class="title">' + lk.sourceName + ' → ' + lk.targetName + '</div>' +
      label +
      '<div class="row"><span class="num">' + fmt(lk.value) + '</span></div>',
      e.clientX, e.clientY
    );
  }});
  p.addEventListener('mouseleave', () => {{ clearHighlight(); hideTip(); }});
  gLinks.appendChild(p);
}});

DATA.nodes.forEach(n => {{
  const r = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
  r.setAttribute('x', n.x0);
  r.setAttribute('y', n.y0);
  r.setAttribute('width', n.x1 - n.x0);
  r.setAttribute('height', n.y1 - n.y0);
  r.setAttribute('fill', n.color);
  r.classList.add('node');
  r.dataset.id = n.id;

  const incoming = DATA.links.filter(lk => lk.targetId === n.id);
  const outgoing = DATA.links.filter(lk => lk.sourceId === n.id);

  r.addEventListener('mouseenter', e => {{
    highlightNode(n.id);
    let rows = '<div class="title">' + n.name + '</div>';
    rows += '<div class="row">' + I18N.total + ': <span class="num">' + fmt(n.value) + '</span></div>';
    if (incoming.length) {{
      rows += '<div class="row" style="margin-top:6px">' + I18N.incoming + ':</div>';
      incoming.forEach(lk => {{
        const lbl = lk.label ? ' (' + lk.label + ')' : '';
        rows += '<div class="row">· ' + lk.sourceName + lbl + ': <span class="num">' + fmt(lk.value) + '</span></div>';
      }});
    }}
    if (outgoing.length) {{
      rows += '<div class="row" style="margin-top:6px">' + I18N.outgoing + ':</div>';
      outgoing.forEach(lk => {{
        const lbl = lk.label ? ' (' + lk.label + ')' : '';
        rows += '<div class="row">· ' + lk.targetName + lbl + ': <span class="num">' + fmt(lk.value) + '</span></div>';
      }});
    }}
    showTip(rows, e.clientX, e.clientY);
  }});
  r.addEventListener('mousemove', e => {{
    let rows = '<div class="title">' + n.name + '</div>';
    rows += '<div class="row">' + I18N.total + ': <span class="num">' + fmt(n.value) + '</span></div>';
    if (incoming.length) {{
      rows += '<div class="row" style="margin-top:6px">' + I18N.incoming + ':</div>';
      incoming.forEach(lk => {{
        const lbl = lk.label ? ' (' + lk.label + ')' : '';
        rows += '<div class="row">· ' + lk.sourceName + lbl + ': <span class="num">' + fmt(lk.value) + '</span></div>';
      }});
    }}
    if (outgoing.length) {{
      rows += '<div class="row" style="margin-top:6px">' + I18N.outgoing + ':</div>';
      outgoing.forEach(lk => {{
        const lbl = lk.label ? ' (' + lk.label + ')' : '';
        rows += '<div class="row">· ' + lk.targetName + lbl + ': <span class="num">' + fmt(lk.value) + '</span></div>';
      }});
    }}
    showTip(rows, e.clientX, e.clientY);
  }});
  r.addEventListener('mouseleave', () => {{ clearHighlight(); hideTip(); }});
  gNodes.appendChild(r);

  const nodeWidth = n.x1 - n.x0;
  const cx = (n.x0 + n.x1) / 2;
  const cy = (n.y0 + n.y1) / 2;
  const lines = (n.name || '').split('\\n');
  const t = document.createElementNS('http://www.w3.org/2000/svg', 'text');
  t.setAttribute('x', cx);
  t.setAttribute('y', cy);
  t.setAttribute('text-anchor', 'middle');
  t.setAttribute('dominant-baseline', 'central');
  t.classList.add('node-label');
  t.setAttribute('fill', NODE_LABEL_FILL);
  const lineHeight = 1.1;
  lines.forEach((line, i) => {{
    const sp = document.createElementNS('http://www.w3.org/2000/svg', 'tspan');
    sp.setAttribute('x', cx);
    const dy = i === 0
      ? (-(lines.length - 1) * lineHeight / 2) + 'em'
      : lineHeight + 'em';
    sp.setAttribute('dy', dy);
    sp.setAttribute('fill', NODE_LABEL_FILL);
    sp.textContent = line;
    t.appendChild(sp);
  }});
  t.dataset.maxLabelW = nodeWidth - 8;
  gLabels.appendChild(t);
}});

document.fonts.ready.then(() => {{
  gLabels.querySelectorAll('text').forEach(t => {{
    const maxLabelW = +t.dataset.maxLabelW;
    if (!(maxLabelW > 0)) return;
    t.querySelectorAll('tspan').forEach(sp => {{
      if (sp.getComputedTextLength() <= maxLabelW) return;
      let txt = sp.textContent;
      do {{
        txt = txt.slice(0, -1);
        sp.textContent = txt + '…';
      }} while (txt.length > 0 && sp.getComputedTextLength() > maxLabelW);
    }});
  }});
}});

svg.addEventListener('mouseleave', () => {{ clearHighlight(); hideTip(); }});
{streamlit_resize_js}
</script>
</body>
</html>"""
