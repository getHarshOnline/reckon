# Retrodiction is an Inverse Problem (Identifiability, Instability, Noise)

Use this model to estimate how far back a stored observation can recover a state or property. It applies when you can specify what the observation preserves, how reconstruction errors grow and how much uncertainty the record introduces.

## 1. Effective Observation Map

Fix horizon $\tau$, resources $R$, and scale $s$.

Define the effective record map:

```math
O_{\tau,R,s} := \mathcal{C}_R \circ \Pi_s \circ \Phi_\tau \circ U
```

where $U$ is an allowed preparation/control segment (omit if none).

Retrodiction asks you to infer $x_0$ or one of its properties from $y_\tau \sim O_{\tau,R,s}(x_0)$. The record law already includes the channel noise. Specify the effective reconstruction error separately.

## 2. Three Explicit Assumptions

**A1: Identifiability**: $O_{\tau,R,s}$ is injective on the relevant set $K \subseteq \mathcal{X}$ (possibly modulo symmetries). If different states induce the same record law, you cannot identify the full state from that law. You can still ask about a property that agrees across all states with the same law.

**A2: Instability**: For the estimate below, assume inverse errors are amplified in proportion to $e^{\lambda\tau}$ along the relevant directions, with $\lambda > 0$. The norm and proportionality constants belong to the declared observation model.

**A3: Noise floor**: Records have effective uncertainty $\varepsilon_{\text{noise}}$ in that error model due to finite precision, stochasticity, and channel noise. The finite logarithmic estimate assumes $\varepsilon_{\text{noise}} > 0$.

## 3. Logarithmic Horizon Bound

Under A1–A3, the noise-amplification model gives the following necessary scaling condition for reconstruction error $\leq \varepsilon$:

```math
\varepsilon_{\text{noise}} \lesssim \varepsilon \, e^{-\lambda\tau}
```

Thus:

```math
\tau_{\max} \lesssim \frac{1}{\lambda} \log\left(\frac{\varepsilon}{\varepsilon_{\text{noise}}}\right)
```

This logarithmic comparison assumes $0 < \varepsilon_{\text{noise}} \leq \varepsilon$ and $\lambda > 0$. The assumptions give a scaling estimate. Check achievable horizons against the reconstruction procedure for your experiment. To use a non-negative estimate:

```math
\tau_{\text{estimate}} := \max\left\{0,\, \frac{1}{\lambda} \log\left(\frac{\varepsilon}{\varepsilon_{\text{noise}}}\right)\right\}
```

As $\varepsilon$ approaches $\varepsilon_{\text{noise}}$ from above, this estimate approaches zero. If the target error is below the model's noise floor, clipping the estimate to zero does not establish successful recovery even at horizon zero.

> [!IMPORTANT]
>
> **Check the model before applying the bound.** Zero noise, zero or non-exponential instability, and a non-identifiable observation map need separate treatment. The formula does not apply merely because a configuration supplies a `noise_floor` field; its default value is zero.

**Interpretation**:

- Time reversal can exist mathematically
- Under the assumed exponential instability, inverse errors grow exponentially
- Extending the estimated horizon requires an exponential reduction in the relevant effective noise; the resources needed to obtain that reduction depend on the recording model

## 4. Engineering Implication

If better sensing or recording lowers $\varepsilon_{\text{noise}}$, record that assumption in your experiment. The code exposes two places to represent it:

- `ResourceVector.noise_floor` ([`resources.py`](../src/reckon/core/resources.py))
- `RecordChannel.noise_level()` ([`channels.py`](../src/reckon/core/channels.py))

Logging context, storing more bits, or running controlled probes may improve the estimate when they reduce the relevant effective uncertainty and preserve identifiability. Increasing a budget alone does not show either change. The resource field and abstract channel interface do not compute an inverse map, calibrate $\lambda$, or implement a horizon solver.

## Implementation

- [Memory Module README](../src/reckon/memory/README.md): record storage and event logging used to collect observations for a declared reconstruction model
- [Rust Core README](../kernel/README.md): the `EventLogger` ring buffer; a reconstruction experiment must account for which observations it retains or drops
