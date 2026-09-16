import argparse
import sys
from pathlib import Path
import networkx as nx
import datetime

from lut2networkx import LUTGraphBuilder
from pruner import (
    apply_hardware_aware_pruning, 
    apply_kcore_pruning,
    apply_centrality_pruning,
    apply_backbone_pruning,
    apply_depth_aware_pruning,
    apply_entropy_aware_pruning
)
from evaluator import CircuitSimulator

# Import metrics and plotting functions
from graph_metrics import (
    compute_basic_stats,
    compute_connectivity_stats,
    compute_clustering_stats,
    compute_bias_stats,
    compute_weight_stats,
    print_report,
    plot_degree_distribution,
    plot_metrics_overview,
    plot_bias_distribution,
    plot_weight_distribution
)

def extract_id(port_name):
    """Extracts numeric ID from Yosys port strings for proper bit ordering."""
    if isinstance(port_name, int):
        return port_name
    return int(str(port_name).split('_')[-1])

def get_ordered_ports(G, port_type):
    """Retrieves and sorts boundary ports from the graph."""
    ports = [n for n, d in G.nodes(data=True) if d.get('type') == port_type]
    ports.sort(key=extract_id)
    return ports

def load_mem_dataset(filepath):
    """Loads a .mem file and converts the binary string bus to an integer."""
    data = []
    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            if line:
                data.append(int(line, 2))
    return data

def save_report_to_file(filepath, basic, connectivity, clustering, bias, weights, graph_name=""):
    """Redirects the report printout to a text file for safekeeping."""
    original_stdout = sys.stdout
    try:
        with open(filepath, 'w') as f:
            sys.stdout = f
            print_report(basic, connectivity, clustering, bias, weights, graph_name)
    finally:
        sys.stdout = original_stdout

def main():
    parser = argparse.ArgumentParser(description="LUT2Graph: Complex Networks for Logic Circuits")
    parser.add_argument('netlist', type=str, help='Path to the Yosys JSON netlist')
    
    parser.add_argument('--test-name', type=str, default=None, 
                        help='Name for the test (used for the results folder). Defaults to netlist name.')
    
    parser.add_argument('--prune', action='store_true', help='Apply structural pruning')
    
    # Pruning Method Selection
    parser.add_argument('--method', type=str, choices=['baseline', 'kcore', 'centrality', 'backbone', 'depth', 'entropy'], default='baseline', 
                        help='Select the pruning strategy')
    # Baseline args
    parser.add_argument('--sens-threshold', type=float, default=0.05, help='Edge sensitivity threshold')
    parser.add_argument('--bias-lower', type=float, default=0.05, help='Lower bound for Boolean Bias')
    parser.add_argument('--bias-upper', type=float, default=0.95, help='Upper bound for Boolean Bias')
    
    # K-Core args
    parser.add_argument('--max-shell', type=int, default=1, help='Maximum shell to remove in K-Core pruning')
    
    # Centrality & Depth args
    parser.add_argument('--centrality-metric', type=str, choices=['pagerank', 'eigenvector', 'degree'], default='pagerank', 
                        help='Centrality metric to rank node importance')
    parser.add_argument('--drop-fraction', type=float, default=0.05, 
                        help='Fraction of nodes to remove (e.g. 0.05 for 5%%)')
    

    
    # Evaluation args
    parser.add_argument('--test-data', type=str, help='Path to X_test.mem')
    parser.add_argument('--test-labels', type=str, help='Path to y_test.mem')
    
    args = parser.parse_args()

    # Create timestamped results directory (nome_ddMMaa_hhMM)
    netlist_path = Path(args.netlist)
    test_name = args.test_name if args.test_name else netlist_path.stem
    timestamp = datetime.datetime.now().strftime("%d%m%y_%H%M")
    folder_name = f"{test_name}_{timestamp}"
    run_dir = Path("results") / folder_name
    run_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"[setup] Test directory created at: {run_dir}")

    # 1. Build Graph
    print(f"[build] Loading netlist: {args.netlist}")
    builder = LUTGraphBuilder(args.netlist)
    G_orig = builder.build()
    
    print(f"[build] Graph ready: {G_orig.number_of_nodes()} nodes, {G_orig.number_of_edges()} edges")
    
    G_eval = G_orig

    # 2. Apply Hardware-Aware Pruning
    if args.prune:
        print(f"\n[pruning] Applying {args.method.upper()} Topological Reduction ...")
        
        if args.method == 'kcore':
            G_eval, stuck_at_count, pruned_edges = apply_kcore_pruning(G_orig, args.max_shell)
            print(f"[Pruning] Target: Outermost K-Core shells (k <= {args.max_shell})")
            
        elif args.method == 'centrality':
            G_eval, stuck_at_count, pruned_edges = apply_centrality_pruning(G_orig, args.centrality_metric, args.drop_fraction)
            print(f"[Pruning] Target: Bottom {args.drop_fraction * 100}% nodes by {args.centrality_metric.capitalize()}")
            
        elif args.method == 'backbone':
            G_eval, stuck_at_count, pruned_edges = apply_backbone_pruning(G_orig, args.sens_threshold)
            print(f"[Pruning] Target: Weak edges (Sensitivity < {args.sens_threshold}) while protecting structural bridges")

        elif args.method == 'depth':
            G_eval, stuck_at_count, pruned_edges = apply_depth_aware_pruning(G_orig, args.drop_fraction)
            print(f"[Pruning] Target: Bottom {args.drop_fraction * 100}% nodes by Parabolic Depth-Weighted Centrality")
            
        elif args.method == 'entropy':
            G_eval, stuck_at_count, pruned_edges = apply_entropy_aware_pruning(G_orig, args.drop_fraction)
            print(f"[Pruning] Target: Bottom {args.drop_fraction * 100}% nodes by Shannon Entropy (Predictable data flow)")
            
        else:
            G_eval, stuck_at_count, pruned_edges = apply_hardware_aware_pruning(
                G_orig, args.sens_threshold, args.bias_lower, args.bias_upper
            )
            print(f"[Pruning] Target: Sensitivity < {args.sens_threshold} | Bias limits: {args.bias_lower}-{args.bias_upper}")
            
        orig_nodes = G_orig.number_of_nodes()
        orig_edges = G_orig.number_of_edges()
        
        print(f"[Pruning] {pruned_edges} structural edges removed.")
        print(f"[Pruning] {stuck_at_count} nodes converted to Constants (Hybrid Stuck-at).")
        print(f"[pruning] Nodes reduction (active logic): {100 * stuck_at_count / orig_nodes:.2f}%")
        print(f"[pruning] Edges reduction: {100 * pruned_edges / orig_edges:.2f}%")
        
        largest_wcc = len(max(nx.weakly_connected_components(G_eval), key=len))
        print(f"[Connectivity] Post-pruning Largest WCC Size: {largest_wcc}")

    # 3. Export Pruned Graph
    graph_path = run_dir / f"{test_name}_pruned.gexf"
    try:
        nx.write_gexf(G_eval, graph_path)
        print(f"[export] Pruned graph exported to: {graph_path}")
    except Exception as e:
        print(f"[export] Warning: Could not save GEXF directly due to attribute format ({e}).")

    # 4. Generate Graph Metrics & Plots
    print("\n[stats] Computing complex-network metrics and generating plots ...")
    basic = compute_basic_stats(G_eval)
    connectivity = compute_connectivity_stats(G_eval)
    clustering = compute_clustering_stats(G_eval)
    bias = compute_bias_stats(G_eval)
    weights = compute_weight_stats(G_eval)
    
    # Save text report
    report_path = run_dir / "metrics_report.txt"
    save_report_to_file(report_path, basic, connectivity, clustering, bias, weights, graph_name=test_name)
    print(f"[stats] Metrics report saved to: {report_path}")
    
    # Generate and save plots
    plot_degree_distribution(basic, run_dir, node_type="$lut")
    plot_metrics_overview(basic, connectivity, clustering, run_dir)
    plot_bias_distribution(bias, run_dir)
    plot_weight_distribution(weights, run_dir)
    print(f"[stats] Metric plots saved to: {run_dir}")

    # 5. Evaluate Fidelity
    if args.test_data and args.test_labels:
        print("\n[eval] Loading test datasets (.mem files) ...")
        X_test = load_mem_dataset(args.test_data)
        y_test = load_mem_dataset(args.test_labels)
        print(f"[eval] Loaded {len(X_test)} test vectors.")
        
        print("[eval] Running topological logic simulation ...")
        
        # Simulate Original
        sim_orig = CircuitSimulator(G_orig,name="Original", reverse_bits=True)
        acc_orig = sim_orig.evaluate_fidelity(X_test, y_test)
        
        # Simulate Pruned
        sim_pruned = CircuitSimulator(G_eval, name="Pruned", reverse_bits=True)
        acc_pruned = sim_pruned.evaluate_fidelity(X_test, y_test)
        
        print(f"[Evaluation] ML Accuracy (Original Circuit): {acc_orig:.2f}%")
        print(f"[Evaluation] ML Accuracy (Pruned Circuit)  : {acc_pruned:.2f}%")
        
        with open(run_dir / "evaluation_accuracy.txt", "w") as f:
            f.write(f"ML Accuracy (Original Circuit): {acc_orig:.2f}%\n")
            f.write(f"ML Accuracy (Pruned Circuit)  : {acc_pruned:.2f}%\n")

    print(f"\n[done] Pipeline complete. Check the '{run_dir}' folder for all artifacts.")

if __name__ == "__main__":
    main()