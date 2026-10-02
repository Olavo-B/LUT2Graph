import json
from pathlib import Path

import pytest

import context  # noqa: F401  (adds src/ to sys.path)
from lut2networkx import LUTGraphBuilder
from netlist_export import pipeline_netlist, write_verilog
from netlist_sim import verify_pipeline
from retime import level_to_stage, schedule_graph, summarize

ROOT = Path(__file__).resolve().parents[1]
BRANCH_JOIN = ROOT / "misc" / "examples" / "branch_join_moc.json"
PAVIA = ROOT / "misc" / "data" / "paviaU_.json"

# branch_join: c = a(x0, x1) & b3(b2(b1(x2))) -> depth 4
# bits: x0=2 x1=3 x2=4 | a=5 b1=6 b2=7 b3=8 c=10


@pytest.fixture
def branch_join_graph(tmp_path):
    return LUTGraphBuilder(BRANCH_JOIN, results_path=tmp_path).build()


def test_asap_alap_levels(branch_join_graph):
    schedule = schedule_graph(branch_join_graph, "asap", levels_per_stage=1)
    assert {n: (schedule[n].asap, schedule[n].alap) for n in (5, 6, 7, 8, 10)} == {
        5: (1, 3), 6: (1, 1), 7: (2, 2), 8: (3, 3), 10: (4, 4),
    }


def test_level_to_stage_modes():
    assert level_to_stage(5, levels_per_stage=2) == [0, 0, 0, 1, 1, 2]
    assert level_to_stage(5, num_stages=4) == [0, 0, 0, 1, 2, 3]
    with pytest.raises(ValueError):
        level_to_stage(5, num_stages=6)
    with pytest.raises(ValueError):
        level_to_stage(5, levels_per_stage=2, num_stages=2)


@pytest.mark.parametrize("policy, expected_flip_flops", [("asap", 2), ("alap", 3)])
def test_branch_join_register_count(branch_join_graph, policy, expected_flip_flops):
    schedule = schedule_graph(branch_join_graph, policy, levels_per_stage=2)
    summary = summarize(branch_join_graph, schedule)
    assert summary["num_stages"] == 2 and summary["max_comb_depth"] == 2

    design = json.loads(BRANCH_JOIN.read_text())
    stage_of_bit = {n: s.stage for n, s in schedule.items() if isinstance(n, int)}
    pipelined, flip_flops = pipeline_netlist(design, stage_of_bit, summary["latency_cycles"])
    assert flip_flops == expected_flip_flops
    verify_pipeline(design, pipelined, summary["latency_cycles"], num_vectors=32)


@pytest.mark.parametrize("policy", ["asap", "alap"])
@pytest.mark.parametrize("cut", [{"levels_per_stage": 1}, {"levels_per_stage": 3}, {"num_stages": 2}])
def test_pavia_pipeline_is_equivalent(tmp_path, policy, cut):
    G = LUTGraphBuilder(PAVIA, results_path=tmp_path).build()
    schedule = schedule_graph(G, policy, **cut)
    summary = summarize(G, schedule)
    design = json.loads(PAVIA.read_text())
    stage_of_bit = {n: s.stage for n, s in schedule.items() if G.nodes[n]["type"] != "output"}
    pipelined, _ = pipeline_netlist(design, stage_of_bit, summary["latency_cycles"])
    verify_pipeline(design, pipelined, summary["latency_cycles"], num_vectors=50)
    write_verilog(pipelined, tmp_path / "pavia.v")
