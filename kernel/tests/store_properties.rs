//! Exhaustive small-state checks against an independent map and budget model.

use reckon_kernel::{select_retention, Record, RecordStore, RetentionRule};
use std::collections::{BTreeMap, BTreeSet};

fn record(id: &str, bytes: i64, utility: f64) -> Record {
    let mut record = Record::new(id.into(), 0, "test".into(), "cue".into(), vec![], bytes);
    record.utility = utility;
    record
}

#[test]
fn every_small_operation_trace_preserves_accounting_and_priority() {
    // Every length-five trace of writes, replacement, removal, utility/access
    // updates, pruning and rebuilding. Capacity admission belongs to the caller.
    for trace in 0..8_usize.pow(5) {
        let store = RecordStore::new(2);
        let mut model = BTreeMap::<String, (i64, f64, i32)>::new();
        let mut remaining = trace;
        for step in 0..5 {
            let action = remaining % 8;
            remaining /= 8;
            match action {
                0..=2 => {
                    let (id, cost, utility) = match action {
                        0 => ("a", 1, 0.0),
                        1 => ("b", 3, 0.5),
                        _ => ("a", 7, 1.0),
                    };
                    let expected = model.insert(id.into(), (cost, utility, 0));
                    let previous = store.insert(record(id, cost, utility)).unwrap();
                    assert_eq!(previous.map(|r| r.cost_bytes), expected.map(|r| r.0));
                }
                3 => {
                    assert_eq!(
                        store.remove("a").map(|r| r.cost_bytes),
                        model.remove("a").map(|r| r.0)
                    );
                }
                4 => {
                    assert_eq!(store.update_utility("a", -1.0), model.contains_key("a"));
                    if let Some(value) = model.get_mut("a") {
                        value.1 = -1.0;
                    }
                }
                5 => {
                    assert_eq!(store.touch("a", step), Ok(model.contains_key("a")));
                    if let Some(value) = model.get_mut("a") {
                        value.2 += 1;
                    }
                }
                6 => {
                    for id in store.select_for_pruning(3) {
                        assert!(store.remove(&id).is_some());
                        assert!(model.remove(&id).is_some());
                    }
                }
                _ => store.force_rebuild(),
            }
            assert_eq!(store.len(), model.len(), "trace {trace}, step {step}");
            assert_eq!(
                store.current_bytes(),
                model.values().map(|r| r.0).sum::<i64>()
            );
            assert_eq!(
                store.ids().into_iter().collect::<BTreeSet<_>>(),
                model.keys().cloned().collect()
            );
            for (id, &(cost, utility, uses)) in &model {
                let actual = store.get(id).unwrap();
                assert_eq!(
                    (actual.cost_bytes, actual.utility, actual.use_count),
                    (cost, utility, uses)
                );
            }
            let mut ordered = model.iter().collect::<Vec<_>>();
            ordered.sort_by(|(a, av), (b, bv)| av.1.total_cmp(&bv.1).then_with(|| a.cmp(b)));
            let expected = ordered
                .iter()
                .map(|(id, _)| (*id).clone())
                .collect::<Vec<_>>();
            // Selection must leave every live record eligible for another call.
            assert_eq!(store.select_for_pruning(i64::MAX), expected);
            assert_eq!(store.select_for_pruning(i64::MAX), expected);
            let mut freed = 0;
            let mut expected_prefix = Vec::new();
            for (id, value) in ordered {
                if freed >= 3 {
                    break;
                }
                freed += value.0;
                expected_prefix.push(id.clone());
            }
            assert_eq!(store.select_for_pruning(3), expected_prefix);
        }
    }
}

#[test]
fn every_small_cost_vector_meets_both_pressures_with_a_minimal_prefix() {
    let rules = [
        RetentionRule::Fifo,
        RetentionRule::Lru,
        RetentionRule::LruThenCreated,
        RetentionRule::RawUtility,
        RetentionRule::UtilityPerByte,
        RetentionRule::EvidencePerByte { weight: 0.0 },
        RetentionRule::EvidencePerByte { weight: 0.5 },
        RetentionRule::EvidencePerByte { weight: 1.0 },
        RetentionRule::WeightedEvidence { weight: 0.5 },
        RetentionRule::Diversity { min_per_type: 0 },
        RetentionRule::Diversity { min_per_type: 2 },
        RetentionRule::Diversity {
            min_per_type: usize::MAX,
        },
        RetentionRule::InputOrder,
    ];
    for count in 0..=4_u32 {
        for vector in 0..4_usize.pow(count) {
            let mut digits = vector;
            let records = (0..count)
                .map(|index| {
                    let cost = [0, 1, 9, i64::MAX / 4][digits % 4];
                    digits /= 4;
                    let mut value = record(&index.to_string(), cost, f64::from(index % 3) - 1.0);
                    value.timestamp = i64::from(count - index);
                    value.last_used = i64::from(index % 2);
                    value.payload_type = (index % 2).to_string();
                    value.ablation_delta = [None, Some(-1.0), Some(0.0), Some(1.0)][index as usize];
                    value.counterfactual_delta = Some(0.5);
                    value.influence_proxy = Some(-0.75);
                    value
                })
                .collect::<Vec<_>>();
            let refs = records.iter().collect::<Vec<_>>();
            let total: i64 = records.iter().map(|r| r.cost_bytes).sum();
            for rule in rules {
                let order = select_retention(&refs, rule, 0, records.len(), 0).unwrap();
                for bytes in [0, 1, total / 2, total, total + 1, i64::MAX] {
                    for slots in 0..=records.len() + 1 {
                        let chosen = select_retention(&refs, rule, bytes, slots, 0).unwrap();
                        assert_eq!(chosen, order[..chosen.len()], "{rule:?}, vector {vector}");
                        assert_eq!(chosen.iter().collect::<BTreeSet<_>>().len(), chosen.len());
                        let costs = chosen
                            .iter()
                            .map(|id| records.iter().find(|r| &r.id == id).unwrap().cost_bytes)
                            .collect::<Vec<_>>();
                        let freed: i128 = costs.iter().map(|&v| i128::from(v)).sum();
                        if total >= bytes && records.len() >= slots {
                            assert!(freed >= i128::from(bytes) && chosen.len() >= slots);
                        } else {
                            assert_eq!(chosen.len(), records.len());
                        }
                        if let Some(&last) = costs.last() {
                            assert!(
                                freed - i128::from(last) < i128::from(bytes)
                                    || chosen.len() - 1 < slots
                            );
                        }
                    }
                }
            }
        }
    }
}
