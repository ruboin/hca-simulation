"""Rotate horizontal Sankey layout to vertical (top-to-bottom flow)."""


def orient_vertical(graph):
    """
    After horizontal layout: layers on x, node breadth on y.
    Transpose so layers are on y (top = low layer) and breadth on x.
    """
    nodes = graph["nodes"]
    links = graph["links"]

    for node in nodes:
        x0, y0, x1, y1 = node["x0"], node["y0"], node["x1"], node["y1"]
        node["x0"], node["y0"], node["x1"], node["y1"] = y0, x0, y1, x1

    for link in links:
        link["x0"] = link["y0"]
        link["x1"] = link["y1"]

    return graph
