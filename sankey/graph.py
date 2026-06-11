"""Build a Sankey graph from flow records and node styling."""

from typing import Any, Callable, Dict, List, Optional

from .layout import Sankey
from .orient import orient_vertical

FlowRecord = Dict[str, Any]
NodeStyle = Dict[str, Any]


def build_graph(
    flows: List[FlowRecord],
    node_styles: Optional[Dict[str, NodeStyle]] = None,
    default_node_color: str = "#888888",
    default_flow_color: str = "gradient",
    default_padding: float = 8,
) -> Dict[str, Any]:
    """
    Each flow: source, layer, target, label, weight.
    Optional: target_layer (default source layer + 1) to skip intermediate rows.
    Optional per-flow: flow_color in {source, target, gradient} or a CSS color.
    node_styles keyed by node name: color, padding.
    """
    node_styles = node_styles or {}
    nodes_by_key: Dict[tuple, Dict[str, Any]] = {}
    links: List[Dict[str, Any]] = []

    def get_node(name: str, layer: int) -> Dict[str, Any]:
        key = (name, layer)
        if key not in nodes_by_key:
            style = node_styles.get(name, {})
            nodes_by_key[key] = {
                "id": f"{name}@{layer}",
                "name": name,
                "layer": layer,
                "color": style.get("color", default_node_color),
                "padding": style.get("padding", default_padding),
            }
        return nodes_by_key[key]

    for i, row in enumerate(flows):
        source_name = str(row["source"])
        target_name = str(row["target"])
        layer = int(row["layer"])
        weight = float(row["weight"])
        label = str(row.get("label", ""))
        flow_color = row.get("flow_color", default_flow_color)
        if isinstance(flow_color, str):
            fc_lower = flow_color.lower()
            if fc_lower in ("source", "target", "gradient"):
                flow_color = fc_lower
            # else: literal CSS color (e.g. rgba(...))
        else:
            flow_color = default_flow_color

        source = get_node(source_name, layer)
        tgt_layer = row.get("target_layer")
        if tgt_layer is not None:
            target = get_node(target_name, int(tgt_layer))
        else:
            target = get_node(target_name, layer + 1)

        links.append(
            {
                "source": source["id"],
                "target": target["id"],
                "value": weight,
                "label": label,
                "flow_color": flow_color,
                "index": i,
            }
        )

    nodes = list(nodes_by_key.values())
    return {"nodes": nodes, "links": links}


def tighten_split_layer(
    graph: Dict[str, Any],
    parent_layer: int,
    child_layer: int,
    parent_to_children: Dict[str, List[str]],
    gap: float = 0,
    sibling_gap: float = 0,
    group_gap: float = 0,
) -> Dict[str, Any]:
    """
    Place child_layer nodes flush below parent_layer (no vertical gap), with each
    parent's children stacked horizontally starting at the parent's left edge
    (no padding between siblings). The parent row visually splits into its
    children below. Links touching either layer have their x positions
    recomputed from the new node positions.
    sibling_gap: extra horizontal space inserted between siblings within one parent.
    group_gap: minimum horizontal space enforced between consecutive parent groups.
    """
    parent_nodes = {n["name"]: n for n in graph["nodes"] if n["layer"] == parent_layer}
    child_nodes = {n["name"]: n for n in graph["nodes"] if n["layer"] == child_layer}
    if not parent_nodes or not child_nodes:
        return graph

    sample_child = next(iter(child_nodes.values()))
    row_thickness = sample_child["y1"] - sample_child["y0"]

    # Process parents left-to-right so group_gap is applied in the right direction.
    ordered = sorted(
        [(n, ch) for n, ch in parent_to_children.items() if n in parent_nodes],
        key=lambda item: parent_nodes[item[0]]["x0"],
    )
    prev_group_end: Optional[float] = None
    for parent_name, child_names in ordered:
        parent = parent_nodes[parent_name]
        # Anchor to THIS parent's bottom edge — other nodes in the parent layer
        # may sit at a different height (e.g. already tightened under their own
        # parent), so a layer-wide sample would misplace the children.
        parent_y1 = parent["y1"]
        group_start = parent["x0"]
        if prev_group_end is not None and group_gap > 0:
            group_start = max(group_start, prev_group_end + group_gap)
        cursor_x = group_start
        for j, child_name in enumerate(child_names):
            child = child_nodes.get(child_name)
            if child is None:
                continue
            child_width = child["x1"] - child["x0"]
            child["x0"] = cursor_x
            child["x1"] = cursor_x + child_width
            child["y0"] = parent_y1 + gap
            child["y1"] = parent_y1 + gap + row_thickness
            cursor_x += child_width
            if sibling_gap and j < len(child_names) - 1:
                cursor_x += sibling_gap
        prev_group_end = cursor_x

    for node in graph["nodes"]:
        x = node["x0"]
        for link in node.get("sourceLinks", []):
            link["x0"] = x + link["width"] / 2
            x += link["width"]
        x = node["x0"]
        for link in node.get("targetLinks", []):
            link["x1"] = x + link["width"] / 2
            x += link["width"]

    return graph


def tighten_merge_layer(
    graph: Dict[str, Any],
    parent_layer: int,
    child_layer: int,
    child_to_parents: Dict[str, List[str]],
) -> Dict[str, Any]:
    """
    Inverse of tighten_split_layer: multiple parents in parent_layer collapse
    into a single child in child_layer flush below (no vertical gap), with the
    named parents stacked horizontally with no padding between them. The child
    is placed directly below at the combined horizontal range of its parents.
    Parents not listed are left untouched.
    """
    parent_nodes = {n["name"]: n for n in graph["nodes"] if n["layer"] == parent_layer}
    child_nodes = {n["name"]: n for n in graph["nodes"] if n["layer"] == child_layer}
    if not parent_nodes or not child_nodes:
        return graph

    sample_parent = next(iter(parent_nodes.values()))
    parent_y1 = sample_parent["y1"]
    sample_child = next(iter(child_nodes.values()))
    row_thickness = sample_child["y1"] - sample_child["y0"]

    for child_name, parent_names in child_to_parents.items():
        existing = [parent_nodes[p] for p in parent_names if p in parent_nodes]
        if not existing:
            continue
        start_x = min(p["x0"] for p in existing)
        cursor_x = start_x
        for parent_name in parent_names:
            parent = parent_nodes.get(parent_name)
            if parent is None:
                continue
            parent_width = parent["x1"] - parent["x0"]
            parent["x0"] = cursor_x
            parent["x1"] = cursor_x + parent_width
            cursor_x += parent_width
        child = child_nodes.get(child_name)
        if child is not None:
            child["x0"] = start_x
            child["x1"] = cursor_x
            child["y0"] = parent_y1
            child["y1"] = parent_y1 + row_thickness

    for node in graph["nodes"]:
        x = node["x0"]
        for link in node.get("sourceLinks", []):
            link["x0"] = x + link["width"] / 2
            x += link["width"]
        x = node["x0"]
        for link in node.get("targetLinks", []):
            link["x1"] = x + link["width"] / 2
            x += link["width"]

    return graph


def _reflow_node_links(node: Dict[str, Any]) -> None:
    """Recompute link x offsets from the node's left edge."""
    x = node["x0"]
    for link in node.get("sourceLinks", []):
        link["x0"] = x + link["width"] / 2
        x += link["width"]
    x = node["x0"]
    for link in node.get("targetLinks", []):
        link["x1"] = x + link["width"] / 2
        x += link["width"]


def place_node_after(
    graph: Dict[str, Any],
    layer: int,
    node_name: str,
    after_name: str,
    gap: float,
) -> Dict[str, Any]:
    """Move a node so it sits `gap` to the right of another node in the same layer."""
    by_name = {n["name"]: n for n in graph["nodes"] if n["layer"] == layer}
    node = by_name.get(node_name)
    anchor = by_name.get(after_name)
    if node is None or anchor is None:
        return graph
    width = node["x1"] - node["x0"]
    node["x0"] = anchor["x1"] + gap
    node["x1"] = node["x0"] + width
    _reflow_node_links(node)
    return graph


def resort_links_by_position(graph: Dict[str, Any]) -> Dict[str, Any]:
    """Re-sort each node's ribbons by the other end's x position to minimize crossings."""
    for node in graph["nodes"]:
        node["sourceLinks"].sort(key=lambda lk: lk["target"]["x0"])
        x = node["x0"]
        for link in node["sourceLinks"]:
            link["x0"] = x + link["width"] / 2
            x += link["width"]
    for node in graph["nodes"]:
        node["targetLinks"].sort(key=lambda lk: lk["source"]["x0"])
        x = node["x0"]
        for link in node["targetLinks"]:
            link["x1"] = x + link["width"] / 2
            x += link["width"]
    return graph


def layout_graph(
    graph: Dict[str, Any],
    width: float = 960,
    height: float = 500,
    node_width: float = 18,
    node_padding: float = 8,
    margin_top: float = 48,
    margin_bottom: float = 24,
    node_sort_key: Optional[Callable[[Dict[str, Any]], Any]] = None,
) -> Dict[str, Any]:
    id_map = {n["id"]: n for n in graph["nodes"]}
    resolved_links = [
        {**link, "source": id_map[link["source"]], "target": id_map[link["target"]]}
        for link in graph["links"]
    ]

    # Layout horizontally (layers on x), then transpose for top-to-bottom flow.
    # margin_top on the layer axis becomes vertical space above the first row (for labels).
    layout = (
        Sankey()
        .extent(margin_top, 0, height + margin_bottom, width)
        .node_width(node_width)
        .node_padding(node_padding)
        .node_align("justify")
        .node_id(lambda d, *_: d["id"])
    )
    if node_sort_key is not None:
        layout.node_sort(node_sort_key)
    layout({"nodes": graph["nodes"], "links": resolved_links})
    orient_vertical({"nodes": graph["nodes"], "links": resolved_links})
    graph["links"] = resolved_links
    graph["width"] = width
    graph["height"] = height + margin_bottom
    graph["layout_height"] = height
    graph["margin_top"] = margin_top
    graph["margin_bottom"] = margin_bottom
    return graph
