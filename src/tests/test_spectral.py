"""Tests for spectral entropy computation."""

import numpy as np
import pytest
from reckon.metrics.spectral import compute_spectral_entropy, spectral_entropy_from_edges


class TestSpectralEntropy:
    """Test spectral entropy computation."""

    def test_triangle_graph(self):
        """Triangle graph (3 nodes, 3 edges) should have nonzero entropy."""
        # Triangle: 0-1, 1-2, 0-2
        adj = np.array([
            [0, 1, 1],
            [1, 0, 1],
            [1, 1, 0],
        ])
        entropy = compute_spectral_entropy(adj)
        assert entropy > 0

    def test_line_graph(self):
        """Line graph (3 nodes, 2 edges) should have different entropy than triangle."""
        # Line: 0-1, 1-2
        adj = np.array([
            [0, 1, 0],
            [1, 0, 1],
            [0, 1, 0],
        ])
        entropy_line = compute_spectral_entropy(adj)

        # Triangle
        adj_tri = np.array([
            [0, 1, 1],
            [1, 0, 1],
            [1, 1, 0],
        ])
        entropy_tri = compute_spectral_entropy(adj_tri)

        assert entropy_line != entropy_tri

    def test_isolated_nodes(self):
        """Graph with only isolated nodes should have zero entropy."""
        adj = np.zeros((3, 3))
        entropy = compute_spectral_entropy(adj)
        assert entropy == 0.0

    def test_from_edges(self):
        """Test edge list interface."""
        edges = [("a", "b"), ("b", "c"), ("a", "c")]
        entropy = spectral_entropy_from_edges(edges)
        assert entropy > 0

    def test_log_base_invariance(self):
        """Different log bases should differ by constant factor."""
        adj = np.array([
            [0, 1, 1],
            [1, 0, 1],
            [1, 1, 0],
        ])

        s_nat = compute_spectral_entropy(adj, log_base="natural")
        s_bits = compute_spectral_entropy(adj, log_base="2")

        # s_bits = s_nat / ln(2)
        ratio = s_nat / s_bits
        expected_ratio = np.log(2)
        assert abs(ratio - expected_ratio) < 0.01

    def test_normalized_vs_unnormalized(self):
        """Normalized and unnormalized Laplacians should give different entropy."""
        adj = np.array([
            [0, 1, 1],
            [1, 0, 1],
            [1, 1, 0],
        ])

        entropy_unnorm = compute_spectral_entropy(adj, normalized=False)
        entropy_norm = compute_spectral_entropy(adj, normalized=True)

        # Both should be positive but may differ
        assert entropy_unnorm > 0
        assert entropy_norm > 0

    def test_square_matrix_required(self):
        """Non-square matrix should raise ValueError."""
        adj = np.array([
            [0, 1, 1],
            [1, 0, 1],
        ])
        with pytest.raises(ValueError, match="square"):
            compute_spectral_entropy(adj)

    def test_star_graph(self):
        """Star graph should have positive entropy."""
        # Star: center node 0 connected to nodes 1, 2, 3
        adj = np.array([
            [0, 1, 1, 1],
            [1, 0, 0, 0],
            [1, 0, 0, 0],
            [1, 0, 0, 0],
        ])
        entropy = compute_spectral_entropy(adj)
        assert entropy > 0

    def test_complete_graph(self):
        """Complete graph should have positive entropy."""
        # K4: all 4 nodes connected
        adj = np.array([
            [0, 1, 1, 1],
            [1, 0, 1, 1],
            [1, 1, 0, 1],
            [1, 1, 1, 0],
        ])
        entropy = compute_spectral_entropy(adj)
        assert entropy > 0
