# /*****************************************************************************/
#  * File: netlist_export.py
#  * Author: Olavo Alves Barros Silva
#  * Contact: olavo.barros@ufv.com
#  * Date: 2026-10-02
#  * License: MIT
#  * Description: Inserts pipeline registers into a Yosys JSON LUT netlist and
#  * writes the result as Yosys JSON or structural Verilog.
# /*****************************************************************************/
"""Register insertion on Yosys JSON netlists and Verilog emission.

Registers are shared per driver: a net that must be delayed by up to k
cycles gets one k-long chain of $dff cells, and every consumer taps the
chain at the depth it needs.
"""

from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Mapping

CLOCK_PORT = "clk"
LUT_CELL = "$lut"
DFF_CELL = "$dff"
IGNORED_CELLS = {"$scopeinfo"}
_WIDTH_ONE = format(1, "032b")


def single_module(design: dict) -> tuple[str, dict]:
    modules = design["modules"]
    if len(modules) != 1:
        raise ValueError(f"Expected exactly one module, found {len(modules)}.")
    return next(iter(modules.items()))


def _max_bit(module: dict) -> int:
    bits = [b for p in module["ports"].values() for b in p["bits"]]
    bits += [b for c in module["cells"].values() for bs in c["connections"].values() for b in bs]
    bits += [b for n in module.get("netnames", {}).values() for b in n["bits"]]
    return max(b for b in bits if isinstance(b, int))


def _dff_cell(clk_bit: int, d_bit: int, q_bit: int) -> dict:
    return {
        "hide_name": 1,
        "type": DFF_CELL,
        "parameters": {"CLK_POLARITY": "1", "WIDTH": _WIDTH_ONE},
        "attributes": {},
        "port_directions": {"CLK": "input", "D": "input", "Q": "output"},
        "connections": {"CLK": [clk_bit], "D": [d_bit], "Q": [q_bit]},
    }


def pipeline_netlist(
    design: dict, stage_of_bit: Mapping[int, int], output_stage: int
) -> tuple[dict, int]:
    """Returns (pipelined design, number of flip-flops inserted).

    `stage_of_bit` maps every primary-input bit and every LUT output bit
    to its pipeline stage; primary outputs are read at `output_stage`.
    """
    design = copy.deepcopy(design)
    _, module = single_module(design)
    ports, cells = module["ports"], module["cells"]
    if CLOCK_PORT in ports:
        raise ValueError(f"Port '{CLOCK_PORT}' already exists in the netlist.")
    unsupported = {c["type"] for c in cells.values()} - {LUT_CELL} - IGNORED_CELLS
    if unsupported:
        raise ValueError(f"Unsupported cell types for retiming: {sorted(unsupported)}")

    luts = [c for c in cells.values() if c["type"] == LUT_CELL]
    output_ports = [p for p in ports.values() if p["direction"] == "output"]

    def registers_needed(bit: int, consumer_stage: int) -> int:
        if bit not in stage_of_bit:
            raise KeyError(f"Net {bit} has no driver stage (undriven net?).")
        delay = consumer_stage - stage_of_bit[bit]
        if delay < 0:
            raise ValueError(f"Net {bit} is consumed before it is produced.")
        return delay

    # (bit list, consumer stage) for every sink in the netlist.
    sinks = [(lut["connections"]["A"], stage_of_bit[lut["connections"]["Y"][0]]) for lut in luts]
    sinks += [(port["bits"], output_stage) for port in output_ports]

    chain_length: dict[int, int] = {}
    for bits, consumer_stage in sinks:
        for bit in bits:
            if isinstance(bit, int):
                needed = registers_needed(bit, consumer_stage)
                chain_length[bit] = max(chain_length.get(bit, 0), needed)

    next_bit = _max_bit(module) + 1
    clk_bit = next_bit
    next_bit += 1
    netnames = module.setdefault("netnames", {})
    netnames[CLOCK_PORT] = {"hide_name": 0, "bits": [clk_bit], "attributes": {}}

    taps: dict[int, list[int]] = {}
    for driver, length in chain_length.items():
        previous, chain = driver, []
        for index in range(1, length + 1):
            q_bit, next_bit = next_bit, next_bit + 1
            cells[f"$retime$dff${driver}${index}"] = _dff_cell(clk_bit, previous, q_bit)
            netnames[f"$retime$n{driver}$d{index}"] = {"hide_name": 1, "bits": [q_bit], "attributes": {}}
            chain.append(q_bit)
            previous = q_bit
        taps[driver] = chain

    def tapped(bits: list, consumer_stage: int) -> list:
        return [
            bit if not isinstance(bit, int) or registers_needed(bit, consumer_stage) == 0
            else taps[bit][registers_needed(bit, consumer_stage) - 1]
            for bit in bits
        ]

    for lut in luts:
        connections = lut["connections"]
        connections["A"] = tapped(connections["A"], stage_of_bit[connections["Y"][0]])
    for port_name, port in ports.items():
        if port["direction"] == "output":
            port["bits"] = tapped(port["bits"], output_stage)
            if port_name in netnames:
                netnames[port_name]["bits"] = port["bits"]

    module["ports"] = {CLOCK_PORT: {"direction": "input", "bits": [clk_bit]}, **ports}
    return design, sum(chain_length.values())


# ---------------------------------------------------------------------------
# Verilog emission
# ---------------------------------------------------------------------------

_SIMPLE_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")
_CONSTANTS = {"0": "1'b0", "1": "1'b1", "x": "1'bx", "z": "1'bz"}


def _ident(name: str) -> str:
    return name if _SIMPLE_IDENT.match(name) else f"\\{name} "


def _net(bit: int | str) -> str:
    return f"n{bit}" if isinstance(bit, int) else _CONSTANTS[bit]


def write_verilog(design: dict, path: str | Path) -> None:
    """Writes a single-module LUT/$dff netlist as structural Verilog."""
    module_name, module = single_module(design)
    ports, cells = module["ports"], module["cells"]
    unsupported = {c["type"] for c in cells.values()} - {LUT_CELL, DFF_CELL} - IGNORED_CELLS
    if unsupported:
        raise ValueError(f"Unsupported cell types for Verilog export: {sorted(unsupported)}")

    luts = [c for c in cells.values() if c["type"] == LUT_CELL]
    dffs = [c for c in cells.values() if c["type"] == DFF_CELL]
    reg_bits = {c["connections"]["Q"][0] for c in dffs}
    all_bits = {b for p in ports.values() for b in p["bits"] if isinstance(b, int)}
    all_bits |= {b for c in luts + dffs for bs in c["connections"].values() for b in bs if isinstance(b, int)}

    lines = [f"module {_ident(module_name)} ({', '.join(_ident(p) for p in ports)});"]
    for port_name, port in ports.items():
        width = len(port["bits"])
        range_ = f"[{width - 1}:0] " if width > 1 else ""
        lines.append(f"  {port['direction']} {range_}{_ident(port_name)};")
    lines += [f"  {'reg' if b in reg_bits else 'wire'} n{b};" for b in sorted(all_bits)]

    for port_name, port in ports.items():
        for index, bit in enumerate(port["bits"]):
            select = f"[{index}]" if len(port["bits"]) > 1 else ""
            if port["direction"] == "input":
                lines.append(f"  assign n{bit} = {_ident(port_name)}{select};")

    for index, lut in enumerate(luts):
        table = lut["parameters"]["LUT"]
        address = ", ".join(_net(b) for b in reversed(lut["connections"]["A"]))
        lines.append(f"  localparam [{len(table) - 1}:0] LUT_{index} = {len(table)}'b{table};")
        lines.append(f"  assign {_net(lut['connections']['Y'][0])} = LUT_{index}[{{{address}}}];")

    for dff in dffs:
        connections = dff["connections"]
        clock = _net(connections["CLK"][0])
        lines.append(f"  always @(posedge {clock}) {_net(connections['Q'][0])} <= {_net(connections['D'][0])};")

    for port_name, port in ports.items():
        if port["direction"] == "output":
            for index, bit in enumerate(port["bits"]):
                select = f"[{index}]" if len(port["bits"]) > 1 else ""
                lines.append(f"  assign {_ident(port_name)}{select} = {_net(bit)};")

    lines.append("endmodule")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
