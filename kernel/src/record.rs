//! Laboratory values. Python adapters retain object references in the generic
//! fields; the default byte representation is suitable for explicit exchange.
//! The daemon's typed tags and links are a separate domain.

use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use ts_rs::TS;

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize, JsonSchema, TS)]
pub struct Byte(#[schemars(range(max = 255))] pub u8);

macro_rules! payload_kinds {
    ($(($variant:ident, $name:literal)),+ $(,)?) => {
        #[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize, JsonSchema, TS)]
        #[serde(rename_all = "lowercase")]
        pub enum PayloadType { $($variant),+ }

        impl PayloadType {
            pub fn name(self) -> &'static str { match self { $(Self::$variant => $name),+ } }
            pub fn parse(value: &str) -> Option<Self> { match value { $($name => Some(Self::$variant),)+ _ => None } }
            pub fn members() -> Vec<(String, &'static str)> {
                vec![$((stringify!($variant).to_uppercase(), $name)),+]
            }
        }
    };
}

payload_kinds!(
    (Unspecified, "unspecified"),
    (Observation, "observation"),
    (Action, "action"),
    (Reward, "reward"),
    (Cue, "cue"),
    (Trace, "trace"),
    (Representation, "representation"),
    (Custom, "custom")
);

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema, TS)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct RecordCost {
    #[serde(with = "decimal")]
    #[schemars(with = "String")]
    #[ts(type = "string")]
    pub bytes: i64,
    /// None means no count was supplied; Some(0) is a declared zero.
    #[serde(default, with = "optional_decimal")]
    #[schemars(with = "Option<String>")]
    #[ts(type = "string | null")]
    pub tokens: Option<i64>,
    pub slots: i32,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema, TS)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct RecordOrigin<I = Vec<String>> {
    pub source_op: String,
    pub input_ids: I,
    pub hash: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema, TS)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct UtilityEstimate {
    pub value: f64,
    pub uncertainty: f64,
    #[serde(with = "decimal")]
    #[schemars(with = "String")]
    #[ts(type = "string")]
    pub last_used: i64,
    pub use_count: i32,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema, TS)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct CausalScore {
    pub ablation_delta: Option<f64>,
    pub counterfactual_delta: Option<f64>,
    pub influence_proxy: Option<f64>,
    #[serde(with = "decimal")]
    #[schemars(with = "String")]
    #[ts(type = "string")]
    pub last_evaluated: i64,
}

/// Full record shape, shared by byte exchange and the Python object adapter.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema, TS)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct MemoryRecord<
    P = Vec<Byte>,
    M = Vec<Byte>,
    T = Vec<String>,
    O = Option<RecordOrigin>,
    C = RecordCost,
    U = UtilityEstimate,
    S = CausalScore,
    K = PayloadType,
> {
    pub id: String,
    #[serde(with = "decimal")]
    #[schemars(with = "String")]
    #[ts(type = "string")]
    pub timestamp: i64,
    pub payload_type: K,
    pub payload: P,
    pub cost: C,
    pub tags: T,
    pub provenance: O,
    pub utility: U,
    pub causal_score: S,
    pub episode_id: String,
    pub metadata: M,
    pub compressed: bool,
    pub encoding: String,
    #[serde(default, with = "optional_decimal")]
    #[schemars(with = "Option<String>")]
    #[ts(type = "string | null")]
    pub created_at_step: Option<i64>,
    #[serde(default, with = "optional_decimal")]
    #[schemars(with = "Option<String>")]
    #[ts(type = "string | null")]
    pub created_at_sequence: Option<i64>,
}

pub type ByteRecord = MemoryRecord;

mod decimal {
    use serde::{Deserialize, Deserializer, Serializer};

    pub fn serialize<S: Serializer>(value: &i64, serializer: S) -> Result<S::Ok, S::Error> {
        serializer.serialize_str(&value.to_string())
    }

    pub fn deserialize<'de, D: Deserializer<'de>>(deserializer: D) -> Result<i64, D::Error> {
        let text = String::deserialize(deserializer)?;
        text.parse().map_err(serde::de::Error::custom)
    }
}

mod optional_decimal {
    use serde::{Deserialize, Deserializer, Serialize, Serializer};

    pub fn serialize<S: Serializer>(value: &Option<i64>, serializer: S) -> Result<S::Ok, S::Error> {
        value.map(|value| value.to_string()).serialize(serializer)
    }

    pub fn deserialize<'de, D: Deserializer<'de>>(
        deserializer: D,
    ) -> Result<Option<i64>, D::Error> {
        Option::<String>::deserialize(deserializer)?
            .map(|text| text.parse().map_err(serde::de::Error::custom))
            .transpose()
    }
}

pub fn typescript() -> String {
    format!(
        "// Generated from reckon-kernel record.rs. Do not edit.\n{}\n{}\n{}\n{}\n{}\n{}\n{}\n",
        Byte::decl(),
        PayloadType::decl(),
        RecordCost::decl(),
        RecordOrigin::<Vec<String>>::decl(),
        UtilityEstimate::decl(),
        CausalScore::decl(),
        ByteRecord::decl_concrete()
    )
    .replace("\ntype ", "\nexport type ")
}

pub fn json_schema() -> schemars::schema::RootSchema {
    schemars::schema_for!(ByteRecord)
}
