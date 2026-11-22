use super::*;

async fn write(service: &ReckonService, bytes: usize) -> String {
    service
        .write(Request::new(WriteRequest {
            payload: vec![1; bytes],
            ..Default::default()
        }))
        .await
        .unwrap()
        .into_inner()
        .record_id
}

#[tokio::test]
async fn zero_capacity_refuses_write_without_mutation() {
    let state = Arc::new(DaemonState::new(0));
    let service = ReckonService::new(state.clone());
    let error = service
        .write(Request::new(WriteRequest::default()))
        .await
        .unwrap_err();
    assert_eq!(error.code(), tonic::Code::ResourceExhausted);
    assert_eq!(state.stats(), (0, 0, 0));
}

#[tokio::test]
async fn replacement_preserves_other_records_and_counts_only_current_bytes() {
    let state = Arc::new(DaemonState::new(2));
    let service = ReckonService::new(state.clone());
    let first = write(&service, 3).await;
    let other = write(&service, 5).await;
    for size in [9, 1] {
        let mut replacement = state.get_record(&first).unwrap();
        replacement.payload = vec![2; size];
        replacement.cost.as_mut().unwrap().bytes = size as i64;
        state.write_record(replacement).unwrap();
        assert_eq!(state.stats(), (2, size as i64 + 5, 2));
        assert_eq!(state.get_record(&other).unwrap().payload, vec![1; 5]);
        assert_eq!(state.get_record(&first).unwrap().payload, vec![2; size]);
    }
    assert!(state.remove_record(&first).is_some());
    assert!(state.remove_record(&first).is_none());
    assert_eq!(state.stats(), (1, 5, 2));
}

#[tokio::test]
async fn concurrent_writes_respect_capacity_and_byte_accounting() {
    let state = Arc::new(DaemonState::new(3));
    let service = ReckonService::new(state.clone());
    let id = write(&service, 5).await;
    let template = state.get_record(&id).unwrap();
    let start = Arc::new(std::sync::Barrier::new(8));
    std::thread::scope(|scope| {
        for worker in 0..8 {
            let state = &state;
            let template = &template;
            let start = &start;
            scope.spawn(move || {
                start.wait();
                for step in 0..50 {
                    let mut record = template.clone();
                    record.id = format!("{worker}-{step}");
                    state.write_record(record).unwrap();
                    assert!(state.stats().0 <= 3);
                }
            });
        }
    });
    assert_eq!(state.stats(), (3, 15, 3));
    for id in state.all_record_ids() {
        state.remove_record(&id).unwrap();
    }
    assert_eq!(state.stats(), (0, 0, 3));
}
