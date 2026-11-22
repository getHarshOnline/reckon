use reckon_kernel::{
    select_retention, Record, RetentionPolicy, RetentionRule, WeightedEvidencePolicy,
};

fn record(id: &str, cost: i64, utility: f64) -> Record {
    let mut record = Record::new(id.into(), 0, "trial".into(), "cue".into(), vec![], cost);
    record.utility = utility;
    record
}

#[test]
fn distinct_rankings_keep_cost_and_measurement_precedence() {
    let mut first = record("a", 10, 0.4);
    first.timestamp = 2;
    first.ablation_delta = Some(-0.9);
    first.counterfactual_delta = Some(1.0);
    first.influence_proxy = Some(99.0);
    let mut second = record("b", 1, 0.2);
    second.timestamp = 1;
    second.ablation_delta = Some(0.2);
    let records = [&first, &second];
    for (rule, expected) in [
        (RetentionRule::RawUtility, "b"),
        (RetentionRule::UtilityPerByte, "a"),
        (RetentionRule::EvidencePerByte { weight: 1.0 }, "a"),
        (RetentionRule::WeightedEvidence { weight: 1.0 }, "b"),
        (RetentionRule::Lru, "a"),
        (RetentionRule::LruThenCreated, "b"),
    ] {
        assert_eq!(
            select_retention(&records, rule, 0, 1, 0).unwrap(),
            [expected]
        );
    }
    assert_eq!(
        WeightedEvidencePolicy::new(1.0)
            .select_for_budget(&records, 0, 1, 0)
            .unwrap(),
        ["b"]
    );
    assert_eq!(first.ablation_delta, Some(-0.9));
}

#[test]
fn selection_is_the_shortest_prefix_meeting_both_pressures() {
    let records = (1..=4)
        .map(|cost| record(&cost.to_string(), cost, 0.0))
        .collect::<Vec<_>>();
    let refs = records.iter().collect::<Vec<_>>();
    for bytes in 0..=11 {
        for slots in 0..=5 {
            let selected =
                select_retention(&refs, RetentionRule::InputOrder, bytes, slots, 0).unwrap();
            let count = selected.len();
            assert_eq!(
                selected,
                records[..count]
                    .iter()
                    .map(|r| r.id.clone())
                    .collect::<Vec<_>>()
            );
            let freed: i64 = records[..count].iter().map(|r| r.cost_bytes).sum();
            assert!(count == records.len() || (freed >= bytes && count >= slots));
            if count > 0 {
                assert!(freed - records[count - 1].cost_bytes < bytes || count - 1 < slots);
            }
        }
    }
    let large = [
        record("large-a", i64::MAX, 0.0),
        record("large-b", i64::MAX, 0.0),
    ];
    assert_eq!(
        select_retention(
            &large.iter().collect::<Vec<_>>(),
            RetentionRule::InputOrder,
            i64::MAX,
            2,
            0
        )
        .unwrap()
        .len(),
        2
    );
}

#[test]
fn diversity_exhausts_surplus_then_meets_pressure_below_minima() {
    let mut records = Vec::new();
    for kind in ["b", "a"] {
        for index in 0..3 {
            let mut value = record(&format!("{kind}{index}"), 1, f64::from(index));
            value.payload_type = kind.into();
            records.push(value);
        }
    }
    let selected = select_retention(
        &records.iter().collect::<Vec<_>>(),
        RetentionRule::Diversity { min_per_type: 2 },
        5,
        0,
        0,
    )
    .unwrap();
    assert_eq!(selected, ["a0", "b0", "a1", "b1", "a2"]);
}

#[test]
fn invalid_inputs_are_refused_before_a_selection_is_returned() {
    let mut first = record("a", 1, 0.0);
    let second = record("b", 1, f64::NAN);
    assert!(select_retention(&[&first, &second], RetentionRule::RawUtility, 0, 1, 0).is_err());
    assert!(select_retention(
        &[&first],
        RetentionRule::EvidencePerByte { weight: 1.1 },
        1,
        0,
        0
    )
    .is_err());
    assert!(select_retention(&[&first, &first], RetentionRule::Fifo, 1, 0, 0).is_err());
    first.cost_bytes = -1;
    assert!(select_retention(&[&first], RetentionRule::Fifo, 1, 0, 0).is_err());
}
