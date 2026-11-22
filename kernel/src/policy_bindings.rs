//! Optional Python projections of the kernel retention rules.

use pyo3::prelude::*;

/// Policy type enum for Python interop.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PolicyType {
    Fifo,
    Lru,
    Utility,
    EvidencePerByte,
    Diversity,
}

/// Python-exposed retention policy wrapper.
#[pyclass(name = "RetentionPolicy")]
#[derive(Clone)]
pub struct PyRetentionPolicy {
    policy_type: PolicyType,
    evidence_weight: f64,
    min_per_type: usize,
}

#[pymethods]
impl PyRetentionPolicy {
    /// Create a FIFO policy.
    #[staticmethod]
    fn fifo() -> Self {
        Self {
            policy_type: PolicyType::Fifo,
            evidence_weight: 0.0,
            min_per_type: 0,
        }
    }

    /// Create an LRU policy.
    #[staticmethod]
    fn lru() -> Self {
        Self {
            policy_type: PolicyType::Lru,
            evidence_weight: 0.0,
            min_per_type: 0,
        }
    }

    /// Create a utility-based policy.
    #[staticmethod]
    fn utility() -> Self {
        Self {
            policy_type: PolicyType::Utility,
            evidence_weight: 0.0,
            min_per_type: 0,
        }
    }

    /// Describe the per-byte rule; this value does not perform selection.
    #[staticmethod]
    #[pyo3(signature = (evidence_weight=0.5))]
    fn evidence_per_byte(evidence_weight: f64) -> Self {
        Self {
            policy_type: PolicyType::EvidencePerByte,
            evidence_weight,
            min_per_type: 0,
        }
    }

    /// Create a diversity policy.
    #[staticmethod]
    #[pyo3(signature = (min_per_type=1))]
    fn diversity(min_per_type: usize) -> Self {
        Self {
            policy_type: PolicyType::Diversity,
            evidence_weight: 0.0,
            min_per_type,
        }
    }

    /// Get the policy name.
    #[getter]
    fn name(&self) -> &str {
        match self.policy_type {
            PolicyType::Fifo => "FIFO",
            PolicyType::Lru => "LRU",
            PolicyType::Utility => "Utility",
            PolicyType::EvidencePerByte => "EvidencePerByte",
            PolicyType::Diversity => "Diversity",
        }
    }

    fn __repr__(&self) -> String {
        match self.policy_type {
            PolicyType::EvidencePerByte => format!(
                "RetentionPolicy.evidence_per_byte(weight={})",
                self.evidence_weight
            ),
            PolicyType::Diversity => {
                format!(
                    "RetentionPolicy.diversity(min_per_type={})",
                    self.min_per_type
                )
            }
            _ => format!("RetentionPolicy.{}()", self.name().to_lowercase()),
        }
    }
}

/// Only the ranking inputs cross this binding; payloads stay with the caller.
type PolicyInput = (
    String,
    i64,
    i64,
    i64,
    f64,
    Option<f64>,
    Option<f64>,
    Option<f64>,
    String,
    i64,
);

#[pyfunction(name = "select_retention")]
#[pyo3(signature = (inputs, policy, overflow_bytes, overflow_slots=0, weight=0.5, min_per_type=1, overflow_tokens=0))]
pub(crate) fn py_select_retention(
    inputs: Vec<PolicyInput>,
    policy: &str,
    overflow_bytes: i64,
    overflow_slots: usize,
    weight: f64,
    min_per_type: usize,
    overflow_tokens: i64,
) -> PyResult<Vec<String>> {
    use crate::{Record, RetentionRule};
    use pyo3::exceptions::PyValueError;
    let rule = match policy {
        "fifo" => RetentionRule::Fifo,
        "lru" => RetentionRule::LruThenCreated,
        "utility_per_byte" | "importance_per_byte" => RetentionRule::UtilityPerByte,
        "evidence_per_byte" => RetentionRule::EvidencePerByte { weight },
        "diversity" => RetentionRule::Diversity { min_per_type },
        "ordered" => RetentionRule::InputOrder,
        _ => return Err(PyValueError::new_err("unknown retention rule")),
    };
    let records = inputs
        .into_iter()
        .map(
            |(
                id,
                timestamp,
                last_used,
                bytes,
                utility,
                ablation,
                counterfactual,
                proxy,
                payload_type,
                tokens,
            )| {
                let mut record = Record::new(
                    id,
                    timestamp,
                    String::new(),
                    payload_type,
                    Vec::new(),
                    bytes,
                );
                record.cost_tokens = tokens;
                record.last_used = last_used;
                record.utility = utility;
                record.ablation_delta = ablation;
                record.counterfactual_delta = counterfactual;
                record.influence_proxy = proxy;
                record
            },
        )
        .collect::<Vec<_>>();
    crate::select_retention(
        &records.iter().collect::<Vec<_>>(),
        rule,
        overflow_bytes,
        overflow_slots,
        overflow_tokens,
    )
    .map_err(|error| PyValueError::new_err(error.to_string()))
}
