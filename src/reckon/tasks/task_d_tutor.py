"""
Task D: Tutor Loop Simulation

A multi-session tutoring simulation where a student has persistent misconceptions.
The tutor must remember which hints worked across sessions to efficiently
teach the student.

Memory challenge: Remember which hints cleared misconceptions across sessions.
"""

# pylint: disable=duplicate-code

# Standard library
from dataclasses import dataclass, field
from typing import Optional

# Third party
import numpy as np

from reckon.core.episode_context import EpisodeContext
from reckon.memory.manager import CausalMemoryManager
from reckon.memory.record import PayloadType
from reckon.metrics import MemoryEfficiencyMetrics, PerformanceMetrics

# Local
from reckon.tasks.base import BaseTask, TaskResult


@dataclass
class TutorConfig:
    """Configuration for the tutor task."""

    num_concepts: int = 10
    num_sessions: int = 5
    questions_per_session: int = 10
    misconception_probability: float = 0.4  # Probability of initial misconception
    hint_success_probability: float = 0.7  # Base probability hint clears misconception
    hint_effectiveness_boost: float = 0.2  # Boost for previously effective hints


@dataclass
class StudentModel:
    """Simulated student with misconceptions."""

    concepts_mastered: dict[int, bool] = field(default_factory=dict)
    misconceptions: dict[int, bool] = field(default_factory=dict)
    hints_received: dict[int, list[str]] = field(default_factory=dict)


class TutorEnvironment:
    """
    Tutoring environment with persistent student state.

    - Student has N concepts, some with misconceptions
    - Tutor asks questions and gives hints
    - Hints probabilistically clear misconceptions
    - Student state persists across sessions
    """

    HINT_TYPES = ["analogy", "example", "definition", "visualization", "practice"]

    def __init__(self, config: TutorConfig, rng: np.random.Generator):
        self.config = config
        self.rng = rng
        self.reset_student()

    def reset_student(self) -> StudentModel:
        """Create a new student with random misconceptions."""
        self.student = StudentModel()

        for concept_id in range(self.config.num_concepts):
            self.student.concepts_mastered[concept_id] = False
            self.student.hints_received[concept_id] = []

            # Randomly assign misconceptions
            if self.rng.random() < self.config.misconception_probability:
                self.student.misconceptions[concept_id] = True
            else:
                self.student.misconceptions[concept_id] = False
                self.student.concepts_mastered[concept_id] = True

        return self.student

    def ask_question(self, concept_id: int) -> tuple[bool, bool]:
        """
        Ask student a question about a concept.

        Returns:
            (correct_answer, has_misconception)
        """
        has_misconception = self.student.misconceptions.get(concept_id, False)
        is_mastered = self.student.concepts_mastered.get(concept_id, False)

        if is_mastered:
            # Mastered concepts answered correctly
            correct = True
        elif has_misconception:
            # Misconception leads to wrong answer
            correct = False
        else:
            # No misconception but not mastered - random with 50% chance
            correct = self.rng.random() > 0.5

        return correct, has_misconception

    def give_hint(
        self,
        concept_id: int,
        hint_type: str,
        was_effective_before: bool = False,
    ) -> bool:
        """
        Give a hint for a concept.

        Args:
            concept_id: Concept to provide hint for
            hint_type: Type of hint
            was_effective_before: Whether this hint type worked before

        Returns:
            True if hint cleared the misconception
        """
        self.student.hints_received.setdefault(concept_id, []).append(hint_type)

        if not self.student.misconceptions.get(concept_id, False):
            # No misconception to clear
            return False

        # Calculate success probability
        success_prob = self.config.hint_success_probability
        if was_effective_before:
            success_prob += self.config.hint_effectiveness_boost
        success_prob = min(success_prob, 0.95)

        if self.rng.random() < success_prob:
            # Hint cleared misconception
            self.student.misconceptions[concept_id] = False
            self.student.concepts_mastered[concept_id] = True
            return True

        return False


class TutorTask(BaseTask):
    """
    Tutor Loop benchmark task.

    Tests agent's ability to:
    1. Remember which hints worked for which misconceptions
    2. Apply learned hint strategies across sessions
    3. Track student progress over time

    Metrics:
    - improvement_rate: Fraction of misconceptions cleared
    - mean_episode_effective_hint_read_fraction: Mean episode fraction of effective hint reads
    """

    def __init__(self, config: Optional[TutorConfig] = None):
        self.config = config or TutorConfig()

    @property
    def name(self) -> str:
        return "Tutor Loop"

    @property
    def description(self) -> str:
        return "Multi-session tutoring; remember effective hints for misconceptions"

    # pylint: disable=too-many-locals,too-many-statements,too-many-nested-blocks
    # Keep the common task interface, including its keyword-only memory controls.
    def run(  # pylint: disable=too-many-arguments
        self,
        cmm: CausalMemoryManager,
        num_episodes: int,
        seed: int,
        *,
        reset_memory: bool = False,
        learn_utility: bool = True,
    ) -> TaskResult:
        """Run the tutor task."""
        if num_episodes < 1:
            raise ValueError("num_episodes must be positive")
        episode_seeds = np.random.SeedSequence(seed).spawn(num_episodes)

        all_improvement_rates = []
        all_effective_hint_read_fractions = []
        episodes_data = []

        for ep in range(num_episodes):
            with EpisodeContext(episode_id=f"tutor_ep{ep}"):
                student_seed, response_seed, concept_seed, hint_seed = episode_seeds[ep].spawn(4)
                env = TutorEnvironment(self.config, np.random.default_rng(student_seed))
                concept_rng = np.random.default_rng(concept_seed)
                hint_rng = np.random.default_rng(hint_seed)
                response_seeds = response_seed.spawn(
                    self.config.num_sessions * self.config.questions_per_session
                )
                cmm.set_episode(f"tutor_ep{ep}", reset_memory=reset_memory)

                # Track initial misconceptions
                initial_misconceptions = sum(1 for v in env.student.misconceptions.values() if v)
                cleared_misconceptions = 0

                total_writes = 0
                total_reads = 0
                useful_reads = 0  # Reads that led to successful hints

                # Effective hints: {concept_id: hint_type}
                effective_hints: dict[int, str] = {}
                step = 0

                for session in range(self.config.num_sessions):
                    for _q in range(self.config.questions_per_session):
                        cmm.set_step(step)
                        # Keep each question's response randomness fixed even if
                        # another policy skips a hint or clears a concept sooner.
                        env.rng = np.random.default_rng(response_seeds[step])
                        step += 1

                        # Select a concept to ask about
                        # Prioritize concepts with misconceptions
                        concept_candidates = [
                            c
                            for c, m in env.student.misconceptions.items()
                            if m and not env.student.concepts_mastered.get(c, False)
                        ]

                        if not concept_candidates:
                            # All misconceptions cleared, ask random concept
                            concept_id = int(concept_rng.integers(0, self.config.num_concepts))
                        else:
                            concept_id = int(concept_rng.choice(concept_candidates))

                        # Ask question
                        correct, has_misconception = env.ask_question(concept_id)

                        if not correct and has_misconception:
                            # Need to give a hint

                            # Check memory for effective hints
                            hint_type = None
                            was_effective = False

                            records = cmm.retrieve(
                                query={"tags": [f"concept_{concept_id}"]},
                                limit=1,
                            )

                            if records:
                                total_reads += 1
                                hint_type = records[0].payload.get("hint_type")
                                was_effective = True
                            else:
                                # Try random hint
                                hint_type = hint_rng.choice(env.HINT_TYPES)

                            # Give the hint
                            success = env.give_hint(concept_id, hint_type, was_effective)

                            if success:
                                cleared_misconceptions += 1
                                effective_hints[concept_id] = hint_type

                                if was_effective:
                                    useful_reads += 1

                                # Store this effective hint
                                cmm.write(
                                    payload={
                                        "concept_id": int(concept_id),
                                        "hint_type": hint_type,
                                        "session": int(session),
                                    },
                                    payload_type=PayloadType.TRACE,
                                    tags=[
                                        f"concept_{concept_id}",
                                        "effective_hint",
                                        f"session_{session}",
                                    ],
                                    source_op="store_effective_hint",
                                    metadata={"importance": 1.0},
                                )
                                total_writes += 1

                # Compute episode metrics
                improvement_rate = (
                    cleared_misconceptions / initial_misconceptions
                    if initial_misconceptions > 0
                    else 1.0
                )
                effective_hint_read_fraction = (
                    useful_reads / total_reads if total_reads > 0 else 0.0
                )

                all_improvement_rates.append(improvement_rate)
                all_effective_hint_read_fractions.append(effective_hint_read_fraction)

                episodes_data.append(
                    {
                        "initial_misconceptions": initial_misconceptions,
                        "cleared_misconceptions": cleared_misconceptions,
                        "improvement_rate": improvement_rate,
                        "total_writes": total_writes,
                        "total_reads": total_reads,
                        "useful_reads": useful_reads,
                        "effective_hints": dict(effective_hints),
                    }
                )

                if learn_utility:
                    cmm.observe(outcome=improvement_rate)

        # Aggregate metrics
        mean_improvement = float(np.mean(all_improvement_rates))
        mean_episode_effective_hint_read_fraction = float(
            np.mean(all_effective_hint_read_fractions)
        )

        performance = PerformanceMetrics(
            success_rate=mean_improvement,  # Success = clearing misconceptions
            mean_return=mean_improvement,
        )

        total_writes_all = sum(e["total_writes"] for e in episodes_data)
        total_reads_all = sum(e["total_reads"] for e in episodes_data)
        useful_reads_all = sum(e["useful_reads"] for e in episodes_data)

        memory = MemoryEfficiencyMetrics(
            reads_per_write=total_reads_all / max(total_writes_all, 1),
        )
        diagnostics = {
            "mean_episode_effective_hint_read_fraction": mean_episode_effective_hint_read_fraction,
            "pooled_effective_hint_read_fraction": useful_reads_all / max(total_reads_all, 1),
            "mean_misconception_clearance": mean_improvement,
        }

        return TaskResult(
            performance=performance,
            memory=memory,
            diagnostics=diagnostics,
            raw_data={
                "reset_memory": reset_memory,
                "learn_utility": learn_utility,
                "episodes": episodes_data,
                "config": {
                    "num_concepts": self.config.num_concepts,
                    "num_sessions": self.config.num_sessions,
                },
            },
        )
