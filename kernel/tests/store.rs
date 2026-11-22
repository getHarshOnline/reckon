use reckon_kernel::{PriorityIndex, Record, RecordStore};

#[test]
fn test_priority_index() {
    let mut index = PriorityIndex::new();
    index.insert("a".to_string(), 0.5);
    index.insert("b".to_string(), 0.1);
    index.insert("c".to_string(), 0.9);

    // Should return lowest priority first
    assert_eq!(index.pop_lowest(), Some("b".to_string()));
    assert_eq!(index.pop_lowest(), Some("a".to_string()));
    assert_eq!(index.pop_lowest(), Some("c".to_string()));
    assert_eq!(index.pop_lowest(), None);
}

#[test]
fn priority_index_matches_latest_values_after_mutations() {
    let mut index = PriorityIndex::with_rebuild_threshold(0.9);
    for (id, priority) in [("a", 0.1), ("b", 0.4), ("c", 0.7), ("d", 0.7)] {
        index.insert(id.into(), priority);
    }
    index.update("a", 0.8);
    index.update("a", 0.9);
    index.update("c", 0.2);
    index.remove("c");
    index.insert("c".into(), 0.7);
    index.insert("nan".into(), f64::NAN);

    assert_eq!(index.len(), 5);
    for id in ["nan", "b", "c", "d", "a"] {
        assert_eq!(index.peek_lowest().as_deref(), Some(id));
        assert_eq!(index.pop_lowest().as_deref(), Some(id));
    }
    assert!(index.is_empty());
    assert_eq!(index.pop_lowest(), None);
}

#[test]
fn test_record_store_insert_get() {
    let store = RecordStore::new(100);
    let record = Record::new(
        "r1".to_string(),
        1,
        "ep1".to_string(),
        "observation".to_string(),
        vec![1, 2, 3],
        100,
    );

    store.insert(record).unwrap();
    assert_eq!(store.len(), 1);
    assert_eq!(store.current_bytes(), 100);

    let retrieved = store.get("r1").unwrap();
    assert_eq!(retrieved.id, "r1");
}

#[test]
fn test_select_for_pruning() {
    let store = RecordStore::new(100);

    // Insert records with different utilities
    let mut r1 = Record::new(
        "r1".to_string(),
        1,
        "ep1".to_string(),
        "obs".to_string(),
        vec![],
        50,
    );
    r1.utility = 0.1;
    store.insert(r1).unwrap();

    let mut r2 = Record::new(
        "r2".to_string(),
        2,
        "ep1".to_string(),
        "obs".to_string(),
        vec![],
        50,
    );
    r2.utility = 0.9;
    store.insert(r2).unwrap();

    // Should select r1 (lower utility) for pruning
    let to_prune = store.select_for_pruning(50);
    assert_eq!(to_prune, vec!["r1".to_string()]);
    assert_eq!(store.select_for_pruning(50), to_prune);

    assert!(store.update_utility("r1", 0.95));
    assert_eq!(store.select_for_pruning(50), vec!["r2".to_string()]);
    store.force_rebuild();
    assert_eq!(store.select_for_pruning(50), vec!["r2".to_string()]);
    store.remove("r2");
    assert_eq!(store.select_for_pruning(100), vec!["r1".to_string()]);
}

#[test]
fn rebuild_during_mutations_keeps_live_records_and_priority_order() {
    let store = RecordStore::new(100);
    std::thread::scope(|scope| {
        scope.spawn(|| {
            for _ in 0..100 {
                store.force_rebuild();
            }
        });
        for worker in 0..4 {
            let store = &store;
            scope.spawn(move || {
                let id = worker.to_string();
                for step in 0..100 {
                    let record =
                        Record::new(id.clone(), step, "ep".into(), "obs".into(), vec![], 1);
                    store.insert(record).unwrap();
                    assert!(store.update_utility(&id, worker as f64));
                    if step < 99 {
                        assert!(store.remove(&id).is_some());
                    }
                }
            });
        }
    });

    assert_eq!(store.current_bytes(), 4);
    assert!(store.staleness_ratio() <= store.rebuild_threshold());
    assert_eq!(store.select_for_pruning(4), ["0", "1", "2", "3"]);
}
