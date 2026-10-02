"""visualize.py

Renders a LUT graph (as produced by LUTGraphBuilder, optionally scheduled by
retime.py) as a Graphviz DOT file, in the style of the retiming note
(misc/doc/retiming): LUTs as rounded boxes, I/O ports as circles, one column
per LUT level, one dashed red cluster per pipeline stage, and the inserted
flip-flops as small grey boxes on the cuts between stages.

Writes plain DOT text directly, so the only external tool needed to view the
result is Graphviz itself (e.g. `dot -Tsvg out.dot -o out.svg`).
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Mapping, Optional, Protocol

import networkx as nx


class _Scheduled(Protocol):
    """Anything exposing the drawing column (`level`) and pipeline `stage`."""

    level: int
    stage: int


_FONT = "DejaVu Serif"
_STAGE_COLOR = "#b22222"
_MUTED_COLOR = "gray45"

_GRAPH_HEADER = [
    "digraph netlist {",
    "  rankdir=LR; newrank=true; nodesep=0.2; ranksep=0.4;",
    f'  graph [fontname="{_FONT}", fontsize=9];',
    f'  node [fontname="{_FONT}", fontsize=10, penwidth=0.8];',
    "  edge [arrowsize=0.5, penwidth=0.8];",
]

_NODE_STYLE = {
    "$lut": "shape=box, style=rounded, height=0.3",
    "input": "shape=circle, margin=0.02",
    "output": "shape=circle, margin=0.02",
}
_FLIP_FLOP_STYLE = (
    'shape=box, style=filled, fillcolor="gray88", label="", '
    "width=0.1, height=0.25, fixedsize=true"
)
_COLUMN_LABEL_STYLE = f'shape=plaintext, fontsize=8, fontcolor="{_MUTED_COLOR}"'


def _quote(name: object) -> str:
    return '"' + str(name).replace('"', '\\"') + '"'


def _node_line(graph: nx.DiGraph, node: object) -> str:
    data = graph.nodes[node]
    node_type = data["type"]
    label = data["tag"] if node_type == "$lut" else f'{data["tag"]}[{data["port_idx"]}]'
    return f"  {_quote(node)} [label={_quote(label)}, {_NODE_STYLE[node_type]}];"


def _column_keys(schedule: Mapping[object, _Scheduled]) -> list[tuple[str, int]]:
    """Left-to-right columns: every level, plus one cut column between stages."""
    stage_of_level = {s.level: s.stage for s in schedule.values()}
    columns: list[tuple[str, int]] = []
    previous_stage = 0
    for level in sorted(stage_of_level):
        stage = stage_of_level[level]
        columns += [("cut", cut) for cut in range(previous_stage, stage)]
        columns.append(("level", level))
        previous_stage = stage
    return columns


def _column_label(column: tuple[str, int], output_level: int) -> str:
    kind, index = column
    if kind == "cut":
        return ""
    return "out" if index == output_level else f"level {index}"


def _pipeline_lines(graph: nx.DiGraph, schedule: Mapping[object, _Scheduled]) -> list[str]:
    columns = _column_keys(schedule)
    members: dict[tuple[str, int], list[str]] = defaultdict(list)
    for node, s in schedule.items():
        members[("level", s.level)].append(_quote(node))

    lines: list[str] = []
    flip_flops = 0
    for u in graph.nodes:
        delays = {v: schedule[v].stage - schedule[u].stage for v in graph.successors(u)}
        chain = [_quote(f"ff:{u}:{depth}") for depth in range(1, max(delays.values(), default=0) + 1)]
        flip_flops += len(chain)
        for depth, ff in enumerate(chain, start=1):
            lines.append(f"  {ff} [{_FLIP_FLOP_STYLE}];")
            lines.append(f"  {chain[depth - 2] if depth > 1 else _quote(u)} -> {ff};")
            members[("cut", schedule[u].stage + depth - 1)].append(ff)
        for v, delay in delays.items():
            lines.append(f"  {chain[delay - 1] if delay else _quote(u)} -> {_quote(v)};")

    output_level = max(s.level for s in schedule.values())
    column_ids = [_quote(f"col:{kind}:{index}") for kind, index in columns]
    for column, column_id in zip(columns, column_ids):
        lines.append(f"  {column_id} [label={_quote(_column_label(column, output_level))}, {_COLUMN_LABEL_STYLE}];")
        lines.append(f"  {{ rank=same; {'; '.join([column_id] + members[column])}; }}")
    lines.append(f"  {' -> '.join(column_ids)} [style=invis];")

    stages = sorted({s.stage for s in schedule.values()})
    for stage in stages:
        nodes = "; ".join(_quote(n) for n, s in schedule.items() if s.stage == stage)
        lines += [
            f"  subgraph cluster_stage_{stage} {{",
            f'    label="stage {stage}"; labelloc=b; style=dashed; penwidth=1.2;',
            f'    color="{_STAGE_COLOR}"; fontcolor="{_STAGE_COLOR}";',
            f"    {nodes};",
            "  }",
        ]
    latency = len(stages) - 1
    lines.append(
        f'  label="flip-flops: {flip_flops}    stages: {len(stages)}    '
        f'latency: {latency} cycle{"" if latency == 1 else "s"}"; labelloc=b;'
    )
    return lines


def write_dot(
    graph: nx.DiGraph,
    path: str | Path,
    schedule: Optional[Mapping[object, _Scheduled]] = None,
) -> None:
    """Writes `graph` as a Graphviz DOT file.

    Without `schedule`, draws the plain netlist structure. With `schedule`
    (as returned by `retime.schedule_graph`), nodes are placed in one column
    per level and grouped into one cluster per stage, and every net that
    crosses a stage cut gets a shared chain of flip-flops (one per cut), each
    consumer tapping the chain at the depth it needs -- the same sharing
    `netlist_export.pipeline_netlist` uses, so the flip-flop count matches.
    """
    lines = _GRAPH_HEADER + [_node_line(graph, n) for n in graph.nodes]
    if schedule is None:
        lines += [f"  {_quote(u)} -> {_quote(v)};" for u, v in graph.edges]
    else:
        lines += _pipeline_lines(graph, schedule)
    lines.append("}")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
