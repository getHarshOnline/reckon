use super::*;

fn string(value: &str) -> TagValue {
    TagValue {
        value: Some(tag_value::Value::StringValue(value.into())),
    }
}

fn list(values: &[&str]) -> TagValue {
    TagValue {
        value: Some(tag_value::Value::ListValue(StringList {
            values: values.iter().map(|value| (*value).into()).collect(),
        })),
    }
}

fn write_request() -> WriteRequest {
    WriteRequest {
        payload: vec![0, 255, 1],
        payload_type: PayloadType::Cue as i32,
        tags: HashMap::from([
            ("scalar".into(), string("shared")),
            ("ordered".into(), list(&["second", "first", "second"])),
            ("empty-list".into(), list(&[])),
            ("empty-string".into(), string("")),
            ("unset".into(), TagValue::default()),
        ]),
        links: vec![
            Link {
                rel: "derived_from".into(),
                to_record_id: "second".into(),
                meta_json: br#"{ "weight": 0, "note": "supplied" }"#.to_vec(),
            },
            Link {
                rel: "caused_by".into(),
                to_record_id: "first".into(),
                meta_json: vec![],
            },
        ],
        initial_utility: 0.5,
        run_id: "complete-record".into(),
    }
}

async fn retrieve(service: &ReckonService, query: retrieve_request::Query) -> RetrieveResponse {
    service
        .retrieve(Request::new(RetrieveRequest {
            query: Some(query),
            run_id: "complete-record".into(),
            ..Default::default()
        }))
        .await
        .unwrap()
        .into_inner()
}

#[tokio::test]
async fn write_lookup_search_observe_and_export_preserve_declared_record_inputs() {
    let state = Arc::new(DaemonState::new(10));
    state.set_episode("episode".into());
    state.set_step(7);
    let service = ReckonService::new(state.clone());
    let input = write_request();
    let written = service
        .write(Request::new(input.clone()))
        .await
        .unwrap()
        .into_inner();
    let original = state.get_record(&written.record_id).unwrap();
    assert_eq!(original.payload, input.payload);
    assert_eq!(original.payload_type, input.payload_type);
    assert_eq!(original.tags, input.tags);
    assert_eq!(original.links, input.links);
    assert_eq!(original.utility_value(), input.initial_utility);
    assert_eq!(original.cost, written.cost);
    assert_eq!(original.timestamp, 7);
    assert_eq!(original.episode_id, "episode");
    assert_eq!(original.created_at_step, Some(7));
    assert_eq!(original.created_at_sequence, None);
    assert!(!original.compressed);
    assert!(original.encoding.is_empty() && original.metadata.is_empty());
    assert_eq!(original.causal_score.as_ref().unwrap().last_evaluated, -1);

    for query in [
        retrieve_request::Query::ByIds(IdQuery {
            ids: vec![written.record_id.clone()],
        }),
        retrieve_request::Query::ByTags(TagQuery {
            tags: input.tags.clone(),
        }),
        retrieve_request::Query::ByUtility(UtilityQuery {
            min_utility: 0.5,
            episode_id: None,
        }),
    ] {
        let before = state.get_record(&written.record_id).unwrap();
        let retrieved = retrieve(&service, query).await;
        assert_eq!(retrieved.records, [before]);
        service
            .observe(Request::new(ObserveRequest {
                episode_context_id: retrieved.episode_context_id,
                outcome_value: 1.0,
                credit_policy: CreditPolicy::Simple as i32,
                ..Default::default()
            }))
            .await
            .unwrap();
        let current = state.get_record(&written.record_id).unwrap();
        assert_eq!(current.tags, input.tags);
        assert_eq!(current.links, input.links);
        let request = ExportRunRequest {
            run_id: input.run_id.clone(),
            record_scope: RecordScope::Touched as i32,
            ..Default::default()
        };
        let exported = service
            .export_run(Request::new(request.clone()))
            .await
            .unwrap()
            .into_inner()
            .export
            .unwrap();
        let rows: Vec<serde_json::Value> =
            serde_json::from_slice(exported.records_snapshot_json.as_ref().unwrap()).unwrap();
        assert_eq!(rows, [serde_json::to_value(current).unwrap()]);
        let repeated = service
            .export_run(Request::new(request))
            .await
            .unwrap()
            .into_inner()
            .export
            .unwrap();
        assert_eq!(exported, repeated);
    }
}

#[tokio::test]
async fn typed_tag_predicates_keep_all_constraints_including_lists_and_presence() {
    let service = ReckonService::new(Arc::new(DaemonState::new(10)));
    let input = write_request();
    let expected = service
        .write(Request::new(input.clone()))
        .await
        .unwrap()
        .into_inner()
        .record_id;
    service
        .write(Request::new(WriteRequest {
            tags: HashMap::from([("scalar".into(), string("shared"))]),
            ..Default::default()
        }))
        .await
        .unwrap();
    for (key, value) in &input.tags {
        let tags = HashMap::from([
            (key.clone(), value.clone()),
            ("ordered".into(), list(&["second", "first", "second"])),
        ]);
        let result = retrieve(&service, retrieve_request::Query::ByTags(TagQuery { tags })).await;
        assert_eq!(
            result
                .records
                .iter()
                .map(|record| &record.id)
                .collect::<Vec<_>>(),
            [&expected]
        );
    }
    for (key, value) in [
        ("ordered", list(&["first", "second", "second"])),
        ("ordered", list(&["second", "first"])),
        ("ordered", string("second")),
        ("ordered", list(&[])),
        ("missing", TagValue::default()),
        ("empty-list", string("")),
        ("empty-string", TagValue::default()),
    ] {
        for mixed in [false, true] {
            let mut tags = HashMap::from([(key.into(), value.clone())]);
            if mixed {
                tags.insert("scalar".into(), string("shared"));
            }
            assert!(
                retrieve(&service, retrieve_request::Query::ByTags(TagQuery { tags }))
                    .await
                    .records
                    .is_empty()
            );
        }
    }
}
