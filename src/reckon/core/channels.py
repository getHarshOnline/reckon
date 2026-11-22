"""
Coarse-graining and record channels.

Defines the observer interface through which agents interact with microstates.
"""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

# Type variables for state spaces
MicroState = TypeVar("MicroState")
MacroState = TypeVar("MacroState")
Record = TypeVar("Record")


class CoarseGraining(ABC, Generic[MicroState, MacroState]):
    """
    Abstract interface for projecting a microstate to a macrostate at scale s.

    Implement project() and the corresponding fiber measure for the chosen
    state spaces. MONAD's model uses a deterministic measurable projection
    followed by a separate noisy record channel; this interface does not
    verify those mathematical assumptions.
    """

    @property
    @abstractmethod
    def scale(self) -> float:
        """The scale parameter s for this coarse-graining."""

    @abstractmethod
    def project(self, microstate: MicroState) -> MacroState:
        """Project a microstate to a macrostate."""

    @abstractmethod
    def fiber_measure(self, macrostate: MacroState) -> float:
        """
        Compute μ(Γ_m) - the measure of the fiber/preimage.

        Used for Boltzmann entropy: S_B(m) = k log μ(Γ_m)
        """


class RecordChannel(ABC, Generic[MacroState, Record]):
    """
    Abstract record channel: M_s -> Δ(Y_R)

    A noisy storage/measurement channel that maps observations
    to stored records under resource constraints.
    """

    @abstractmethod
    def encode(self, observation: MacroState) -> Record:
        """Encode an observation into a record."""

    @abstractmethod
    def decode(self, record: Record) -> MacroState:
        """Decode a record back to an observation (possibly lossy)."""

    @abstractmethod
    def noise_level(self) -> float:
        """Return the effective noise level ε_noise of this channel."""

    @abstractmethod
    def cost(self, record: Record) -> int:
        """Return the resource cost (e.g., bytes) of storing this record."""
