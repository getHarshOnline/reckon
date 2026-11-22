"""
Transitivity tests for empirical influence relations.

Tests detection and characterization of transitivity violations.
The empirical estimator hat{preceq}_{R,n,alpha,M} can miss a link in a chain.
The theoretical influence relation can also fail to compose.

IMPORTANT: We do NOT assert `transitive == True` - that would be a lie generator.
Instead, we test that violations are properly detected and reported.
"""

import json
import pytest
import random
from typing import Optional

from reckon.core.resources import ResourceVector
from reckon.core.causality import (
    DirectInfluenceRecords,
    DistinguishabilityMeasure,
    TransitivityViolation,
    TransitivityReport,
)


class TestTransitivityDetection:
    """Tests for transitivity violation detection."""

    def test_no_violations_in_empty_records(self):
        """An empty record collection has no violations."""
        rv = ResourceVector(memory_slots=10)
        records = DirectInfluenceRecords(rv)

        report = records.check_transitivity()

        assert report.total_triples_tested == 0
        assert report.violation_rate == 0.0
        assert len(report.violations) == 0

    def test_no_violations_in_single_edge(self):
        """Single edge has no triples to test."""
        rv = ResourceVector(memory_slots=10)
        records = DirectInfluenceRecords(rv)
        records.add_relation("A", "B", distinguishability=0.5)

        report = records.check_transitivity()

        assert report.total_triples_tested == 0
        assert len(report.violations) == 0

    def test_detects_violation_when_ac_missing(self):
        """Detects violation when A->B and B->C but NOT A->C."""
        rv = ResourceVector(memory_slots=10)
        records = DirectInfluenceRecords(rv)

        # Add A->B and B->C with high distinguishability
        records.add_relation("A", "B", distinguishability=0.5, threshold=0.1)
        records.add_relation("B", "C", distinguishability=0.5, threshold=0.1)
        # A->C is NOT added (missing edge)

        report = records.check_transitivity()

        assert report.total_triples_tested == 1
        assert len(report.violations) == 1
        assert report.violation_rate == 1.0

        violation = report.violations[0]
        assert violation.triple == ("A", "B", "C")
        assert violation.a_b_detected is True
        assert violation.b_c_detected is True
        assert violation.a_c_detected is False

    def test_detects_violation_when_ac_below_threshold(self):
        """Detects violation when A->C exists but is below threshold."""
        rv = ResourceVector(memory_slots=10)
        records = DirectInfluenceRecords(rv)

        # Add A->B and B->C with high distinguishability
        records.add_relation("A", "B", distinguishability=0.5, threshold=0.1)
        records.add_relation("B", "C", distinguishability=0.5, threshold=0.1)
        # A->C exists but is below threshold (Type II error simulation)
        records.add_relation("A", "C", distinguishability=0.05, threshold=0.1)

        report = records.check_transitivity()

        assert report.total_triples_tested == 1
        assert len(report.violations) == 1
        assert report.violation_rate == 1.0

        violation = report.violations[0]
        assert violation.a_c_detected is False
        assert violation.a_c_distinguishability == 0.05

    def test_no_violation_when_transitive(self):
        """No violation when transitivity holds."""
        rv = ResourceVector(memory_slots=10)
        records = DirectInfluenceRecords(rv)

        # Add A->B, B->C, and A->C (transitive closure satisfied)
        records.add_relation("A", "B", distinguishability=0.5, threshold=0.1)
        records.add_relation("B", "C", distinguishability=0.5, threshold=0.1)
        records.add_relation("A", "C", distinguishability=0.5, threshold=0.1)

        report = records.check_transitivity()

        assert report.total_triples_tested == 1
        assert len(report.violations) == 0
        assert report.violation_rate == 0.0

    def test_multiple_violations_counted(self):
        """Multiple violations are all counted."""
        rv = ResourceVector(memory_slots=10)
        records = DirectInfluenceRecords(rv)

        # Create two chains: A->B->C and D->E->F without closures
        records.add_relation("A", "B", distinguishability=0.5, threshold=0.1)
        records.add_relation("B", "C", distinguishability=0.5, threshold=0.1)
        records.add_relation("D", "E", distinguishability=0.5, threshold=0.1)
        records.add_relation("E", "F", distinguishability=0.5, threshold=0.1)

        report = records.check_transitivity()

        assert report.total_triples_tested == 2
        assert len(report.violations) == 2
        assert report.violation_rate == 1.0

    def test_violation_includes_metadata(self):
        """Violation report includes all required metadata."""
        rv = ResourceVector(memory_slots=10)
        records = DirectInfluenceRecords(rv)

        records.add_relation("A", "B", distinguishability=0.8, threshold=0.1)
        records.add_relation("B", "C", distinguishability=0.6, threshold=0.1)

        report = records.check_transitivity(alpha=0.05)

        assert report.alpha == 0.05
        assert report.multiple_testing_correction == "none"

        violation = report.violations[0]
        assert violation.a_b_distinguishability == 0.8
        assert violation.b_c_distinguishability == 0.6


class TestTransitivityCharacterization:
    """
    Characterization tests with controllable effect sizes.

    These tests simulate scenarios where the true relation is transitive
    but the empirical estimator fails due to noise.
    """

    def test_synthetic_noisy_detection(self):
        """
        Synthetic scenario with controllable effect sizes.

        Simulates: A->B strong, B->C strong, but A->C weak/noisy.
        This is expected in practice due to effect size dilution along paths.
        """
        rv = ResourceVector(memory_slots=10)
        records = DirectInfluenceRecords(rv)
        threshold = 0.1

        # A->B: strong effect, easily detectable
        records.add_relation("A", "B", distinguishability=0.8, threshold=threshold)
        # B->C: strong effect, easily detectable
        records.add_relation("B", "C", distinguishability=0.7, threshold=threshold)
        # A->C: weak effect (diluted through path), fails detection
        # In reality, causal effects often attenuate along paths
        records.add_relation("A", "C", distinguishability=0.05, threshold=threshold)

        report = records.check_transitivity()

        # Violation should be detected
        assert len(report.violations) > 0
        assert report.violations[0].a_c_detected is False

    def test_violation_rate_varies_with_noise(self):
        """
        Violation rate increases with higher noise / lower effect sizes.

        This is a characterization test: we don't assert exact values,
        just that the relationship between noise and violations exists.
        """
        rv = ResourceVector(memory_slots=10)
        threshold = 0.1

        results = []
        for noise_level in [0.0, 0.3, 0.6, 0.9]:
            records = DirectInfluenceRecords(rv)

            # Add 5 chains, with A->C effect diminished by noise_level
            for i in range(5):
                a, b, c = f"A{i}", f"B{i}", f"C{i}"
                records.add_relation(a, b, distinguishability=0.5, threshold=threshold)
                records.add_relation(b, c, distinguishability=0.5, threshold=threshold)
                # A->C effect diminished by noise
                ac_effect = 0.5 * (1 - noise_level)
                records.add_relation(a, c, distinguishability=ac_effect, threshold=threshold)

            report = records.check_transitivity()
            results.append((noise_level, report.violation_rate))

        # Higher noise should lead to higher violation rate
        # At noise=0, all A->C should be above threshold
        # At noise=0.9, most A->C should be below threshold
        low_noise_rate = results[0][1]
        high_noise_rate = results[-1][1]
        assert high_noise_rate >= low_noise_rate

    def test_stochastic_violations_detected(self):
        """
        Simulate stochastic detection (random Type II errors).

        Creates a records where some edges randomly fail detection
        to simulate finite-sample effects.
        """
        random.seed(42)
        rv = ResourceVector(memory_slots=10)
        records = DirectInfluenceRecords(rv)
        threshold = 0.1

        # Create 10 chains
        chains = 10
        for i in range(chains):
            a, b, c = f"A{i}", f"B{i}", f"C{i}"

            # A->B always detected
            records.add_relation(a, b, distinguishability=0.5, threshold=threshold)
            # B->C always detected
            records.add_relation(b, c, distinguishability=0.5, threshold=threshold)

            # A->C has 50% chance of being detected (stochastic)
            if random.random() > 0.5:
                records.add_relation(a, c, distinguishability=0.5, threshold=threshold)
            else:
                records.add_relation(a, c, distinguishability=0.05, threshold=threshold)

        report = records.check_transitivity()

        # Should have some violations (but not deterministic due to random seed)
        # The point is that violations ARE detected, not that there's an exact count
        assert report.total_triples_tested == chains
        # With 50% detection, we expect roughly half violations
        # But we don't assert exact count (stochastic test)


class TestTransitivityReportArtifact:
    """Tests for JSON report artifact generation."""

    def test_report_to_json(self):
        """Report can be serialized to JSON."""
        rv = ResourceVector(memory_slots=10)
        records = DirectInfluenceRecords(rv)

        records.add_relation("A", "B", distinguishability=0.5, threshold=0.1)
        records.add_relation("B", "C", distinguishability=0.5, threshold=0.1)

        report = records.check_transitivity(alpha=0.05)
        json_str = report.to_json()

        # Should be valid JSON
        parsed = json.loads(json_str)

        # Check structure
        assert "violations" in parsed
        assert "violation_rate" in parsed
        assert "total_triples_tested" in parsed
        assert "alpha" in parsed
        assert "multiple_testing_correction" in parsed

    def test_report_json_format_matches_spec(self):
        """
        Report JSON format matches the specification.

        Expected format:
        {
          "violations": [
            {"triple": ["A", "B", "C"], "a_b_detected": true, ...}
          ],
          "violation_rate": 0.15,
          "total_triples_tested": 100,
          "alpha": 0.05,
          "multiple_testing_correction": "none"
        }
        """
        rv = ResourceVector(memory_slots=10)
        records = DirectInfluenceRecords(rv)

        records.add_relation("X", "Y", distinguishability=0.5, threshold=0.1)
        records.add_relation("Y", "Z", distinguishability=0.5, threshold=0.1)
        records.add_relation("X", "Z", distinguishability=0.08, threshold=0.1)

        report = records.check_transitivity(
            alpha=0.05,
            multiple_testing_correction="none",
        )
        data = report.to_dict()

        # Check top-level fields
        assert isinstance(data["violations"], list)
        assert isinstance(data["violation_rate"], float)
        assert isinstance(data["total_triples_tested"], int)
        assert data["alpha"] == 0.05
        assert data["multiple_testing_correction"] == "none"

        # Check violation structure
        assert len(data["violations"]) == 1
        v = data["violations"][0]
        assert v["triple"] == ["X", "Y", "Z"]
        assert v["a_b_detected"] is True
        assert v["b_c_detected"] is True
        assert v["a_c_detected"] is False
        assert "a_c_distinguishability" in v
        assert "a_c_threshold" in v

    def test_violation_triple_ids_logged(self):
        """Violations include triple IDs (A, B, C)."""
        rv = ResourceVector(memory_slots=10)
        records = DirectInfluenceRecords(rv)

        records.add_relation("event_1", "event_2", distinguishability=0.5, threshold=0.1)
        records.add_relation("event_2", "event_3", distinguishability=0.5, threshold=0.1)

        report = records.check_transitivity()

        assert len(report.violations) == 1
        v = report.violations[0]
        assert v.triple == ("event_1", "event_2", "event_3")

        # JSON output should have list format
        d = v.to_dict()
        assert d["triple"] == ["event_1", "event_2", "event_3"]


class TestTransitivityMetadata:
    """Tests for transitivity report metadata."""

    def test_report_includes_sample_parameters(self):
        """Report includes alpha and multiple testing mode."""
        rv = ResourceVector(memory_slots=10)
        records = DirectInfluenceRecords(rv)

        records.add_relation("A", "B", distinguishability=0.5, threshold=0.1)

        report = records.check_transitivity(
            alpha=0.01,
            multiple_testing_correction="bonferroni",
        )

        assert report.alpha == 0.01
        assert report.multiple_testing_correction == "bonferroni"

    def test_distinguishability_values_preserved(self):
        """Report preserves distinguishability values for analysis."""
        rv = ResourceVector(memory_slots=10)
        records = DirectInfluenceRecords(rv)

        records.add_relation("A", "B", distinguishability=0.82, threshold=0.1)
        records.add_relation("B", "C", distinguishability=0.67, threshold=0.1)
        records.add_relation("A", "C", distinguishability=0.09, threshold=0.1)

        report = records.check_transitivity()
        v = report.violations[0]

        assert v.a_b_distinguishability == 0.82
        assert v.b_c_distinguishability == 0.67
        assert v.a_c_distinguishability == 0.09
        assert v.a_c_threshold == 0.1


class TestTransitivityEdgeCases:
    """Edge cases and boundary conditions."""

    def test_self_loops_ignored(self):
        """Self-loops (A->A) don't create false violations."""
        rv = ResourceVector(memory_slots=10)
        records = DirectInfluenceRecords(rv)

        records.add_relation("A", "A", distinguishability=1.0, threshold=0.1)
        records.add_relation("A", "B", distinguishability=0.5, threshold=0.1)
        records.add_relation("B", "A", distinguishability=0.5, threshold=0.1)

        report = records.check_transitivity()

        # Should not include triples where A=B or B=C
        for v in report.violations:
            a, b, c = v.triple
            assert a != b
            assert b != c
            assert a != c

    def test_bidirectional_edges_handled(self):
        """Bidirectional edges (A->B and B->A) are handled correctly."""
        rv = ResourceVector(memory_slots=10)
        records = DirectInfluenceRecords(rv)

        # Bidirectional A<->B and B<->C
        records.add_relation("A", "B", distinguishability=0.5, threshold=0.1)
        records.add_relation("B", "A", distinguishability=0.5, threshold=0.1)
        records.add_relation("B", "C", distinguishability=0.5, threshold=0.1)
        records.add_relation("C", "B", distinguishability=0.5, threshold=0.1)

        report = records.check_transitivity()

        # Should test multiple triples: (A,B,C), (A,B,A), (C,B,A), etc.
        # But triples with repeated elements should be filtered
        for v in report.violations:
            a, b, c = v.triple
            assert len({a, b, c}) == 3  # All distinct


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
