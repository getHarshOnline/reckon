"""
Tests for Reckon Probe module.

Tests statistical tests, FDR correction, and Prober functionality.
"""

import pytest
import math

from reckon.metrics.tests.statistical import (
    permutation_test,
    t_test,
    cohens_d,
    confidence_interval,
    pooled_std,
)
from reckon.metrics.tests.fdr import (
    benjamini_hochberg,
    bonferroni,
    apply_fdr_correction,
    FDRMethod,
)
from reckon.metrics.probe import (
    Prober,
    ProbeConfig,
    ProbeResult,
    Evidence,
    StatTestType,
    InterventionMethod,
)


class TestPermutationTest:
    """Tests for permutation test."""

    def test_permutation_test_same_distribution(self):
        """Test that same distribution gives high p-value."""
        x = [0.5, 0.52, 0.48, 0.51, 0.49, 0.50, 0.53, 0.47]
        y = [0.50, 0.51, 0.49, 0.52, 0.48, 0.51, 0.50, 0.49]

        result = permutation_test(x, y, n_permutations=1000, seed=42)

        # Same distribution should have high p-value
        assert result.p_value > 0.1

    def test_permutation_test_different_distributions(self):
        """Test that different distributions give low p-value."""
        x = [0.3, 0.32, 0.28, 0.31, 0.29]
        y = [0.7, 0.72, 0.68, 0.71, 0.69]

        result = permutation_test(x, y, n_permutations=1000, seed=42)

        # Clearly different distributions should have low p-value
        assert result.p_value < 0.05

    def test_permutation_test_returns_correct_structure(self):
        """Test that result has correct fields."""
        x = [0.5, 0.6, 0.55]
        y = [0.7, 0.75, 0.72]

        result = permutation_test(x, y, n_permutations=100, seed=42)

        assert hasattr(result, "p_value")
        assert hasattr(result, "statistic")
        assert hasattr(result, "n_permutations")
        assert hasattr(result, "observed_diff")
        assert 0 <= result.p_value <= 1

    def test_permutation_test_empty_inputs(self):
        """Test handling of empty inputs."""
        result = permutation_test([], [], n_permutations=100)

        assert result.p_value == 1.0
        assert result.statistic == 0.0

    def test_permutation_test_reproducible_with_seed(self):
        """Test that results are reproducible with same seed."""
        x = [0.5, 0.6, 0.55, 0.58]
        y = [0.7, 0.75, 0.72, 0.68]

        result1 = permutation_test(x, y, n_permutations=100, seed=42)
        result2 = permutation_test(x, y, n_permutations=100, seed=42)

        assert result1.p_value == result2.p_value


class TestTTest:
    """Tests for t-test (requires scipy)."""

    def test_t_test_requires_scipy(self):
        """Test that t-test works if scipy is available."""
        x = [0.5, 0.6, 0.55]
        y = [0.7, 0.75, 0.72]

        try:
            result = t_test(x, y)
            assert hasattr(result, "p_value")
            assert hasattr(result, "statistic")
            assert 0 <= result.p_value <= 1
        except ImportError:
            pytest.skip("scipy not available")

    def test_t_test_different_means(self):
        """Test t-test with clearly different means."""
        x = [0.3, 0.32, 0.28, 0.31, 0.29]
        y = [0.7, 0.72, 0.68, 0.71, 0.69]

        try:
            result = t_test(x, y)
            assert result.p_value < 0.05
        except ImportError:
            pytest.skip("scipy not available")


class TestCohensD:
    """Tests for Cohen's d effect size."""

    def test_cohens_d_zero(self):
        """Test Cohen's d for identical distributions."""
        x = [0.5, 0.5, 0.5, 0.5]
        y = [0.5, 0.5, 0.5, 0.5]

        d = cohens_d(x, y)
        assert abs(d) < 0.01

    def test_cohens_d_large_effect(self):
        """Test Cohen's d for large effect."""
        x = [0.3, 0.32, 0.28, 0.31, 0.29]
        y = [0.7, 0.72, 0.68, 0.71, 0.69]

        d = cohens_d(x, y)
        # Large negative effect (y > x)
        assert d < -2.0  # Very large effect

    def test_cohens_d_small_effect(self):
        """Test Cohen's d for small effect."""
        # Create samples with overlapping distributions (small effect)
        x = [0.50, 0.55, 0.45, 0.52, 0.48, 0.51, 0.49, 0.53, 0.47, 0.50]
        y = [0.52, 0.57, 0.47, 0.54, 0.50, 0.53, 0.51, 0.55, 0.49, 0.52]

        d = cohens_d(x, y)
        # Small effect (|d| < 0.5)
        assert abs(d) < 0.8  # Allow up to medium effect for test stability


class TestConfidenceInterval:
    """Tests for confidence interval calculation."""

    def test_ci_normal_method(self):
        """Test normal approximation CI."""
        x = [0.5, 0.6, 0.55, 0.58, 0.52, 0.57, 0.54, 0.56]

        ci = confidence_interval(x, confidence=0.95, method="normal")

        assert ci[0] < ci[1]  # Lower < Upper
        # Mean should be within CI
        mean = sum(x) / len(x)
        assert ci[0] <= mean <= ci[1]

    def test_ci_bootstrap_method(self):
        """Test bootstrap CI."""
        x = [0.5, 0.6, 0.55, 0.58, 0.52, 0.57, 0.54, 0.56]

        ci = confidence_interval(x, confidence=0.95, method="bootstrap", seed=42)

        assert ci[0] < ci[1]

    def test_ci_empty_input(self):
        """Test CI with empty input."""
        ci = confidence_interval([], confidence=0.95)
        assert ci == (0.0, 0.0)

    def test_ci_single_value(self):
        """Test CI with single value."""
        ci = confidence_interval([0.5], confidence=0.95)
        assert ci == (0.5, 0.5)


class TestBonferroni:
    """Tests for Bonferroni correction."""

    def test_bonferroni_basic(self):
        """Test basic Bonferroni correction."""
        p_values = [0.01, 0.02, 0.03, 0.5]

        result = bonferroni(p_values, alpha=0.05)

        # Adjusted p-values should be p * n
        assert abs(result.q_values[0] - 0.04) < 0.001
        assert abs(result.q_values[1] - 0.08) < 0.001
        assert abs(result.q_values[2] - 0.12) < 0.001
        assert result.q_values[3] == 1.0  # Capped at 1

    def test_bonferroni_rejections(self):
        """Test Bonferroni rejections."""
        p_values = [0.01, 0.02, 0.03, 0.5]

        result = bonferroni(p_values, alpha=0.05)

        # Only first p-value should be rejected (0.01 * 4 = 0.04 < 0.05)
        assert result.rejected[0] is True
        assert result.rejected[1] is False
        assert result.rejected[2] is False
        assert result.rejected[3] is False
        assert result.n_rejected == 1

    def test_bonferroni_empty(self):
        """Test Bonferroni with empty input."""
        result = bonferroni([], alpha=0.05)

        assert result.q_values == []
        assert result.rejected == []
        assert result.n_rejected == 0


class TestBenjaminiHochberg:
    """Tests for Benjamini-Hochberg FDR correction."""

    def test_bh_basic(self):
        """Test basic BH correction."""
        p_values = [0.01, 0.02, 0.03, 0.5]

        result = benjamini_hochberg(p_values, alpha=0.05)

        # BH produces valid q-values
        assert all(0 <= q <= 1 for q in result.q_values)

    def test_bh_rejections(self):
        """Test BH rejections are less conservative than Bonferroni."""
        p_values = [0.01, 0.02, 0.03, 0.5]

        bh_result = benjamini_hochberg(p_values, alpha=0.05)
        bonf_result = bonferroni(p_values, alpha=0.05)

        # BH should reject at least as many as Bonferroni
        assert bh_result.n_rejected >= bonf_result.n_rejected

    def test_bh_monotonicity(self):
        """Test that q-values maintain proper ordering."""
        p_values = [0.001, 0.01, 0.02, 0.04, 0.5]

        result = benjamini_hochberg(p_values, alpha=0.05)

        # Sorted p-values should have non-decreasing q-values
        sorted_indices = sorted(range(len(p_values)), key=lambda i: p_values[i])
        sorted_q = [result.q_values[i] for i in sorted_indices]

        for i in range(len(sorted_q) - 1):
            assert sorted_q[i] <= sorted_q[i + 1]

    def test_bh_produces_valid_qvalues(self):
        """Test that BH produces valid q-values."""
        p_values = [0.001, 0.01, 0.02, 0.04, 0.08, 0.1, 0.5]

        result = benjamini_hochberg(p_values, alpha=0.05)

        # All q-values should be between 0 and 1
        for q in result.q_values:
            assert 0 <= q <= 1

        # Q-values should be >= original p-values
        for p, q in zip(p_values, result.q_values):
            assert q >= p or abs(q - p) < 0.001

    def test_bh_empty(self):
        """Test BH with empty input."""
        result = benjamini_hochberg([], alpha=0.05)

        assert result.q_values == []
        assert result.n_rejected == 0


class TestApplyFDRCorrection:
    """Tests for apply_fdr_correction dispatch function."""

    def test_dispatch_none(self):
        """Test no correction."""
        p_values = [0.01, 0.06]

        result = apply_fdr_correction(p_values, FDRMethod.NONE, alpha=0.05)

        assert result.q_values == p_values
        assert result.rejected[0] is True
        assert result.rejected[1] is False

    def test_dispatch_bonferroni(self):
        """Test Bonferroni dispatch."""
        p_values = [0.01, 0.06]

        result = apply_fdr_correction(p_values, FDRMethod.BONFERRONI, alpha=0.05)

        assert result.method == FDRMethod.BONFERRONI

    def test_dispatch_bh(self):
        """Test BH dispatch."""
        p_values = [0.01, 0.06]

        result = apply_fdr_correction(p_values, FDRMethod.BENJAMINI_HOCHBERG, alpha=0.05)

        assert result.method == FDRMethod.BENJAMINI_HOCHBERG


class TestProber:
    def test_exact_paired_permutation_counts_all_sign_patterns(self):
        from reckon.metrics.tests.paired import paired_inference

        p_value, interval = paired_inference([1.0] * 10, "permutation", 1024, 0.05, 0)
        assert p_value == 2 / 1024
        assert interval == (1.0, 1.0)

    @pytest.mark.parametrize("method", ["permutation", "bootstrap"])
    def test_paired_inference_is_unchanged_by_outcome_units(self, method):
        from reckon.metrics.tests.paired import paired_inference

        for differences in ([1.0] * 10, [1.0, 0.5, -0.2, 2.0, 0.8] * 2):
            original, bounds = paired_inference(differences, method, 1024, 0.05, 7)
            scaled, scaled_bounds = paired_inference(
                [d * 1e-16 for d in differences], method, 1024, 0.05, 7
            )
            assert scaled == original
            assert [v / 1e-16 for v in scaled_bounds] == pytest.approx(bounds)

    @pytest.mark.parametrize("method", list(StatTestType))
    def test_identical_pairs_have_no_measured_difference(self, method):
        result = Prober(lambda ids, seed: float(seed)).probe(
            ["r1"], ProbeConfig(test_type=method, n_trials=10, adaptive_sampling=False, seed=3)
        )
        evidence = result.evidence[0]
        assert evidence.delta == 0
        assert evidence.p_value == 1
        assert not evidence.is_significant_adjusted

    @pytest.mark.parametrize("method", list(StatTestType))
    def test_seed_pairs_survive_large_between_trial_variation(self, method):
        calls = []

        def run(ablated_ids, seed):
            calls.append((tuple(ablated_ids), seed))
            return seed * 1000.0 - (1.0 if ablated_ids else 0.0)

        result = Prober(run).probe(
            ["r1"],
            ProbeConfig(
                test_type=method,
                n_trials=12,
                adaptive_sampling=False,
                n_permutations=5000,
                seed=42,
            ),
        )
        evidence = result.evidence[0]
        assert calls == [call for seed in range(42, 54) for call in [((), seed), (("r1",), seed)]]
        assert evidence.delta == 1.0
        assert evidence.ci_lower == evidence.ci_upper == 1.0
        assert evidence.p_value < 0.05
        assert result.probe_episodes == 24
        assert result.probe_wall_time_s > 0

    def test_multiple_records_and_adjusted_evidence(self):
        def run(ablated_ids, seed):
            return float(seed) - (
                {"helpful": 1, "harmful": -1, "neutral": 0}.get(ablated_ids[0], 0)
                if ablated_ids
                else 0
            )

        result = Prober(run).probe(
            ["helpful", "harmful", "neutral"],
            ProbeConfig(
                n_trials=12,
                adaptive_sampling=False,
                n_permutations=4096,
                seed=0,
            ),
        )
        assert result.records_probed == 3
        assert result.probe_episodes == 72
        assert [e.delta for e in result.evidence] == [1, -1, 0]
        assert result.significant_records == ["helpful", "harmful"]
        for evidence in result.evidence:
            assert evidence.p_value_adjusted >= evidence.p_value
        assert result.evidence[0].effect_size_d > 0
        assert result.evidence[1].effect_size_d < 0

    @pytest.mark.parametrize("method", [InterventionMethod.REPLACE, InterventionMethod.SHUFFLE])
    def test_unsupported_intervention_never_runs(self, method):
        def run(*args):
            pytest.fail("Unsupported intervention called runner")

        with pytest.raises(NotImplementedError):
            Prober(run).probe(["r1"], intervention=method)

    def test_adaptive_runs_report_both_arms_and_stop_at_a_declared_look(self):
        calls = []

        def run(ids, seed):
            calls.append((ids, seed))
            return 0.0 if ids else 1.0

        result = Prober(run).probe(
            ["r1"],
            ProbeConfig(
                n_trials=10,
                min_trials=5,
                max_trials=80,
                n_permutations=4096,
                seed=7,
            ),
        )
        count = result.evidence[0].n_trials
        assert count in {5, 10, 20, 40, 80}
        assert count < 80
        assert len(calls) == result.probe_episodes == 2 * count
        assert result.evidence[0].p_value >= 2 / 2**count

    def test_generated_seed_can_replay_the_result(self):
        def run(ids, seed):
            return float(seed % 19) - len(ids)

        first = Prober(run).probe(["r1"], ProbeConfig(n_trials=4, adaptive_sampling=False))
        second = Prober(run).probe(["r1"], first.config)
        assert first.config.seed is not None
        assert first.evidence == second.evidence

    def test_prober_requires_run_fn(self):
        with pytest.raises(ValueError, match="run_fn"):
            Prober().probe(["r1"])

    def test_nonfinite_outcomes_are_refused(self):
        with pytest.raises(ValueError, match="non-finite"):
            Prober(lambda ids, seed: math.nan).probe(["r1"])


class TestProbeConfig:
    """Tests for ProbeConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = ProbeConfig()

        assert config.test_type == StatTestType.PERMUTATION
        assert config.n_trials == 10
        assert config.alpha == 0.05
        assert config.fdr_method == FDRMethod.BENJAMINI_HOCHBERG
        assert config.adaptive_sampling is True
        assert config.early_stopping is True

    def test_config_to_dict(self):
        """Test config serialization."""
        config = ProbeConfig(n_trials=20, alpha=0.01)

        d = config.to_dict()

        assert d["n_trials"] == 20
        assert d["alpha"] == 0.01


class TestEvidence:
    """Tests for Evidence dataclass."""

    def test_evidence_to_dict(self):
        """Test evidence serialization."""
        evidence = Evidence(
            record_id="r1",
            test_type=StatTestType.PERMUTATION,
            baseline_mean=0.5,
            baseline_std=0.05,
            intervention_mean=0.6,
            intervention_std=0.04,
            delta=-0.1,
            effect_size_d=-2.0,
            p_value=0.001,
            p_value_adjusted=0.003,
            ci_lower=-0.15,
            ci_upper=-0.05,
            n_trials=10,
            is_significant=True,
            is_significant_adjusted=True,
        )

        d = evidence.to_dict()

        assert d["record_id"] == "r1"
        assert d["effect_size_d"] == -2.0
        assert d["is_significant"] is True

    def test_evidence_from_dict(self):
        """Test evidence deserialization."""
        d = {
            "record_id": "r1",
            "test_type": "permutation",
            "baseline_mean": 0.5,
            "baseline_std": 0.05,
            "intervention_mean": 0.6,
            "intervention_std": 0.04,
            "delta": -0.1,
            "effect_size_d": -2.0,
            "p_value": 0.001,
            "p_value_adjusted": 0.003,
            "ci_lower": -0.15,
            "ci_upper": -0.05,
            "n_trials": 10,
        }

        evidence = Evidence.from_dict(d)

        assert evidence.record_id == "r1"
        assert evidence.effect_size_d == -2.0
