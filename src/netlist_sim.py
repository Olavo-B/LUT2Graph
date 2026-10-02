# /*****************************************************************************/
#  * File: netlist_sim.py
#  * Author: Olavo Alves Barros Silva
#  * Contact: olavo.barros@ufv.com
#  * Date: 2026-10-02
#  * License: MIT
#  * Description: Cycle-accurate simulator for Yosys JSON LUT/$dff netlists,
#  * used to check that a pipelined netlist matches the original one.
# /*****************************************************************************/

from __future__ import annotations

import random

import networkx as nx

from netlist_export import CLOCK_PORT, DFF_CELL, LUT_CELL, single_module

_CONSTANT_VALUES = {"0": 0, "1": 1}


def lut_output(table: str, input_values: list[int]) -> int:
    """Yosys $lut semantics: A[0] is the address LSB, table is MSB-first."""
    address = sum(value << i for i, value in enumerate(input_values))
    return int(table[-1 - address])


class NetlistSimulator:
    """Simulates one clock cycle at a time; registers start at 0."""

    def __init__(self, design: dict) -> None:
        _, module = single_module(design)
        self._ports = module["ports"]
        cells = module["cells"].values()
        self._dffs = [c["connections"] for c in cells if c["type"] == DFF_CELL]
        self._luts = self._topological_luts([c for c in cells if c["type"] == LUT_CELL])
        self._state = {dff["Q"][0]: 0 for dff in self._dffs}

    @staticmethod
    def _topological_luts(luts: list[dict]) -> list[tuple[str, list, int]]:
        driver = {lut["connections"]["Y"][0]: i for i, lut in enumerate(luts)}
        order = nx.DiGraph()
        order.add_nodes_from(range(len(luts)))
        for i, lut in enumerate(luts):
            order.add_edges_from((driver[b], i) for b in lut["connections"]["A"] if b in driver)
        return [
            (luts[i]["parameters"]["LUT"], luts[i]["connections"]["A"], luts[i]["connections"]["Y"][0])
            for i in nx.topological_sort(order)
        ]

    def input_ports(self) -> dict[str, int]:
        return {
            name: len(port["bits"]) for name, port in self._ports.items()
            if port["direction"] == "input" and name != CLOCK_PORT
        }

    def step(self, inputs: dict[str, int]) -> dict[str, int]:
        """Applies `inputs` (port -> integer), returns outputs, then clocks."""
        values = dict(_CONSTANT_VALUES)
        values.update(self._state)
        for name, width in self.input_ports().items():
            for index, bit in enumerate(self._ports[name]["bits"]):
                values[bit] = (inputs[name] >> index) & 1
        for table, address_bits, y_bit in self._luts:
            values[y_bit] = lut_output(table, [values[b] for b in address_bits])

        outputs = {
            name: sum(values[b] << i for i, b in enumerate(port["bits"]))
            for name, port in self._ports.items() if port["direction"] == "output"
        }
        self._state = {dff["Q"][0]: values[dff["D"][0]] for dff in self._dffs}
        return outputs


def verify_pipeline(original: dict, pipelined: dict, latency: int, num_vectors: int, seed: int = 0) -> None:
    """Raises AssertionError unless pipelined(t + latency) == original(t)."""
    reference = NetlistSimulator(original)
    pipeline = NetlistSimulator(pipelined)
    rng = random.Random(seed)
    vectors = [
        {name: rng.getrandbits(width) for name, width in reference.input_ports().items()}
        for _ in range(num_vectors)
    ]
    expected = [reference.step(v) for v in vectors]
    idle = {name: 0 for name in reference.input_ports()}
    observed = [pipeline.step(v) for v in vectors + [idle] * latency][latency:]
    for t, (want, got) in enumerate(zip(expected, observed)):
        if want != got:
            raise AssertionError(f"Vector {t}: expected {want}, got {got} (latency {latency}).")
