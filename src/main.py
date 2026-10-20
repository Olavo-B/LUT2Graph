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



def main(netlist_path: str = NETLIST, test_name: str = TEST_NAME):
    
    # Create timestamped results directory (nome_ddMMaa_hhMM)
    netlist_path = Path(netlist_path)
    test_name = test_name
    timestamp = datetime.datetime.now().strftime("%d%m%y_%H%M")
    folder_name = f"{test_name}_{timestamp}"
    run_dir = Path("results") / folder_name
    run_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"[setup] Test directory created at: {run_dir}")

    # 1. Build Graph
    print(f"[build] Loading netlist: {netlist_path}")
    builder = LUTGraphBuilder(netlist_path)
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
    print(f"  - Critical path length: {critical_path["critical_path_length"]} : {critical_path["critical_path"]}")
    
    write_dot(G_orig, run_dir / "graph_original.dot")


if __name__ == "__main__":
    
    # Make arguments optional for testing purposes
    parser = argparse.ArgumentParser(description="Build and analyze a NetworkX directed graph from a Yosys JSON netlist.")
    parser.add_argument("--netlist", type=str, default=NETLIST, help="Path to the Yosys JSON netlist file.")
    parser.add_argument("--test_name", type=str, default=TEST_NAME, help="Name of the test for results directory.")
    args = parser.parse_args()
    
    
    
    main(args.netlist, args.test_name)
