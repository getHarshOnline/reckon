"""Memory-fed TextWorld integration with deterministic protocol fixtures.

These tests exercise the real memory manager and recording methods. The adapter
is a fixture; passing them does not establish that TextWorld's native engine runs.
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "notebooks"))
from _utils.adapters import text_game, textworld_adapter
from reckon.memory import FIFOPolicy


@pytest.mark.parametrize(
    "instruction, command, distractor",
    [
        ("First, pick-up the brass key from the floor.", "take brass key", "take iron key"),
        ("Ensure that the chest is unlocked.", "unlock chest with brass key", "lock chest with brass key"),
        ("Insert the key into the chest to lock it.", "lock chest with key", "insert key into chest"),
        ("Make sure the chest is wide open.", "open chest", "close chest"),
        ("Make sure the door is shut.", "close door", "open door"),
        ("Retrieve the apple from the counter.", "take apple from counter", "take pear from counter"),
        ("Rest the apple on the counter.", "put apple on counter", "drop apple"),
        ("Deposit the apple into the chest.", "insert apple into chest", "put apple on counter"),
        ("Place the apple on the floor.", "drop apple", "put apple on counter"),
        ("Eat the apple.", "eat apple", "eat pear"),
        ("Take a trip through the east door.", "go east", "go west"),
        ("Once you have opened the chest, recover the mop from the chest.", "take mop from chest", "open chest"),
        ("If you can get your hands on the cup, you can put the cup inside the case.", "insert cup into case", "put cup on case"),
        ("After you have locked the chest, open the box.", "open box", "lock chest with key"),
        ("Having put the apple on the counter, deposit the pear into the chest.", "insert pear into chest", "put pear on counter"),
        ("After pulling open the door, go east.", "go east", "open door"),
        ("If you can manage to go south, take a trip north.", "go north", "go south"),
        ("Once you have opened the chest, take the apple from the counter.", "take apple from counter", "take apple from chest"),
        ("First of all, you could, like, put the apple on the counter.", "put apple on counter", "insert apple into counter"),
    ],
)
def test_visible_instruction_selects_matching_action_and_objects(instruction, command, distractor):
    assert text_game.instruction_matches(command, instruction)
    assert not text_game.instruction_matches(distractor, instruction)


def test_goal_and_progress_require_actual_retained_records():
    objective = "Welcome! First, go east. Then, go west. Then, go east.\n\n-= Hall =-"
    goal = SimpleNamespace(timestamp=0, tags=["description"], payload={"description": objective})
    history = [
        SimpleNamespace(timestamp=i, tags=["action"], payload={"command": command})
        for i, command in enumerate(["go east", "go west"], 1)
    ]
    commands = ["examine lamp", "go east", "go west"]
    observation = "-= Hall =-\nA lamp."
    assert text_game.select_scripted_action(commands, [], objective) == "go east"
    assert text_game.select_scripted_action(commands, [goal, history[0]], observation) == "go west"
    # Retrieval order need not be chronological. A command used in an earlier
    # instruction remains available when the visible task explicitly repeats it.
    assert text_game.select_scripted_action(commands, [history[1], goal, history[0]], observation) == "go east"
    assert text_game.select_scripted_action(commands, history, observation) == "examine lamp"
    assert text_game.select_scripted_action(commands, [], observation) == "examine lamp"


@pytest.mark.parametrize(
    "objective, prior_actions, commands, expected",
    [
        (
            "First thing I need you to do is to look and see that the chest is wide open. "
            "Once you have opened the chest, recover the mop from the chest. "
            "And then, deposit the mop on the floor of the laundry place.",
            ["open chest"],
            ["close chest", "take mop from chest"],
            "take mop from chest",
        ),
        (
            "First step, go to the south. Then, take the coffee cup from the cabinet. "
            "If you can get your hands on the coffee cup, you can put the coffee cup "
            "inside the case in the scullery.",
            ["go south", "take coffee cup from cabinet"],
            ["close cabinet", "insert coffee cup into cabinet", "insert coffee cup into case"],
            "insert coffee cup into case",
        ),
    ],
)
def test_diagnostic_prompts_advance_only_from_retained_actions(objective, prior_actions, commands, expected):
    """Saved 64007/64008 prompts are parser regressions, not replayed game results."""
    goal = SimpleNamespace(timestamp=0, tags=["description"], payload={"description": objective + "\n\n-= Room =-"})
    history = [
        SimpleNamespace(timestamp=i, tags=["action"], payload={"command": command})
        for i, command in enumerate(prior_actions, 1)
    ]
    assert text_game.select_scripted_action(commands, [goal, *history], "Current room.") == expected
    assert text_game.select_scripted_action(commands, [goal], "Current room.") == commands[0]
    assert text_game.select_scripted_action(commands, history, "Current room.") == commands[0]


class FixtureAdapter(textworld_adapter.TextworldAdapter):
    closed = False

    def __init__(self, config):
        self.config = config
        self.calls = 0
        self.closed = False

    def reset(self):
        return "A locked door. Choose a command.", {
            "admissible_commands": ["look", "open door"],
            "inventory": "a rusty key",
        }

    def step(self, command):
        self.calls += 1
        return (
            "A locked door. Choose a command.",
            1.0,
            command == "open door",
            {
                "admissible_commands": ["look", "open door"],
                "inventory": "a rusty key",
                "won": command == "open door",
            },
        )

    def close(self):
        self.closed = True


def test_retained_actions_change_the_next_command_and_score_is_not_summed():
    read = text_game.run_textworld_episode(
        42, 100, max_steps=3, policy=FIFOPolicy(), adapter_factory=FixtureAdapter
    )
    withheld = text_game.run_textworld_episode(
        42, 100, max_steps=3, policy=FIFOPolicy(), use_memory=False, adapter_factory=FixtureAdapter
    )
    assert [turn["command"] for turn in read["transcript"]] == ["look", "open door"]
    assert [turn["command"] for turn in withheld["transcript"]] == ["look"] * 3
    assert read["success"] and not withheld["success"]
    assert read["total_reward"] == 1
    assert [turn["reward_delta"] for turn in read["transcript"]] == [1, 0]
    assert withheld["step_limit_reached"]
    assert any(e["op_type"] == "update_score" for e in read["events"])
    assert not any(e["op_type"] == "update_score" for e in withheld["events"])
    assert read["environment"] == "integration_fixture"
    assert read["scripted_controller"] == "visible_ordered_instructions_v2"
    assert not read["seed_controls_game"]


def test_pruned_actions_cannot_drive_the_scripted_choice():
    result = text_game.run_textworld_episode(
        42, 1, max_steps=3, policy=FIFOPolicy(), adapter_factory=FixtureAdapter
    )
    assert [turn["command"] for turn in result["transcript"]] == ["look"] * 3
    assert not result["success"]
    assert any(e["op_type"] == "prune" for e in result["events"])


def test_optional_model_gets_actual_memory_and_counts_invalid_indices(monkeypatch):
    prompts = []

    def model(**kwargs):
        prompt = kwargs["messages"][0]["content"]
        prompts.append(prompt)
        index = 1 if '"command": "look"' in prompt else 0
        return {"message": {"content": json.dumps({"action_index": index})}}

    monkeypatch.setattr(text_game, "OLLAMA_AVAILABLE", True)
    monkeypatch.setattr(text_game, "ollama_chat", model)
    result = text_game.run_textworld_episode(
        42, 100, policy_backend="ollama", adapter_factory=FixtureAdapter
    )
    assert result["success"]
    assert result["fallback_count"] == 0
    assert '"command": "look"' in prompts[1]
    assert result["transcript"][1]["retrieved_ids"]
    monkeypatch.setattr(
        text_game,
        "ollama_chat",
        lambda **kwargs: {"message": {"content": '{"action_index": true}'}},
    )
    result = text_game.run_textworld_episode(
        42, 100, policy_backend="ollama", adapter_factory=FixtureAdapter
    )
    assert result["fallback_count"] == result["steps"]
    assert result["success"]  # The same memory-fed scripted fallback completes the fixture.


def test_adapter_closes_on_failure():
    adapter = FixtureAdapter(textworld_adapter.TextworldConfig())

    def broken(command):
        raise RuntimeError("fixture failure")

    adapter.step = broken
    with pytest.raises(RuntimeError, match="fixture failure"):
        text_game.run_textworld_episode(42, adapter_factory=lambda config: adapter)
    assert adapter.closed


def test_native_factory_uses_filter_and_seeds_generation(monkeypatch, tmp_path):
    seen = {}

    class RawEnvironment:
        def seed(self, value):
            seen["environment_seed"] = value

    class Wrapper:
        def __init__(self, raw):
            seen["wrapped"] = raw
            self.raw = raw

        def seed(self, value):
            self.raw.seed(value)

    def generate(options):
        seen["generation_seed"] = options.seeds
        return "game"

    game_path = tmp_path / "fixture.z8"
    metadata_path = game_path.with_suffix(".json")

    def compile_fixture(game, options):
        metadata_path.write_text(
            json.dumps(
                {
                    "KB": {"text_grammars_path": "/machine/default/grammars"},
                    "objective": "retain this fixture",
                }
            )
        )
        return str(game_path)

    fake = SimpleNamespace(
        GameOptions=SimpleNamespace,
        EnvInfos=lambda **kwargs: seen.setdefault("requested", kwargs),
        generator=SimpleNamespace(make_game=generate, compile_game=compile_fixture),
        start=lambda game, infos: RawEnvironment(),
    )
    monkeypatch.setattr(textworld_adapter, "TEXTWORLD_AVAILABLE", True)
    monkeypatch.setattr(textworld_adapter, "textworld", fake)
    monkeypatch.setattr(textworld_adapter, "generator", fake.generator)
    monkeypatch.setattr(textworld_adapter, "Filter", Wrapper, raising=False)
    adapter = textworld_adapter.TextworldAdapter(textworld_adapter.TextworldConfig(seed=17))
    assert isinstance(adapter.make_env(), Wrapper)
    assert seen["generation_seed"] == seen["environment_seed"] == 17
    assert seen["requested"]["won"] and seen["requested"]["lost"]

    assert json.loads(metadata_path.read_text()) == {
        "KB": {"text_grammars_path": ""},
        "objective": "retain this fixture",
    }
    original = '{"KB": {"text_grammars_path": "/owner/custom/grammar"}}'
    metadata_path.write_text(original)
    custom = textworld_adapter.TextworldAdapter(
        textworld_adapter.TextworldConfig(seed=17, game_file=str(game_path))
    )
    custom.make_env()
    assert metadata_path.read_text() == original
