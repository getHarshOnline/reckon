use reckon_kernel::{Record, RecordStore};

#[test]
fn fork_preserves_complete_records_priorities_and_accounting_without_sharing_mutations() {
    let store = RecordStore::new(7);
    let mut record = Record::new("a".into(), 4, "source".into(), "cue".into(), vec![3, 4], 9);
    record.cost_tokens = 12;
    record.tags = vec!["tag".into()];
    record.ablation_delta = Some(-0.4);
    store.insert(record).unwrap();
    store.update_utility("a", 5.0);
    store.update_utility("a", 2.0);
    assert_eq!(store.touch("a", 19), Ok(true));
    let fork = store.fork();
    assert_eq!(
        serde_json::to_value(store.get("a")).unwrap(),
        serde_json::to_value(fork.get("a")).unwrap()
    );
    assert_eq!(
        (fork.capacity(), fork.current_bytes(), fork.current_tokens()),
        (7, 9, 12)
    );
    assert_eq!(store.select_for_pruning(1), fork.select_for_pruning(1));
    fork.remove("a");
    assert!(store.get("a").is_some());
    assert_eq!((fork.current_bytes(), fork.current_tokens()), (0, 0));
    assert_eq!((store.current_bytes(), store.current_tokens()), (9, 12));
    store.remove("a");
    fork.insert(Record::new(
        "b".into(),
        0,
        "fork".into(),
        "cue".into(),
        vec![],
        1,
    ))
    .unwrap();
    assert!(store.get("b").is_none());
}
