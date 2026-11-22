use reckon_kernel::{
    FifoPolicy, LruPolicy, Record, RetentionPolicy, UtilityPolicy, WeightedEvidencePolicy,
};

fn make_records() -> Vec<Record> {
    vec![
        {
            let mut r = Record::new(
                "r1".to_string(),
                1,
                "ep".to_string(),
                "obs".to_string(),
                vec![],
                100,
            );
            r.utility = 0.5;
            r.last_used = 10;
            r
        },
        {
            let mut r = Record::new(
                "r2".to_string(),
                2,
                "ep".to_string(),
                "act".to_string(),
                vec![],
                100,
            );
            r.utility = 0.8;
            r.last_used = 5;
            r
        },
        {
            let mut r = Record::new(
                "r3".to_string(),
                3,
                "ep".to_string(),
                "obs".to_string(),
                vec![],
                100,
            );
            r.utility = 0.2;
            r.last_used = 15;
            r
        },
    ]
}

#[test]
fn test_fifo_policy() {
    let records = make_records();
    let refs: Vec<&Record> = records.iter().collect();
    let policy = FifoPolicy;

    let to_prune = policy.select_for_pruning(&refs, 100).unwrap();
    assert_eq!(to_prune, vec!["r1"]); // Oldest first
}

#[test]
fn test_lru_policy() {
    let records = make_records();
    let refs: Vec<&Record> = records.iter().collect();
    let policy = LruPolicy;

    let to_prune = policy.select_for_pruning(&refs, 100).unwrap();
    assert_eq!(to_prune, vec!["r2"]); // Least recently used (last_used=5)
}

#[test]
fn test_utility_policy() {
    let records = make_records();
    let refs: Vec<&Record> = records.iter().collect();
    let policy = UtilityPolicy;

    let to_prune = policy.select_for_pruning(&refs, 100).unwrap();
    assert_eq!(to_prune, vec!["r3"]); // Lowest utility (0.2)
}

#[test]
fn test_weighted_evidence_policy() {
    let mut records = make_records();
    // Give r1 a positive measured ablation effect.
    records[0].ablation_delta = Some(0.9);

    let refs: Vec<&Record> = records.iter().collect();
    let policy = WeightedEvidencePolicy::new(0.8);
    assert_eq!(policy.evidence_weight, 0.8);
    assert_eq!(policy.name(), "WeightedEvidence");
    assert_eq!(policy.reason(), "weighted_evidence_lowest");

    let to_prune = policy.select_for_pruning(&refs, 100).unwrap();
    // r3 has the lowest combined score: low utility and no supplied effects.
    assert_eq!(to_prune, vec!["r3"]);
}
