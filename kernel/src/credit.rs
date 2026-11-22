//! Credit weights and bounded utility updates shared by laboratory callers.

#[cfg(feature = "python")]
use pyo3::{exceptions::PyValueError, prelude::*};
use serde::{Deserialize, Serialize};

pub const DEFAULT_ETA: f64 = 0.1;
pub const DEFAULT_U_MIN: f64 = 0.0;
pub const DEFAULT_U_MAX: f64 = 1.0;
pub const DEFAULT_SHAPED_SCALE: f64 = 1.0;

/// How one observation distributes credit across its retrieved records.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum CreditPolicy {
    None,
    Simple,
    Shaped,
    Ablation,
}

/// Scores for one retrieved record, in the caller's retrieval order.
#[derive(Debug, Clone, Copy)]
pub struct CreditInput {
    pub utility: f64,
    /// Outcome with the record minus outcome without it; absence is unmeasured.
    pub ablation_delta: Option<f64>,
}

#[derive(Debug, thiserror::Error)]
#[error("{0}")]
pub struct CreditError(&'static str);

/// Return weights in input order; NONE and an empty retrieval return no weights.
///
/// SHAPED uses stable softplus at the supplied positive scale. ABLATION uses only
/// positive measured deltas: when all measurements are non-positive the weights
/// are zero. Equal credit is a fallback only when every delta is absent.
/// Invalid or unrepresentable inputs fail before the caller updates a record.
pub fn compute_credit(
    inputs: &[CreditInput],
    outcome: f64,
    policy: CreditPolicy,
    shaped_scale: f64,
) -> Result<Vec<f64>, CreditError> {
    if inputs.is_empty() || policy == CreditPolicy::None {
        return Ok(Vec::new());
    }
    if !outcome.is_finite() {
        return Err(CreditError("credit requires a finite outcome"));
    }
    match policy {
        CreditPolicy::None => unreachable!("handled above"),
        CreditPolicy::Simple => Ok(equal_credit(inputs.len())),
        CreditPolicy::Shaped => {
            if !shaped_scale.is_finite() || shaped_scale <= 0.0 {
                return Err(CreditError(
                    "SHAPED credit requires a finite positive scale",
                ));
            }
            let weights = inputs
                .iter()
                .map(|input| {
                    let value = input.utility / shaped_scale;
                    if !value.is_finite() {
                        return Err(CreditError(
                            "SHAPED credit requires finite scaled utilities",
                        ));
                    }
                    Ok(value.max(0.0) + (-value.abs()).exp().ln_1p())
                })
                .collect::<Result<Vec<_>, _>>()?;
            let normalized = normalize(weights);
            if normalized.iter().any(|credit| *credit <= 0.0) {
                return Err(CreditError("SHAPED credit underflowed"));
            }
            Ok(normalized)
        }
        CreditPolicy::Ablation => {
            if inputs.iter().all(|input| input.ablation_delta.is_none()) {
                return Ok(equal_credit(inputs.len()));
            }
            let weights = inputs
                .iter()
                .map(|input| {
                    let delta = input.ablation_delta.unwrap_or(0.0);
                    if !delta.is_finite() {
                        return Err(CreditError("ABLATION credit requires finite measured deltas"));
                    }
                    Ok(delta.max(0.0))
                })
                .collect::<Result<Vec<_>, _>>()?;
            Ok(normalize(weights))
        }
    }
}

fn equal_credit(count: usize) -> Vec<f64> {
    normalize(vec![1.0; count])
}

/// Rescale before summing to avoid overflow, then use a compensated sum.
fn normalize(mut weights: Vec<f64>) -> Vec<f64> {
    let largest = weights.iter().copied().fold(0.0, f64::max);
    if largest == 0.0 {
        return weights;
    }
    let (mut total, mut correction) = (0.0, 0.0);
    for weight in &mut weights {
        *weight /= largest;
        let adjusted = *weight - correction;
        let next = total + adjusted;
        correction = (next - total) - adjusted;
        total = next;
    }
    for weight in &mut weights {
        *weight /= total;
    }
    weights
}

/// Apply u <- (1 - eta) * u + eta * credit * outcome, then clamp to the bounds.
///
/// All inputs must be finite, credit must be in [0, 1], eta in (0, 1], and the
/// lower bound must not exceed the upper bound. Negative outcomes are allowed.
pub fn update_utility(
    current: f64,
    credit: f64,
    outcome: f64,
    eta: f64,
    u_min: f64,
    u_max: f64,
) -> Result<f64, CreditError> {
    if ![current, credit, outcome, eta, u_min, u_max]
        .iter()
        .all(|value| value.is_finite())
    {
        return Err(CreditError("utility update requires finite inputs"));
    }
    if !(0.0..=1.0).contains(&credit) || eta <= 0.0 || eta > 1.0 || u_min > u_max {
        return Err(CreditError(
            "invalid utility credit, learning rate or bounds",
        ));
    }
    let updated = (1.0 - eta) * current + eta * credit * outcome;
    if !updated.is_finite() {
        return Err(CreditError("utility update overflowed"));
    }
    Ok(updated.clamp(u_min, u_max))
}

#[cfg(feature = "python")]
#[pyfunction(name = "compute_credit")]
pub(crate) fn py_compute_credit(
    inputs: Vec<(f64, Option<f64>)>,
    outcome: f64,
    policy: &str,
    shaped_scale: f64,
) -> PyResult<Vec<f64>> {
    let policy = match policy {
        "none" => CreditPolicy::None,
        "simple" => CreditPolicy::Simple,
        "shaped" => CreditPolicy::Shaped,
        "ablation" => CreditPolicy::Ablation,
        _ => return Err(PyValueError::new_err("unknown credit policy")),
    };
    let inputs = inputs
        .into_iter()
        .map(|(utility, ablation_delta)| CreditInput {
            utility,
            ablation_delta,
        })
        .collect::<Vec<_>>();
    compute_credit(&inputs, outcome, policy, shaped_scale)
        .map_err(|error| PyValueError::new_err(error.to_string()))
}

#[cfg(feature = "python")]
#[pyfunction(name = "update_utility")]
pub(crate) fn py_update_utility(
    current: f64,
    credit: f64,
    outcome: f64,
    eta: f64,
    u_min: f64,
    u_max: f64,
) -> PyResult<f64> {
    update_utility(current, credit, outcome, eta, u_min, u_max)
        .map_err(|error| PyValueError::new_err(error.to_string()))
}
