use reckon_kernel::{select_retention, Record, RecordStore, RecordStoreError, RetentionRule};
use std::sync::{Arc, Barrier};

fn record(id: &str, bytes: i64, tokens: i64, index: usize) -> Record {
    let mut value = Record::new(
        id.into(),
        index as i64,
        "trial".into(),
        (index % 2).to_string(),
        vec![],
        bytes,
    );
    value.cost_tokens = tokens;
    value.utility = (index % 3) as f64;
    value.ablation_delta = Some(0.5);
    value
}

#[test]
fn every_rule_keeps_its_order_and_stops_at_the_first_feasible_three_dimension_prefix() {
    let rules = [
        RetentionRule::Fifo,
        RetentionRule::Lru,
        RetentionRule::LruThenCreated,
        RetentionRule::RawUtility,
        RetentionRule::UtilityPerByte,
        RetentionRule::EvidencePerByte { weight: 0.5 },
        RetentionRule::WeightedEvidence { weight: 0.5 },
        RetentionRule::Diversity { min_per_type: 0 },
        RetentionRule::Diversity { min_per_type: 2 },
        RetentionRule::InputOrder,
    ];
    for vector in 0..81_usize {
        let mut digits = vector;
        let records = (0..4)
            .map(|i| {
                let tokens = [0, 1, 7][digits % 3];
                digits /= 3;
                record(&i.to_string(), [7, 0, 1, 3][i], tokens, i)
            })
            .collect::<Vec<_>>();
        let refs = records.iter().collect::<Vec<_>>();
        for rule in rules {
            let order = select_retention(&refs, rule, 0, 4, 0).unwrap();
            for bytes in [0, 1, 8, 12] {
                for slots in 0..=5 {
                    for tokens in [0, 1, 7, 14, 29] {
                        let selected = select_retention(&refs, rule, bytes, slots, tokens).unwrap();
                        let expected = (0..=4)
                            .find(|&count| {
                                let prefix = &order[..count];
                                let b: i64 = prefix
                                    .iter()
                                    .map(|id| {
                                        records.iter().find(|r| &r.id == id).unwrap().cost_bytes
                                    })
                                    .sum();
                                let t: i64 = prefix
                                    .iter()
                                    .map(|id| {
                                        records.iter().find(|r| &r.id == id).unwrap().cost_tokens
                                    })
                                    .sum();
                                b >= bytes && t >= tokens && count >= slots
                            })
                            .unwrap_or(4);
                        assert_eq!(selected, order[..expected], "{rule:?}, vector {vector}");
                    }
                }
            }
        }
    }
}

#[test]
fn selection_validates_token_costs_and_uses_wide_sums() {
    let mut first = record("a", 1, i64::MAX, 0);
    let second = record("b", 1, i64::MAX, 1);
    assert_eq!(
        select_retention(&[&first, &second], RetentionRule::Fifo, 0, 2, i64::MAX).unwrap(),
        ["a", "b"]
    );
    assert!(select_retention(&[&first], RetentionRule::Fifo, 0, 0, -1).is_err());
    first.cost_tokens = -1;
    assert!(select_retention(&[&first], RetentionRule::Fifo, 0, 0, 0).is_err());
}

#[test]
fn store_replacement_removal_and_refusal_preserve_both_totals() {
    let store = RecordStore::new(4);
    store.insert(record("a", 3, i64::MAX, 0)).unwrap();
    assert!(matches!(
        store.insert(record("b", 9, 1, 1)),
        Err(RecordStoreError::TokenTotalOverflow)
    ));
    assert!(matches!(
        store.insert(record("a", 4, -1, 0)),
        Err(RecordStoreError::NegativeTokenCost)
    ));
    assert_eq!(
        (store.len(), store.current_bytes(), store.current_tokens()),
        (1, 3, i64::MAX)
    );
    assert_eq!(store.get("a").unwrap().cost_tokens, i64::MAX);
    assert!(store.get("b").is_none());
    store.insert(record("a", 2, 5, 0)).unwrap();
    store.insert(record("b", 4, 7, 1)).unwrap();
    assert_eq!((store.current_bytes(), store.current_tokens()), (6, 12));
    assert_eq!(store.remove("a").unwrap().cost_tokens, 5);
    assert_eq!((store.current_bytes(), store.current_tokens()), (4, 7));
}

#[test]
fn concurrent_insertions_cannot_spend_the_same_token_range() {
    let store = Arc::new(RecordStore::new(3));
    store.insert(record("base", 1, i64::MAX - 1, 0)).unwrap();
    let barrier = Arc::new(Barrier::new(3));
    let handles = (0..2)
        .map(|i| {
            let store = store.clone();
            let barrier = barrier.clone();
            std::thread::spawn(move || {
                barrier.wait();
                store.insert(record(&i.to_string(), 1, 1, i)).is_ok()
            })
        })
        .collect::<Vec<_>>();
    barrier.wait();
    assert_eq!(
        handles
            .into_iter()
            .filter_map(|h| h.join().unwrap().then_some(()))
            .count(),
        1
    );
    assert_eq!(
        (store.current_bytes(), store.current_tokens()),
        (2, i64::MAX)
    );
}
