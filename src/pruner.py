import networkx as nx
import logging
import math

def apply_hardware_aware_pruning(G, sens_threshold, bias_lower, bias_upper):
    """
    Baseline Method: Prunes edges based on Boolean Sensitivity and 
    converts extreme bias nodes to Stuck-at Faults (0 or 1).
    Preserves structural bridges to maintain graph connectivity.
    """
    G_pruned = G.copy()
    stuck_at_count = 0
    pruned_edges = 0

    # 1. Node Pruning via Stuck-at Faults (Boolean Bias)
    lut_nodes = [n for n, d in G_pruned.nodes(data=True) if d.get('type') == 'lut']
    for node in lut_nodes:
        bias = G_pruned.nodes[node].get('bias', 0.5)
        
        if bias <= bias_lower or bias >= bias_upper:
            # Decide constant based on bias tendency
            const_val = 0 if bias <= bias_lower else 1
            
            # Convert to constant node
            G_pruned.nodes[node]['type'] = f'const_{const_val}'
            G_pruned.nodes[node]['lut_str'] = str(const_val)
            
            # Remove structural edges (isolating the node logically)
            in_edges = list(G_pruned.in_edges(node))
            out_edges = list(G_pruned.out_edges(node))
            
            pruned_edges += len(in_edges) + len(out_edges)
            G_pruned.remove_edges_from(in_edges)
            G_pruned.remove_edges_from(out_edges)
            
            stuck_at_count += 1

    # 2. Edge Pruning (Boolean Sensitivity) with Bridge Protection
    undirected_G = G_pruned.to_undirected()
    bridges = list(nx.bridges(undirected_G))
    
    edges_to_remove = []
    for u, v, data in G_pruned.edges(data=True):
        sens = data.get('weight', 1.0) # Weight is the Sensitivity
        
        # If sensitivity is low AND it's not a critical structural bridge
        if sens < sens_threshold:
            if (u, v) not in bridges and (v, u) not in bridges:
                edges_to_remove.append((u, v))

    # G_pruned.remove_edges_from(edges_to_remove)
    pruned_edges += len(edges_to_remove)

    return G_pruned, stuck_at_count, pruned_edges


def apply_kcore_pruning(G, max_shell=1):
    """
    K-Core Method: Decomposes the graph and prunes the outermost shells.
    Nodes in shells <= max_shell are converted to Stuck-at Faults 
    based on their Boolean Bias (Hybrid topology-logic approach).
    """
    G_pruned = G.copy()
    
    # Calculate the core number for each node in the DAG
    core_numbers = nx.core_number(G_pruned)
    
    stuck_at_count = 0
    pruned_edges = 0

    # Identify LUT nodes that belong to the outer shells
    target_nodes = [
        n for n, core_val in core_numbers.items() 
        if core_val <= max_shell and G_pruned.nodes[n].get('type') == 'lut'
    ]

    for node in target_nodes:
        
        # Hybrid Stuck-at: Decide constant based on bias tendency
        bias = G_pruned.nodes[node].get('bias', 0.5)
        const_val = 1 if bias >= 0.5 else 0
        
        # Convert to constant node (Changing Type and Value)
        G_pruned.nodes[node]['type'] = f'const_{const_val}'
        G_pruned.nodes[node]['lut_str'] = str(const_val)
        G_pruned.nodes[node]['status'] = f'Pruned_{const_val}'
        
        # Change Color for Gephi Visualization natively
        if const_val == 0:
            # Red color for Stuck-at-0
            G_pruned.nodes[node]['viz'] = {'color': {'r': 255, 'g': 65, 'b': 54, 'a': 1.0}}
        else:
            # Green color for Stuck-at-1
            G_pruned.nodes[node]['viz'] = {'color': {'r': 46, 'g': 204, 'b': 64, 'a': 1.0}}
        
        # Isolate structurally (Edges are removed, but logic_depth is preserved)
        in_edges = list(G_pruned.in_edges(node))
        out_edges = list(G_pruned.out_edges(node))
        
        pruned_edges += len(in_edges) + len(out_edges)
        
        # G_pruned.remove_edges_from(in_edges)
        # G_pruned.remove_edges_from(out_edges)
        
        stuck_at_count += 1
    return G_pruned, stuck_at_count, pruned_edges

def apply_centrality_pruning(G, metric='pagerank', drop_fraction=0.05):
    """
    Centrality Method: Removes the bottom N% of nodes based on structural centrality.
    Uses Hybrid Stuck-at based on Boolean Bias to preserve datapath integrity.
    """
    import logging
    G_pruned = G.copy()
    
    if metric == 'pagerank':
        centrality = nx.pagerank(G_pruned)
    elif metric == 'eigenvector':
        try:
            centrality = nx.eigenvector_centrality(G_pruned, max_iter=1000)
        except nx.PowerIterationFailedConvergence:
            logging.warning("Eigenvector centrality failed to converge. Falling back to Degree Centrality.")
            centrality = nx.degree_centrality(G_pruned)
    else:
        centrality = nx.degree_centrality(G_pruned)
        
    # Identify LUTs to avoid pruning inputs or outputs
    lut_nodes = [n for n, d in G_pruned.nodes(data=True) if d.get('type') in ['lut', '$lut']]
    
    # Sort LUTs by centrality (lowest first)
    lut_scores = [(n, centrality[n]) for n in lut_nodes]
    lut_scores.sort(key=lambda x: x[1])
    
    # Select the bottom percentage to drop
    num_to_drop = int(len(lut_nodes) * drop_fraction)
    target_nodes = [n for n, score in lut_scores[:num_to_drop]]
    
    stuck_at_count = 0
    pruned_edges = 0
    
    for node in target_nodes:
        
        # Hybrid Stuck-at: Decide constant based on bias tendency
        bias = G_pruned.nodes[node].get('bias', 0.5)
        const_val = 1 if bias >= 0.5 else 0
        
        # Convert to constant node (Changing Type and Value)
        G_pruned.nodes[node]['type'] = f'const_{const_val}'
        G_pruned.nodes[node]['lut_str'] = str(const_val)
        G_pruned.nodes[node]['status'] = f'Pruned_{const_val}'
        
        # Change Color for Gephi Visualization natively
        if const_val == 0:
            # Red color for Stuck-at-0
            G_pruned.nodes[node]['viz'] = {'color': {'r': 255, 'g': 65, 'b': 54, 'a': 1.0}}
        else:
            # Green color for Stuck-at-1
            G_pruned.nodes[node]['viz'] = {'color': {'r': 46, 'g': 204, 'b': 64, 'a': 1.0}}
        
        # Isolate structurally (Edges are removed, but logic_depth is preserved)
        in_edges = list(G_pruned.in_edges(node))
        out_edges = list(G_pruned.out_edges(node))
        
        pruned_edges += len(in_edges) + len(out_edges)
        
        
        stuck_at_count += 1
        
    return G_pruned, stuck_at_count, pruned_edges

def apply_backbone_pruning(G, sens_threshold):
    """
    Backbone Method: Focuses entirely on edges. Removes weak connections 
    (Sensitivity < threshold) while strictly preserving structural bridges.
    Nodes that lose inputs naturally default to logical 0 in the evaluator.
    """
    G_pruned = G.copy()
    stuck_at_count = 0
    pruned_edges = 0
    
    undirected_G = G_pruned.to_undirected()
    bridges = list(nx.bridges(undirected_G))
    
    edges_to_remove = []
    for u, v, data in G_pruned.edges(data=True):
        sens = data.get('weight', 1.0)
        
        if sens < sens_threshold:
            # Protect the structural backbone
            if (u, v) not in bridges and (v, u) not in bridges:
                edges_to_remove.append((u, v))
                # If a node losses a input, it will be treated as a logical 0 in the evaluator.
                
        
        # If a node loses all its inputs, it will be treated as a logical 0 in the evaluator.
        if G_pruned.in_degree(v) == 0 and G_pruned.nodes[v].get('type') == 'lut':
            G_pruned.nodes[v]['type'] = 'const_0'
            G_pruned.nodes[v]['lut_str'] = '0'
            G_pruned.nodes[v]['status'] = 'Pruned_0'
            stuck_at_count += 1
        
                
    G_pruned.remove_edges_from(edges_to_remove)
    pruned_edges += len(edges_to_remove)
    
    return G_pruned, stuck_at_count, pruned_edges

def apply_depth_aware_pruning(G, drop_fraction=0.05):
    """
    Parabolic Depth-Aware Pruning: Prioritizes pruning nodes in the MIDDLE 
    of the datapath. Protects early nodes (to prevent cascading errors) and 
    protects deep nodes (to prevent destroying heavily aggregated information).
    """
    import logging
    G_pruned = G.copy()
    stuck_at_count = 0
    pruned_edges = 0
    
    # Calculate basic topological metrics
    centrality = nx.pagerank(G_pruned)
    
    # Find the maximum depth of the circuit to normalize scores
    max_depth = max([d.get('logic_depth', 0) for n, d in G_pruned.nodes(data=True)])
    
    lut_nodes = [n for n, d in G_pruned.nodes(data=True) if d.get('type') in ['lut', '$lut']]
    
    node_scores = []
    for node in lut_nodes:
        node_depth = G_pruned.nodes[node].get('logic_depth', 0)
        node_centr = centrality.get(node, 0)
        
        # Normalized depth (0.0 at inputs, 1.0 at outputs)
        nd = node_depth / max_depth if max_depth > 0 else 0.5
        
        # Parabolic Distance: How far is the node from the exact middle (0.5)?
        # 0.0 = Node is exactly in the middle (Safest to prune)
        # 0.5 = Node is at the absolute edges (Most dangerous to prune)
        distance_from_center = abs(nd - 0.5)
        
        # We scale this to create a strong penalty. 
        # (distance_from_center * 2) maps it from [0.0 -> 1.0]
        depth_penalty = (distance_from_center * 2.0)
        
        # Add a tiny base value to avoid multiplying by true zero
        # Nodes in the middle have low penalty -> low vulnerability score -> targeted for pruning
        vulnerability_score = node_centr * ((depth_penalty + 0.1) ** 2)
        
        node_scores.append((node, vulnerability_score))

    # Sort nodes by vulnerability (lowest score = best candidate for pruning)
    node_scores.sort(key=lambda x: x[1])
    
    # Select the bottom percentage to drop
    num_to_drop = int(len(lut_nodes) * drop_fraction)
    target_nodes = [n for n, score in node_scores[:num_to_drop]]
    
    # Apply Hybrid Stuck-at Faults (Visual & Functional)
    for node in target_nodes:
        bias = G_pruned.nodes[node].get('bias', 0.5)
        const_val = 1 if bias >= 0.5 else 0
        
        # Change Type and Values
        G_pruned.nodes[node]['type'] = f'const_{const_val}'
        G_pruned.nodes[node]['lut_str'] = str(const_val)
        G_pruned.nodes[node]['status'] = f'Pruned_{const_val}'
        
        # Apply Gephi Colors (Red for 0, Green for 1)
        if const_val == 0:
            G_pruned.nodes[node]['viz'] = {'color': {'r': 255, 'g': 65, 'b': 54, 'a': 1.0}}
        else:
            G_pruned.nodes[node]['viz'] = {'color': {'r': 46, 'g': 204, 'b': 64, 'a': 1.0}}
        
        # Isolate Structurally
        in_edges = list(G_pruned.in_edges(node))
        out_edges = list(G_pruned.out_edges(node))
        
        pruned_edges += len(in_edges) + len(out_edges)
        
        # G_pruned.remove_edges_from(in_edges)
        # G_pruned.remove_edges_from(out_edges)
        
        stuck_at_count += 1
        
    return G_pruned, stuck_at_count, pruned_edges


def apply_entropy_aware_pruning(G, drop_fraction=0.05):
    """
    Entropy-Aware Pruning: Fuses Information Theory with Structural Pruning.
    Calculates the Shannon Entropy of each LUT based on its Boolean Bias.
    Nodes with low entropy (predictable behavior, e.g., mostly 0 or mostly 1) 
    are pruned first using the Hybrid Stuck-at strategy.
    Nodes with high entropy (~0.5 bias) are protected as active datapath carriers.
    """
    logging.info(f"[Pruning] Applying Shannon Entropy-Aware Pruning (Dropping bottom {drop_fraction * 100}% nodes) ...")
    
    G_pruned = G.copy()
    stuck_at_count = 0
    pruned_edges = 0
    
    # Isolate LUT nodes
    lut_nodes = [n for n, d in G_pruned.nodes(data=True) if d.get('type') in ['lut', '$lut']]
    
    node_scores = []
    
    # 1. Calculate Shannon Entropy for each LUT
    for node in lut_nodes:
        bias = G_pruned.nodes[node].get('bias', 0.5)
        
        # Protect against log2(0) math errors
        if bias <= 0.0 or bias >= 1.0:
            entropy = 0.0
        else:
            # Shannon Entropy Formula: H(X) = -p*log2(p) - (1-p)*log2(1-p)
            entropy = - (bias * math.log2(bias)) - ((1.0 - bias) * math.log2(1.0 - bias))
            
        node_scores.append((node, entropy))
        
        # Save entropy back to the graph for potential GEXF visualization
        G_pruned.nodes[node]['shannon_entropy'] = entropy

    # 2. Sort nodes by Entropy (Lowest entropy = Safest candidate for pruning)
    node_scores.sort(key=lambda x: x[1])
    
    # 3. Select the bottom percentage to drop
    num_to_drop = int(len(lut_nodes) * drop_fraction)
    target_nodes = [n for n, score in node_scores[:num_to_drop]]
    
    # 4. Apply Hybrid Stuck-at Faults
    for node in target_nodes:
        bias = G_pruned.nodes[node].get('bias', 0.5)
        const_val = 1 if bias >= 0.5 else 0
        
        # Reconfigure the node
        G_pruned.nodes[node]['type'] = f'const_{const_val}'
        G_pruned.nodes[node]['lut_str'] = str(const_val)
        G_pruned.nodes[node]['status'] = f'Pruned_Entropy_{const_val}'
        
        # Apply Gephi Colors for visual clarity
        if const_val == 0:
            # Red for Stuck-at-0
            G_pruned.nodes[node]['viz'] = {'color': {'r': 255, 'g': 65, 'b': 54, 'a': 1.0}}
        else:
            # Green for Stuck-at-1
            G_pruned.nodes[node]['viz'] = {'color': {'r': 46, 'g': 204, 'b': 64, 'a': 1.0}}
            
        # Isolate structurally (Cut the wires)
        in_edges = list(G_pruned.in_edges(node))
        out_edges = list(G_pruned.out_edges(node))
        
        pruned_edges += len(in_edges) + len(out_edges)
        
        # G_pruned.remove_edges_from(in_edges)
        # G_pruned.remove_edges_from(out_edges)
        
        stuck_at_count += 1
        
    return G_pruned, stuck_at_count, pruned_edges