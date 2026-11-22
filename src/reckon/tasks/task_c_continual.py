"""
Task C: Continual Classification with Replay Budget

A sequence of binary classification tasks where the decision boundary rotates.
The agent has a limited replay buffer and must decide which examples to store.
Catastrophic forgetting is measured by performance drop on earlier tasks.

Memory challenge: Select which examples to store for replay to prevent forgetting.
"""

# pylint: disable=duplicate-code

# Standard library
from dataclasses import dataclass
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
class ContinualConfig:
    """Configuration for the continual learning task."""

    num_tasks: int = 5
    samples_per_task: int = 100
    test_samples_per_task: int = 20
    feature_dim: int = 2
    replay_fraction: float = 0.2  # Fraction of batch from replay
    learning_rate: float = 0.1


class LinearClassifier:
    """Simple linear classifier with SGD updates."""

    def __init__(self, feature_dim: int, learning_rate: float):
        self.weights = np.zeros(feature_dim)
        self.bias = 0.0
        self.lr = learning_rate

    def predict(self, x: np.ndarray) -> int:
        """Predict class (0 or 1)."""
        score = np.dot(x, self.weights) + self.bias
        return 1 if score > 0 else 0

    def predict_proba(self, x: np.ndarray) -> float:
        """Predict probability of class 1."""
        score = np.dot(x, self.weights) + self.bias
        return 1.0 / (1.0 + np.exp(-np.clip(score, -10, 10)))

    def update(self, x: np.ndarray, y: int) -> None:
        """Single SGD update."""
        pred = self.predict_proba(x)
        error = y - pred
        self.weights += self.lr * error * x
        self.bias += self.lr * error


class ContinualClassificationTask:  # pylint: disable=too-few-public-methods
    """
    Sequence of 2D classification tasks with rotating decision boundaries.

    Each task has:
    - Two Gaussian clusters (class 0 and class 1)
    - Decision boundary at a different angle
    """

    def __init__(self, config: ContinualConfig, rng: np.random.Generator):
        self.config = config
        self.rng = rng

        # Generate task parameters (rotation angles)
        self.task_angles = np.linspace(0, np.pi, config.num_tasks, endpoint=False)

        # Generate all data upfront
        self.train_data: list[list[tuple[np.ndarray, int]]] = []
        self.test_data: list[list[tuple[np.ndarray, int]]] = []

        for task_idx in range(config.num_tasks):
            angle = self.task_angles[task_idx]

            # Generate training data
            train_samples = self._generate_samples(angle, config.samples_per_task)
            self.train_data.append(train_samples)

            # Generate test data
            test_samples = self._generate_samples(angle, config.test_samples_per_task)
            self.test_data.append(test_samples)

    def _generate_samples(self, angle: float, n_samples: int) -> list[tuple[np.ndarray, int]]:
        """Generate samples for a task with given decision boundary angle."""
        samples = []

        # Rotation matrix
        cos_a, sin_a = np.cos(angle), np.sin(angle)

        for _ in range(n_samples):
            # Generate random label
            label = self.rng.integers(0, 2)

            # Generate point in canonical space (class 0 at y<0, class 1 at y>0)
            y_coord = self.rng.uniform(-2, -0.5) if label == 0 else self.rng.uniform(0.5, 2)
            x_coord = self.rng.uniform(-1, 1)

            # Rotate to task-specific angle
            x_rot = cos_a * x_coord - sin_a * y_coord
            y_rot = sin_a * x_coord + cos_a * y_coord

            point = np.array([x_rot, y_rot])
            samples.append((point, label))

        return samples


def _mean_forgetting(accuracy_matrix: np.ndarray) -> float:
    """Average positive drops from each earlier task’s diagonal to its final accuracy."""
    scores = [
        max(0, accuracy_matrix[index, index] - accuracy_matrix[-1, index])
        for index in range(accuracy_matrix.shape[0] - 1)
    ]
    return float(np.mean(scores)) if scores else 0.0


class ContinualTask(BaseTask):
    """
    Continual Classification benchmark task.

    Tests agent's ability to:
    1. Learn new classification tasks
    2. Store informative examples for replay
    3. Prevent catastrophic forgetting on old tasks

    Metrics:
    - mean_accuracy: Average accuracy across all tasks
    - forgetting: Drop in accuracy on old tasks after learning new ones
    - memory_efficiency: Accuracy gain per stored example
    """

    def __init__(self, config: Optional[ContinualConfig] = None):
        self.config = config or ContinualConfig()

    @property
    def name(self) -> str:
        return "Continual Classification"

    @property
    def description(self) -> str:
        return "Learn sequence of tasks; use memory replay to prevent forgetting"

    # Keep the common task interface, including its keyword-only memory controls.
    def run(  # pylint: disable=too-many-locals,too-many-arguments
        self,
        cmm: CausalMemoryManager,
        num_episodes: int,
        seed: int,
        *,
        reset_memory: bool = False,
        learn_utility: bool = True,
    ) -> TaskResult:
        """Run the continual learning task."""
        if num_episodes < 1:
            raise ValueError("num_episodes must be positive")
        environment_rng, replay_rng = (
            np.random.default_rng(stream) for stream in np.random.SeedSequence(seed).spawn(2)
        )

        # Aggregate metrics across episodes
        all_accuracies = []
        all_forgetting = []
        all_memory_efficiency = []
        episodes_data = []

        for ep in range(num_episodes):
            with EpisodeContext(episode_id=f"continual_ep{ep}"):
                # Generate new data for each episode
                task_env = ContinualClassificationTask(self.config, environment_rng)
                classifier = LinearClassifier(self.config.feature_dim, self.config.learning_rate)
                cmm.set_episode(f"continual_ep{ep}", reset_memory=reset_memory)

                # Track accuracy after each task
                accuracy_matrix = np.zeros((self.config.num_tasks, self.config.num_tasks))
                # accuracy_matrix[i, j] = accuracy on task j after training on task i

                total_writes = 0
                total_reads = 0
                step = 0

                for task_idx in range(self.config.num_tasks):
                    cmm.set_step(step)

                    # Train on current task
                    train_samples = task_env.train_data[task_idx]

                    for x, y in train_samples:
                        # Fix each training position's replay opportunity independently
                        # of writes, and allow records carried from an earlier episode.
                        if replay_rng.random() < self.config.replay_fraction:
                            # Retrieve retained samples ranked by utility.
                            records = cmm.retrieve(
                                query={"tags": ["replay_sample"]},
                                limit=1,
                            )
                            if records:
                                total_reads += 1
                                replay_x = np.array(records[0].payload["x"])
                                replay_y = records[0].payload["y"]
                                classifier.update(replay_x, replay_y)

                        # Update on current sample
                        classifier.update(x, y)
                        step += 1
                        cmm.set_step(step)

                        # Store sample with probability based on uncertainty
                        pred = classifier.predict(x)
                        if pred != y:  # Store misclassified examples
                            cmm.write(
                                payload={"x": x.tolist(), "y": int(y), "task": int(task_idx)},
                                payload_type=PayloadType.REPRESENTATION,
                                tags=["replay_sample", f"task_{task_idx}"],
                                source_op="store_sample",
                                metadata={"importance": 1.0},
                            )
                            total_writes += 1

                    # Evaluate on all tasks seen so far
                    for eval_task in range(task_idx + 1):
                        test_samples = task_env.test_data[eval_task]
                        correct = sum(1 for x, y in test_samples if classifier.predict(x) == y)
                        accuracy_matrix[task_idx, eval_task] = correct / len(test_samples)

                # Compute metrics for this episode
                # Mean accuracy: average of final row (after all tasks)
                final_accuracies = accuracy_matrix[-1, :]
                mean_acc = float(np.mean(final_accuracies))

                mean_forgetting = _mean_forgetting(accuracy_matrix)

                # Memory efficiency: accuracy per stored sample
                mem_efficiency = mean_acc / max(total_writes, 1)

                all_accuracies.append(mean_acc)
                all_forgetting.append(mean_forgetting)
                all_memory_efficiency.append(mem_efficiency)

                episodes_data.append(
                    {
                        "mean_accuracy": mean_acc,
                        "forgetting": mean_forgetting,
                        "total_writes": total_writes,
                        "total_reads": total_reads,
                        "accuracy_matrix": accuracy_matrix.tolist(),
                    }
                )

                if learn_utility:
                    cmm.observe(outcome=mean_acc)

        # Aggregate across episodes
        performance = PerformanceMetrics(
            mean_accuracy=float(np.mean(all_accuracies)),
            forgetting=float(np.mean(all_forgetting)),
        )

        # Calculate memory metrics
        total_writes_all = sum(e["total_writes"] for e in episodes_data)
        total_reads_all = sum(e["total_reads"] for e in episodes_data)

        memory = MemoryEfficiencyMetrics(
            reads_per_write=total_reads_all / max(total_writes_all, 1),
        )
        diagnostics = {
            "mean_episode_accuracy_per_write": float(np.mean(all_memory_efficiency)),
            "one_minus_mean_forgetting": 1.0 - float(np.mean(all_forgetting)),
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
                    "num_tasks": self.config.num_tasks,
                    "samples_per_task": self.config.samples_per_task,
                },
            },
        )
