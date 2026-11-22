//! Named retention rankings and selection under byte, slot and token pressure.

use crate::store::Record;
use std::collections::{BTreeMap, HashSet};

#[derive(Debug, thiserror::Error)]
#[error("{0}")]
pub struct RetentionError(pub &'static str);

/// Distinct rankings remain explicit even when they share selection machinery.
#[derive(Debug, Clone, Copy)]
pub enum RetentionRule {
    Fifo,
    Lru,
    LruThenCreated,
    RawUtility,
    UtilityPerByte,
    EvidencePerByte {
        weight: f64,
    },
    WeightedEvidence {
        weight: f64,
    },
    Diversity {
        min_per_type: usize,
    },
    /// Use the caller's order, for example an independently seeded permutation.
    InputOrder,
}

fn finite(value: f64) -> Result<f64, RetentionError> {
    if value.is_finite() {
        Ok(value)
    } else {
        Err(RetentionError("retention scores must be finite"))
    }
}

fn measured(value: Option<f64>) -> Result<f64, RetentionError> {
    Ok(finite(value.unwrap_or(0.0))?.max(0.0))
}

fn score(record: &Record, rule: RetentionRule) -> Result<f64, RetentionError> {
    let utility = finite(record.utility)?;
    let value = match rule {
        RetentionRule::RawUtility | RetentionRule::Diversity { .. } => utility,
        RetentionRule::UtilityPerByte => utility / record.cost_bytes.max(1) as f64,
        RetentionRule::EvidencePerByte { weight } => {
            // A present measured zero or harmful effect never falls through to a proxy.
            let effect = if record.ablation_delta.is_some() {
                measured(record.ablation_delta)?
            } else if record.counterfactual_delta.is_some() {
                measured(record.counterfactual_delta)?
            } else {
                finite(record.influence_proxy.unwrap_or(0.0))?.abs()
            };
            ((1.0 - weight) * utility + weight * effect) / record.cost_bytes.max(1) as f64
        }
        RetentionRule::WeightedEvidence { weight } => {
            let effect = measured(record.ablation_delta)?
                + 0.5 * measured(record.counterfactual_delta)?
                + 0.25 * finite(record.influence_proxy.unwrap_or(0.0))?.abs();
            (1.0 - weight) * utility + weight * effect
        }
        _ => unreachable!("only scored rules call score"),
    };
    finite(value)
}

/// Select the shortest policy-ordered prefix satisfying all three pressures.
///
/// Each record consumes one store slot. Equal ranking keys preserve input order.
/// Invalid costs, duplicate identities and non-finite selected scores fail before
/// returning a selection. If all records cannot satisfy the request, all are
/// returned; the caller must refuse an infeasible admission before mutation.
pub fn select_retention(
    records: &[&Record],
    rule: RetentionRule,
    target_bytes: i64,
    target_slots: usize,
    target_tokens: i64,
) -> Result<Vec<String>, RetentionError> {
    if target_bytes < 0 || target_tokens < 0 {
        return Err(RetentionError(
            "retention byte and token pressure must be non-negative",
        ));
    }
    let mut ids = HashSet::new();
    for record in records {
        if record.cost_bytes < 0 || record.cost_tokens < 0 || !ids.insert(&record.id) {
            return Err(RetentionError(
                "retention requires non-negative costs and unique record IDs",
            ));
        }
    }
    if let RetentionRule::EvidencePerByte { weight } | RetentionRule::WeightedEvidence { weight } =
        rule
    {
        if !weight.is_finite() || !(0.0..=1.0).contains(&weight) {
            return Err(RetentionError(
                "retention effect weight must be finite and in [0, 1]",
            ));
        }
    }
    let mut ordered = records.to_vec();
    match rule {
        RetentionRule::Fifo => ordered.sort_by_key(|r| r.timestamp),
        RetentionRule::Lru => ordered.sort_by_key(|r| r.last_used),
        RetentionRule::LruThenCreated => ordered.sort_by_key(|r| (r.last_used, r.timestamp)),
        RetentionRule::InputOrder => {}
        _ => {
            let mut scored = records
                .iter()
                .map(|r| Ok((*r, score(r, rule)?)))
                .collect::<Result<Vec<_>, RetentionError>>()?;
            scored.sort_by(|a, b| a.1.partial_cmp(&b.1).expect("validated finite scores"));
            ordered = scored.into_iter().map(|(record, _)| record).collect();
        }
    }
    if let RetentionRule::Diversity { min_per_type } = rule {
        ordered = diversity_order(ordered, min_per_type);
    }
    let mut selected = Vec::new();
    let mut freed = 0_i128;
    let mut freed_tokens = 0_i128;
    for record in ordered {
        if freed >= i128::from(target_bytes)
            && selected.len() >= target_slots
            && freed_tokens >= i128::from(target_tokens)
        {
            break;
        }
        selected.push(record.id.clone());
        freed += i128::from(record.cost_bytes);
        freed_tokens += i128::from(record.cost_tokens);
    }
    Ok(selected)
}

/// Round-robin payload types in lexical order, exhausting surplus before protected rows.
fn diversity_order(records: Vec<&Record>, minimum: usize) -> Vec<&Record> {
    let mut groups: BTreeMap<&str, std::collections::VecDeque<&Record>> = BTreeMap::new();
    for record in records {
        groups
            .entry(&record.payload_type)
            .or_default()
            .push_back(record);
    }
    let mut ordered = Vec::new();
    for protected in [minimum, 0] {
        loop {
            let before = ordered.len();
            for group in groups.values_mut() {
                if group.len() > protected {
                    ordered.push(group.pop_front().unwrap());
                }
            }
            if ordered.len() == before {
                break;
            }
        }
    }
    ordered
}

/// A named rule for choosing records; storage and actual removal belong to its caller.
pub trait RetentionPolicy: Send + Sync {
    fn reason(&self) -> &'static str;
    fn name(&self) -> &'static str;
    fn select_for_budget(
        &self,
        records: &[&Record],
        bytes: i64,
        slots: usize,
        tokens: i64,
    ) -> Result<Vec<String>, RetentionError>;
    fn select_for_pruning(
        &self,
        records: &[&Record],
        bytes: i64,
    ) -> Result<Vec<String>, RetentionError> {
        self.select_for_budget(records, bytes, 0, 0)
    }
}

#[derive(Debug, Default, Clone)]
pub struct FifoPolicy;
impl RetentionPolicy for FifoPolicy {
    fn select_for_budget(
        &self,
        records: &[&Record],
        bytes: i64,
        slots: usize,
        tokens: i64,
    ) -> Result<Vec<String>, RetentionError> {
        select_retention(records, RetentionRule::Fifo, bytes, slots, tokens)
    }
    fn reason(&self) -> &'static str {
        "fifo_oldest"
    }
    fn name(&self) -> &'static str {
        "FIFO"
    }
}

#[derive(Debug, Default, Clone)]
pub struct LruPolicy;
impl RetentionPolicy for LruPolicy {
    fn select_for_budget(
        &self,
        records: &[&Record],
        bytes: i64,
        slots: usize,
        tokens: i64,
    ) -> Result<Vec<String>, RetentionError> {
        select_retention(records, RetentionRule::Lru, bytes, slots, tokens)
    }
    fn reason(&self) -> &'static str {
        "lru_least_recent"
    }
    fn name(&self) -> &'static str {
        "LRU"
    }
}

/// Raw utility ranking; the laboratory's per-byte rule is a separate choice.
#[derive(Debug, Default, Clone)]
pub struct UtilityPolicy;
impl RetentionPolicy for UtilityPolicy {
    fn select_for_budget(
        &self,
        records: &[&Record],
        bytes: i64,
        slots: usize,
        tokens: i64,
    ) -> Result<Vec<String>, RetentionError> {
        select_retention(records, RetentionRule::RawUtility, bytes, slots, tokens)
    }
    fn reason(&self) -> &'static str {
        "utility_lowest"
    }
    fn name(&self) -> &'static str {
        "Utility"
    }
}

/// Weighted measured effects and proxy magnitude, without cost division.
#[derive(Debug, Clone)]
pub struct WeightedEvidencePolicy {
    pub evidence_weight: f64,
}
impl Default for WeightedEvidencePolicy {
    fn default() -> Self {
        Self {
            evidence_weight: 0.5,
        }
    }
}
impl WeightedEvidencePolicy {
    /// Clamp the weight to [0, 1]; NaN is refused when selecting records.
    pub fn new(evidence_weight: f64) -> Self {
        Self {
            evidence_weight: evidence_weight.clamp(0.0, 1.0),
        }
    }
}
impl RetentionPolicy for WeightedEvidencePolicy {
    fn select_for_budget(
        &self,
        records: &[&Record],
        bytes: i64,
        slots: usize,
        tokens: i64,
    ) -> Result<Vec<String>, RetentionError> {
        select_retention(
            records,
            RetentionRule::WeightedEvidence {
                weight: self.evidence_weight,
            },
            bytes,
            slots,
            tokens,
        )
    }
    fn reason(&self) -> &'static str {
        "weighted_evidence_lowest"
    }
    fn name(&self) -> &'static str {
        "WeightedEvidence"
    }
}

/// Prefer removing surplus records before reducing each payload type below its minimum.
#[derive(Debug, Default, Clone)]
pub struct DiversityPolicy {
    pub min_per_type: usize,
}
impl DiversityPolicy {
    pub fn new(min_per_type: usize) -> Self {
        Self { min_per_type }
    }
}
impl RetentionPolicy for DiversityPolicy {
    fn select_for_budget(
        &self,
        records: &[&Record],
        bytes: i64,
        slots: usize,
        tokens: i64,
    ) -> Result<Vec<String>, RetentionError> {
        select_retention(
            records,
            RetentionRule::Diversity {
                min_per_type: self.min_per_type,
            },
            bytes,
            slots,
            tokens,
        )
    }
    fn reason(&self) -> &'static str {
        "diversity_maintain_coverage"
    }
    fn name(&self) -> &'static str {
        "Diversity"
    }
}
