# /*****************************************************************************/
#  * File: evaluator.py
#  * Author: Olavo Alves Barros Silva
#  * Contact: olavo.barros@ufv.com
#  * Date: 2026-05-27
#  * License: MIT
#  * Description: This class is responsible to make the evaluation of the circuit
#  * pos prune
# /*****************************************************************************/

import networkx as nx
import math

class CircuitSimulator:
    def __init__(self, G,name = None,  reverse_bits=True):
        """
        Initializes the topological simulator.
        reverse_bits: Handles Endianness (MSB/LSB) alignment with Verilog datasets.
        """
        self.G = G
        self.name = name
        self.reverse_bits = reverse_bits

    def _evaluate_lut(self, node, node_data, input_values):
        """
        Evaluates the logic output of a node based on its Truth Table and incoming edges.
        """
        node_type = node_data.get('type')
        
        # Hardware-Aware: Propagate Stuck-at constants without checking truth tables
        if node_type == 'const_0':
            return 0
        if node_type == 'const_1':
            return 1

        lut_str = node_data.get('lut_str', '')
        if not lut_str:
            return 0

        in_edges = list(self.G.in_edges(node, data=True))
        
        # Calculate maximum pins based on LUT configuration (e.g., 16-bit string = 4 pins)
        try:
            max_pins = int(math.log2(len(lut_str)))
        except ValueError:
            max_pins = len(in_edges)

        # Hardware-Aware LUT Readjustment: missing/pruned edges default to logic 0
        pin_values = [0] * max_pins

        # Map incoming signals to their exact pin index
        for u, _, edge_data in in_edges:
            pin_idx = edge_data.get('pin_idx', 0)
            if pin_idx < max_pins:
                pin_values[pin_idx] = input_values[u]

        # Calculate Truth Table index from pin values
        idx = 0
        for i, val in enumerate(pin_values):
            if val:
                idx |= (1 << i)

        # Apply Endianness correction for hardware string reading
        if self.reverse_bits and idx < len(lut_str):
            str_idx = len(lut_str) - 1 - idx
            return int(lut_str[str_idx])
        elif idx < len(lut_str):
            return int(lut_str[idx])
            
        return 0

    def evaluate_fidelity(self, test_dataset, expected_labels=None):
        """
        Simulates the entire Directed Acyclic Graph (DAG) for a batch of test vectors.
        """
        correct_predictions = 0
        total_predictions = len(test_dataset)
        
        # Topological sort ensures we evaluate inputs before outputs
        eval_order = list(nx.topological_sort(self.G))

        def extract_id(port_name):
            try:
                return int(str(port_name).split('_')[-1])
            except ValueError:
                return 0

        # Get and sort input nodes by their ID to ensure proper bit significance (LSB to MSB)
        in_nodes = [n for n, d in self.G.nodes(data=True) if d.get('type') == 'input']
        in_nodes.sort(key=extract_id)
        
        with open(f"evaluation_states_{self.name}.csv", "w") as f:
            f.write("test_vector_index,node_type,evaluated_state\n")

        for i, test_vector in enumerate(test_dataset):
            node_states = {}
            
            # Load initial inputs
            if isinstance(test_vector, int):
                # Unpack the integer bit by bit to the sorted input ports
                for bit_idx, in_node in enumerate(in_nodes):
                    node_states[in_node] = (test_vector >> bit_idx) & 1
            else:
                # Fallback if test_vector is already a dictionary
                for k, v in test_vector.items():
                    node_states[k] = v
                
            # Propagate logic through the graph
            for node in eval_order:
                node_data = self.G.nodes[node]
                n_type = node_data.get('type')
                
                if n_type == 'input':
                    continue # Already loaded from test_vector
                
                elif n_type in ['$lut', 'const_0', 'const_1']:
                    node_states[node] = self._evaluate_lut(node, node_data, node_states)
                
                elif n_type == 'output':
                    # Find the node driving this output port
                    in_edges = list(self.G.in_edges(node))
                    if in_edges:
                        driver = in_edges[0][0]
                        node_states[node] = node_states.get(driver, 0)
                        
                        
                # Save the evaluated state for debugging in an .csv file
                if i == 0:  # Only write for one sample
                    with open(f"evaluation_states_{self.name}.csv", "a") as f:
                        f.write(f"{i},{n_type},{node_states.get(node, 0)}\n")

            # Check matching output logic (handling multi-bit output buses)
            out_nodes = [n for n, d in self.G.nodes(data=True) if d.get('type') == 'output']
            out_nodes.sort(key=extract_id)

            if out_nodes and expected_labels:
                # Reconstruct the integer prediction from the output bus bits
                pred_val = 0
                for bit_idx, out_node in enumerate(out_nodes):
                    bit_val = node_states.get(out_node, 0)
                    if bit_val:
                        pred_val |= (1 << bit_idx)
                
                expected = expected_labels[i]
                if pred_val == expected:
                    correct_predictions += 1

        accuracy = (correct_predictions / total_predictions) * 100 if total_predictions > 0 else 0.0
        return accuracy