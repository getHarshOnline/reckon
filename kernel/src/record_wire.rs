//! Lossless conversions for complete laboratory records.
//!
//! The daemon's `core.v1.Record` has typed tags and links and is a different
//! contract. These conversions accept only the laboratory `MemoryRecord`.

use crate::{proto, Record};

#[derive(Debug, thiserror::Error)]
pub enum RecordWireError {
    #[error("laboratory record is missing {0}")]
    Missing(&'static str),
    #[error("unsupported laboratory payload type: {0}")]
    Payload(String),
    #[error("historical laboratory wire cannot represent an unknown token count")]
    UnknownTokenCost,
}

fn payload_name(value: i32) -> Result<&'static str, RecordWireError> {
    use proto::PayloadType::*;
    Ok(match proto::PayloadType::try_from(value) {
        Ok(Unspecified) => "unspecified",
        Ok(Observation) => "observation",
        Ok(Action) => "action",
        Ok(Reward) => "reward",
        Ok(Cue) => "cue",
        Ok(Trace) => "trace",
        Ok(Representation) => "representation",
        Ok(Custom) => "custom",
        Err(_) => return Err(RecordWireError::Payload(value.to_string())),
    })
}

fn payload_number(value: &str) -> Result<i32, RecordWireError> {
    use proto::PayloadType::*;
    Ok(match value {
        "unspecified" => Unspecified,
        "observation" => Observation,
        "action" => Action,
        "reward" => Reward,
        "cue" => Cue,
        "trace" => Trace,
        "representation" => Representation,
        "custom" => Custom,
        other => return Err(RecordWireError::Payload(other.into())),
    } as i32)
}

impl TryFrom<proto::MemoryRecord> for Record {
    type Error = RecordWireError;

    /// Preserve every declared field of a complete laboratory record.
    ///
    /// Cost, utility and score messages are required even when their values are
    /// zero or their optional measurements are absent. Refusing an incomplete
    /// record avoids fabricating those messages during a later round trip.
    fn try_from(value: proto::MemoryRecord) -> Result<Self, Self::Error> {
        let cost = value.cost.ok_or(RecordWireError::Missing("cost"))?;
        let utility = value.utility.ok_or(RecordWireError::Missing("utility"))?;
        let score = value
            .causal_score
            .ok_or(RecordWireError::Missing("causal_score"))?;
        Ok(Self {
            id: value.id,
            timestamp: value.timestamp,
            episode_id: value.episode_id,
            payload_type: payload_name(value.payload_type)?.into(),
            payload: value.payload,
            cost_bytes: cost.bytes,
            cost_tokens: cost.tokens,
            cost_slots: cost.slots,
            tags: value.tags,
            utility: utility.value,
            utility_uncertainty: utility.uncertainty,
            last_used: utility.last_used,
            use_count: utility.use_count,
            ablation_delta: score.ablation_delta,
            counterfactual_delta: score.counterfactual_delta,
            influence_proxy: score.influence_proxy,
            provenance: value.provenance,
            metadata: value.metadata,
            compressed: value.compressed,
            encoding: value.encoding,
            last_evaluated: score.last_evaluated,
            created_at_step: value.created_at_step,
            created_at_sequence: value.created_at_sequence,
        })
    }
}

impl TryFrom<&Record> for proto::MemoryRecord {
    type Error = RecordWireError;

    fn try_from(value: &Record) -> Result<Self, Self::Error> {
        Ok(Self {
            id: value.id.clone(),
            timestamp: value.timestamp,
            episode_id: value.episode_id.clone(),
            payload_type: payload_number(&value.payload_type)?,
            payload: value.payload.clone(),
            compressed: value.compressed,
            encoding: value.encoding.clone(),
            cost: Some(proto::RecordCost {
                bytes: value.cost_bytes,
                tokens: value.cost_tokens,
                slots: value.cost_slots,
            }),
            tags: value.tags.clone(),
            provenance: value.provenance.clone(),
            utility: Some(proto::UtilityEstimate {
                value: value.utility,
                uncertainty: value.utility_uncertainty,
                last_used: value.last_used,
                use_count: value.use_count,
            }),
            causal_score: Some(proto::CausalScore {
                ablation_delta: value.ablation_delta,
                counterfactual_delta: value.counterfactual_delta,
                influence_proxy: value.influence_proxy,
                last_evaluated: value.last_evaluated,
            }),
            metadata: value.metadata.clone(),
            created_at_step: value.created_at_step,
            created_at_sequence: value.created_at_sequence,
        })
    }
}
