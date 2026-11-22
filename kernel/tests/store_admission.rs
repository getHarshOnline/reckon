use reckon_kernel::{Record, RecordStore, RecordStoreError};

fn record(id: &str, cost: i64) -> Record {
    Record::new(id.into(), 0, "trial".into(), "cue".into(), vec![1], cost)
}

fn snapshot(store: &RecordStore) -> (i64, serde_json::Value, Vec<String>) {
    let mut records = store.iter();
    records.sort_by(|a, b| a.id.cmp(&b.id));
    (
        store.current_bytes(),
        serde_json::to_value(records).unwrap(),
        store.select_for_pruning(i64::MAX),
    )
}

#[test]
fn invalid_new_records_and_replacements_leave_the_store_unchanged() {
    let store = RecordStore::new(2);
    store.insert(record("a", i64::MAX - 1)).unwrap();
    store.insert(record("b", 1)).unwrap();
    store.update_utility("a", 0.5);
    let before = snapshot(&store);
    for (id, cost, expected) in [
        ("new", -1, RecordStoreError::NegativeByteCost),
        ("a", -1, RecordStoreError::NegativeByteCost),
        ("new", 1, RecordStoreError::ByteTotalOverflow),
        ("b", 2, RecordStoreError::ByteTotalOverflow),
    ] {
        assert_eq!(store.insert(record(id, cost)).unwrap_err(), expected);
        assert_eq!(snapshot(&store), before);
    }
}

#[test]
fn replacement_checks_the_final_total_and_preserves_zero_cost() {
    let store = RecordStore::new(1);
    assert!(store.insert(record("a", i64::MAX)).unwrap().is_none());
    assert_eq!(
        store
            .insert(record("a", i64::MAX))
            .unwrap()
            .unwrap()
            .cost_bytes,
        i64::MAX
    );
    assert_eq!(store.current_bytes(), i64::MAX);
    store.insert(record("a", 0)).unwrap();
    assert_eq!(store.len(), 1);
    assert_eq!(store.current_bytes(), 0);
    store.remove("a").unwrap();
    assert_eq!(store.current_bytes(), 0);
}

#[test]
fn concurrent_insertions_check_and_update_the_total_under_one_lock() {
    let store = RecordStore::new(16);
    let barrier = std::sync::Barrier::new(16);
    let cost = i64::MAX / 2 + 1;
    let admitted = std::thread::scope(|scope| {
        let handles = (0..16)
            .map(|index| {
                let (store, barrier) = (&store, &barrier);
                scope.spawn(move || {
                    barrier.wait();
                    match store.insert(record(&index.to_string(), cost)) {
                        Ok(None) => 1,
                        Err(RecordStoreError::ByteTotalOverflow) => 0,
                        other => panic!("unexpected insertion result: {other:?}"),
                    }
                })
            })
            .collect::<Vec<_>>();
        handles
            .into_iter()
            .map(|handle| handle.join().unwrap())
            .sum::<usize>()
    });
    assert_eq!(admitted, 1);
    assert_eq!(store.len(), 1);
    assert_eq!(store.current_bytes(), cost);
    let id = store.ids().pop().unwrap();
    store.remove(&id).unwrap();
    assert_eq!(store.current_bytes(), 0);
}
