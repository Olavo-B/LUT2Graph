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
import numpy as np
import matplotlib.pyplot as plt

# ---------------------------------------------------------------------------
# Optional heavy-weight imports (only needed for interactive visualisation)
# ---------------------------------------------------------------------------
try:
    from pyvis import network as pyvis_net  # type: ignore
    _PYVIS_AVAILABLE = True
except ImportError:
    _PYVIS_AVAILABLE = False




# ===========================================================================
# Main class
# ===========================================================================

class LUTGraphBuilder:
    """Build and analyse a NetworkX directed graph from a Yosys JSON netlist.

    The builder reads a Yosys synthesis output (``write_json`` command)
    and constructs an annotated ``networkx.DiGraph`` where:

    * **Input port** nodes are coloured blue  (``type='input'``).
    * **Output port** nodes are coloured red  (``type='output'``).
    * **LUT cell** nodes are coloured green   (``type='$lut'``).

    Node attributes
    ---------------
    ``type``  : ``'input'``, ``'output'``, or ``'$lut'``
    ``tag``   : human-readable port/cell name from the netlist
    ``color`` : colour hint for visualisation (``'blue'``, ``'red'``,
                ``'green'``)
    ``bias``  : (LUT nodes only) Boolean Bias in ``[0.0, 1.0]``

    Edge attributes
    ---------------
    ``weight`` : Boolean Sensitivity of the target LUT input, or
                 ``1.0`` for edges that terminate at output ports.

    Parameters
    ----------
    json_path:
        Path to the Yosys ``*.json`` netlist file.
    results_path:
        Directory where output artefacts (GEXF, plots, HTML) are saved.
        Created automatically if it does not exist.

    Examples
    --------
    >>> builder = LUTGraphBuilder("design.json", "results/my_design")
    >>> G = builder.build()
    >>> builder.print_summary()
    >>> builder.export_gexf()
    >>> builder.plot_degree_distribution()
    """

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(
        self,
        json_path: str | Path,
        results_path: str | Path = "results",
    ) -> None:
        self._json_path    = Path(json_path)
        self._results_path = Path(results_path)
        self._results_path.mkdir(parents=True, exist_ok=True)

        self._graph: nx.DiGraph | None = None  # populated by build()

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def graph(self) -> nx.DiGraph:
        """The constructed graph.

        Raises
        ------
        RuntimeError
            If :py:meth:`build` has not been called yet.
        """
        if self._graph is None:
            raise RuntimeError(
                "Graph has not been built yet.  Call build() first."
            )
        return self._graph

    @property
    def json_path(self) -> Path:
        """Path to the Yosys JSON netlist (read-only)."""
        return self._json_path

    @property
    def results_path(self) -> Path:
        """Directory where all output artefacts are written (read-only)."""
        return self._results_path

    @property
    def is_built(self) -> bool:
        """``True`` if :py:meth:`build` has been called successfully."""
        return self._graph is not None

    # ------------------------------------------------------------------
    # Core build pipeline
    # ------------------------------------------------------------------

    def build(self) -> nx.DiGraph:
        """Parse the Yosys JSON netlist and construct the graph.

        Performs three passes over the netlist data:

        1. **Port registration** – adds input / output port nodes.
        2. **LUT node registration** – adds LUT cell nodes annotated
           with their Boolean Bias.
        3. **Edge creation** – adds directed edges weighted by Boolean
           Sensitivity.

        Returns
        -------
        networkx.DiGraph
            The fully constructed graph (also stored in
            :py:attr:`graph`).

        Raises
        ------
        FileNotFoundError
            If *json_path* does not exist.
        KeyError
            If the JSON file does not contain a ``'modules'`` key.
        """
        design = self._load_json()
        module_name = list(design["modules"].keys())[0]
        module      = design["modules"][module_name]
        cells       = module.get("cells",  {})
        ports       = module.get("ports",  {})

        G = nx.DiGraph()
        self._register_ports(G, ports)
        self._register_lut_nodes(G, cells)
        output_bit_map = self._build_output_bit_map(ports)
        self._create_edges(G, cells, output_bit_map)

        self._graph = G
        return G


    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_output_bit_map(ports: dict) -> dict[Any, str]:
        """Map each output-port bit to its node identifier in the graph.

        Output port nodes are named ``'<port_name>_<bit>'`` to avoid
        collisions with internal signal identifiers.

        Parameters
        ----------
        ports:
            ``ports`` sub-dict from the Yosys JSON module.

        Returns
        -------
        dict
            ``{bit_id: node_name}`` for every output-direction bit.
        """
        mapping: dict[Any, str] = {}
        for port_name, port_data in ports.items():
            if port_data.get("direction") == "output":
                for bit in port_data.get("bits", []):
                    mapping[bit] = f"{port_name}_{bit}"
        return mapping

    def _load_json(self) -> dict:
        """Load and return the Yosys JSON file as a Python dict.

        Returns
        -------
        dict
            Parsed JSON content.

        Raises
        ------
        FileNotFoundError
            If *json_path* does not exist.
        """
        if not self._json_path.exists():
            raise FileNotFoundError(
                f"Yosys JSON file not found: {self._json_path}"
            )
        with open(self._json_path, "r", encoding="utf-8") as fh:
            return json.load(fh)

    def _register_ports(
        self,
        G: nx.DiGraph,
        ports: dict,
    ) -> None:
        """Add primary input and output port nodes to *G*.

        Input port bits become individual nodes with ``type='input'``
        and ``color='blue'``.  Output port bits become nodes named
        ``'<port_name>_<bit>'`` with ``type='output'`` and
        ``color='red'``.

        Parameters
        ----------
        G:
            Graph being constructed (mutated in place).
        ports:
            ``ports`` sub-dict from the Yosys JSON module.
        """
        for port_name, port_data in ports.items():
            direction = port_data.get("direction")
            bits      = port_data.get("bits", [])

            if direction == "input":
                for bit in bits:
                    G.add_node(
                        bit,
                        type="input",
                        tag=port_name,
                        color="blue",
                    )

            elif direction == "output":
                for bit in bits:
                    G.add_node(
                        f"{port_name}_{bit}",
                        type="output",
                        tag=port_name,
                        color="red",
                    )

    def _register_lut_nodes(
        self,
        G: nx.DiGraph,
        cells: dict,
    ) -> None:
        """Add LUT cell nodes annotated with Boolean Bias to *G*.

        Only cells whose ``type`` is ``'$lut'`` are processed.  The
        output bit of the LUT's ``Y`` connection is used as the node
        identifier.

        Parameters
        ----------
        G:
            Graph being constructed (mutated in place).
        cells:
            ``cells`` sub-dict from the Yosys JSON module.
        """
        for cell_name, cell_data in cells.items():
            if cell_data.get("type") != "$lut":
                continue

            connections = cell_data.get("connections", {})
            node_name   = connections.get("Y", [cell_name])[0]
            lut_str     = cell_data.get("parameters", {}).get("LUT", "")
            bias        = self._get_boolean_bias(lut_str)

            G.add_node(
                node_name,
                type="$lut",
                tag=cell_name,
                bias=bias,
                color="green",
            )

    def _create_edges(
        self,
        G: nx.DiGraph,
        cells: dict,
        output_bit_map: dict,
    ) -> None:
        """Add directed edges with Boolean Sensitivity weights to *G*.

        For each LUT's input port ``'A'``, one edge is drawn from each
        driver node to the LUT node, weighted by the sensitivity of that
        specific input.  Edges that connect to primary outputs carry a
        fixed weight of ``1.0``.

        Parameters
        ----------
        G:
            Graph being constructed (mutated in place).
        cells:
            ``cells`` sub-dict from the Yosys JSON module.
        output_bit_map:
            Mapping produced by :py:meth:`_build_output_bit_map`.
        """
        for cell_name, cell_data in cells.items():
            if cell_data.get("type") != "$lut":
                continue

            connections = cell_data.get("connections", {})
            node        = connections.get("Y", [cell_name])[0]
            lut_str     = cell_data.get("parameters", {}).get("LUT", "")

            for port_key, bits in connections.items():
                if port_key == "A":
                    num_inputs = len(bits)
                    for input_idx, bit in enumerate(bits):
                        if G.has_node(bit):
                            weight = self._get_boolean_sensitivity(
                                lut_str, input_idx, num_inputs
                            )
                            G.add_edge(bit, node, weight=weight)

                elif port_key == "Y":
                    for bit in bits:
                        if bit in output_bit_map:
                            G.add_edge(
                                node,
                                output_bit_map[bit],
                                weight=1.0,
                            )

    def _compute_degree_stats(self) -> dict[str, dict[str, list[int]]]:
        """Collect in/out-degree lists grouped by node type.

        Returns
        -------
        dict
            ``{node_type: {'in_degree': [...], 'out_degree': [...]}}``.
        """
        G      = self.graph
        stats: dict[str, dict[str, list[int]]] = {}

        for node, data in G.nodes(data=True):
            node_type = data.get("type", "unknown")
            if node_type not in stats:
                stats[node_type] = {"in_degree": [], "out_degree": []}
            stats[node_type]["in_degree"].append(G.in_degree(node))
            stats[node_type]["out_degree"].append(G.out_degree(node))

        return stats

    def _get_boolean_bias(self, lut_string: str) -> float:
        """Compute the Boolean Bias of a LUT truth table.

        The Boolean Bias is defined as the fraction of output bits that are
        ``'1'`` in the truth-table string produced by Yosys.  A value close
        to ``0`` or ``1`` indicates highly predictable (redundant) logic,
        while a value near ``0.5`` indicates balanced logic.

        Parameters
        ----------
        lut_string:
            Binary truth-table string (e.g. ``"01101001"``).  If the string
            is empty or not a ``str``, ``0.5`` (maximum uncertainty) is
            returned as a safe default.

        Returns
        -------
        float
            Ratio of ``'1'`` characters in *lut_string*, in ``[0.0, 1.0]``.

        Examples
        --------
        >>> builder._get_boolean_bias("1111")
        1.0
        >>> builder._get_boolean_bias("0000")
        0.0
        >>> builder._get_boolean_bias("0110")
        0.5
        """
        if not lut_string or not isinstance(lut_string, str):
            return 0.5
        return lut_string.count("1") / len(lut_string)

    def _get_boolean_sensitivity(
        self,
        lut_string: str,
        input_index: int,
        num_inputs: int,
    ) -> float:
        """Compute the Boolean Sensitivity of a specific LUT input.

        Boolean Sensitivity (also called *influence*) of input *i* is the
        probability that flipping bit *i* of a uniformly random input
        vector also flips the LUT output.  It is used as the edge weight
        between a driver node and the LUT node it feeds.

        Parameters
        ----------
        lut_string:
            Binary truth-table string of length ``2 ** num_inputs``.
        input_index:
            Zero-based index of the input whose sensitivity is computed.
        num_inputs:
            Total number of inputs of the LUT (determines truth-table size).

        Returns
        -------
        float
            Sensitivity value in ``[0.0, 1.0]``.  Returns ``1.0`` (full
            structural weight) when *lut_string* is missing or has the wrong
            length, so the edge is still retained in the graph.

        Notes
        -----
        The computation iterates over all ``2^(k-1)`` input pairs that
        differ only in bit *input_index* and counts how many pairs yield
        different outputs.

        Examples
        --------
        >>> # AND gate: output flips on input 0 only when input 1 == 1
        >>> builder._get_boolean_sensitivity("0001", 0, 2)
        0.5
        """
        expected_len = 1 << num_inputs
        if (
            not lut_string
            or not isinstance(lut_string, str)
            or len(lut_string) != expected_len
        ):
            return 1.0  # Fallback: treat edge as fully sensitive

        flips = 0
        for state in range(expected_len):
            # Only consider states where the target input is 0
            if (state & (1 << input_index)) == 0:
                toggled_state = state | (1 << input_index)
                if lut_string[state] != lut_string[toggled_state]:
                    flips += 1

        # Normalise by the number of checked pairs: 2^(k-1)
        return flips / (1 << (num_inputs - 1))


