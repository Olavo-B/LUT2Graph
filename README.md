# LUT2Graph

![Logo](misc/doc/imgs/logo.png)

This repository contains the code for the final project of the course **INF 791 - Redes Complexas** at the Universidade Federal de Viçosa (UFV) in the 2026/1 semester.

The project consists of a tool that converts a Look-Up Table (LUT) netlist — produced by the [Yosys](https://yosyshq.net/yosys/) synthesis tool — into an annotated directed graph representation. Each LUT cell becomes a node, each inter-cell connection becomes a weighted edge, and primary I/O ports are registered as boundary nodes. The resulting graph is then analysed using complex-network metrics to guide pruning and optimisation of the circuit.

> **Author:** Olavo Alves Barros Silva — [olavo.barros@ufv.br](mailto:olavo.barros@ufv.br)

---

## Table of Contents

- [Installation](#installation)
- [Usage](#usage)
- [Theoretical Background](#theoretical-background)
  - [LUT](#lut)
  - [Graph Representation](#graph-representation)
  - [Main Concepts](#main-concepts)
- [Repository Structure](#repository-structure)
- [Results](#results)

---

## Installation

**Requirements:** Python ≥ 3.10

### 1. Clone the repository

```bash
git clone https://github.com/<your-username>/lut2graph.git
cd lut2graph
```

### 2. Create a virtual environment (recommended)

```bash
python -m venv .venv
source .venv/bin/activate      # Linux / macOS
.venv\Scripts\activate         # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

Core dependencies:

| Package | Purpose |
|---|---|
| `networkx` | Graph construction and analysis |
| `numpy` | Numerical statistics |
| `matplotlib` | Static plots |
| `pyvis` | Interactive HTML visualisation (optional) |

### 4. Install Yosys (for synthesis)

If you need to synthesise your own designs into JSON netlists, install [Yosys](https://yosyshq.net/yosys/download.html).  
Pre-synthesised example netlists are provided in `misc/data/`.

---

## Usage

### Command-line interface

```bash
python src/main.py <json_path> [options]
```

**Arguments:**

| Argument | Description |
|---|---|
| `json_path` | Path to a Yosys `*.json` netlist |
| `--results-path DIR` | Output directory for plots and exports (default: `results/`) |
| `--graph-name NAME` | Label used in the report header |
| `--no-plots` | Skip all plot generation |
| `--export-gexf` | Export graph to GEXF (Gephi-compatible) |
| `--export-graphml` | Export graph to GraphML |
| `--visualize` | Generate an interactive Pyvis HTML visualisation |
| `--skip-heavy` | Skip slow metrics (path length, Jaccard overlap) for large graphs |

**Example:**

```bash
python src/main.py misc/data/paviaU_.json \
    --results-path results/paviaU_ \
    --graph-name paviaU_ \
    --export-gexf \
    --visualize
```

### Python API

```python
from lut2networkx import LUTGraphBuilder

# Build the graph
builder = LUTGraphBuilder("misc/data/paviaU_.json", results_path="results/paviaU_")
G = builder.build()

# Inspect
print(G.number_of_nodes(), G.number_of_edges())

# Export
builder.export_gexf()
```

---

## Theoretical Background

### LUT

A **Look-Up Table (LUT)** is the fundamental building block of Field-Programmable Gate Arrays (FPGAs). A $k$-input LUT stores a truth table of $2^k$ binary values and can implement any Boolean function of up to $k$ variables. Modern synthesis tools (such as Yosys + ABC) map arbitrary combinational logic to networks of LUTs during technology mapping.

In the Yosys JSON format, each LUT cell is represented by:
- a `LUT` parameter — a binary string of length $2^k$ encoding the truth table;
- an `A` connection — a list of $k$ input signal identifiers;
- a `Y` connection — the output signal identifier.

### Graph Representation

The netlist is modelled as a **directed graph** $G = (V, E)$ where:

- **Nodes $V$** represent signals:
  - `input` — primary input ports (blue).
  - `output` — primary output ports (red).
  - `$lut` — internal LUT cells (green), annotated with their *Boolean Bias*.

- **Edges $E$** represent data-flow dependencies from a driver signal to a driven LUT input, annotated with their *Boolean Sensitivity*.

This formulation preserves the combinational depth (critical path), fan-in/fan-out structure, and the functional character of each gate — going beyond a purely structural graph.

### Main Concepts

#### Boolean Bias

The **Boolean Bias** of a LUT is the fraction of output bits that equal `1` in its truth table:

$$\beta = \frac{|\{i : \text{LUT}[i] = 1\}|}{2^k}$$

A bias near $0$ or $1$ indicates highly predictable, potentially redundant logic. A bias near $0.5$ indicates balanced logic. Bias is stored as a node attribute and drives node-level analysis.

#### Boolean Sensitivity

The **Boolean Sensitivity** (or *influence*) of input $j$ of a LUT measures the probability that flipping bit $j$ of a uniformly random input vector also flips the output:

$$\sigma_j = \frac{1}{2^{k-1}} \sum_{\substack{x \in \{0,1\}^k \\ x_j = 0}} \mathbf{1}[\text{LUT}(x) \neq \text{LUT}(x \oplus e_j)]$$

where $e_j$ is the unit vector with a $1$ in position $j$. High sensitivity means the edge carries more functional weight. Sensitivity is stored as the `weight` attribute on each edge.

#### Complex-Network Metrics

The following metrics from complex-network theory are computed over the resulting graph:

| Metric | Description |
|---|---|
| **Degree distribution** | In- and out-degree histograms, per node type |
| **Density** | Fraction of possible edges that are present |
| **Weakly / Strongly Connected Components** | Number and size of WCC/SCC |
| **Is DAG** | Whether the graph is a directed acyclic graph (always true for acyclic circuits) |
| **Global Clustering Coefficient** | Average local clustering over the undirected projection |
| **Average Path Length** | Mean shortest path in the Largest Connected Component |
| **Neighbourhood Overlap (Jaccard)** | Mean Jaccard coefficient over all edges — measures local redundancy |
| **Boolean Bias statistics** | Mean, std, min, max of $\beta$ across all LUT nodes |
| **Edge Weight statistics** | Mean, std, min, max of $\sigma_j$ across all edges |

These metrics guide the pruning strategy: edges with low sensitivity and nodes with extreme bias are natural candidates for removal without significant functional loss.

---

## Repository Structure

```
.
├── misc
│   ├── data                   # Pre-synthesised Yosys JSON netlists
│   ├── doc
│   │   └── imgs               # Documentation images (logo, diagrams)
│   └── examples               # Pyvis interactive HTML output examples
│       └── lib
│           ├── bindings
│           ├── tom-select
│           └── vis-9.1.2
├── results
│   ├── example_graph          # Analysis outputs for the example netlist
│   │   └── vis                # Pyvis HTML visualisation assets
│   └── result
│       └── vis
├── src
│   ├── lut2networkx.py        # LUTGraphBuilder class
│   └── main.py                # CLI entry-point and statistics pipeline
└── test                       # Unit tests
```

### Key source files

| File | Role |
|---|---|
| `src/lut2networkx.py` | `LUTGraphBuilder` — parses the Yosys JSON, registers nodes/edges with Boolean Bias and Sensitivity annotations, and exposes the `networkx.DiGraph` |
| `src/main.py` | CLI pipeline — builds the graph, computes all metrics, prints a formatted report, and saves plots + exports |


---

## Results

Results and analysis results for the provided example netlist (`misc/data/paviaU_.json`) are available in the `results/example_graph/` directory

## License

MIT License — see `LICENSE` for details.