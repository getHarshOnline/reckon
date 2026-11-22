//! Explicit adapters between laboratory values and the historical scalar wire.
use crate::{proto, record, Record, RecordWireError};

impl TryFrom<&Record> for record::ByteRecord {
    type Error = RecordWireError;
    fn try_from(value: &Record) -> Result<Self, Self::Error> {
        Ok(Self {
            id: value.id.clone(),
            timestamp: value.timestamp,
            episode_id: value.episode_id.clone(),
            payload_type: record::PayloadType::parse(&value.payload_type)
                .ok_or_else(|| RecordWireError::Payload(value.payload_type.clone()))?,
            payload: value.payload.iter().copied().map(record::Byte).collect(),
            cost: record::RecordCost {
                bytes: value.cost_bytes,
                tokens: Some(value.cost_tokens),
                slots: value.cost_slots,
            },
            tags: value.tags.clone(),
            provenance: value
                .provenance
                .as_ref()
                .map(|origin| record::RecordOrigin {
                    source_op: origin.source_op.clone(),
                    input_ids: origin.input_ids.clone(),
                    hash: origin.hash.clone(),
                }),
            utility: record::UtilityEstimate {
                value: value.utility,
                uncertainty: value.utility_uncertainty,
                last_used: value.last_used,
                use_count: value.use_count,
            },
            causal_score: record::CausalScore {
                ablation_delta: value.ablation_delta,
                counterfactual_delta: value.counterfactual_delta,
                influence_proxy: value.influence_proxy,
                last_evaluated: value.last_evaluated,
            },
            metadata: value.metadata.iter().copied().map(record::Byte).collect(),
            compressed: value.compressed,
            encoding: value.encoding.clone(),
            created_at_step: value.created_at_step,
            created_at_sequence: value.created_at_sequence,
        })
    }
}

impl TryFrom<record::ByteRecord> for Record {
    type Error = RecordWireError;

    fn try_from(value: record::ByteRecord) -> Result<Self, Self::Error> {
        Ok(Self {
            id: value.id,
            timestamp: value.timestamp,
            episode_id: value.episode_id,
            payload_type: value.payload_type.name().into(),
            payload: value.payload.into_iter().map(|byte| byte.0).collect(),
            cost_bytes: value.cost.bytes,
            cost_tokens: value.cost.tokens.ok_or(RecordWireError::UnknownTokenCost)?,
            cost_slots: value.cost.slots,
            tags: value.tags,
            provenance: value.provenance.map(|origin| proto::RecordOrigin {
                source_op: origin.source_op,
                input_ids: origin.input_ids,
                hash: origin.hash,
            }),
            utility: value.utility.value,
            utility_uncertainty: value.utility.uncertainty,
            last_used: value.utility.last_used,
            use_count: value.utility.use_count,
            ablation_delta: value.causal_score.ablation_delta,
            counterfactual_delta: value.causal_score.counterfactual_delta,
            influence_proxy: value.causal_score.influence_proxy,
            last_evaluated: value.causal_score.last_evaluated,
            metadata: value.metadata.into_iter().map(|byte| byte.0).collect(),
            compressed: value.compressed,
            encoding: value.encoding,
            created_at_step: value.created_at_step,
            created_at_sequence: value.created_at_sequence,
        })
    }
}

impl record::ByteRecord {
    /// JSON has no non-finite numbers; refuse them instead of replacing them with null.
    pub fn to_json(&self) -> Result<String, String> {
        if [
            Some(self.utility.value),
            Some(self.utility.uncertainty),
            self.causal_score.ablation_delta,
            self.causal_score.counterfactual_delta,
            self.causal_score.influence_proxy,
        ]
        .into_iter()
        .flatten()
        .any(|x| !x.is_finite())
        {
            return Err("record JSON requires finite utility and score values".into());
        }
        serde_json::to_string(self).map_err(|error| error.to_string())
    }
}
