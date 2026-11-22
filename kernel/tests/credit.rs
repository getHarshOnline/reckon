use reckon_kernel::credit::{compute_credit, update_utility, CreditInput, CreditPolicy};

fn input(utility: f64, ablation_delta: Option<f64>) -> CreditInput {
    CreditInput {
        utility,
        ablation_delta,
    }
}

#[test]
fn shaped_signed_vector_has_independently_derived_weights() {
    // softplus(-ln 2), softplus(0), softplus(ln 2) sum to ln 9.
    let inputs = [
        input(-2.0 * 2.0_f64.ln(), None),
        input(0.0, None),
        input(2.0 * 2.0_f64.ln(), None),
    ];
    let actual = compute_credit(&inputs, -1.0, CreditPolicy::Shaped, 2.0).unwrap();
    let expected = [
        1.5_f64.ln() / 9.0_f64.ln(),
        2.0_f64.ln() / 9.0_f64.ln(),
        0.5,
    ];
    for (actual, expected) in actual.iter().zip(expected) {
        assert!((actual - expected).abs() < 1e-15);
    }
}

#[test]
fn large_weights_stay_finite_and_shaped_underflow_is_refused() {
    for policy in [CreditPolicy::Shaped, CreditPolicy::Ablation] {
        let actual = compute_credit(
            &[input(1.6e308, Some(1.6e308)), input(8e307, Some(8e307))],
            1.0,
            policy,
            1.0,
        )
        .unwrap();
        assert_eq!(actual, vec![2.0 / 3.0, 1.0 / 3.0]);
    }
    for inputs in [
        vec![input(-1000.0, None)],
        vec![input(-500.0, None), input(1e308, None)],
    ] {
        assert!(compute_credit(&inputs, 1.0, CreditPolicy::Shaped, 1.0).is_err());
    }
}

#[test]
fn ablation_measurements_do_not_turn_harm_into_fallback_credit() {
    for deltas in [vec![Some(-10.0), Some(0.0)], vec![Some(-10.0), None]] {
        let inputs = deltas
            .into_iter()
            .map(|delta| input(0.5, delta))
            .collect::<Vec<_>>();
        assert_eq!(
            compute_credit(&inputs, 1.0, CreditPolicy::Ablation, 1.0).unwrap(),
            vec![0.0, 0.0]
        );
    }
    assert_eq!(
        compute_credit(&[input(0.5, None); 2], 1.0, CreditPolicy::Ablation, 1.0).unwrap(),
        vec![0.5, 0.5]
    );
    assert_eq!(
        compute_credit(
            &[input(0.5, Some(-2.0)), input(0.5, Some(3.0))],
            1.0,
            CreditPolicy::Ablation,
            1.0
        )
        .unwrap(),
        vec![0.0, 1.0]
    );
}

#[test]
fn credit_noops_and_nonfinite_inputs_are_explicit() {
    assert!(compute_credit(&[], f64::NAN, CreditPolicy::Shaped, 0.0)
        .unwrap()
        .is_empty());
    assert!(
        compute_credit(&[input(f64::NAN, None)], f64::NAN, CreditPolicy::None, 0.0)
            .unwrap()
            .is_empty()
    );
    for policy in [
        CreditPolicy::Simple,
        CreditPolicy::Shaped,
        CreditPolicy::Ablation,
    ] {
        assert!(compute_credit(&[input(0.5, None)], f64::NAN, policy, 1.0).is_err());
    }
    assert!(compute_credit(
        &[input(0.0, Some(f64::NAN))],
        1.0,
        CreditPolicy::Ablation,
        1.0
    )
    .is_err());
    assert!(compute_credit(
        &[input(f64::INFINITY, None)],
        1.0,
        CreditPolicy::Shaped,
        1.0
    )
    .is_err());
}

#[test]
fn utility_example_bounds_and_invalid_inputs() {
    assert!((update_utility(0.5, 0.33, 1.0, 0.1, 0.0, 1.0).unwrap() - 0.483).abs() < 1e-15);
    assert_eq!(update_utility(0.5, 1.0, -10.0, 1.0, 0.0, 1.0).unwrap(), 0.0);
    assert_eq!(update_utility(0.5, 1.0, 10.0, 1.0, 0.0, 1.0).unwrap(), 1.0);
    assert!(update_utility(f64::NAN, 1.0, 1.0, 0.1, 0.0, 1.0).is_err());
    assert!(update_utility(0.5, 1.0, 1.0, 0.0, 0.0, 1.0).is_err());
    assert!(update_utility(0.5, 1.1, 1.0, 0.1, 0.0, 1.0).is_err());
    assert!(update_utility(0.5, 1.0, 1.0, 0.1, 1.0, 0.0).is_err());
}
