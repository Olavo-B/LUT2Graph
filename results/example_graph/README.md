# Graph Statistics Report: paviaU

![Graph Visualization of paviaU](gephi-lite-export.jpg)

## Basic Structure

This section details the fundamental structural properties of the paviaU graph.

* **Nodes:** 2,674
* **Edges:** 4,646
* **Density:** 0.000650
* **Avg Degree:** 3.4749
* **Avg In-Degree:** 1.7375
* **Avg Out-Degree:** 1.7375
* **Max In-Degree:** 6
* **Max Out-Degree:** 27

### Node Type Breakdown

| Node Type | Count |
| :--- | :--- |
| `$lut` | 1,022 |
| `input` | 1,648 |
| `output` | 4 |

### Per-Type Degree Averages

| Node Type | Avg In-Degree | Avg Out-Degree |
| :--- | :--- | :--- |
| `$lut` | 4.54 | 3.37 |
| `input` | 0.00 | 0.73 |
| `output` | 1.00 | 0.00 |

---

## Connectivity

Connectivity properties describe how the nodes are linked and the overall component structure of the network.

* **Is DAG (Directed Acyclic Graph):** True
* **Weakly Connected Components (WCC):** 732
* **Strongly Connected Components (SCC):** 2,674
* **Largest WCC Size:** 1,943
* **Top-5 Component Sizes:** [1943, 1, 1, 1, 1]

---

## Clustering & Path Length

These metrics analyze the tendency of nodes to form clusters and the navigation efficiency within the network.

* **Global Clustering Coefficient:** 0.003662
* **Avg Neighbourhood Overlap:** 0.002798
* **Avg Path Length (LCC):** 6.3909

---

## Boolean Bias (LUT nodes)

Statistical analysis of the boolean bias for Look-Up Table (LUT) nodes.

* **Mean:** 0.3228
* **Std:** 0.1907
* **Min:** 0.0156
* **Max:** 0.9375

---

## Boolean Sensitivity (edge weights)

Statistical analysis of the boolean sensitivity, reflected in the edge weights.

* **Mean:** 0.3107
* **Std:** 0.2505
* **Min:** 0.0312
* **Max:** 1.0000
