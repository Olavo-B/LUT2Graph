# /*****************************************************************************/
#  * File: retime.py
#  * Author: Olavo Alves Barros Silva
#  * Contact: olavo.barros@ufv.com
#  * Date: 2026-09-16
#  * License: MIT
#  * Description: Pipelines a LUT graph by levelizing it with ASAP or ALAP
#  * scheduling and inserting register ranks at stage boundaries. The
#  * pipelined circuit is exported back to Yosys JSON and Verilog.
# /*****************************************************************************/
"""ASAP/ALAP levelization and register insertion for LUT graphs.

Levels count LUTs only: primary inputs sit at level 0, and each LUT sits
one level after its deepest predecessor (ASAP) or one level before its
shallowest successor (ALAP). The circuit depth D is the largest ASAP
level, i.e. the number of LUTs on the critical path.

A stage is a contiguous range of levels. Stages are cut either every
`levels_per_stage` levels or into `num_stages` balanced ranges. An edge
whose endpoints lie k stages apart needs k registers; primary outputs
are placed in the last stage so every output path has the same latency
(num_stages - 1 cycles).
"""

from __future__ import annotations

import argparse
import datetime
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import networkx as nx

from lut2networkx import LUTGraphBuilder
from netlist_export import pipeline_netlist, write_verilog
from netlist_sim import verify_pipeline
from visualize import write_dot

Policy = Literal["asap", "alap"]


@dataclass(frozen=True)
class NodeSchedule:
    asap: int
    alap: int
    level: int
    stage: int

    @property
    def mobility(self) -> int:
        return self.alap - self.asap


def _node_type(G: nx.DiGraph, node: object) -> str:
    return G.nodes[node]["type"]


def compute_asap(G: nx.DiGraph) -> dict[object, int]:
    """Earliest level of every input and LUT node."""
    if not nx.is_directed_acyclic_graph(G):
        raise ValueError("Retiming requires a DAG; the LUT graph has a cycle.")
    asap: dict[object, int] = {}
    for node in nx.topological_sort(G):
        node_type = _node_type(G, node)
        if node_type == "input":
            asap[node] = 0
        elif node_type == "$lut":
            asap[node] = 1 + max((asap[p] for p in G.predecessors(node)), default=0)
    return asap


def compute_alap(G: nx.DiGraph, depth: int) -> dict[object, int]:
    """Latest level of every input and LUT node that still meets `depth`."""
    alap: dict[object, int] = {}
    for node in reversed(list(nx.topological_sort(G))):
        node_type = _node_type(G, node)
        if node_type == "input":
            alap[node] = 0
        elif node_type == "$lut":
            lut_successor_levels = [
                alap[s] for s in G.successors(node) if _node_type(G, s) == "$lut"
            ]
            alap[node] = min(lut_successor_levels, default=depth + 1) - 1
    return alap


def level_to_stage(
    depth: int,
    *,
    levels_per_stage: int | None = None,
    num_stages: int | None = None,
) -> list[int]:
    """Returns `stage_of_level`, indexed by level 0..depth.

    Exactly one of `levels_per_stage` (cut every x levels) or
    `num_stages` (split the depth into balanced ranges) must be given.
    """
    if (levels_per_stage is None) == (num_stages is None):
        raise ValueError("Give exactly one of levels_per_stage or num_stages.")
    levels = range(1, depth + 1)
    if levels_per_stage is not None:
        if levels_per_stage < 1:
            raise ValueError(f"levels_per_stage must be >= 1, got {levels_per_stage}.")
        return [0] + [(level - 1) // levels_per_stage for level in levels]
    if not 1 <= num_stages <= depth:
        raise ValueError(f"num_stages must be in [1, {depth}], got {num_stages}.")
    return [0] + [(level - 1) * num_stages // depth for level in levels]


def schedule_graph(
    G: nx.DiGraph,
    policy: Policy,
    *,
    levels_per_stage: int | None = None,
    num_stages: int | None = None,
) -> dict[object, NodeSchedule]:
    """Assigns ASAP/ALAP levels and a pipeline stage to every node."""
    if policy not in ("asap", "alap"):
        raise ValueError(f"Unknown policy '{policy}'.")
    asap = compute_asap(G)
    lut_levels = [asap[n] for n in asap if _node_type(G, n) == "$lut"]
    if not lut_levels:
        raise ValueError("The graph has no LUT nodes to pipeline.")
    depth = max(lut_levels)
    alap = compute_alap(G, depth)
    stage_of_level = level_to_stage(
        depth, levels_per_stage=levels_per_stage, num_stages=num_stages
    )
    chosen_level = asap if policy == "asap" else alap

    schedule = {
        node: NodeSchedule(
            asap[node], alap[node], chosen_level[node], stage_of_level[chosen_level[node]]
        )
        for node in asap
    }
    output_stage = stage_of_level[depth]
    for node in G.nodes:
        if _node_type(G, node) == "output":
            schedule[node] = NodeSchedule(depth + 1, depth + 1, depth + 1, output_stage)
    return schedule


def summarize(G: nx.DiGraph, schedule: dict[object, NodeSchedule]) -> dict:
    """Per-stage LUT counts and combinational depth, plus mobility stats."""
    luts = [n for n in G.nodes if _node_type(G, n) == "$lut"]
    depth = max(schedule[n].asap for n in luts)
    num_stages = max(s.stage for s in schedule.values()) + 1
    luts_per_stage = Counter(schedule[n].stage for n in luts)

    # Combinational depth of a stage = longest LUT chain inside it.
    stage_depth = Counter()
    chain_length: dict[object, int] = {}
    for node in nx.topological_sort(G):
        if _node_type(G, node) != "$lut":
            continue
        same_stage_preds = [
            chain_length[p] for p in G.predecessors(node)
            if p in chain_length and schedule[p].stage == schedule[node].stage
        ]
        chain_length[node] = 1 + max(same_stage_preds, default=0)
        stage = schedule[node].stage
        stage_depth[stage] = max(stage_depth[stage], chain_length[node])

    return {
        "depth": depth,
        "num_stages": num_stages,
        "latency_cycles": num_stages - 1,
        "luts_per_stage": [luts_per_stage[s] for s in range(num_stages)],
        "comb_depth_per_stage": [stage_depth[s] for s in range(num_stages)],
        "max_comb_depth": max(stage_depth.values()),
        "luts_with_mobility": sum(1 for n in luts if schedule[n].mobility > 0),
        "max_mobility": max(schedule[n].mobility for n in luts),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ASAP/ALAP pipelining of a LUT netlist.")
    parser.add_argument("netlist", type=Path, help="Yosys JSON netlist")
    cut = parser.add_mutually_exclusive_group(required=True)
    cut.add_argument("--levels-per-stage", type=int, help="insert a register rank every X LUT levels")
    cut.add_argument("--stages", type=int, help="split the critical depth into N balanced stages")
    parser.add_argument("--policy", choices=["asap", "alap"], default="asap")
    parser.add_argument("--name", default=None, help="run name (default: netlist stem)")
    parser.add_argument("--results-path", type=Path, default=Path("results"))
    parser.add_argument("--verify-vectors", type=int, default=200,
                        help="random vectors for the equivalence check (0 disables)")
    parser.add_argument("--dot", action="store_true", help="also write a staged DOT graph")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    name = args.name or args.netlist.stem
    timestamp = datetime.datetime.now().strftime("%d%m%y_%H%M")
    run_dir = args.results_path / f"{name}_{args.policy}_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    G = LUTGraphBuilder(args.netlist, results_path=run_dir).build()
    print(f"[build] {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

    schedule = schedule_graph(
        G, args.policy, levels_per_stage=args.levels_per_stage, num_stages=args.stages
    )
    summary = summarize(G, schedule)

    design = json.loads(args.netlist.read_text(encoding="utf-8"))
    stage_of_bit = {
        node: s.stage for node, s in schedule.items() if _node_type(G, node) != "output"
    }
    pipelined, flip_flops = pipeline_netlist(design, stage_of_bit, summary["latency_cycles"])
    summary.update(policy=args.policy, flip_flops=flip_flops)

    json_path = run_dir / f"{name}_retimed.json"
    json_path.write_text(json.dumps(pipelined, indent=2), encoding="utf-8")
    write_verilog(pipelined, run_dir / f"{name}_retimed.v")
    if args.dot:
        write_dot(G, run_dir / f"{name}_staged.dot", schedule=schedule)

    if args.verify_vectors > 0:
        verify_pipeline(design, pipelined, summary["latency_cycles"], args.verify_vectors)
        print(f"[verify] {args.verify_vectors} random vectors match after "
              f"{summary['latency_cycles']} cycles")

    (run_dir / "retime_report.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("[retime] ")
    print(f"\tPolicy: {args.policy}")
    print(f"\tDepth: {summary['depth']}, stages: {summary['num_stages']}, latency: {summary['latency_cycles']} cycles")
    print(f"\tLUTs per stage: {summary['luts_per_stage']}")
    print(f"\tCombinational depth per stage: {summary['comb_depth_per_stage']}, max: {summary['max_comb_depth']}")   
    print(f"\tLUTs with mobility: {summary['luts_with_mobility']}, max mobility: {summary['max_mobility']}")
    print(f"\tInserted flip-flops: {summary['flip_flops']}")
    
    
    print(f"[retime] outputs written to {run_dir}")


if __name__ == "__main__":
    main()
