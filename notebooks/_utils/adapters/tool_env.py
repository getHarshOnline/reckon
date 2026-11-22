"""
Tool-Using Conversation Environment for Reckon notebooks.

A deterministic environment that simulates realistic assistant workloads:
- Changing constraints mid-conversation
- Red herrings and distractors
- Delayed references ("as I said earlier...")
- Multi-step goals requiring tool outputs

No external dependencies required.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

__all__ = [
    "ToolEnvConfig",
    "ToolEnv",
    "Episode",
    "StepResult",
    "EpisodeMetrics",
    "get_demo_episodes",
    "run_demo_episode",
]


# =============================================================================
# Tool Implementations
# =============================================================================

class Scratchpad:
    """Simple key-value scratchpad for tool use."""

    def __init__(self):
        self._data: dict[str, str] = {}

    def write(self, key: str, value: str) -> str:
        """Write a value to the scratchpad."""
        self._data[key] = value
        return f"Stored '{key}'"

    def read(self, key: str) -> str:
        """Read a value from the scratchpad."""
        if key in self._data:
            return self._data[key]
        return f"Key '{key}' not found"

    def clear(self) -> None:
        """Clear the scratchpad."""
        self._data.clear()

    def get_all(self) -> dict[str, str]:
        """Get all stored data."""
        return self._data.copy()


def calculator(expr: str) -> str:
    """
    Safe calculator for simple math expressions.

    Supports: +, -, *, /, **, (), numbers
    Returns: numeric result as string or error message
    """
    # Sanitize: only allow safe characters
    allowed = set("0123456789+-*/().eE ")
    if not all(c in allowed for c in expr):
        return "Error: Invalid characters in expression"

    # Prevent code injection
    if any(kw in expr.lower() for kw in ["import", "eval", "exec", "__"]):
        return "Error: Invalid expression"

    try:
        # Use eval with restricted builtins
        result = eval(expr, {"__builtins__": {}}, {})
        if isinstance(result, (int, float)):
            return str(result)
        return "Error: Result is not a number"
    except (SyntaxError, TypeError, ZeroDivisionError, OverflowError) as e:
        return f"Error: {type(e).__name__}"


# Small in-notebook corpus for local_search
LOCAL_CORPUS = [
    "The weather in Boston is typically cold in winter, with temperatures around 30F.",
    "Seattle is known for its rainy weather, averaging 150 rainy days per year.",
    "Python was created by Guido van Rossum and first released in 1991.",
    "Machine learning models require training data to learn patterns.",
    "The capital of France is Paris, known for the Eiffel Tower.",
    "Memory management is crucial for long-running applications.",
    "The Pythagorean theorem states that a^2 + b^2 = c^2 for right triangles.",
    "Neural networks are inspired by biological neurons in the brain.",
    "The speed of light is approximately 299,792,458 meters per second.",
    "Reckon studies what agents should retain under memory and compute budgets.",
    "Agents use external memory to overcome context length limitations.",
    "Tool use allows LLMs to interact with external systems.",
    "The Fibonacci sequence starts with 1, 1, 2, 3, 5, 8, 13...",
    "HTTP status code 404 means 'Not Found'.",
    "JSON is a lightweight data interchange format.",
]


def local_search(query: str, corpus: Optional[list[str]] = None) -> str:
    """
    Simple keyword-based search over a local corpus.

    Args:
        query: Search terms (space-separated)
        corpus: Optional custom corpus, defaults to LOCAL_CORPUS

    Returns:
        Matching snippets as newline-separated string
    """
    if corpus is None:
        corpus = LOCAL_CORPUS

    query_terms = query.lower().split()
    if not query_terms:
        return "No search terms provided"

    matches = []
    for doc in corpus:
        doc_lower = doc.lower()
        score = sum(1 for term in query_terms if term in doc_lower)
        if score > 0:
            matches.append((score, doc))

    # Sort by score descending
    matches.sort(key=lambda x: -x[0])

    if not matches:
        return "No results found"

    # Return top 3
    return "\n".join(doc for _, doc in matches[:3])


def schema_validate(json_str: str) -> str:
    """
    Validate a JSON string.

    Args:
        json_str: JSON string to validate

    Returns:
        "Valid JSON" or error message
    """
    try:
        json.loads(json_str)
        return "Valid JSON"
    except json.JSONDecodeError as e:
        return f"Invalid JSON: {e}"


# Tool registry
TOOLS: dict[str, Callable[..., str]] = {
    "calculator": calculator,
    "local_search": local_search,
    "schema_validate": schema_validate,
}


# =============================================================================
# Episode Generation
# =============================================================================

@dataclass
class UserMessage:
    """A user message in an episode."""
    content: str
    step: int
    is_constraint: bool = False  # States a constraint agent must remember
    is_red_herring: bool = False  # Distractor
    is_reference: bool = False  # References earlier content
    constraint_key: Optional[str] = None
    constraint_value: Optional[str] = None
    requires_tool: Optional[str] = None  # Tool needed to answer
    requires_memory_of_step: Optional[int] = None  # Needs memory of this step


@dataclass
class Episode:
    """A complete episode with user messages and success criteria."""
    id: str
    seed: int
    messages: list[UserMessage]
    final_goal: str
    required_constraints: dict[str, str]  # Must maintain these
    expected_tool_calls: list[str]  # Tools that should be called
    total_steps: int

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "seed": self.seed,
            "messages": [
                {
                    "content": m.content,
                    "step": m.step,
                    "is_constraint": m.is_constraint,
                    "is_red_herring": m.is_red_herring,
                    "is_reference": m.is_reference,
                    "constraint_key": m.constraint_key,
                    "constraint_value": m.constraint_value,
                    "requires_tool": m.requires_tool,
                    "requires_memory_of_step": m.requires_memory_of_step,
                }
                for m in self.messages
            ],
            "final_goal": self.final_goal,
            "required_constraints": self.required_constraints,
            "expected_tool_calls": self.expected_tool_calls,
            "total_steps": self.total_steps,
        }


class EpisodeGenerator:
    """Generates deterministic episodes from seeds."""

    # Templates for constraints
    CONSTRAINT_TEMPLATES = [
        ("format", ["JSON only", "bullet points", "numbered list", "single paragraph"]),
        ("length", ["under 50 words", "exactly 3 sentences", "2-3 paragraphs", "one sentence"]),
        ("tone", ["formal", "casual", "technical", "friendly"]),
        ("language", ["simple words only", "include examples", "be concise", "be detailed"]),
        ("topic_focus", ["focus on facts", "focus on opinions", "focus on how-to", "focus on why"]),
    ]

    # Templates for red herrings
    RED_HERRINGS = [
        "By the way, did you know that {fact}?",
        "Interesting aside: {fact}",
        "Oh, I just remembered - {fact}",
        "Speaking of which, {fact}",
        "Fun fact: {fact}",
    ]

    RANDOM_FACTS = [
        "dolphins sleep with one eye open",
        "honey never spoils",
        "octopuses have three hearts",
        "bananas are berries but strawberries aren't",
        "a group of flamingos is called a flamboyance",
    ]

    # Templates for references
    REFERENCE_TEMPLATES = [
        "As I mentioned earlier, please {action}",
        "Remember what I said about {topic}? {action}",
        "Going back to my earlier request about {topic}, {action}",
        "Following up on {topic} - {action}",
    ]

    # Templates for tool-requiring messages
    TOOL_MESSAGES = {
        "calculator": [
            "Can you calculate {expr}?",
            "What is {expr}?",
            "Help me compute {expr}",
        ],
        "local_search": [
            "What do you know about {topic}?",
            "Find information about {topic}",
            "Search for {topic}",
        ],
        "scratchpad_write": [
            "Please remember this: {value}",
            "Store this for later: {value}",
            "Note this down: {value}",
        ],
        "scratchpad_read": [
            "What did I ask you to remember about {key}?",
            "Can you recall the {key} I mentioned?",
            "What did you store about {key}?",
        ],
    }

    # Final goal templates
    FINAL_GOALS = [
        "Now summarize everything following all the constraints I gave you.",
        "Please provide a final answer considering all my requirements.",
        "Give me a complete response following all the guidelines I specified.",
        "Compile everything we discussed into a response that meets my criteria.",
    ]

    def __init__(self, seed: int):
        """Initialize with seed."""
        self.seed = seed
        self.rng = random.Random(seed)

    def generate(self, n_steps: int = 8) -> Episode:
        """
        Generate a deterministic episode.

        Args:
            n_steps: Number of user messages in episode

        Returns:
            Episode with messages, constraints, and success criteria
        """
        messages = []
        constraints: dict[str, str] = {}
        expected_tools: list[str] = []

        # Decide structure
        n_constraints = self.rng.randint(2, 3)
        n_red_herrings = self.rng.randint(1, 2)
        n_tool_uses = self.rng.randint(1, 3)
        n_references = self.rng.randint(1, 2)

        # Pick positions for each type
        positions = list(range(n_steps - 1))  # Last step is final goal
        self.rng.shuffle(positions)

        constraint_positions = positions[:n_constraints]
        remaining = positions[n_constraints:]

        red_herring_positions = remaining[:n_red_herrings]
        remaining = remaining[n_red_herrings:]

        tool_positions = remaining[:n_tool_uses]
        remaining = remaining[n_tool_uses:]

        reference_positions = remaining[:n_references]

        # Select constraints
        available_constraints = self.CONSTRAINT_TEMPLATES.copy()
        self.rng.shuffle(available_constraints)

        for i, pos in enumerate(sorted(constraint_positions)):
            key, values = available_constraints[i % len(available_constraints)]
            value = self.rng.choice(values)
            constraints[key] = value

            messages.append(UserMessage(
                content=f"Important: when you respond, use {value} ({key} requirement).",
                step=pos,
                is_constraint=True,
                constraint_key=key,
                constraint_value=value,
            ))

        # Add red herrings
        for pos in red_herring_positions:
            template = self.rng.choice(self.RED_HERRINGS)
            fact = self.rng.choice(self.RANDOM_FACTS)
            content = template.format(fact=fact)

            messages.append(UserMessage(
                content=content,
                step=pos,
                is_red_herring=True,
            ))

        # Add tool-requiring messages
        tools_used = []
        for pos in tool_positions:
            tool = self.rng.choice(["calculator", "local_search"])
            tools_used.append(tool)

            if tool == "calculator":
                a, b = self.rng.randint(10, 99), self.rng.randint(10, 99)
                op = self.rng.choice(["+", "-", "*"])
                expr = f"{a} {op} {b}"
                template = self.rng.choice(self.TOOL_MESSAGES["calculator"])
                content = template.format(expr=expr)
            else:  # local_search
                topics = ["Python", "memory", "neural networks", "weather", "speed of light"]
                topic = self.rng.choice(topics)
                template = self.rng.choice(self.TOOL_MESSAGES["local_search"])
                content = template.format(topic=topic)

            messages.append(UserMessage(
                content=content,
                step=pos,
                requires_tool=tool,
            ))

        expected_tools = tools_used

        # Add references to earlier messages
        for pos in reference_positions:
            # Reference an earlier constraint
            if constraints:
                key = self.rng.choice(list(constraints.keys()))
                value = constraints[key]
                topic = f"the {key} requirement"
                action = f"please keep following the {value} format"
                template = self.rng.choice(self.REFERENCE_TEMPLATES)
                content = template.format(topic=topic, action=action)

                # Find the step where this constraint was introduced
                constraint_step = None
                for m in messages:
                    if m.constraint_key == key:
                        constraint_step = m.step
                        break

                messages.append(UserMessage(
                    content=content,
                    step=pos,
                    is_reference=True,
                    requires_memory_of_step=constraint_step,
                ))

        # Sort by step
        messages.sort(key=lambda m: m.step)

        # Add final goal
        final_goal = self.rng.choice(self.FINAL_GOALS)
        messages.append(UserMessage(
            content=final_goal,
            step=n_steps - 1,
            is_reference=True,  # Implicitly references all constraints
        ))

        # Generate episode ID from seed
        episode_id = hashlib.md5(f"episode-{self.seed}".encode()).hexdigest()[:8]

        return Episode(
            id=episode_id,
            seed=self.seed,
            messages=messages,
            final_goal=final_goal,
            required_constraints=constraints,
            expected_tool_calls=expected_tools,
            total_steps=n_steps,
        )


# =============================================================================
# Step Results and Metrics
# =============================================================================

@dataclass
class StepResult:
    """Result of a single step in the environment."""
    step: int
    user_message: str
    agent_response: Optional[dict[str, Any]]  # Parsed agent response
    tool_called: Optional[str]
    tool_result: Optional[str]
    memory_written: list[dict[str, str]]
    parse_error: Optional[str]
    constraint_violated: Optional[str]
    success: bool


@dataclass
class EpisodeMetrics:
    """Metrics for a completed episode."""
    episode_id: str
    seed: int
    total_steps: int
    constraint_retention_accuracy: float  # Literal constraint recall in the final answer
    contradiction_rate: float  # How often agent contradicted itself
    final_goal_success: bool  # Did agent achieve the goal
    tool_use_correctness: float  # Correct tool calls / expected tool calls
    parse_failures: int  # Number of JSON parse failures
    total_tool_calls: int
    correct_tool_calls: int

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "episode_id": self.episode_id,
            "seed": self.seed,
            "total_steps": self.total_steps,
            "constraint_retention_accuracy": self.constraint_retention_accuracy,
            "contradiction_rate": self.contradiction_rate,
            "final_goal_success": self.final_goal_success,
            "tool_use_correctness": self.tool_use_correctness,
            "parse_failures": self.parse_failures,
            "total_tool_calls": self.total_tool_calls,
            "correct_tool_calls": self.correct_tool_calls,
        }


# =============================================================================
# Tool Environment
# =============================================================================

@dataclass
class ToolEnvConfig:
    """Configuration for ToolEnv."""
    n_steps: int = 8  # Steps per episode
    require_strict_json: bool = True  # Fail on invalid JSON
    corpus: Optional[list[str]] = None  # Custom search corpus


class ToolEnv:
    """
    Tool-Using Conversation Environment.

    Simulates a realistic assistant workload with:
    - Changing constraints mid-conversation
    - Red herrings (distractors)
    - Delayed references ("as I said earlier...")
    - Multi-step goals requiring tool outputs

    The environment is fully deterministic given a seed.
    """

    def __init__(self, config: Optional[ToolEnvConfig] = None):
        """Initialize environment."""
        self.config = config or ToolEnvConfig()
        self._episode: Optional[Episode] = None
        self._step: int = 0
        self._scratchpad = Scratchpad()
        self._history: list[StepResult] = []
        self._tool_calls: list[str] = []
        self._constraint_violations: list[str] = []

    def reset(self, seed: int) -> tuple[str, dict[str, Any]]:
        """
        Reset environment with a new episode.

        Args:
            seed: Random seed for deterministic episode generation

        Returns:
            Initial observation (first user message) and info dict
        """
        generator = EpisodeGenerator(seed)
        self._episode = generator.generate(n_steps=self.config.n_steps)
        self._step = 0
        self._scratchpad.clear()
        self._history = []
        self._tool_calls = []
        self._constraint_violations = []

        first_message = self._episode.messages[0].content

        info = {
            "episode_id": self._episode.id,
            "seed": seed,
            "total_steps": self._episode.total_steps,
            "constraints": self._episode.required_constraints,
        }

        return first_message, info

    def step(
        self,
        agent_response: dict[str, Any],
    ) -> tuple[str, float, bool, bool, dict[str, Any]]:
        """
        Process agent response and return next observation.

        Args:
            agent_response: Parsed agent response dict with:
                - "tool": {"name": "...", "args": {...}} | null
                - "final": "message to user"
                - "memory_write": [{"tag": "...", "content": "..."}]

        Returns:
            Tuple of (observation, reward, terminated, truncated, info)
        """
        if self._episode is None:
            raise RuntimeError("Must call reset() before step()")

        current_message = self._episode.messages[self._step]
        result = StepResult(
            step=self._step,
            user_message=current_message.content,
            agent_response=agent_response,
            tool_called=None,
            tool_result=None,
            memory_written=[],
            parse_error=None,
            constraint_violated=None,
            success=True,
        )

        reward = 0.0

        # Handle tool call if present
        tool_spec = agent_response.get("tool")
        if tool_spec is not None:
            tool_name = tool_spec.get("name", "")
            tool_args = tool_spec.get("args", {})

            result.tool_called = tool_name
            self._tool_calls.append(tool_name)

            if tool_name == "calculator":
                expr = tool_args.get("expr", "")
                result.tool_result = calculator(expr)
            elif tool_name == "local_search":
                query = tool_args.get("query", "")
                result.tool_result = local_search(query, self.config.corpus)
            elif tool_name == "scratchpad_write":
                key = tool_args.get("key", "")
                value = tool_args.get("value", "")
                result.tool_result = self._scratchpad.write(key, value)
            elif tool_name == "scratchpad_read":
                key = tool_args.get("key", "")
                result.tool_result = self._scratchpad.read(key)
            elif tool_name == "schema_validate":
                json_str = tool_args.get("json_str", "")
                result.tool_result = schema_validate(json_str)
            else:
                result.tool_result = f"Unknown tool: {tool_name}"

            # Check if this was the expected tool
            if current_message.requires_tool == tool_name:
                reward += 0.5

        # Handle memory writes
        memory_writes = agent_response.get("memory_write", [])
        result.memory_written = memory_writes

        # Small reward for appropriate memory use
        if memory_writes and current_message.is_constraint:
            reward += 0.2

        # Check for constraint handling
        if current_message.is_constraint:
            # Reward for acknowledging constraint
            final_msg = agent_response.get("final", "").lower()
            if current_message.constraint_value and \
               current_message.constraint_value.lower() in final_msg:
                reward += 0.3

        self._history.append(result)
        self._step += 1

        # Check if done
        terminated = self._step >= len(self._episode.messages)
        truncated = False

        # Get next observation
        if terminated:
            observation = ""
            # Final reward based on overall success
            final_reward = self._compute_final_reward()
            reward += final_reward
        else:
            observation = self._episode.messages[self._step].content

        info = {
            "step": self._step,
            "tool_result": result.tool_result,
            "is_final": terminated,
        }

        return observation, reward, terminated, truncated, info

    def _compute_final_reward(self) -> float:
        """Compute final reward based on episode success metrics."""
        metrics = self.get_metrics()

        reward = 0.0

        # Reward for constraint retention
        reward += metrics.constraint_retention_accuracy * 2.0

        # Reward for correct tool use
        reward += metrics.tool_use_correctness * 1.0

        # Penalty for contradictions
        reward -= metrics.contradiction_rate * 1.0

        # Penalty for parse failures
        reward -= metrics.parse_failures * 0.5

        return reward

    def get_metrics(self) -> EpisodeMetrics:
        """
        Compute metrics for the current episode.

        Uses ground truth constraints from Episode for accurate measurement.
        The final answer is scored for literal recall of required values, not prose compliance.
        """
        if self._episode is None:
            raise RuntimeError("No episode in progress")

        # Only the answer to the last prompt can demonstrate delayed recall.
        # Earlier acknowledgements and writes do not survive in this score.
        ground_truth = self._episode.required_constraints
        completed = self._step >= len(self._episode.messages)
        final_response = (
            self._history[-1].agent_response or {}
            if completed and self._history else {}
        )
        final_text = final_response.get("final", "").lower()
        recalled = sum(value.lower() in final_text for value in ground_truth.values())
        constraint_accuracy = recalled / len(ground_truth) if ground_truth else 1.0

        hedge_phrases = [
            "i'm not sure", "not certain", "might be", "could be",
            "possibly", "perhaps", "i think", "maybe", "unclear",
        ]

        # Compute contradiction rate with confidence weighting
        # Hedged responses weighted at 0.3x, confident wrong at 1.0x
        weighted_contradictions = 0.0

        for result in self._history:
            if result.constraint_violated:
                final_msg = result.agent_response.get("final", "").lower() if result.agent_response else ""
                is_hedged = any(phrase in final_msg for phrase in hedge_phrases)
                # Hedged wrong is less bad than confident wrong
                weight = 0.3 if is_hedged else 1.0
                weighted_contradictions += weight

        contradiction_rate = weighted_contradictions / max(len(self._history), 1)

        # Compute tool use correctness
        expected = set(self._episode.expected_tool_calls)
        called = set(self._tool_calls)
        correct = len(expected & called)
        tool_correctness = correct / max(len(expected), 1)

        # Count parse failures
        parse_failures = sum(1 for r in self._history if r.parse_error is not None)

        # Final goal success (stricter criteria)
        final_success = (
            constraint_accuracy >= 0.5 and
            tool_correctness >= 0.5 and
            parse_failures == 0 and
            contradiction_rate < 0.3  # Added contradiction check
        )

        return EpisodeMetrics(
            episode_id=self._episode.id,
            seed=self._episode.seed,
            total_steps=self._episode.total_steps,
            constraint_retention_accuracy=constraint_accuracy,
            contradiction_rate=contradiction_rate,
            final_goal_success=final_success,
            tool_use_correctness=tool_correctness,
            parse_failures=parse_failures,
            total_tool_calls=len(self._tool_calls),
            correct_tool_calls=correct,
        )

    def get_episode(self) -> Optional[Episode]:
        """Get the current episode."""
        return self._episode

    def get_history(self) -> list[StepResult]:
        """Get step history."""
        return self._history.copy()

    def get_scratchpad(self) -> dict[str, str]:
        """Get scratchpad contents."""
        return self._scratchpad.get_all()


# =============================================================================
# Demo Episodes
# =============================================================================

def get_demo_episodes(n_episodes: int = 3, base_seed: int = 42) -> list[Episode]:
    """
    Generate demo episodes for testing.

    Args:
        n_episodes: Number of episodes to generate
        base_seed: Starting seed

    Returns:
        List of deterministic episodes
    """
    episodes = []
    for i in range(n_episodes):
        generator = EpisodeGenerator(base_seed + i)
        episodes.append(generator.generate())
    return episodes


def run_demo_episode(
    env: ToolEnv,
    seed: int,
    scripted_responses: Optional[list[dict[str, Any]]] = None,
) -> tuple[list[StepResult], EpisodeMetrics]:
    """
    Run a demo episode with scripted responses.

    Args:
        env: ToolEnv instance
        seed: Episode seed
        scripted_responses: Optional pre-defined responses

    Returns:
        Tuple of (step history, episode metrics)
    """
    obs, info = env.reset(seed)

    # Default scripted responses
    if scripted_responses is None:
        scripted_responses = [
            {"tool": None, "final": "I understand. I'll follow that constraint.", "memory_write": []},
            {"tool": None, "final": "Got it, I'll keep that in mind.", "memory_write": []},
            {"tool": {"name": "calculator", "args": {"expr": "42 + 7"}}, "final": "Let me calculate.", "memory_write": []},
            {"tool": None, "final": "Interesting fact!", "memory_write": []},
            {"tool": {"name": "local_search", "args": {"query": "memory"}}, "final": "Searching...", "memory_write": []},
            {"tool": None, "final": "Yes, I remember that requirement.", "memory_write": []},
            {"tool": None, "final": "Here's my final response following all constraints.", "memory_write": []},
            {"tool": None, "final": "Summary complete.", "memory_write": []},
        ]

    step_idx = 0
    terminated = False

    while not terminated:
        response = scripted_responses[step_idx % len(scripted_responses)]
        obs, reward, terminated, truncated, info = env.step(response)
        step_idx += 1

    return env.get_history(), env.get_metrics()
