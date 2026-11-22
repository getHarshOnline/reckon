use super::*;

#[tokio::test]
async fn probe_refuses_known_missing_and_empty_records_without_mutation() {
    let state = Arc::new(DaemonState::new(100));
    let service = ReckonService::new(state.clone());
    let record_id = service
        .write(Request::new(WriteRequest {
            payload: b"record whose utility is not probe evidence".to_vec(),
            initial_utility: 0.8,
            ..Default::default()
        }))
        .await
        .unwrap()
        .into_inner()
        .record_id;
    let before = state.get_record(&record_id).unwrap();
    for record_ids in [vec![], vec![record_id.clone()], vec!["missing".into()]] {
        let error = service
            .probe(Request::new(ProbeRequest {
                record_ids,
                ..Default::default()
            }))
            .await
            .unwrap_err();
        assert_eq!(error.code(), tonic::Code::Unimplemented);
        assert!(error.message().contains("episode runner"));
    }
    let after = state.get_record(&record_id).unwrap();
    assert_eq!(after, before);
}
