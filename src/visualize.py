"""visualize.py

Renders a LUT graph (as produced by LUTGraphBuilder, optionally
scheduled by retime.py) as a Graphviz DOT file, for quick visual
sanity checks.

Writes plain DOT text directly instead of depending on pydot/graphviz
Python bindings, so the only external tool needed to view the result is
Graphviz itself (e.g. `dot -Tsvg out.dot -o out.svg`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Optional, Protocol

import networkx as nx


class _HasStage(Protocol):
    """Structural type for whatever a stage-assignment value looks like.

    Kept local and minimal on purpose: visualize.py has no dependency on
    retime.py (or any other module) -- it only needs values that expose
    a `.stage` attribute, whatever produced them.
    """

    stage: int


_NODE_TYPE_FILL_COLOR = {
    "input": "lightblue",
    "output": "lightpink",
    "$lut": "palegreen",
}
_DEFAULT_FILL_COLOR = "lightgray"

_NODE_TYPE_SHAPE = {
    "$lut": "square",
}
_DEFAULT_SHAPE = "ellipse"


def write_dot(
    graph: nx.DiGraph,
    path: str | Path,
    stage_assignment: Optional[Mapping[object, _HasStage]] = None,
) -> None:
    """Writes `graph` as a Graphviz DOT file.

    Without `stage_assignment`, this draws the plain netlist structure,
    colored by node type (input / output / $lut) using the same palette
    LUTGraphBuilder already assigns.

    With `stage_assignment` (as returned by `Retimer.assign_stages`),
    nodes are additionally grouped into one same-rank cluster per
    pipeline stage -- so Graphviz lays the pipeline out left to right --
    and each edge crossing a stage boundary is drawn bold and labelled
    with how many registers it needs. `stage_assignment` is the single
    source of truth for register counts here; the graph's own
    `registers` edge attribute (set by `annotate_graph`) is not read,
    since `annotate_graph` only ever initializes it to 0.
    """
    lines = ["digraph netlist {", '  rankdir="LR";', "  node [style=filled];"]

    for node, data in graph.nodes(data=True):
        label_parts = [str(data.get("tag", node)), str(data.get("type", "?"))]
        if stage_assignment is not None and node in stage_assignment:
            label_parts.append(f"stage {stage_assignment[node].stage}")
        label = "\\n".join(label_parts)
        fill_color = _NODE_TYPE_FILL_COLOR.get(data.get("type"), _DEFAULT_FILL_COLOR)
        shape = _NODE_TYPE_SHAPE.get(data.get("type"), _DEFAULT_SHAPE)
        lines.append(
            f'  "{node}" [label="{label}", fillcolor="{fill_color}", shape="{shape}"];'
        )

    if stage_assignment is not None:
        stage_to_nodes: dict[int, list[object]] = {}
        for node, assignment in stage_assignment.items():
            stage_to_nodes.setdefault(assignment.stage, []).append(node)
        for stage, nodes in sorted(stage_to_nodes.items()):
            node_list = ", ".join(f'"{n}"' for n in nodes)
            lines.append(f"  {{ rank=same; {node_list}; }}")

    for u, v in graph.edges():
        if stage_assignment is not None:
            registers = stage_assignment[v].stage - stage_assignment[u].stage
            if registers > 0:
                lines.append(f'  "{u}" -> "{v}" [style=bold, label="{registers} reg"];')
                continue
        lines.append(f'  "{u}" -> "{v}";')

    lines.append("}")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")