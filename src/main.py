# /*****************************************************************************/
#  * File: main.py
#  * Author: Olavo Alves Barros Silva
#  * Contact: olavo.barros@ufv.com
#  * Date: 2026-05-31
#  * License: MIT
#  * Description: Build LUT graphs, perform pruning, simulate logic and compute metrics.
# /*****************************************************************************/

import argparse
import sys
import json
import networkx as nx

# Assume these modules are in the same directory or accessible path
from lut2networkx import LUTGraphBuilder
from pruner import apply_hardware_aware_pruning
from evaluator import CircuitSimulator
# from graph_metrics import generate_report # (Optional, uncomment if using)

def load_mem_dataset(mem_file_path, port_order, is_label=False):
    """
    Parses a Verilog .mem file containing binary strings and maps them 
    to the hardware port order (LSB -> MSB mapping).
    """
    dataset = []
    try:
        with open(mem_file_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('//'):
                    continue
                
                if is_label:
                    # Multi-bit label logic: read the entire binary string as an integer
                    dataset.append(int(line, 2))
                else:
                    vector = {}
                    # Read string from right to left assuming index 0 is MSB in string
                    reversed_line = line[::-1] 
                    for i, port in enumerate(port_order):
                        if i < len(reversed_line):
                            vector[port] = int(reversed_line[i])
                        else:
                            vector[port] = 0
                    dataset.append(vector)
    except Exception as e:
        print(f"[Error] Failed to load .mem file {mem_file_path}: {e}")
        sys.exit(1)
        
    return dataset

def get_ordered_ports(G, port_type):
    """
    Extracts I/O ports from the graph and sorts them numerically.
    Handles both Yosys integer bit IDs and string-based port names.
    """
    ports = [n for n, d in G.nodes(data=True) if d.get('type') == port_type]
    
    def extract_id(port_name):
        # If the port is already an integer (Yosys internal bit ID), use it directly
        if isinstance(port_name, int):
            return port_name
            
        # If it is a string like "A_0" or "out_1", extract the number
        try:
            return int(str(port_name).split('_')[-1])
        except ValueError:
            return 0
            
    ports.sort(key=extract_id)
    return ports

def main():
    parser = argparse.ArgumentParser(description="LUT2Graph - Complex Networks Analysis for Hardware")
    parser.add_argument("json_file", help="Path to Yosys generated JSON netlist")
    parser.add_argument("--prune", action="store_true", help="Apply hardware-aware pruning")
    parser.add_argument("--sens-threshold", type=float, default=0.01, help="Edge sensitivity pruning threshold")
    parser.add_argument("--bias-lower", type=float, default=0.05, help="Lower bias threshold for const_0")
    parser.add_argument("--bias-upper", type=float, default=0.95, help="Upper bias threshold for const_1")
    parser.add_argument("--test-data", help="Path to X_test.mem dataset")
    parser.add_argument("--test-labels", help="Path to y_test.mem dataset")
    parser.add_argument("--no-reverse-bits", action="store_false", dest="reverse_bits", help="Disable endianness swap")
    
    args = parser.parse_args()

    print(f"[build] Loading netlist: {args.json_file}")

    # 1. Build Original Graph
    # Passe a string do caminho do arquivo diretamente para o construtor
    builder = LUTGraphBuilder(args.json_file)


    G_orig = builder.build()
    print(f"[build] Graph ready: {G_orig.number_of_nodes()} nodes, {G_orig.number_of_edges()} edges")

    G_eval = G_orig

    # 2. Apply Hardware-Aware Pruning
    if args.prune:
        print(f"\n[pruning] Applying Hardware-Aware Topological Reduction ...")
        G_eval, stuck_at_count, pruned_edges = apply_hardware_aware_pruning(
            G_orig, args.sens_threshold, args.bias_lower, args.bias_upper
        )
        
        orig_nodes = G_orig.number_of_nodes()
        orig_edges = G_orig.number_of_edges()
        
        print(f"[Pruning] {pruned_edges} edges removed (Sensitivity < {args.sens_threshold}).")
        print(f"[Pruning] {stuck_at_count} nodes converted to Constants (Stuck-at Faults).")
        print(f"[pruning] Nodes reduction (active logic): {100 * stuck_at_count / orig_nodes:.2f}%")
        print(f"[pruning] Edges reduction: {100 * pruned_edges / orig_edges:.2f}%")
        
        largest_wcc = len(max(nx.weakly_connected_components(G_eval), key=len))
        print(f"[Connectivity] Post-pruning Largest WCC Size: {largest_wcc}")

    # 3. Topo-Logic Evaluation
    if args.test_data and args.test_labels:
        print("\n[eval] Loading test datasets (.mem files) ...")
        
        input_ports = get_ordered_ports(G_orig, 'input')
        X_test = load_mem_dataset(args.test_data, input_ports, is_label=False)
        y_test = load_mem_dataset(args.test_labels, [], is_label=True)
        
        print(f"[eval] Loaded {len(X_test)} test vectors.")
        print("[eval] Running topological logic simulation ...")
        
        simulator_orig = CircuitSimulator(G_orig, reverse_bits=args.reverse_bits)
        acc_orig = simulator_orig.evaluate_fidelity(X_test, y_test)
        
        print(f"\n[Evaluation] ML Accuracy (Original Circuit): {acc_orig:.2f}%")
        
        if args.prune:
            simulator_pruned = CircuitSimulator(G_eval, reverse_bits=args.reverse_bits)
            acc_pruned = simulator_pruned.evaluate_fidelity(X_test, y_test)
            print(f"[Evaluation] ML Accuracy (Pruned Circuit)  : {acc_pruned:.2f}%")

    print("\n[done] Pipeline complete.")

if __name__ == "__main__":
    main()