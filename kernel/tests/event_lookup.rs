use reckon_kernel::{EventLogger, OpType};

#[test]
fn event_lookup_preserves_zero_and_does_not_drain_the_ring() {
    let logger = EventLogger::new(2);
    let zero = logger.log(OpType::Write, 0);
    assert_eq!(zero, 0);
    assert_eq!(logger.get_event(zero).unwrap().event_id, zero);
    logger.log(OpType::Read, 0);
    assert_eq!(logger.peek().len(), 2);
    logger.log(OpType::Prune, 1);
    assert!(logger.get_event(zero).is_none());
    assert_eq!(logger.peek().len(), 2);
}
