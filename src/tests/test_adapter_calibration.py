"""The notebook comparison baselines and summaries must describe actual work."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "notebooks/experiments"))
from adapter_calibration import (
    ComparisonMemory,
    compact,
    game_identity,
    run_arm,
    summarize,
    validate_declaration,
    verify_games,
)
from reckon.core.episode_context import EpisodeContext
from reckon.core.resources import MemoryBudget
from reckon.memory import ImportancePolicy, PayloadType


@pytest.mark.parametrize(
    "change, message",
    [
        ({"seeds": [1, 1]}, "unique"),
        ({"smoke_seed": 1}, "exclude"),
        ({"adapters": {"conversation": 8, "minigrid": 100}}, "one adapter"),
        ({"planning": {"family_size": 2}}, "family size"),
    ],
)
def test_confirmation_rejects_unpaired_or_ambiguous_inference(change, message):
    plan = {
        "seeds": [1, 2],
        "smoke_seed": 3,
        "adapters": {"conversation": 8},
        "planning": {"family_size": 1},
        "primary_contrasts": [{"policy": "measured", "slots": 2, "reference": "utility"}],
    }
    validate_declaration(plan)
    with pytest.raises(ValueError, match=message):
        validate_declaration({**plan, **change})


def test_explicit_importance_stays_at_admission_value_after_outcome_learning():
    memory = ComparisonMemory(MemoryBudget(max_slots=2), ImportancePolicy(), "importance")
    record_id = memory.write("key", PayloadType.CUE, initial_utility=0.25)
    context = EpisodeContext()
    memory.retrieve(record_ids=[record_id], context=context)
    memory.observe(1, context=context)
    record = memory.get_record(record_id)
    assert record is not None
    assert record.metadata["importance"] == 0.25
    assert record.utility.value != 0.25


def test_no_memory_discards_before_any_controller_read_and_full_never_prunes():
    none = run_arm("conversation", 4, 60001, "none", None, None, 0.5)
    full = run_arm("conversation", 4, 60001, "full", None, None, 0.5)
    assert none["usage"]["writes"] == none["usage"]["prunes"] == none["usage"]["discards"] > 0
    assert none["usage"]["final_slots"] == 0
    assert not any(turn["retrieved_ids"] for turn in none["evidence"]["result"]["transcript"])
    assert full["usage"]["prunes"] == 0
    assert full["usage"]["final_slots"] == full["usage"]["writes"]
    assert any(turn["retrieved_ids"] for turn in full["evidence"]["result"]["transcript"])


def test_summary_retains_adverse_pairs_and_counts_actual_episodes():
    def arm(name, value, seed):
        return {
            "adapter": "fixture",
            "policy": name,
            "slots": None if name == "none" else 2,
            "outcome": value,
            "seed": seed,
            "success": value > 0,
            "usage": {"peak_slots": 1},
            "inclusive_elapsed_s": 1,
            "probe_elapsed_s": 0,
            "probe_episodes": 0,
            "evidence": {"batches": []},
        }

    reports = [
        compact(
            {
                "seed": seed,
                "rows": [
                    arm("none", 0.5, seed),
                    arm("utility", 0.75, seed),
                    arm("measured", value, seed),
                    arm("measured_improving", value + 0.125, seed),
                ],
            }
        )
        for seed, value in [(1, 0.0), (2, 1.0)]
    ]
    row = summarize(reports)[2]
    assert row["values"] == [0.0, 1.0]
    assert row["paired"]["utility"]["values"] == [-0.75, 0.25]
    assert row["paired"]["utility"]["mean"] == -0.25
    assert row["main_episodes"] == 2
    assert row["probe_episodes"] == 0
    assert row["inclusive_elapsed_s"] == 2
    assert row["sd"] > 0
    candidate = summarize(reports, references=("none", "utility", "measured"))[3]
    assert candidate["paired"]["measured"]["values"] == [0.125, 0.125]

    bad = {"seed": 1, "rows": [arm("none", 0, 1)]}
    bad["rows"][0]["probe_episodes"] = 2
    with pytest.raises(RuntimeError, match="count disagrees"):
        compact(bad)


@pytest.mark.parametrize("changed_suffix", [".z8", ".json"])
@pytest.mark.parametrize("next_policy", ["full", "measured", "measured_improving"])
def test_game_changed_between_arms_is_refused_before_execution(
    monkeypatch, tmp_path, changed_suffix, next_policy
):
    from _utils.adapters import text_game, textworld_adapter

    monkeypatch.setattr(textworld_adapter, "check_available", lambda: True)
    game = tmp_path / "fixture.z8"
    game.write_bytes(b"executable fixture")
    game.with_suffix(".json").write_text("{}")
    pinned = game_identity(game)
    calls = []

    def fixture_episode(*args, **kwargs):
        calls.append(True)
        return {"total_reward": 0.0, "events": [], "success": False, "game_identity": pinned}

    monkeypatch.setattr(text_game, "run_textworld_episode", fixture_episode)
    run_arm("textworld", 3, 60001, "full", None, str(game), 0.5, pinned)
    reports = [{"games": [{"path": game.name, "identity": pinned}]}]
    assert len(verify_games(tmp_path, reports)) == 2
    game.with_suffix(changed_suffix).write_bytes(b"changed between arms")
    with pytest.raises(RuntimeError, match="pinned comparison identity"):
        run_arm("textworld", 3, 60001, next_policy, 2, str(game), 0.5, pinned)
    assert len(calls) == 1
    with pytest.raises(RuntimeError, match="pinned comparison identity"):
        verify_games(tmp_path, reports)


@pytest.mark.parametrize("name,rule", [("measured", "retention-score"), ("measured_improving", "improving-removal")])
def test_measured_comparison_arms_bind_the_declared_selection_rule(monkeypatch, name, rule):
    calls = []
    pinned = {"sha256": "fixture executable", "metadata_sha256": "fixture metadata"}

    def replay(config, seed, **kwargs):
        calls.append((config, seed, kwargs))
        return {"result": {"events": [], "success": False}, "outcome": 0,
                "probe_elapsed_s": 0, "probe_episodes": 0}

    monkeypatch.setattr("adapter_calibration.run_replay_retention_episode", replay)
    row = run_arm("textworld", 30, 65000, name, 4, "fixture.z8", 0.5, pinned)
    assert row["policy"] == name
    config, seed, options = calls[0]
    assert config.budget_slots == 4 and seed == 65000
    assert options["selection_rule"] == rule
    assert options["expected_game_identity"] == pinned


def test_descriptive_reference_must_have_a_declared_arm():
    with pytest.raises(ValueError, match="declared policy arms"):
        validate_declaration({"seeds": [1], "smoke_seed": 2, "policies": ["none"],
                              "descriptive_references": ["measured"]})


def test_declared_selection_rule_cannot_mislabel_a_comparison_arm():
    with pytest.raises(ValueError, match="selection rules differ"):
        validate_declaration({"seeds": [1], "smoke_seed": 2, "policies": ["measured_improving"],
                              "selection_rules": {"measured_improving": "retention-score"}})
