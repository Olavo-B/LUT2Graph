# /*****************************************************************************/
#  * File: main.py
#  * Author: Olavo Alves Barros Silva
#  * Contact: olavo.barros@ufv.com
#  * Date: 2026-05-31
#  * License: [License Type]
#  * Description: [Brief Description]
# /*****************************************************************************/

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path
from typing import Any

import networkx as nx
import numpy as np
import matplotlib.pyplot as plt

# ---------------------------------------------------------------------------
# Optional Pyvis import
# ---------------------------------------------------------------------------
try:
    from pyvis import network as pyvis_net  # type: ignore
    _PYVIS_AVAILABLE = True
except ImportError:
    _PYVIS_AVAILABLE = False

from lut2networkx import LUTGraphBuilder

# ---------------------------------------------------------------------------
# Parameterized font sizes for easy adjustments
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
    """Compute basic structural statistics of the graph.

    Parameters
    ----------
    G:
        A directed graph produced by :class:`LUTGraphBuilder`.

    Returns
    -------
    dict[str, Any]
        Keys: ``num_nodes``, ``num_edges``, ``density``,
        ``avg_degree``, ``avg_in_degree``, ``avg_out_degree``,
        ``max_in_degree``, ``max_out_degree``,
        ``node_type_counts``, ``degree_stats_by_type``.
    """
    in_degrees  = [d for _, d in G.in_degree()]
    out_degrees = [d for _, d in G.out_degree()]
    all_degrees = [i + o for i, o in zip(in_degrees, out_degrees)]

    # Per-type degree buckets
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
    """Compute connectivity and component statistics.

    Parameters
    ----------
    G:
        Directed graph to analyse.

    Returns
    -------
    dict[str, Any]
        Keys: ``num_wcc``, ``lcc_size``, ``component_sizes``,
        ``is_dag``, ``num_scc`` (strongly connected components).
    """
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
    """Compute clustering and path-length statistics.

    Uses the undirected projection of *G* so that standard clustering
    and Jaccard metrics apply.  Path length is computed on the LCC to
    avoid infinite distances between disconnected nodes.

    Parameters
    ----------
    G:
        Directed graph to analyse.

    Returns
    -------
    dict[str, Any]
        Keys: ``global_clustering``, ``clustering_coeffs``,
        ``avg_neighborhood_overlap``, ``overlaps``,
        ``avg_path_length_lcc``.
    """
    G_undir = G.to_undirected()

    clustering_coeffs = nx.clustering(G_undir)



    global_clustering = nx.average_clustering(G_undir)

    overlap_preds = nx.jaccard_coefficient(G_undir, G_undir.edges())
    overlaps      = [p for _, _, p in overlap_preds]
    avg_overlap   = float(np.mean(overlaps)) if overlaps else 0.0

    # Average path length on the LCC only
    lcc        = max(nx.weakly_connected_components(G), key=len)
    G_lcc      = G_undir.subgraph(lcc)
    avg_path   = nx.average_shortest_path_length(G_lcc)

    return {
        "global_clustering":        global_clustering,
        "clustering_coeffs":        clustering_coeffs,
        "avg_neighborhood_overlap": avg_overlap,
        "overlaps":                 overlaps,
        "avg_path_length_lcc":      avg_path,
    }


def compute_bias_stats(G: nx.DiGraph) -> dict[str, Any]:
    """Compute statistics over the Boolean Bias node attribute.

    Only LUT nodes carry a ``bias`` attribute; port nodes are skipped.

    Parameters
    ----------
    G:
        Directed graph produced by :class:`LUTGraphBuilder`.

    Returns
    -------
    dict[str, Any]
        Keys: ``biases``, ``mean_bias``, ``std_bias``,
        ``min_bias``, ``max_bias``.
        Returns empty lists / NaN values if no LUT nodes are found.
    """
    biases = [
        data["bias"]
        for _, data in G.nodes(data=True)
        if data.get("type") == "$lut" and "bias" in data
    ]

    if not biases:
        return {
            "biases":    [],
            "mean_bias": float("nan"),
            "std_bias":  float("nan"),
            "min_bias":  float("nan"),
            "max_bias":  float("nan"),
        }

    return {
        "biases":    biases,
        "mean_bias": float(np.mean(biases)),
        "std_bias":  float(np.std(biases)),
        "min_bias":  float(np.min(biases)),
        "max_bias":  float(np.max(biases)),
    }


def compute_weight_stats(G: nx.DiGraph) -> dict[str, Any]:
    """Compute statistics over Boolean Sensitivity edge weights.

    Parameters
    ----------
    G:
        Directed graph produced by :class:`LUTGraphBuilder`.

    Returns
    -------
    dict[str, Any]
        Keys: ``weights``, ``mean_weight``, ``std_weight``,
        ``min_weight``, ``max_weight``.
    """
    weights = [
        data.get("weight", 1.0)
        for _, _, data in G.edges(data=True)
    ]

    if not weights:
        return {
            "weights":    [],
            "mean_weight": float("nan"),
            "std_weight":  float("nan"),
            "min_weight":  float("nan"),
            "max_weight":  float("nan"),
        }

    return {
        "weights":     weights,
        "mean_weight": float(np.mean(weights)),
        "std_weight":  float(np.std(weights)),
        "min_weight":  float(np.min(weights)),
        "max_weight":  float(np.max(weights)),
    }


# ===========================================================================
# Report printer
# ===========================================================================

def print_report(
    basic: dict[str, Any],
    connectivity: dict[str, Any],
    clustering: dict[str, Any],
    bias: dict[str, Any],
    weights: dict[str, Any],
    graph_name: str = "",
) -> None:
    """Print a formatted statistics report to stdout.

    Parameters
    ----------
    basic:
        Output of :func:`compute_basic_stats`.
    connectivity:
        Output of :func:`compute_connectivity_stats`.
    clustering:
        Output of :func:`compute_clustering_stats`.
    bias:
        Output of :func:`compute_bias_stats`.
    weights:
        Output of :func:`compute_weight_stats`.
    graph_name:
        Optional label printed in the report header.
    """
    sep = "=" * 60

    print(sep)
    title = f"  Graph Statistics Report  —  {graph_name}" if graph_name else "  Graph Statistics Report"
    print(title)
    print(sep)

    # --- Basic ---
    print("\n[ Basic Structure ]")
    print(f"  Nodes            : {basic['num_nodes']:>10,}")
    print(f"  Edges            : {basic['num_edges']:>10,}")
    print(f"  Density          : {basic['density']:>10.6f}")
    print(f"  Avg Degree       : {basic['avg_degree']:>10.4f}")
    print(f"  Avg In-Degree    : {basic['avg_in_degree']:>10.4f}")
    print(f"  Avg Out-Degree   : {basic['avg_out_degree']:>10.4f}")
    print(f"  Max In-Degree    : {basic['max_in_degree']:>10}")
    print(f"  Max Out-Degree   : {basic['max_out_degree']:>10}")

    print("\n  Node type breakdown:")
    for t, count in sorted(basic["node_type_counts"].items()):
        print(f"    {t:>12s} : {count:,}")

    print("\n  Per-type degree averages:")
    for t, stats in sorted(basic["degree_stats_by_type"].items()):
        avg_in  = float(np.mean(stats["in_degree"]))
        avg_out = float(np.mean(stats["out_degree"]))
        print(f"    {t:>12s}  in={avg_in:.2f}  out={avg_out:.2f}")

    # --- Connectivity ---
    print("\n[ Connectivity ]")
    print(f"  Is DAG                         : {connectivity['is_dag']}")
    print(f"  Weakly Connected Components    : {connectivity['num_wcc']:>10,}")
    print(f"  Strongly Connected Components  : {connectivity['num_scc']:>10,}")
    print(f"  Largest WCC Size               : {connectivity['lcc_size']:>10,}")
    top5 = connectivity["component_sizes"][:5]
    print(f"  Top-5 Component Sizes          : {top5}")

    # --- Clustering / Path ---
    print("\n[ Clustering & Path Length ]")
    print(f"  Global Clustering Coefficient  : {clustering['global_clustering']:>10.6f}")
    print(f"  Avg Neighbourhood Overlap      : {clustering['avg_neighborhood_overlap']:>10.6f}")
    print(f"  Avg Path Length (LCC)          : {clustering['avg_path_length_lcc']:>10.4f}")

    # --- Boolean Bias ---
    print("\n[ Boolean Bias  (LUT nodes) ]")
    if bias["biases"]:
        print(f"  Mean : {bias['mean_bias']:.4f}")
        print(f"  Std  : {bias['std_bias']:.4f}")
        print(f"  Min  : {bias['min_bias']:.4f}")
        print(f"  Max  : {bias['max_bias']:.4f}")
    else:
        print("  No LUT nodes found.")

    # --- Edge Weights ---
    print("\n[ Boolean Sensitivity  (edge weights) ]")
    if weights["weights"]:
        print(f"  Mean : {weights['mean_weight']:.4f}")
        print(f"  Std  : {weights['std_weight']:.4f}")
        print(f"  Min  : {weights['min_weight']:.4f}")
        print(f"  Max  : {weights['max_weight']:.4f}")
    else:
        print("  No edges found.")

    print(f"\n{sep}\n")


# ===========================================================================
# Plotting
# ===========================================================================

def plot_degree_distribution(
    basic: dict[str, Any],
    results_path: Path,
    node_type: str = "$lut",
) -> None:
    """Save in/out-degree histograms for a given node type.

    Parameters
    ----------
    basic:
        Output of :func:`compute_basic_stats`.
    results_path:
        Directory where the PNG is saved.
    node_type:
        Which node type to plot (default ``'$lut'``).
    """
    stats = basic["degree_stats_by_type"].get(node_type)
    if stats is None:
        print(f"[plot] Node type '{node_type}' not in graph — skipping degree plot.")
        return

    in_deg  = stats["in_degree"]
    out_deg = stats["out_degree"]

    fig, (ax_in, ax_out) = plt.subplots(1, 2, figsize=(8, 4))

    ax_in.hist(in_deg,  bins=range(max(in_deg)  + 2), alpha=0.7, color="steelblue")
    ax_in.set_title(f"{node_type} — In-Degree Distribution")
    ax_in.set_xlabel("In-Degree")
    ax_in.set_ylabel("Frequency")

    ax_out.hist(out_deg, bins=range(max(out_deg) + 2), alpha=0.7, color="firebrick")
    ax_out.set_title(f"{node_type} — Out-Degree Distribution")
    ax_out.set_xlabel("Out-Degree")
    ax_out.set_ylabel("Frequency")

    plt.tight_layout()
    safe_type = node_type.lstrip("$")
    out_file  = results_path / f"degree_distribution_{safe_type}.png"
    plt.savefig(out_file)
    plt.close(fig)
    print(f"[plot] Degree distribution saved → {out_file}")

def plot_metrics_overview(
    basic: dict[str, Any],
    connectivity: dict[str, Any],
    clustering: dict[str, Any],
    results_path: Path,
) -> None:
    """Save separate plots of core network metrics with optimized scales.

    Plots generated: 
      1. Degree distribution (Log Scale)
      2. Clustering coefficients (ECDF with Mean)
      3. Component sizes (Log Scale)
      4. Neighbourhood overlap (Log Scale)

    Parameters
    ----------
    basic, connectivity, clustering:
        Outputs of the corresponding ``compute_*`` functions.
    results_path:
        Directory where the PNGs are saved.
    """
    # Ensure the output directory exists
    results_path.mkdir(parents=True, exist_ok=True)

    in_degrees  = []
    out_degrees = []
    for stats in basic["degree_stats_by_type"].values():
        in_degrees.extend(stats["in_degree"])
        out_degrees.extend(stats["out_degree"])

    # --- (a) Degree distribution (Log scale applied to Y-axis) ---
    fig, ax = plt.subplots(figsize=(6, 4))
    if in_degrees:
        ax.hist(in_degrees, bins=range(max(in_degrees) + 2),
                alpha=0.5, label="In-Degree", color="steelblue", log=True)
    if out_degrees:
        ax.hist(out_degrees, bins=range(max(out_degrees) + 2),
                alpha=0.5, label="Out-Degree", color="firebrick", log=True)
    ax.set_title("Degree Distribution")
    ax.set_xlabel("Degree")
    ax.set_ylabel("Frequency (log scale)")
    ax.legend()
    plt.tight_layout()
    
    deg_file = results_path / "degree_distribution.png"
    plt.savefig(deg_file)
    plt.close(fig)
    print(f"[plot] Degree distribution saved → {deg_file}")

    # --- (b) Clustering coefficient (ECDF with Mean) ---
    fig, ax = plt.subplots(figsize=(6, 4))
    coeffs = list(clustering["clustering_coeffs"].values())
    
    if coeffs:
        # Calculate the Empirical CDF
        x = np.sort(coeffs)
        y = np.arange(1, len(x) + 1) / len(x)
        ax.step(x, y, where="post", color="seagreen", linewidth=1.5)
        
        # Calculate and plot the mean
        mean_cc = np.mean(coeffs)
        ax.axvline(mean_cc, color="black", linestyle="--", linewidth=1.2, 
                   label=f"mean = {mean_cc:.3f}")
        ax.legend()
        
    ax.set_title("Clustering Coefficient ECDF")
    ax.set_xlabel("Clustering Coefficient")
    ax.set_ylabel("CDF")
    plt.tight_layout()
    
    cc_file = results_path / "clustering_coefficient_ecdf.png"
    plt.savefig(cc_file)
    plt.close(fig)
    print(f"[plot] Clustering ECDF saved → {cc_file}")

    # --- (c) Component sizes (log scale) ---
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.hist(connectivity["component_sizes"], bins=20, color="mediumpurple", log=True)
    ax.set_title("Component Size Distribution")
    ax.set_xlabel("Component Size")
    ax.set_ylabel("Frequency (log scale)")
    plt.tight_layout()
    
    comp_file = results_path / "component_size_distribution.png"
    plt.savefig(comp_file)
    plt.close(fig)
    print(f"[plot] Component sizes saved → {comp_file}")

    # --- (d) Neighbourhood overlap (Log scale applied to Y-axis) ---
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.hist(clustering["overlaps"], bins=20, color="darkorange", log=True)
    ax.set_title("Neighbourhood Overlap (Jaccard) Distribution")
    ax.set_xlabel("Overlap (Jaccard Index)")
    ax.set_ylabel("Frequency (log scale)")
    plt.tight_layout()
    
    over_file = results_path / "neighbourhood_overlap_distribution.png"
    plt.savefig(over_file)
    plt.close(fig)
    print(f"[plot] Neighbourhood overlap saved → {over_file}")

def plot_bias_distribution(
    bias: dict[str, Any],
    results_path: Path,
) -> None:
    """Save a histogram of Boolean Bias values across all LUT nodes.

    Parameters
    ----------
    bias:
        Output of :func:`compute_bias_stats`.
    results_path:
        Directory where the PNG is saved.
    """
    if not bias["biases"]:
        print("[plot] No LUT bias data — skipping bias plot.")
        return

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.hist(bias["biases"], bins=20, color="teal", alpha=0.8)
    ax.axvline(bias["mean_bias"], color="black", linestyle="--",
               linewidth=1, label=f"mean = {bias['mean_bias']:.3f}")
    ax.set_title("Boolean Bias Distribution (LUT nodes)")
    ax.set_xlabel("Bias")
    ax.set_ylabel("Frequency")
    ax.legend()
    plt.tight_layout()
    out_file = results_path / "bias_distribution.png"
    plt.savefig(out_file)
    plt.close(fig)
    print(f"[plot] Bias distribution saved → {out_file}")


def plot_weight_distribution(
    weights: dict[str, Any],
    results_path: Path,
) -> None:
    """Save a histogram of Boolean Sensitivity edge weights.

    Parameters
    ----------
    weights:
        Output of :func:`compute_weight_stats`.
    results_path:
        Directory where the PNG is saved.
    """
    if not weights["weights"]:
        print("[plot] No edge weight data — skipping weight plot.")
        return

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.hist(weights["weights"], bins=20, color="coral", alpha=0.8)
    ax.axvline(weights["mean_weight"], color="black", linestyle="--",
               linewidth=1, label=f"mean = {weights['mean_weight']:.3f}")
    ax.set_title("Boolean Sensitivity Distribution (edge weights)")
    ax.set_xlabel("Sensitivity")
    ax.set_ylabel("Frequency")
    ax.legend()
    plt.tight_layout()
    out_file = results_path / "weight_distribution.png"
    plt.savefig(out_file)
    plt.close(fig)
    print(f"[plot] Weight distribution saved → {out_file}")


# ===========================================================================
# Export helpers
# ===========================================================================

def export_gexf(G: nx.DiGraph, results_path: Path) -> None:
    """Export *G* to GEXF format for Gephi.

    Parameters
    ----------
    G:
        Graph to export.
    results_path:
        Output directory.
    """
    out_file = results_path / "graph.gexf"
    nx.write_gexf(G, out_file)
    print(f"[export] GEXF saved → {out_file}")


def export_graphml(G: nx.DiGraph, results_path: Path) -> None:
    """Export *G* to GraphML format.

    Parameters
    ----------
    G:
        Graph to export.
    results_path:
        Output directory.
    """
    out_file = results_path / "graph.graphml"
    nx.write_graphml(G, out_file)
    print(f"[export] GraphML saved → {out_file}")


def export_interactive_html(
    G: nx.DiGraph,
    results_path: Path,
    filename: str = "graph_visualization.html",
) -> None:
    """Export an interactive Pyvis HTML visualisation of *G*.

    Parameters
    ----------
    G:
        Graph to visualise.
    results_path:
        Output directory.
    filename:
        HTML filename (default ``'graph_visualization.html'``).

    Raises
    ------
    ImportError
        If ``pyvis`` is not installed.
    """
    if not _PYVIS_AVAILABLE:
        print("[export] pyvis not installed — skipping interactive HTML.")
        return

    out_file = results_path / filename
    nt = pyvis_net.Network(notebook=False, directed=True)
    nt.from_nx(G)
    nt.save_graph(str(out_file))
    print(f"[export] Interactive HTML saved → {out_file}")


# ===========================================================================
# CLI argument parser
# ===========================================================================

def _build_parser() -> argparse.ArgumentParser:
    """Construct and return the CLI argument parser.

    Returns
    -------
    argparse.ArgumentParser
        Configured parser instance.
    """
    parser = argparse.ArgumentParser(
        prog="main.py",
        description=(
            "Build a NetworkX graph from a Yosys JSON netlist, "
            "compute complex-network statistics, and optionally export results."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # Required
    parser.add_argument(
        "json_path",
        type=Path,
        help="Path to the Yosys *.json netlist file.",
    )

    # Optional
    parser.add_argument(
        "--results-path",
        type=Path,
        default=Path("results"),
        metavar="DIR",
        help="Directory where plots and export files are saved.",
    )
    parser.add_argument(
        "--graph-name",
        type=str,
        default="",
        metavar="NAME",
        help="Human-readable label used in report header and filenames.",
    )
    parser.add_argument(
        "--no-plots",
        action="store_true",
        help="Skip all plot generation.",
    )
    parser.add_argument(
        "--export-gexf",
        action="store_true",
        help="Export the graph to GEXF (Gephi-compatible).",
    )
    parser.add_argument(
        "--export-graphml",
        action="store_true",
        help="Export the graph to GraphML.",
    )
    parser.add_argument(
        "--visualize",
        action="store_true",
        help="Generate an interactive Pyvis HTML visualisation.",
    )
    parser.add_argument(
        "--skip-heavy",
        action="store_true",
        help=(
            "Skip computationally heavy metrics "
            "(avg path length, neighbourhood overlap). "
            "Useful for very large graphs."
        ),
    )

    return parser


# ===========================================================================
# Main
# ===========================================================================

def main(argv: list[str] | None = None) -> int:
    """Run the full LUT-graph statistics pipeline.

    Parameters
    ----------
    argv:
        Argument list (defaults to ``sys.argv[1:]`` when ``None``).

    Returns
    -------
    int
        Exit code: ``0`` on success, ``1`` on error.
    """
    parser = _build_parser()
    args   = parser.parse_args(argv)

    results_path: Path = args.results_path
    results_path.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 1. Build graph
    # ------------------------------------------------------------------
    print(f"\n[build] Loading netlist: {args.json_path}")
    try:
        builder = LUTGraphBuilder(args.json_path, results_path)
        G       = builder.build()
    except FileNotFoundError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1
    except KeyError as exc:
        print(f"[error] Unexpected JSON structure — missing key {exc}", file=sys.stderr)
        return 1

    print(f"[build] Graph ready: {G.number_of_nodes()} nodes, "
          f"{G.number_of_edges()} edges")

    # ------------------------------------------------------------------
    # 2. Compute statistics
    # ------------------------------------------------------------------
    print("\n[stats] Computing basic statistics …")
    basic = compute_basic_stats(G)

    print("[stats] Computing connectivity …")
    connectivity = compute_connectivity_stats(G)

    bias    = compute_bias_stats(G)
    weights = compute_weight_stats(G)

    clustering: dict[str, Any]
    if args.skip_heavy:
        print("[stats] Skipping heavy metrics (--skip-heavy).")
        clustering = {
            "global_clustering":        float("nan"),
            "clustering_coeffs":        {},
            "avg_neighborhood_overlap": float("nan"),
            "overlaps":                 [],
            "avg_path_length_lcc":      float("nan"),
        }
    else:
        print("[stats] Computing clustering & path length (may be slow) …")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            clustering = compute_clustering_stats(G)

    # ------------------------------------------------------------------
    # 3. Print report
    # ------------------------------------------------------------------
    print_report(basic, connectivity, clustering, bias, weights,
                 graph_name=args.graph_name)

    # ------------------------------------------------------------------
    # 4. Plots
    # ------------------------------------------------------------------
    if not args.no_plots:
        print("[plots] Generating plots …")
        plot_degree_distribution(basic, results_path)
        plot_bias_distribution(bias, results_path)
        plot_weight_distribution(weights, results_path)

        if not args.skip_heavy:
            plot_metrics_overview(basic, connectivity, clustering, results_path)

    # ------------------------------------------------------------------
    # 5. Exports
    # ------------------------------------------------------------------
    if args.export_gexf:
        export_gexf(G, results_path)

    if args.export_graphml:
        export_graphml(G, results_path)

    if args.visualize:
        export_interactive_html(G, results_path)

    print("[done] Pipeline complete.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())