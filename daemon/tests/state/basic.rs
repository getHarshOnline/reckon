use super::*;

#[test]
fn test_write_and_get_record() {
    let state = DaemonState::new(100);
    let mut record = Record::from_write(
        "r1".into(),
        1,
        "ep1".into(),
        crate::service::proto::WriteRequest {
            payload: vec![1, 2, 3],
            payload_type: 1,
            initial_utility: 0.5,
            ..Default::default()
        },
    );
    record.cost.as_mut().unwrap().bytes = 100;

    let id = state.write_record(record).unwrap();
    assert_eq!(id, "r1");

    let retrieved = state.get_record("r1").unwrap();
    assert_eq!(retrieved.utility_value(), 0.5);
}

#[test]
fn test_episode_context() {
    let state = DaemonState::new(100);
    state.set_episode("ep1".to_string());

    let ctx = state
        .with_context(None, None, |context| context.clone())
        .unwrap();
    assert_eq!(ctx.episode_id, "ep1");
    assert!(!ctx.is_expired());
}
