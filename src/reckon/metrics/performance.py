"""
Performance metrics for Reckon evaluations.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class PerformanceMetrics:
    """
    Standard performance metrics.

    Attributes:
        success_rate: Fraction of successful episodes
        mean_return: Average cumulative reward
        mean_regret: Average regret vs optimal
        mean_accuracy: Average accuracy (for classification tasks)
        backward_transfer: Performance on old tasks after learning new
        forgetting: Drop in accuracy on old tasks
    """
    success_rate: Optional[float] = None
    mean_return: Optional[float] = None
    mean_regret: Optional[float] = None
    mean_accuracy: Optional[float] = None
    backward_transfer: Optional[float] = None
    forgetting: Optional[float] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            k: v for k, v in {
                "success_rate": self.success_rate,
                "mean_return": self.mean_return,
                "mean_regret": self.mean_regret,
                "mean_accuracy": self.mean_accuracy,
                "backward_transfer": self.backward_transfer,
                "forgetting": self.forgetting,
            }.items() if v is not None
        }

    @classmethod
    def from_episodes(cls, episodes: list[dict]) -> "PerformanceMetrics":
        """
        Compute performance metrics from episode data.

        Args:
            episodes: List of episode dictionaries. Each may contain:
                - success: bool
                - return: float (cumulative reward)
                - regret: float
                - accuracy: float
                - forgetting: float

        Returns:
            PerformanceMetrics instance with computed values.
        """
        if not episodes:
            return cls()

        len(episodes)

        # Success rate
        successes = [e.get("success") for e in episodes if "success" in e]
        success_rate = sum(1 for s in successes if s) / len(successes) if successes else None

        # Mean return
        returns = [e.get("return", e.get("rewards", e.get("reward"))) for e in episodes]
        returns = [r for r in returns if r is not None]
        mean_return = sum(returns) / len(returns) if returns else None

        # Mean regret
        regrets: list[float] = [float(e["regret"]) for e in episodes if e.get("regret") is not None]
        mean_regret = sum(regrets) / len(regrets) if regrets else None

        # Mean accuracy
        accuracies = [e.get("accuracy", e.get("mean_accuracy")) for e in episodes]
        accuracies = [a for a in accuracies if a is not None]
        mean_accuracy = sum(accuracies) / len(accuracies) if accuracies else None

        # Forgetting
        forgetting_vals: list[float] = [
            float(e["forgetting"]) for e in episodes if e.get("forgetting") is not None
        ]
        forgetting = sum(forgetting_vals) / len(forgetting_vals) if forgetting_vals else None

        return cls(
            success_rate=success_rate,
            mean_return=mean_return,
            mean_regret=mean_regret,
            mean_accuracy=mean_accuracy,
            forgetting=forgetting,
        )
