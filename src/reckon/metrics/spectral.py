"""
Spectral entropy computation from graph Laplacian.

Measures complexity/diversity of causal graph structure.

USAGE NOTE: This is an OPT-IN metric. It requires eigenvalue decomposition
which is O(n^3) for dense matrices. For large graphs (>1000 nodes), consider:
- Using sparse eigensolvers (scipy.sparse.linalg.eigsh)
- Computing only when explicitly requested via config/flag
- Sampling subgraphs for approximate entropy

References:
- SciPy scipy.sparse.csgraph.laplacian for Laplacian computation
- networkqit library for von Neumann entropy from Laplacian spectrum
- Spectral entropy always lies in range [0, log(N)] for N nodes
"""

from typing import Optional
import numpy as np


def _laplacian(adjacency: np.ndarray, normalized: bool) -> np.ndarray:
    """Build the symmetric Laplacian, leaving inverse degree factors at zero."""
    degrees = np.sum(adjacency, axis=1)
    if not normalized:
        return np.diag(degrees) - adjacency
    inverse_sqrt = np.zeros(adjacency.shape[0])
    nonzero = degrees > 0
    inverse_sqrt[nonzero] = 1.0 / np.sqrt(degrees[nonzero])
    scaling = np.diag(inverse_sqrt)
    return np.eye(adjacency.shape[0]) - scaling @ adjacency @ scaling


def compute_spectral_entropy(
    adjacency: np.ndarray,
    normalized: bool = False,
    log_base: str = "natural",
    epsilon: float = 1e-12,
) -> float:
    """
    Compute spectral entropy from graph adjacency matrix.

    Args:
        adjacency: Square adjacency matrix (n x n)
        normalized: If True, use normalized Laplacian L_n = I - D^{-1/2}AD^{-1/2}
        log_base: "natural" (nats), "2" (bits), or "10"
        epsilon: Small value for numerical stability

    Returns:
        Spectral entropy S_spec = -sum(p_i * log(p_i)) over positive eigenvalues

    Notes:
        - Zero eigenvalues (always present for connected graphs) are excluded
        - For disconnected graphs, each component contributes a zero eigenvalue
        - The spectral entropy measures the complexity/diversity of the graph structure
    """
    n = adjacency.shape[0]
    if adjacency.shape[1] != n:
        raise ValueError("Adjacency matrix must be square")

    # Compute eigenvalues
    eigenvalues = np.linalg.eigvalsh(_laplacian(adjacency, normalized))

    # Filter to positive eigenvalues (exclude zero modes)
    positive_eigs = eigenvalues[eigenvalues > epsilon]

    if len(positive_eigs) == 0:
        return 0.0  # Trivial graph (all isolated nodes)

    # Normalize to probability distribution
    total = np.sum(positive_eigs)
    p = positive_eigs / total

    # Choose log function
    if log_base == "natural":
        log_fn = np.log
    elif log_base == "2":
        log_fn = np.log2
    elif log_base == "10":
        log_fn = np.log10
    else:
        raise ValueError(f"Unknown log_base: {log_base}")

    # Compute entropy: S = -sum(p_i * log(p_i))
    # Add epsilon for numerical stability
    entropy = -np.sum(p * log_fn(p + epsilon))

    return float(entropy)


def spectral_entropy_from_edges(
    edges: list[tuple[str, str]],
    node_ids: Optional[list[str]] = None,
    **kwargs,
) -> float:
    """
    Compute spectral entropy from edge list.

    Args:
        edges: List of (source, target) tuples
        node_ids: Optional list of node IDs (for consistent ordering)
        **kwargs: Passed to compute_spectral_entropy

    Returns:
        Spectral entropy
    """
    # Build node index
    if node_ids is None:
        all_nodes: set[str] = set()
        for src, tgt in edges:
            all_nodes.add(src)
            all_nodes.add(tgt)
        node_ids = sorted(all_nodes)

    node_to_idx = {nid: i for i, nid in enumerate(node_ids)}
    n = len(node_ids)

    # Build adjacency matrix
    adjacency = np.zeros((n, n))
    for src, tgt in edges:
        if src in node_to_idx and tgt in node_to_idx:
            i, j = node_to_idx[src], node_to_idx[tgt]
            adjacency[i, j] = 1
            adjacency[j, i] = 1  # Undirected

    return compute_spectral_entropy(adjacency, **kwargs)
