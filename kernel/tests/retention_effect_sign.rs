use reckon_kernel::{Record, RetentionPolicy, WeightedEvidencePolicy};

fn record(id: &str, delta: f64) -> Record {
    let mut record = Record::new(id.into(), 0, "trial".into(), "cue".into(), vec![], 5);
    record.ablation_delta = Some(delta);
    record
}

#[test]
fn harmful_measurements_give_no_bonus_in_policy_or_store_priority() {
    let mut harmful = record("harmful", -100.0);
    harmful.counterfactual_delta = Some(-200.0);
    let useful = record("useful", 1.0);
    assert_eq!(harmful.priority_score(), 0.0);
    assert_eq!(useful.priority_score(), 0.5);
    assert_eq!(
        WeightedEvidencePolicy::new(1.0)
            .select_for_pruning(&[&harmful, &useful], 5)
            .unwrap(),
        vec!["harmful"]
    );
    assert_eq!(harmful.ablation_delta, Some(-100.0));
    assert_eq!(harmful.counterfactual_delta, Some(-200.0));
}

#[test]
fn utility_and_proxy_keep_their_separate_roles() {
    let mut separate = record("separate", -100.0);
    separate.utility = 10.0;
    separate.influence_proxy = Some(-8.0);
    let useful = record("useful", 1.0);
    assert_eq!(separate.priority_score(), 10.0);
    assert_eq!(
        WeightedEvidencePolicy::new(0.5)
            .select_for_pruning(&[&separate, &useful], 5)
            .unwrap(),
        vec!["useful"]
    );
    separate.utility = 0.0;
    assert_eq!(
        WeightedEvidencePolicy::new(1.0)
            .select_for_pruning(&[&separate, &useful], 5)
            .unwrap(),
        vec!["useful"]
    );
}

#[test]
fn store_priority_preserves_nonfinite_ordering() {
    let mut value = record("edge", f64::NAN);
    value.utility = 0.5;
    value.counterfactual_delta = Some(f64::NEG_INFINITY);
    assert_eq!(value.priority_score(), 0.5);
    value.utility = f64::NAN;
    assert_eq!(value.priority_score(), f64::NEG_INFINITY);
    value.utility = f64::INFINITY;
    assert_eq!(value.priority_score(), f64::INFINITY);
}
