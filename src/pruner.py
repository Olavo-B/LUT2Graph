# /*****************************************************************************/
#  * File: pruner.py
#  * Author: Olavo Alves Barros Silva
#  * Contact: olavo.barros@ufv.com
#  * Date: 2026-05-27
#  * License: MIT
#  * Description: This class is responsible to make all prune strategies in the 
#  * LUT graph
# /*****************************************************************************/

import networkx as nx

def apply_hardware_aware_pruning(G_original, sens_threshold=0.05, bias_lower=0.05, bias_upper=0.95):
    """
    Applies hardware-aware pruning to the LUT graph.
    Instead of removing extreme bias nodes, it converts them to Stuck-at constants.
    Protects critical paths (bridges) from being removed due to low sensitivity.
    """
    G = G_original.copy()
    nodes_to_const_0 = []
    nodes_to_const_1 = []
    edges_to_remove = []

    # 1. Identify nodes for Stuck-at Faults based on Boolean Bias
    for n, data in G.nodes(data=True):
        if data.get('type') == '$lut':
            bias = data.get('bias', 0.5)
            if bias < bias_lower:
                nodes_to_const_0.append(n)
            elif bias > bias_upper:
                nodes_to_const_1.append(n)

    # 2. Convert extreme bias nodes to constants (0 or 1)
    # By removing their incoming edges, they become independent source nodes
    for n in nodes_to_const_0:
        G.nodes[n]['type'] = 'const_0'
        in_edges = list(G.in_edges(n))
        G.remove_edges_from(in_edges)

    for n in nodes_to_const_1:
        G.nodes[n]['type'] = 'const_1'
        in_edges = list(G.in_edges(n))
        G.remove_edges_from(in_edges)

    # 3. Identify critical structural bridges to protect the Largest WCC Size
    undirected_G = G.to_undirected()
    bridges = set(nx.bridges(undirected_G))

    # 4. Evaluate edges for pruning based on Boolean Sensitivity
    for u, v, data in G.edges(data=True):
        # Skip if the target node has already been transformed into a constant
        if G.nodes[v].get('type') in ['const_0', 'const_1']:
            continue
            
        weight = data.get('weight', 1.0) # Weight represents Boolean Sensitivity
        
        if weight < sens_threshold:
            # Protect the edge if it is a structural bridge
            if (u, v) not in bridges and (v, u) not in bridges:
                edges_to_remove.append((u, v))

    # 5. Apply edge pruning
    G.remove_edges_from(edges_to_remove)

    stuck_at_count = len(nodes_to_const_0) + len(nodes_to_const_1)
    pruned_edges_count = len(edges_to_remove)
    
    return G, stuck_at_count, pruned_edges_count