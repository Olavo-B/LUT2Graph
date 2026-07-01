# /*****************************************************************************/
#  * File: graph_metrics.py
#  * Description: Complex-network statistics and plotting helpers for LUTGraph.
# /*****************************************************************************/

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any

import networkx as nx
import numpy as np
import matplotlib.pyplot as plt

# ---------------------------------------------------------------------------
# Plotting Configuration
# ---------------------------------------------------------------------------
FONT_SIZE_BASE = 8
LABEL_SIZE = 8
TITLE_SIZE = 8
LEGEND_SIZE = 7
TICK_SIZE = 7

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["DejaVu Serif"],
    "text.usetex": False,
    "svg.fonttype": "none",
    "font.size": FONT_SIZE_BASE,
    "axes.labelsize": LABEL_SIZE,
    "axes.titlesize": TITLE_SIZE,
    "legend.fontsize": LEGEND_SIZE,
    "xtick.labelsize": TICK_SIZE,
    "ytick.labelsize": TICK_SIZE,
    "lines.linewidth": 1,
    "axes.grid": True,
    "grid.linewidth": 0.3,
    "figure.dpi": 300,
    "savefig.dpi": 300,
})

# ===========================================================================
# Statistics helpers
# ===========================================================================

def compute_basic_stats(G: nx.DiGraph) -> dict[str, Any]:
    in_degrees  = [d for _, d in G.in_degree()]
    out_degrees = [d for _, d in G.out_degree()]
    all_degrees = [i + o for i, o in zip(in_degrees, out_degrees)]

    type_counts: dict[str, int] = {}
    degree_stats: dict[str, dict[str, list[int]]] = {}
    for node, data in G.nodes(data=True):
        t = data.get("type", "unknown")
        type_counts[t] = type_counts.get(t, 0) + 1
        if t not in degree_stats:
            degree_stats[t] = {"in_degree": [], "out_degree": []}
        degree_stats[t]["in_degree"].append(G.in_degree(node))
        degree_stats[t]["out_degree"].append(G.out_degree(node))

    return {
        "num_nodes":           G.number_of_nodes(),
        "num_edges":           G.number_of_edges(),
        "density":             nx.density(G),
        "avg_degree":          float(np.mean(all_degrees))   if all_degrees  else 0.0,
        "avg_in_degree":       float(np.mean(in_degrees))    if in_degrees   else 0.0,
        "avg_out_degree":      float(np.mean(out_degrees))   if out_degrees  else 0.0,
        "max_in_degree":       int(max(in_degrees))          if in_degrees   else 0,
        "max_out_degree":      int(max(out_degrees))         if out_degrees  else 0,
        "node_type_counts":    type_counts,
        "degree_stats_by_type": degree_stats,
    }

def compute_connectivity_stats(G: nx.DiGraph) -> dict[str, Any]:
    wccs           = list(nx.weakly_connected_components(G))
    component_sizes = sorted([len(c) for c in wccs], reverse=True)
    lcc_size        = component_sizes[0] if component_sizes else 0
    sccs    = list(nx.strongly_connected_components(G))
    is_dag  = nx.is_directed_acyclic_graph(G)

    return {
        "num_wcc":          len(wccs),
        "lcc_size":         lcc_size,
        "component_sizes":  component_sizes,
        "is_dag":           is_dag,
        "num_scc":          len(sccs),
    }

def compute_clustering_stats(G: nx.DiGraph) -> dict[str, Any]:
    if G.number_of_nodes() == 0:
        return {
            "global_clustering": 0.0, "clustering_coeffs": {},
            "avg_neighborhood_overlap": 0.0, "overlaps": [], "avg_path_length_lcc": 0.0,
        }

    G_undir = G.to_undirected()
    clustering_coeffs = nx.clustering(G_undir)
    global_clustering = nx.average_clustering(G_undir)

    overlap_preds = nx.jaccard_coefficient(G_undir, G_undir.edges())
    overlaps      = [p for _, _, p in overlap_preds]
    avg_overlap   = float(np.mean(overlaps)) if overlaps else 0.0

    wccs = list(nx.weakly_connected_components(G))
    if not wccs:
        avg_path = 0.0
    else:
        lcc        = max(wccs, key=len)
        G_lcc      = G_undir.subgraph(lcc)
        avg_path   = nx.average_shortest_path_length(G_lcc) if len(G_lcc) > 1 else 0.0

    return {
        "global_clustering":        global_clustering,
        "clustering_coeffs":        clustering_coeffs,
        "avg_neighborhood_overlap": avg_overlap,
        "overlaps":                 overlaps,
        "avg_path_length_lcc":      avg_path,
    }

def compute_bias_stats(G: nx.DiGraph) -> dict[str, Any]:
    biases = [
        data["bias"]
        for _, data in G.nodes(data=True)
        if data.get("type") == "$lut" and "bias" in data
    ]
    if not biases:
        return {"biases": [], "mean_bias": float("nan"), "std_bias": float("nan"),
                "min_bias": float("nan"), "max_bias": float("nan")}
    return {
        "biases": biases, "mean_bias": float(np.mean(biases)),
        "std_bias": float(np.std(biases)), "min_bias": float(np.min(biases)),
        "max_bias": float(np.max(biases)),
    }

def compute_weight_stats(G: nx.DiGraph) -> dict[str, Any]:
    weights = [data.get("weight", 1.0) for _, _, data in G.edges(data=True)]
    if not weights:
        return {"weights": [], "mean_weight": float("nan"), "std_weight": float("nan"),
                "min_weight": float("nan"), "max_weight": float("nan")}
    return {
        "weights": weights, "mean_weight": float(np.mean(weights)),
        "std_weight": float(np.std(weights)), "min_weight": float(np.min(weights)),
        "max_weight": float(np.max(weights)),
    }

# ===========================================================================
# Report printer
# ===========================================================================

def print_report(
    basic: dict[str, Any], connectivity: dict[str, Any],
    clustering: dict[str, Any], bias: dict[str, Any],
    weights: dict[str, Any], graph_name: str = "",
) -> None:
    sep = "=" * 60
    print(sep)
    title = f"  Graph Statistics Report  —  {graph_name}" if graph_name else "  Graph Statistics Report"
    print(title)
    print(sep)

    print("\n[ Basic Structure ]")
    print(f"  Nodes            : {basic['num_nodes']:>10,}")
    print(f"  Edges            : {basic['num_edges']:>10,}")
    print(f"  Density          : {basic['density']:>10.6f}")
    
    print("\n  Node type breakdown:")
    for t, count in sorted(basic["node_type_counts"].items()):
        print(f"    {t:>12s} : {count:,}")

    print("\n[ Connectivity ]")
    print(f"  Is DAG                         : {connectivity['is_dag']}")
    print(f"  Largest WCC Size               : {connectivity['lcc_size']:>10,}")
    
    print("\n[ Clustering & Path Length ]")
    print(f"  Global Clustering Coefficient  : {clustering['global_clustering']:>10.6f}")
    print(f"  Avg Path Length (LCC)          : {clustering['avg_path_length_lcc']:>10.4f}")

    print("\n[ Boolean Bias  (LUT nodes) ]")
    if bias["biases"]:
        print(f"  Mean : {bias['mean_bias']:.4f} | Std : {bias['std_bias']:.4f}")
    else:
        print("  No LUT nodes found.")

    print("\n[ Boolean Sensitivity  (edge weights) ]")
    if weights["weights"]:
        print(f"  Mean : {weights['mean_weight']:.4f} | Std : {weights['std_weight']:.4f}")
    else:
        print("  No edges found.")
    print(f"\n{sep}\n")

# ===========================================================================
# Plotting
# ===========================================================================

def plot_degree_distribution(basic: dict[str, Any], results_path: Path, node_type: str = "$lut") -> None:
    stats = basic["degree_stats_by_type"].get(node_type)
    if not stats: return
    
    fig, (ax_in, ax_out) = plt.subplots(1, 2, figsize=(8, 4))
    ax_in.hist(stats["in_degree"], bins=range(max(stats["in_degree"]) + 2), alpha=0.7, color="steelblue")
    ax_in.set_title(f"{node_type} — In-Degree Distribution")
    ax_out.hist(stats["out_degree"], bins=range(max(stats["out_degree"]) + 2), alpha=0.7, color="firebrick")
    ax_out.set_title(f"{node_type} — Out-Degree Distribution")
    
    plt.tight_layout()
    out_file = results_path / f"degree_distribution_{node_type.lstrip('$')}.png"
    plt.savefig(out_file)
    plt.close(fig)

def plot_metrics_overview(basic: dict[str, Any], connectivity: dict[str, Any], clustering: dict[str, Any], results_path: Path) -> None:
    results_path.mkdir(parents=True, exist_ok=True)
    in_degrees, out_degrees = [], []
    for stats in basic["degree_stats_by_type"].values():
        in_degrees.extend(stats["in_degree"])
        out_degrees.extend(stats["out_degree"])

    fig, ax = plt.subplots(figsize=(6, 4))
    if in_degrees: ax.hist(in_degrees, bins=range(max(in_degrees) + 2), alpha=0.5, label="In-Degree", color="steelblue", log=True)
    if out_degrees: ax.hist(out_degrees, bins=range(max(out_degrees) + 2), alpha=0.5, label="Out-Degree", color="firebrick", log=True)
    ax.set_title("Degree Distribution")
    ax.legend()
    plt.savefig(results_path / "degree_distribution.png")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(6, 4))
    coeffs = list(clustering["clustering_coeffs"].values())
    if coeffs:
        x, y = np.sort(coeffs), np.arange(1, len(coeffs) + 1) / len(coeffs)
        ax.step(x, y, where="post", color="seagreen")
        ax.axvline(np.mean(coeffs), color="black", linestyle="--")
    ax.set_title("Clustering Coefficient ECDF")
    plt.savefig(results_path / "clustering_coefficient_ecdf.png")
    plt.close(fig)

def plot_bias_distribution(bias: dict[str, Any], results_path: Path) -> None:
    if not bias["biases"]: return
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.hist(bias["biases"], bins=20, color="teal", alpha=0.8)
    ax.axvline(bias["mean_bias"], color="black", linestyle="--")
    ax.set_title("Boolean Bias Distribution")
    plt.savefig(results_path / "bias_distribution.png")
    plt.close(fig)

def plot_weight_distribution(weights: dict[str, Any], results_path: Path) -> None:
    if not weights["weights"]: return
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.hist(weights["weights"], bins=20, color="coral", alpha=0.8)
    ax.axvline(weights["mean_weight"], color="black", linestyle="--")
    ax.set_title("Boolean Sensitivity Distribution")
    plt.savefig(results_path / "weight_distribution.png")
    plt.close(fig)