"""
TextWorld environment adapter for Reckon.

Converts TextWorld text observations into Reckon memory records.

Requirements:
    pip install textworld
"""

from dataclasses import dataclass
from typing import Any, Optional, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from reckon.memory import CausalMemoryManager
import re
import json
from pathlib import Path

# Guarded imports
try:
    import textworld
    from textworld import generator
    from textworld.envs.wrappers import Filter
    TEXTWORLD_AVAILABLE = True
except ImportError:
    TEXTWORLD_AVAILABLE = False
    textworld = None
    generator = None
    Filter = None


def check_available() -> bool:
    """Check if TextWorld is available."""
    return TEXTWORLD_AVAILABLE


def get_install_command() -> str:
    """Get installation command for TextWorld."""
    return "pip install textworld"


@dataclass
class TextworldConfig:
    """Configuration for TextWorld adapter."""
    game_file: Optional[str] = None  # Path to .z8 game file
    max_steps: int = 100
    seed: int = 42
    game_dir: Optional[str] = None
    record_descriptions: bool = True
    record_inventory: bool = True
    record_actions: bool = True
    extract_entities: bool = True  # Extract key entities as tags


class TextworldAdapter:
    """
    Adapter for TextWorld text-based environments.

    Converts text observations and commands into Reckon memory records.

    Example:
        from reckon.memory import CausalMemoryManager, PayloadType
        from reckon.core.resources import MemoryBudget

        adapter = TextworldAdapter(TextworldConfig(game_file="game.z8"))
        cmm = CausalMemoryManager(MemoryBudget(max_slots=100))

        obs, info = adapter.reset()
        adapter.record_description(cmm, obs, info, step=0)

        obs, reward, done, info = adapter.step("take key")
        adapter.record_action(cmm, "take key", step=1)
    """

    def __init__(self, config: Optional[TextworldConfig] = None):
        """
        Initialize adapter.

        Args:
            config: Adapter configuration

        Raises:
            ImportError: If TextWorld is not installed
        """
        if not TEXTWORLD_AVAILABLE:
            raise ImportError(
                f"TextWorld not available. Install with: {get_install_command()}"
            )

        self.config = config or TextworldConfig()
        self._env: Any = None
        self._step_count: int = 0
        self._inventory: list[str] = []

    def make_env(self, game_file: Optional[str] = None):
        """Create and return the environment."""
        if textworld is None or generator is None or Filter is None:
            raise ImportError(f"TextWorld not available. Install with: {get_install_command()}")
        game = game_file or self.config.game_file

        if game is None:
            # Create a simple treasure hunt game
            options = textworld.GameOptions()
            options.nb_rooms = 3
            options.nb_objects = 5
            options.quest_length = 3
            options.seeds = self.config.seed

            game_dir = Path(self.config.game_dir) if self.config.game_dir else Path(__file__).resolve().parents[2] / "runs" / "textworld_games"
            options.path = str(game_dir) + "/"
            generated = generator.make_game(options)
            game = generator.compile_game(generated, options)
            # Default generated games need no machine-local grammar directory.
            # TextWorld loads its installed default grammar; the game already
            # carries its complete logic, entities, names and quests.
            metadata_path = Path(game).with_suffix(".json")
            if metadata_path.exists():
                metadata = json.loads(metadata_path.read_text())
                if metadata["KB"]["text_grammars_path"]:
                    metadata["KB"]["text_grammars_path"] = ""
                    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False))

        if not isinstance(game, str):
            raise ValueError("TextWorld did not produce a game path")
        self.game_file = game

        request_infos = textworld.EnvInfos(
            description=True,
            inventory=True,
            admissible_commands=True,
            intermediate_reward=True,
            won=True,
            lost=True,
        )

        # Filter supplies (text, info) and (text, cumulative_score, done, info).
        self._env = Filter(textworld.start(game, request_infos))
        self._env.seed(self.config.seed)
        return self._env

    @property
    def env(self):
        """Get or create environment."""
        if self._env is None:
            self.make_env()
        return self._env

    def reset(self) -> tuple[str, dict]:
        """Reset environment and return initial observation."""
        self._step_count = 0
        self._inventory = []
        obs, info = self.env.reset()
        return obs, info

    def step(self, command: str) -> tuple[str, float, bool, dict]:
        """Take a step in the environment."""
        self._step_count += 1
        obs, reward, done, info = self.env.step(command)

        # Update inventory tracking
        if "inventory" in info:
            self._inventory = self._parse_inventory(info["inventory"])

        return obs, reward, done, info

    def close(self) -> None:
        """Close environment."""
        if self._env is not None:
            self._env.close()
            self._env = None

    # === Memory Integration ===

    def record_description(
        self,
        cmm: "CausalMemoryManager",
        obs: str,
        info: dict,
        step: int,
        tags: Optional[list[str]] = None,
    ) -> str:
        """
        Record a room/scene description as a memory record.

        Args:
            cmm: CausalMemoryManager instance
            obs: Text observation
            info: Info dict from environment
            step: Current step number
            tags: Additional tags

        Returns:
            Record ID
        """
        from reckon.memory import PayloadType

        if not self.config.record_descriptions:
            return ""

        payload = {
            "description": obs,
            "room": info.get("description", ""),
        }

        base_tags = ["description", "textworld"]
        if tags:
            base_tags.extend(tags)

        # Extract entities as tags
        if self.config.extract_entities:
            entities = self._extract_entities(obs)
            base_tags.extend(entities)

        cmm.set_step(step)
        return cmm.write(
            payload=payload,
            payload_type=PayloadType.OBSERVATION,
            tags=base_tags,
            source_op="textworld_description",
        )

    def record_inventory(
        self,
        cmm: "CausalMemoryManager",
        info: dict,
        step: int,
        tags: Optional[list[str]] = None,
    ) -> str:
        """Record inventory state as a memory record."""
        from reckon.memory import PayloadType

        if not self.config.record_inventory:
            return ""

        inventory_text = info.get("inventory", "")
        items = self._parse_inventory(inventory_text)

        if not items:
            return ""  # Don't record empty inventory

        payload = {
            "inventory": items,
            "inventory_text": inventory_text,
        }

        base_tags = ["inventory", "textworld"]
        base_tags.extend([f"has_{item}" for item in items])
        if tags:
            base_tags.extend(tags)

        cmm.set_step(step)
        return cmm.write(
            payload=payload,
            payload_type=PayloadType.CUE,
            tags=base_tags,
            source_op="textworld_inventory",
            initial_utility=len(items) * 0.5,  # More items = more useful
        )

    def record_action(
        self,
        cmm: "CausalMemoryManager",
        command: str,
        step: int,
        tags: Optional[list[str]] = None,
    ) -> str:
        """Record an action/command as a memory record."""
        from reckon.memory import PayloadType

        if not self.config.record_actions:
            return ""

        # Parse command
        verb, obj = self._parse_command(command)

        payload = {
            "command": command,
            "verb": verb,
            "object": obj,
        }

        base_tags = ["action", "textworld", verb]
        if obj:
            base_tags.append(obj)
        if tags:
            base_tags.extend(tags)

        cmm.set_step(step)
        return cmm.write(
            payload=payload,
            payload_type=PayloadType.ACTION,
            tags=base_tags,
            source_op="textworld_action",
        )

    def record_reward(
        self,
        cmm: "CausalMemoryManager",
        reward: float,
        step: int,
        tags: Optional[list[str]] = None,
    ) -> str:
        """Record a reward as a memory record."""
        from reckon.memory import PayloadType

        if reward == 0:
            return ""

        payload = {
            "reward": reward,
        }

        base_tags = ["reward", "textworld"]
        if reward > 0:
            base_tags.append("positive_reward")
        if tags:
            base_tags.extend(tags)

        cmm.set_step(step)
        return cmm.write(
            payload=payload,
            payload_type=PayloadType.REWARD,
            tags=base_tags,
            source_op="textworld_reward",
            initial_utility=abs(reward),
        )

    def _extract_entities(self, text: str) -> list[str]:
        """Extract key entities from text as tags."""
        entities = []

        # Common game objects
        patterns = [
            r"\b(key|keys)\b",
            r"\b(door|doors)\b",
            r"\b(chest|chests)\b",
            r"\b(sword|knife|weapon)\b",
            r"\b(book|scroll|note)\b",
            r"\b(coin|gold|treasure)\b",
            r"\b(potion|bottle)\b",
            r"\b(lamp|torch|light)\b",
        ]

        text_lower = text.lower()
        for pattern in patterns:
            match = re.search(pattern, text_lower)
            if match:
                entities.append(match.group(1))

        return list(set(entities))

    def _parse_inventory(self, inventory_text: str) -> list[str]:
        """Parse inventory text to list of items."""
        if not inventory_text or "nothing" in inventory_text.lower():
            return []

        # Simple parsing: split by common delimiters
        items = re.findall(r"(?:a |an |the )?(\w+)", inventory_text.lower())
        # Filter common words
        stop_words = {"you", "are", "carrying", "have", "the", "a", "an", "and"}
        items = [i for i in items if i not in stop_words]
        return items

    def _parse_command(self, command: str) -> tuple[str, Optional[str]]:
        """Parse command into verb and object."""
        parts = command.lower().split()
        if not parts:
            return "unknown", None

        verb = parts[0]
        obj = " ".join(parts[1:]) if len(parts) > 1 else None
        return verb, obj


# === Fallback traces for demo mode ===

DEMO_TRACE = [
    {
        "step": 0,
        "type": "description",
        "text": "You are in a dark room. There is a rusty key on the floor.",
        "entities": ["key", "room"],
    },
    {
        "step": 1,
        "type": "action",
        "command": "take key",
        "verb": "take",
        "object": "key",
    },
    {
        "step": 2,
        "type": "inventory",
        "items": ["rusty key"],
    },
    {
        "step": 3,
        "type": "action",
        "command": "go north",
        "verb": "go",
        "object": "north",
    },
    {
        "step": 4,
        "type": "description",
        "text": "You are in a corridor. There is a locked door to the east.",
        "entities": ["door", "corridor"],
    },
    {
        "step": 5,
        "type": "action",
        "command": "unlock door with key",
        "verb": "unlock",
        "object": "door",
    },
    {
        "step": 6,
        "type": "description",
        "text": "The door opens! You see a treasure chest inside.",
        "entities": ["chest", "treasure"],
    },
    {
        "step": 7,
        "type": "reward",
        "reward": 1.0,
    },
]


def get_demo_trace() -> list[dict]:
    """Get a demo trace when TextWorld is not available."""
    return DEMO_TRACE.copy()


def run_demo_episode(cmm: "CausalMemoryManager", seed: int = 42, quiet: bool = False) -> dict:
    """
    Run a demo episode using fallback trace.

    Args:
        cmm: CausalMemoryManager instance
        seed: Seed (not used for demo, but kept for API compatibility)
        quiet: If False, prints fallback warning banner

    Returns:
        Episode result dict
    """
    from reckon.memory import PayloadType

    if not quiet:
        print('''
================================================================================
    WARNING: RUNNING FALLBACK TRACE (NOT REAL ENVIRONMENT)
================================================================================

    TextWorld is not installed. Running PRE-RECORDED demo trace.

    To enable live runs:
        pip install textworld

================================================================================
''')

    trace = get_demo_trace()
    total_reward = 0
    inventory = []

    for event in trace:
        step = event["step"]
        cmm.set_step(step)

        if event["type"] == "description":
            tags = ["description", "demo"] + event.get("entities", [])
            cmm.write(
                payload={"description": event["text"]},
                payload_type=PayloadType.OBSERVATION,
                tags=tags,
                source_op="demo_description",
            )

        elif event["type"] == "action":
            cmm.write(
                payload={"command": event["command"], "verb": event["verb"]},
                payload_type=PayloadType.ACTION,
                tags=["action", "demo", event["verb"]],
                source_op="demo_action",
            )

        elif event["type"] == "inventory":
            inventory = event["items"]
            cmm.write(
                payload={"inventory": inventory},
                payload_type=PayloadType.CUE,
                tags=["inventory", "demo"] + [f"has_{i}" for i in inventory],
                source_op="demo_inventory",
            )

        elif event["type"] == "reward":
            reward = event["reward"]
            total_reward += reward
            cmm.write(
                payload={"reward": reward},
                payload_type=PayloadType.REWARD,
                tags=["reward", "demo"],
                source_op="demo_reward",
                initial_utility=abs(reward),
            )

    return {
        "success": total_reward > 0,
        "total_reward": total_reward,
        "steps": len(trace),
        "final_inventory": inventory,
        "demo_mode": True,
    }
