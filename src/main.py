import argparse
import sys
from pathlib import Path
import networkx as nx
import datetime

from lut2networkx import LUTGraphBuilder

from evaluator import CircuitSimulator

# Import metrics and plotting functions
from graph_metrics import (
    compute_basic_stats,
    compute_critical_path
)

from visualize import write_dot


NETLIST = "./misc/examples/branch_join_moc.json"
TEST_NAME = 'rato'



def main():
    
    # Create timestamped results directory (nome_ddMMaa_hhMM)
    netlist_path = Path(NETLIST)
    test_name = TEST_NAME
    timestamp = datetime.datetime.now().strftime("%d%m%y_%H%M")
    folder_name = f"{test_name}_{timestamp}"
    run_dir = Path("results") / folder_name
    run_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"[setup] Test directory created at: {run_dir}")

    # 1. Build Graph
    print(f"[build] Loading netlist: {NETLIST}")
    builder = LUTGraphBuilder(NETLIST)
    G_orig = builder.build()
    
    print(f"[build] Graph ready: {G_orig.number_of_nodes()} nodes, {G_orig.number_of_edges()} edges")
    
    # 2. Compute basic graph statistics
    stats = compute_basic_stats(G_orig)
    critical_path= compute_critical_path(G_orig)
    
    print(f"[stats] Basic Graph Statistics:")
    print(f"  - Number of nodes: {stats['num_nodes']}")
    print(f"  - Number of edges: {stats['num_edges']}")
    print(f"  - Average in-degree: {stats['avg_in_degree']:.2f}")
    print(f"  - Average out-degree: {stats['avg_out_degree']:.2f}")
    print(f"  - Critical path length: {critical_path.values()}")
    
    write_dot(G_orig, run_dir / "graph_original.dot")


if __name__ == "__main__":
    main()