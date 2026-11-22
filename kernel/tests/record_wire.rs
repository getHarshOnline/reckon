use reckon_kernel::{proto, Record, RecordStore};

fn full_record() -> proto::MemoryRecord {
    proto::MemoryRecord {
        id: "opaque-cue".into(),
        timestamp: i64::MAX,
        episode_id: "episode".into(),
        payload_type: proto::PayloadType::Cue as i32,
        payload: vec![0, 255, 128, 1],
        compressed: true,
        encoding: "producer-codec".into(),
        cost: Some(proto::RecordCost {
            bytes: 4,
            tokens: 0,
            slots: 1,
        }),
        tags: vec!["second".into(), "first".into(), "second".into()],
        provenance: Some(proto::RecordOrigin {
            source_op: "observe".into(),
            input_ids: vec!["b".into(), "a".into()],
            hash: "supplied".into(),
        }),
        utility: Some(proto::UtilityEstimate {
            value: -0.25,
            uncertainty: 0.75,
            last_used: i64::MIN,
            use_count: 0,
        }),
        causal_score: Some(proto::CausalScore {
            ablation_delta: Some(0.0),
            counterfactual_delta: Some(-0.5),
            influence_proxy: None,
            last_evaluated: 7,
        }),
        metadata: vec![255, 0, 12],
        created_at_step: Some(0),
        created_at_sequence: None,
    }
}

#[test]
fn complete_record_survives_storage_fork_and_mutation() {
    let source = full_record();
    let store = RecordStore::new(2);
    store
        .insert(Record::try_from(source.clone()).unwrap())
        .unwrap();
    assert_eq!(
        proto::MemoryRecord::try_from(&store.get("opaque-cue").unwrap()).unwrap(),
        source
    );
    let fork = store.fork();
    assert_eq!(store.touch("opaque-cue", 19), Ok(true));
    store.update_utility("opaque-cue", 0.5);
    let mut expected = source.clone();
    let utility = expected.utility.as_mut().unwrap();
    utility.last_used = 19;
    utility.use_count = 1;
    utility.value = 0.5;
    assert_eq!(
        proto::MemoryRecord::try_from(&store.remove("opaque-cue").unwrap()).unwrap(),
        expected
    );
    assert_eq!(
        proto::MemoryRecord::try_from(&fork.get("opaque-cue").unwrap()).unwrap(),
        source
    );
}

#[test]
fn absent_origin_and_score_presence_are_not_filled_in() {
    let mut source = full_record();
    source.provenance = None;
    source.created_at_step = None;
    source.created_at_sequence = Some(0);
    source.causal_score.as_mut().unwrap().ablation_delta = None;
    source.causal_score.as_mut().unwrap().influence_proxy = Some(0.0);
    let native = Record::try_from(source.clone()).unwrap();
    assert_eq!(proto::MemoryRecord::try_from(&native).unwrap(), source);
}

#[test]
fn touch_refuses_count_overflow_without_changing_the_record() {
    let mut source = full_record();
    source.utility.as_mut().unwrap().use_count = i32::MAX - 1;
    let store = RecordStore::new(1);
    store.insert(Record::try_from(source).unwrap()).unwrap();
    assert_eq!(store.touch("opaque-cue", 11), Ok(true));
    let before = proto::MemoryRecord::try_from(&store.get("opaque-cue").unwrap()).unwrap();
    assert_eq!(before.utility.as_ref().unwrap().use_count, i32::MAX);
    assert_eq!(
        store.touch("opaque-cue", 12),
        Err(reckon_kernel::RecordStoreError::UseCountOverflow)
    );
    assert_eq!(
        proto::MemoryRecord::try_from(&store.get("opaque-cue").unwrap()).unwrap(),
        before
    );
    assert_eq!(store.touch("missing", 12), Ok(false));
}

#[test]
fn unsupported_or_incomplete_records_are_refused_not_normalized() {
    for field in ["cost", "utility", "causal_score"] {
        let mut source = full_record();
        match field {
            "cost" => source.cost = None,
            "utility" => source.utility = None,
            _ => source.causal_score = None,
        }
        assert!(Record::try_from(source)
            .unwrap_err()
            .to_string()
            .contains(field));
    }
    let mut source = full_record();
    source.payload_type = 999;
    assert!(Record::try_from(source).is_err());
    let native = Record::new("local".into(), 0, "".into(), "local-kind".into(), vec![], 0);
    assert!(proto::MemoryRecord::try_from(&native).is_err());
}

#[test]
fn earlier_native_json_keeps_its_values_and_defaults_new_fields() {
    let record = Record::new("earlier".into(), 0, "".into(), "cue".into(), vec![255], 1);
    let mut earlier = serde_json::to_value(&record).unwrap();
    for field in [
        "provenance",
        "metadata",
        "compressed",
        "encoding",
        "last_evaluated",
        "created_at_step",
        "created_at_sequence",
    ] {
        earlier.as_object_mut().unwrap().remove(field);
    }
    let restored: Record = serde_json::from_value(earlier).unwrap();
    assert_eq!(
        serde_json::to_value(restored).unwrap(),
        serde_json::to_value(record).unwrap()
    );
}
