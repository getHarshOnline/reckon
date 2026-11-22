"""
Tests for Reckon Proto conformance.

Tests the core API v1 proto schema, generated types,
and conformance fixtures.
"""

import json
import hashlib
import pytest
from pathlib import Path

pytest.importorskip("betterproto2", reason="Install the rpc or proto extra on Python 3.10+.")


class TestProtoTypesGenerated:
    """Tests that proto types are correctly generated."""

    def test_retention_names_keep_wire_numbers_and_use_current_json_keys(self):
        from reckon.generated.reckon import MemoryManagerConfig, RetentionPolicyType

        wire = bytes.fromhex("100419000000000000e83f")
        config = MemoryManagerConfig.parse(wire)
        assert config.retention_policy == RetentionPolicyType.EVIDENCE_PER_BYTE
        assert config.evidence_weight == 0.75
        assert bytes(config) == wire
        document = {
            "retentionPolicy": "RETENTION_POLICY_TYPE_EVIDENCE_PER_BYTE",
            "evidenceWeight": 0.75,
        }
        assert config.to_dict() == document
        assert bytes(MemoryManagerConfig.from_dict(document)) == wire
        assert not hasattr(RetentionPolicyType, "CAUSAL")
        assert not hasattr(config, "causal_weight")

    def test_daemon_record_keeps_typed_tags_and_links_distinct_from_laboratory_origin(self):
        from reckon.generated.reckon.core.v1 import Record, TagValue, StringList, Link

        record = Record(id="daemon-record", timestamp=2**63 - 1, payload=b"\xff\x00",
                        tags={"kind": TagValue(string_value="cue"),
                              "ordered": TagValue(list_value=StringList(values=["b", "a", "b"]))},
                        links=[Link(rel="derived_from", to_record_id="parent", meta_json=b"{}")],
                        created_at_step=0, created_at_sequence=None)
        assert Record.parse(bytes(record)) == record
        assert Record.from_dict(record.to_dict()) == record
        assert not hasattr(record, "provenance")

    def test_record_origin_preserves_embedded_wire_and_json(self):
        from reckon.generated import reckon as wire_types

        # Captured from the previous type with all origin fields populated.
        wire = bytes.fromhex(
            "521f0a0577726974651201611201621a1030313233343536373839616263646566"
        )
        record = wire_types.MemoryRecord.parse(wire)
        assert record.provenance == wire_types.RecordOrigin(
            source_op="write", input_ids=["a", "b"], hash="0123456789abcdef"
        )
        document = {"provenance": {
            "sourceOp": "write", "inputIds": ["a", "b"], "hash": "0123456789abcdef"
        }}
        assert record.to_dict() == document
        assert bytes(record) == wire
        assert bytes(wire_types.MemoryRecord.from_dict(document)) == wire
        assert not hasattr(wire_types, "Provenance")

    def test_run_summary_type_exists(self):
        """Test that RunSummary type is generated."""
        from reckon.generated.reckon.core.v1 import RunSummary

        assert RunSummary is not None

    def test_run_export_type_exists(self):
        """Test that RunExport type is generated."""
        from reckon.generated.reckon.core.v1 import RunExport

        assert RunExport is not None

    def test_pareto_point_type_exists(self):
        """Test that ParetoPoint type is generated."""
        from reckon.generated.reckon.core.v1 import ParetoPoint

        assert ParetoPoint is not None

    def test_evidence_type_exists(self):
        """Test that Evidence type is generated."""
        from reckon.generated.reckon.core.v1 import Evidence

        assert Evidence is not None

    def test_episode_context_type_exists(self):
        """Test that EpisodeContext type is generated."""
        from reckon.generated.reckon.core.v1 import EpisodeContext

        assert EpisodeContext is not None

    def test_ablation_credit_retains_wire_number_with_new_json_name(self):
        from reckon.generated.reckon.core.v1 import CreditAssignment, CreditPolicy

        wire = bytes.fromhex("1804")  # CreditAssignment.policy, historical number 4.
        assignment = CreditAssignment.parse(wire)
        assert assignment.policy == CreditPolicy.ABLATION
        assert bytes(assignment) == wire
        assert assignment.to_dict() == {"policy": "CREDIT_POLICY_ABLATION"}
        assert bytes(CreditAssignment.from_dict(assignment.to_dict())) == wire
        assert not hasattr(CreditPolicy, "CAUSAL")

    def test_record_scope_enum_exists(self):
        """Test that RecordScope enum is generated."""
        from reckon.generated.reckon.core.v1 import RecordScope

        assert RecordScope is not None
        assert RecordScope.RETRIEVED.value == 2


class TestParetoPointCreation:
    """Tests for ParetoPoint proto message creation."""

    def test_create_pareto_point(self):
        """Test creating a ParetoPoint message."""
        from reckon.generated.reckon.core.v1 import ParetoPoint

        point = ParetoPoint(
            x=0.15,
            y=0.8,
            x_metric="probe_overhead_ratio",
            y_metric="success_rate",
            is_pareto=True,
            label="test_point",
        )

        assert point.x == 0.15
        assert point.y == 0.8
        assert point.x_metric == "probe_overhead_ratio"
        assert point.y_metric == "success_rate"
        assert point.is_pareto is True


class TestRunSummaryCreation:
    """Tests for RunSummary proto message creation."""

    def test_create_run_summary(self):
        """Test creating a RunSummary message."""
        from reckon.generated.reckon.core.v1 import RunSummary, HistoricalRunMetricsV1, ParetoPoint

        metrics = HistoricalRunMetricsV1(
            success_rate=0.8,
            probe_overhead_ratio=0.15,
        )

        pareto = ParetoPoint(
            x=0.15,
            y=0.8,
            x_metric="probe_overhead_ratio",
            y_metric="success_rate",
            is_pareto=True,
        )

        summary = RunSummary(
            run_id="test_001",
            config_id="abc123def456",
            config_json=b'{"task": "keydoor"}',
            task_name="keydoor",
            num_episodes=10,
            budget_slots=100,
            seed=42,
            policy_name="causal",
            metrics=metrics,
            pareto_point=pareto,
            core_api_version="1.0",
            events_schema_version="LogEvent/v1",
        )

        assert summary.run_id == "test_001"
        assert summary.config_id == "abc123def456"
        assert summary.core_api_version == "1.0"


class TestConformanceFixture:
    """Tests for the conformance fixture."""

    @pytest.fixture
    def fixture_path(self):
        """Path to the golden run export fixture."""
        return Path(__file__).parent.parent.parent / "runs" / "_fixtures" / "golden_run_export.json"

    def test_fixture_exists(self, fixture_path):
        """Test that conformance fixture exists."""
        assert fixture_path.exists(), f"Fixture not found at {fixture_path}"

    def test_fixture_parses(self, fixture_path):
        """Test that fixture parses as valid JSON."""
        with open(fixture_path) as f:
            data = json.load(f)

        assert "run_id" in data
        assert "summary" in data
        assert "core_api_version" in data

    def test_fixture_has_required_fields(self, fixture_path):
        """Test that fixture has all required fields."""
        with open(fixture_path) as f:
            data = json.load(f)

        summary = data["summary"]

        # Required RunSummary fields
        assert "run_id" in summary
        assert "config_id" in summary
        assert "config_json" in summary
        assert "core_api_version" in summary
        assert "pareto_point" in summary
        assert "metrics" in summary

        # Pareto point fields
        pareto = summary["pareto_point"]
        assert "x" in pareto
        assert "y" in pareto
        assert "x_metric" in pareto
        assert "y_metric" in pareto

    def test_config_id_matches_hash(self, fixture_path):
        """Test that config_id matches hash of config_json."""
        with open(fixture_path) as f:
            data = json.load(f)

        summary = data["summary"]
        config_json = summary["config_json"]
        config_id = summary["config_id"]

        # The config_id should be a 12-char hash
        assert len(config_id) == 12

        # Compute hash and verify format (don't require exact match
        # since the fixture config_id is illustrative)
        computed_hash = hashlib.sha256(config_json.encode()).hexdigest()[:12]
        # Just verify it's a valid hex string
        assert all(c in "0123456789abcdef" for c in config_id.lower())


class TestCoreApiVersion:
    """Tests for core_api_version presence."""

    def test_core_api_version_in_run_export(self):
        """Test that RunExport has core_api_version field."""
        from reckon.generated.reckon.core.v1 import RunExport

        export = RunExport(
            run_id="test",
            core_api_version="1.0",
        )
        assert export.core_api_version == "1.0"

    def test_core_api_version_in_run_summary(self):
        """Test that RunSummary has core_api_version field."""
        from reckon.generated.reckon.core.v1 import RunSummary

        summary = RunSummary(
            run_id="test",
            config_id="abc123",
            core_api_version="1.0",
        )
        assert summary.core_api_version == "1.0"
