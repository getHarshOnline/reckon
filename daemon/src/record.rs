//! Daemon behavior over the generated core.v1 record, distinct from laboratory
//! records. The protobuf source owns fields; storage and responses share them.

pub use crate::service::proto::Record;
use crate::service::proto::{CausalScore, RecordCost, UtilityEstimate, WriteRequest};

impl Record {
    /// Retain all declared write inputs and initialize the daemon's own fields.
    pub fn from_write(
        id: String,
        timestamp: i64,
        episode_id: String,
        request: WriteRequest,
    ) -> Self {
        Self {
            id,
            timestamp,
            episode_id,
            payload_type: request.payload_type,
            cost: Some(RecordCost {
                bytes: request.payload.len() as i64,
                tokens: 0,
                slots: 1,
            }),
            payload: request.payload,
            tags: request.tags,
            links: request.links,
            utility: Some(UtilityEstimate {
                value: request.initial_utility,
                uncertainty: 1.0,
                last_used: timestamp,
                use_count: 0,
            }),
            causal_score: Some(CausalScore {
                last_evaluated: -1,
                ..Default::default()
            }),
            created_at_step: Some(timestamp),
            ..Default::default()
        }
    }

    pub fn cost_bytes(&self) -> i64 {
        self.cost.as_ref().map_or(0, |cost| cost.bytes)
    }

    pub fn utility_value(&self) -> f64 {
        self.utility.as_ref().map_or(0.0, |utility| utility.value)
    }

    pub fn ablation_delta(&self) -> Option<f64> {
        self.causal_score
            .as_ref()
            .and_then(|score| score.ablation_delta)
    }

    pub fn priority_score(&self) -> f64 {
        reckon_kernel::retention_priority(
            self.utility_value(),
            self.ablation_delta(),
            self.causal_score
                .as_ref()
                .and_then(|score| score.counterfactual_delta),
        )
    }
}
