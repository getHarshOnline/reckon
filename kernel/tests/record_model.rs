use reckon_kernel::{record, Record, RecordWireError};

#[test]
fn json_preserves_int64_limits_and_nullable_counts_without_changing_scalar_wire_meaning() {
    let mut native = Record::new(
        "model".into(),
        i64::MAX,
        "".into(),
        "cue".into(),
        vec![255, 0],
        1,
    );
    native.last_used = i64::MIN;
    native.created_at_step = Some(0);
    native.ablation_delta = Some(0.0);
    let mut model = record::ByteRecord::try_from(&native).unwrap();
    assert_eq!(model.cost.tokens, Some(0));
    let document: serde_json::Value = serde_json::from_str(&model.to_json().unwrap()).unwrap();
    assert_eq!(document["timestamp"], i64::MAX.to_string());
    assert_eq!(document["utility"]["lastUsed"], i64::MIN.to_string());
    assert_eq!(document["cost"]["tokens"], "0");
    assert_eq!(document["createdAtStep"], "0");
    assert!(document["createdAtSequence"].is_null());
    let decoded: record::ByteRecord = serde_json::from_value(document).unwrap();
    assert_eq!(decoded, model);
    assert_eq!(
        serde_json::to_value(Record::try_from(decoded).unwrap()).unwrap(),
        serde_json::to_value(native).unwrap()
    );
    model.cost.tokens = None;
    let unknown = model.to_json().unwrap();
    assert_eq!(
        serde_json::from_str::<record::ByteRecord>(&unknown)
            .unwrap()
            .cost
            .tokens,
        None
    );
    assert!(matches!(
        Record::try_from(model),
        Err(RecordWireError::UnknownTokenCost)
    ));
}

#[test]
fn descriptions_follow_the_actual_native_model_and_nonfinite_json_is_refused() {
    let source = Record::new("model".into(), 0, "".into(), "cue".into(), vec![], 1);
    let mut value = record::ByteRecord::try_from(&source).unwrap();
    let schema = serde_json::to_value(record::json_schema()).unwrap();
    let document: serde_json::Value = serde_json::from_str(&value.to_json().unwrap()).unwrap();
    assert!(document["provenance"].is_null());
    assert_eq!(
        serde_json::from_value::<record::ByteRecord>(document.clone())
            .unwrap()
            .provenance,
        None
    );
    let mut missing_origin = document.clone();
    missing_origin.as_object_mut().unwrap().remove("provenance");
    assert_eq!(
        serde_json::from_value::<record::ByteRecord>(missing_origin)
            .unwrap()
            .provenance,
        None
    );
    let fields: Vec<_> = document.as_object().unwrap().keys().collect();
    let described: Vec<_> = schema["properties"].as_object().unwrap().keys().collect();
    assert_eq!(fields, described);
    assert!(record::typescript().contains("tokens: string | null"));
    value.causal_score.counterfactual_delta = Some(f64::NAN);
    assert!(value.to_json().is_err());
}
