"""Generic Sankey engine: graph building, d3-style layout, HTML/SVG rendering.

Domain logic (Heizkostenabrechnung) lives in ``sankey.heizkosten`` and is
imported from there directly — this package exports only the engine.
"""

from .graph import (
    build_graph,
    layout_graph,
    place_node_after,
    resort_links_by_position,
    tighten_merge_layer,
    tighten_split_layer,
)
from .render import render_html, render_static_svg

__all__ = [
    "build_graph",
    "layout_graph",
    "place_node_after",
    "resort_links_by_position",
    "tighten_merge_layer",
    "tighten_split_layer",
    "render_html",
    "render_static_svg",
]
