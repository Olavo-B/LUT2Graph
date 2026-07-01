# /*****************************************************************************/
#  * File: lut2networkx.py
#  * Author: Olavo Alves Barros Silva
#  * Contact: olavo.barros@ufv.com
#  * Date: 2026-05-20
#  * License: MIT License
#  * Description: This module defines the main class LUTGraphBuilder, which 
#  * constructs a NetworkX directed graph from a Yosys JSON netlist.  The graph 
#  * captures the structure of the design, with nodes representing input ports, 
#  * output ports, and LUT cells, and edges weighted by
# /*****************************************************************************/

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import networkx as nx

class LUTGraphBuilder:
    """Builds and analyses a NetworkX directed graph from a Yosys JSON netlist."""

    def __init__(self, json_path: str | Path, results_path: str | Path = "results") -> None:
        self._json_path = Path(json_path)
        self._results_path = Path(results_path)
        self._results_path.mkdir(parents=True, exist_ok=True)
        self._graph: nx.DiGraph | None = None

    @property
    def graph(self) -> nx.DiGraph:
        if self._graph is None:
            raise RuntimeError("Graph has not been built yet. Call build() first.")
        return self._graph

    def build(self) -> nx.DiGraph:
        """Parses the Yosys JSON netlist and constructs the graph."""
        design = self._load_json()
        module_name = list(design["modules"].keys())[0]
        module = design["modules"][module_name]
        cells = module.get("cells", {})
        ports = module.get("ports", {})

        G = nx.DiGraph()
        self._register_ports(G, ports)
        self._register_lut_nodes(G, cells)
        output_bit_map = self._build_output_bit_map(ports)
        self._create_edges(G, cells, output_bit_map)

        self._graph = G
        return G

    @staticmethod
    def _build_output_bit_map(ports: dict) -> dict[Any, str]:
        mapping: dict[Any, str] = {}
        for port_name, port_data in ports.items():
            if port_data.get("direction") == "output":
                for bit in port_data.get("bits", []):
                    mapping[bit] = f"{port_name}_{bit}"
        return mapping

    def _load_json(self) -> dict:
        if not self._json_path.exists():
            raise FileNotFoundError(f"Yosys JSON file not found: {self._json_path}")
        with open(self._json_path, "r", encoding="utf-8") as fh:
            return json.load(fh)

    def _register_ports(self, G: nx.DiGraph, ports: dict) -> None:
        """Adds primary input and output port nodes to G, storing their original bus index."""
        for port_name, port_data in ports.items():
            direction = port_data.get("direction")
            bits = port_data.get("bits", [])

            if direction == "input":
                for i, bit in enumerate(bits):
                    # Record port_idx to maintain bus order (LSB to MSB)
                    G.add_node(bit, type="input", tag=port_name, color="blue", port_idx=i)
            elif direction == "output":
                for i, bit in enumerate(bits):
                    # Record port_idx to maintain bus order (LSB to MSB)
                    G.add_node(f"{port_name}_{bit}", type="output", tag=port_name, color="red", port_idx=i)

    def _register_lut_nodes(self, G: nx.DiGraph, cells: dict) -> None:
        """Adds LUT cell nodes annotated with Boolean Bias and the original Truth Table."""
        for cell_name, cell_data in cells.items():
            if cell_data.get("type") != "$lut":
                continue

            connections = cell_data.get("connections", {})
            node_name = connections.get("Y", [cell_name])[0]
            lut_str = cell_data.get("parameters", {}).get("LUT", "")
            bias = self._get_boolean_bias(lut_str)

            G.add_node(
                node_name,
                type="$lut",
                tag=cell_name,
                bias=bias,
                color="green",
                lut_str=lut_str,  # Ensure truth table is saved for logical simulation
            )

    def _create_edges(self, G: nx.DiGraph, cells: dict, output_bit_map: dict) -> None:
        """Adds directed edges annotated with Boolean Sensitivity and pin connection indices."""
        for cell_name, cell_data in cells.items():
            if cell_data.get("type") != "$lut":
                continue

            connections = cell_data.get("connections", {})
            node = connections.get("Y", [cell_name])[0]
            lut_str = cell_data.get("parameters", {}).get("LUT", "")

            for port_key, bits in connections.items():
                if port_key == "A":
                    num_inputs = len(bits)
                    for input_idx, bit in enumerate(bits):
                        if G.has_node(bit):
                            weight = self._get_boolean_sensitivity(lut_str, input_idx, num_inputs)
                            # Record pin_idx to guarantee correct LUT input ordering
                            G.add_edge(bit, node, weight=weight, pin_idx=input_idx)

                elif port_key == "Y":
                    for bit in bits:
                        if bit in output_bit_map:
                            G.add_edge(node, output_bit_map[bit], weight=1.0)

    def _get_boolean_bias(self, lut_string: str) -> float:
        if not lut_string or not isinstance(lut_string, str):
            return 0.5
        return lut_string.count("1") / len(lut_string)

    def _get_boolean_sensitivity(self, lut_string: str, input_index: int, num_inputs: int) -> float:
        expected_len = 1 << num_inputs
        if not lut_string or not isinstance(lut_string, str) or len(lut_string) != expected_len:
            return 1.0 

        flips = 0
        for state in range(expected_len):
            if (state & (1 << input_index)) == 0:
                toggled_state = state | (1 << input_index)
                if lut_string[state] != lut_string[toggled_state]:
                    flips += 1
        return flips / (1 << (num_inputs - 1))