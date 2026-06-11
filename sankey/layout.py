"""
Sankey layout (ported from d3-sankey, MIT license).
Computes node columns, vertical positions, and link ribbons.
"""

from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

Graph = Dict[str, Any]
Node = Dict[str, Any]
Link = Dict[str, Any]


def _sum(values: Sequence[float]) -> float:
    return sum(values)


def _max(iterable: Sequence[Any], key: Callable[[Any], float]) -> float:
    return max(key(x) for x in iterable) if iterable else 0


def _min(iterable: Sequence[Any], key: Callable[[Any], float]) -> float:
    return min(key(x) for x in iterable) if iterable else 0


def justify(node: Node, n: int) -> int:
    """Place sink nodes in the last column."""
    return node["depth"] if node.get("sourceLinks") else n - 1


def _value(link: Link) -> float:
    return link["value"]


def _ascending_breadth(a: Node, b: Node) -> int:
    if a["y0"] != b["y0"]:
        return -1 if a["y0"] < b["y0"] else 1
    return 0


def _link_sort_source(lk: Link) -> tuple:
    s = lk["source"]
    return (s.get("y0", 0), lk["index"])


def _link_sort_target(lk: Link) -> tuple:
    t = lk["target"]
    return (t.get("y0", 0), lk["index"])


class Sankey:
    def __init__(self) -> None:
        self.x0 = 0.0
        self.y0 = 0.0
        self.x1 = 1.0
        self.y1 = 1.0
        self.dx = 24.0
        self.dy = 8.0
        self.py: Optional[float] = None
        self.id_fn: Callable[[Node, int, List[Node]], Any] = lambda d, i, _: i
        self.align_fn: Callable[[Node, int], int] = justify
        self.sort_key: Optional[Callable[[Node], Any]] = None
        self.link_sort: Optional[Callable[[Link, Link], int]] = None
        self.iterations = 6

    def extent(self, x0: float, y0: float, x1: float, y1: float) -> "Sankey":
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1
        return self

    def size(self, width: float, height: float) -> "Sankey":
        return self.extent(0, 0, width, height)

    def node_width(self, dx: float) -> "Sankey":
        self.dx = float(dx)
        return self

    def node_padding(self, dy: float) -> "Sankey":
        self.dy = self.py = float(dy)
        return self

    def node_id(self, fn: Callable[[Node, int, List[Node]], Any]) -> "Sankey":
        self.id_fn = fn
        return self

    def node_sort(self, key: Callable[[Node], Any]) -> "Sankey":
        """Sort nodes within each column by key (e.g. fixed name order)."""
        self.sort_key = key
        return self

    def node_align(self, align: Union[str, Callable[[Node, int], int]]) -> "Sankey":
        if align == "justify":
            self.align_fn = justify
        elif align == "left":
            self.align_fn = lambda n, _: n["depth"]
        elif align == "right":
            self.align_fn = lambda n, _: n["height"]
        elif callable(align):
            self.align_fn = align
        else:
            raise ValueError(f"unknown align: {align}")
        return self

    def iterations(self, n: int) -> "Sankey":
        self.iterations = int(n)
        return self

    def __call__(self, graph: Graph) -> Graph:
        nodes = graph["nodes"]
        links = graph["links"]
        self._compute_node_links(nodes, links)
        self._compute_node_values(nodes)
        self._compute_node_depths(nodes)
        self._compute_node_heights(nodes)
        self._compute_node_breadths(nodes)
        self._compute_link_breadths(nodes)
        return graph

    def update(self, graph: Graph) -> Graph:
        self._compute_link_breadths(graph["nodes"])
        return graph

    def _compute_node_links(self, nodes: List[Node], links: List[Link]) -> None:
        for i, node in enumerate(nodes):
            node["index"] = i
            node["sourceLinks"] = []
            node["targetLinks"] = []

        node_by_id = {self.id_fn(d, i, nodes): d for i, d in enumerate(nodes)}

        for i, link in enumerate(links):
            link["index"] = i
            source = link["source"]
            target = link["target"]
            if not isinstance(source, dict):
                source = link["source"] = node_by_id[source]
            if not isinstance(target, dict):
                target = link["target"] = node_by_id[target]
            source["sourceLinks"].append(link)
            target["targetLinks"].append(link)

        if self.link_sort is not None:
            for node in nodes:
                node["sourceLinks"].sort(key=self.link_sort)
                node["targetLinks"].sort(key=self.link_sort)

    def _compute_node_values(self, nodes: List[Node]) -> None:
        for node in nodes:
            if "fixedValue" in node and node["fixedValue"] is not None:
                node["value"] = node["fixedValue"]
            else:
                out_v = _sum(l["value"] for l in node["sourceLinks"])
                in_v = _sum(l["value"] for l in node["targetLinks"])
                node["value"] = max(out_v, in_v)

    def _compute_node_depths(self, nodes: List[Node]) -> None:
        n = len(nodes)
        current = list(nodes)
        seen = set()
        x = 0
        while current:
            next_list = []
            for node in current:
                node["depth"] = x
                for link in node["sourceLinks"]:
                    tgt = link["target"]
                    tid = id(tgt)
                    if tid not in seen:
                        seen.add(tid)
                        next_list.append(tgt)
            x += 1
            if x > n:
                raise ValueError("circular link")
            current = next_list

    def _compute_node_heights(self, nodes: List[Node]) -> None:
        n = len(nodes)
        current = list(nodes)
        seen = set()
        x = 0
        while current:
            next_list = []
            for node in current:
                node["height"] = x
                for link in node["targetLinks"]:
                    src = link["source"]
                    sid = id(src)
                    if sid not in seen:
                        seen.add(sid)
                        next_list.append(src)
            x += 1
            if x > n:
                raise ValueError("circular link")
            current = next_list

    def _compute_node_layers(self, nodes: List[Node]) -> List[List[Node]]:
        if any("layer" in n and n["layer"] is not None for n in nodes):
            x = int(max(n.get("layer", 0) for n in nodes)) + 1
        else:
            x = int(_max(nodes, lambda d: d["depth"])) + 1

        kx = (self.x1 - self.x0 - self.dx) / max(x - 1, 1)
        columns: List[List[Node]] = [[] for _ in range(x)]

        for node in nodes:
            if "layer" in node and node["layer"] is not None:
                i = int(node["layer"])
            else:
                i = max(0, min(x - 1, int(self.align_fn(node, x))))
            node["layer"] = i
            node["x0"] = self.x0 + i * kx
            node["x1"] = node["x0"] + self.dx
            columns[i].append(node)

        if self.sort_key is not None:
            for column in columns:
                column.sort(key=self.sort_key)

        return columns

    def _initialize_node_breadths(self, columns: List[List[Node]]) -> None:
        def col_sum(c: List[Node]) -> float:
            return _sum(n["value"] for n in c)

        ky = _min(
            columns,
            lambda c: (self.y1 - self.y0 - (len(c) - 1) * (self.py or 0)) / col_sum(c)
            if c and col_sum(c) > 0
            else float("inf"),
        )

        for nodes in columns:
            y = self.y0
            for node in nodes:
                pad = node.get("padding", self.dy)
                node["padding"] = pad
                node["y0"] = y
                node["y1"] = y + node["value"] * ky
                y = node["y1"] + pad
                for link in node["sourceLinks"]:
                    link["width"] = link["value"] * ky

            slack = (self.y1 - y + (self.py or 0)) / (len(nodes) + 1)
            for i, node in enumerate(nodes):
                node["y0"] += slack * (i + 1)
                node["y1"] += slack * (i + 1)

            self._reorder_links(nodes)

    def _compute_node_breadths(self, nodes: List[Node]) -> None:
        columns = self._compute_node_layers(nodes)
        max_len = _max(columns, lambda c: len(c))
        self.py = min(self.dy, (self.y1 - self.y0) / max(max_len - 1, 1))

        self._initialize_node_breadths(columns)

        for i in range(self.iterations):
            alpha = 0.99**i
            beta = max(1 - alpha, (i + 1) / self.iterations)
            self._relax_right_to_left(columns, alpha, beta)
            self._relax_left_to_right(columns, alpha, beta)

    def _relax_left_to_right(
        self, columns: List[List[Node]], alpha: float, beta: float
    ) -> None:
        for i in range(1, len(columns)):
            column = columns[i]
            for target in column:
                y = 0.0
                w = 0.0
                for link in target["targetLinks"]:
                    source = link["source"]
                    v = link["value"] * (target["layer"] - source["layer"])
                    y += self._target_top(source, target) * v
                    w += v
                if w <= 0:
                    continue
                dy = (y / w - target["y0"]) * alpha
                target["y0"] += dy
                target["y1"] += dy
                self._reorder_node_links(target)

            if self.sort_key is None:
                column.sort(key=lambda n: n["y0"])
            self._resolve_collisions(column, beta)

    def _relax_right_to_left(
        self, columns: List[List[Node]], alpha: float, beta: float
    ) -> None:
        for i in range(len(columns) - 2, -1, -1):
            column = columns[i]
            for source in column:
                y = 0.0
                w = 0.0
                for link in source["sourceLinks"]:
                    target = link["target"]
                    v = link["value"] * (target["layer"] - source["layer"])
                    y += self._source_top(source, target) * v
                    w += v
                if w <= 0:
                    continue
                dy = (y / w - source["y0"]) * alpha
                source["y0"] += dy
                source["y1"] += dy
                self._reorder_node_links(source)

            if self.sort_key is None:
                column.sort(key=lambda n: n["y0"])
            self._resolve_collisions(column, beta)

    def _resolve_collisions(self, nodes: List[Node], alpha: float) -> None:
        if not nodes:
            return
        i = len(nodes) >> 1
        subject = nodes[i]
        py = self.py or 0
        self._resolve_collisions_bottom_to_top(nodes, subject["y0"] - py, i - 1, alpha)
        self._resolve_collisions_top_to_bottom(nodes, subject["y1"] + py, i + 1, alpha)
        self._resolve_collisions_bottom_to_top(nodes, self.y1, len(nodes) - 1, alpha)
        self._resolve_collisions_top_to_bottom(nodes, self.y0, 0, alpha)

    def _resolve_collisions_top_to_bottom(
        self, nodes: List[Node], y: float, i: int, alpha: float
    ) -> None:
        py = self.py or 0
        while i < len(nodes):
            node = nodes[i]
            dy = (y - node["y0"]) * alpha
            if dy > 1e-6:
                node["y0"] += dy
                node["y1"] += dy
            y = node["y1"] + py
            i += 1

    def _resolve_collisions_bottom_to_top(
        self, nodes: List[Node], y: float, i: int, alpha: float
    ) -> None:
        py = self.py or 0
        while i >= 0:
            node = nodes[i]
            dy = (node["y1"] - y) * alpha
            if dy > 1e-6:
                node["y0"] -= dy
                node["y1"] -= dy
            y = node["y0"] - py
            i -= 1

    def _reorder_node_links(self, node: Node) -> None:
        if self.link_sort is not None:
            return
        for link in node["targetLinks"]:
            link["source"]["sourceLinks"].sort(key=_link_sort_target)
        for link in node["sourceLinks"]:
            link["target"]["targetLinks"].sort(key=_link_sort_source)

    def _reorder_links(self, nodes: List[Node]) -> None:
        if self.link_sort is not None:
            return
        for node in nodes:
            node["sourceLinks"].sort(key=_link_sort_target)
            node["targetLinks"].sort(key=_link_sort_source)

    def _target_top(self, source: Node, target: Node) -> float:
        py = self.py or 0
        y = source["y0"] - (len(source["sourceLinks"]) - 1) * py / 2
        for link in source["sourceLinks"]:
            if link["target"] is target:
                break
            y += link["width"] + py
        for link in target["targetLinks"]:
            if link["source"] is source:
                break
            y -= link["width"]
        return y

    def _source_top(self, source: Node, target: Node) -> float:
        py = self.py or 0
        y = target["y0"] - (len(target["targetLinks"]) - 1) * py / 2
        for link in target["targetLinks"]:
            if link["source"] is source:
                break
            y += link["width"] + py
        for link in source["sourceLinks"]:
            if link["target"] is target:
                break
            y -= link["width"]
        return y

    def _compute_link_breadths(self, nodes: List[Node]) -> None:
        for node in nodes:
            y0 = node["y0"]
            y1 = y0
            for link in node["sourceLinks"]:
                link["y0"] = y0 + link["width"] / 2
                y0 += link["width"]
            for link in node["targetLinks"]:
                link["y1"] = y1 + link["width"] / 2
                y1 += link["width"]
