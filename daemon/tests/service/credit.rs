use super::*;

async fn fixture(utilities: &[f64]) -> (Arc<DaemonState>, ReckonService, Vec<String>, String) {
    let state = Arc::new(DaemonState::new(100));
    let service = ReckonService::new(state.clone());
    let mut ids = Vec::new();
    for utility in utilities {
        ids.push(
            service
                .write(Request::new(WriteRequest {
                    initial_utility: *utility,
                    ..Default::default()
                }))
                .await
                .unwrap()
                .into_inner()
                .record_id,
        );
    }
    // Repeated retrieval of one ID must not award it credit twice.
    let mut retrieved = ids.clone();
    retrieved.push(ids[0].clone());
    let context = service
        .retrieve(Request::new(RetrieveRequest {
            query: Some(retrieve_request::Query::ByIds(IdQuery { ids: retrieved })),
            ..Default::default()
        }))
        .await
        .unwrap()
        .into_inner()
        .episode_context_id;
    (state, service, ids, context)
}

#[tokio::test]
async fn observe_shaped_uses_softplus_and_kernel_utility_bounds() {
    let (state, service, ids, context) = fixture(&[-2.0_f64.ln(), 0.0, 2.0_f64.ln()]).await;
    let response = service
        .observe(Request::new(ObserveRequest {
            episode_context_id: context,
            outcome_value: -1.0,
            credit_policy: CreditPolicy::Shaped as i32,
            ..Default::default()
        }))
        .await
        .unwrap()
        .into_inner();
    assert_eq!(response.credits.len(), 3);
    let expected = [
        1.5_f64.ln() / 9.0_f64.ln(),
        2.0_f64.ln() / 9.0_f64.ln(),
        0.5,
    ];
    for ((assignment, id), expected) in response.credits.iter().zip(&ids).zip(expected) {
        assert_eq!(&assignment.record_id, id);
        assert!((assignment.credit - expected).abs() < 1e-15);
    }
    assert_eq!(state.get_record(&ids[0]).unwrap().utility_value(), 0.0);
    assert!(
        (state.get_record(&ids[2]).unwrap().utility_value() - (0.9 * 2.0_f64.ln() - 0.05)).abs()
            < 1e-15
    );
}

#[tokio::test]
async fn observe_ablation_keeps_harmful_measurement_but_assigns_no_credit() {
    let (state, service, ids, context) = fixture(&[0.5, 0.5]).await;
    state
        .records
        .get_mut(&ids[0])
        .unwrap()
        .causal_score
        .as_mut()
        .unwrap()
        .ablation_delta = Some(-2.0);
    state
        .records
        .get_mut(&ids[1])
        .unwrap()
        .causal_score
        .as_mut()
        .unwrap()
        .ablation_delta = Some(0.0);
    let response = service
        .observe(Request::new(ObserveRequest {
            episode_context_id: context,
            outcome_value: 1.0,
            credit_policy: CreditPolicy::Ablation as i32,
            ..Default::default()
        }))
        .await
        .unwrap()
        .into_inner();
    assert_eq!(
        response
            .credits
            .iter()
            .map(|value| value.credit)
            .collect::<Vec<_>>(),
        vec![0.0, 0.0]
    );
    assert_eq!(
        state.get_record(&ids[0]).unwrap().ablation_delta(),
        Some(-2.0)
    );
    assert_eq!(state.get_record(&ids[0]).unwrap().utility_value(), 0.45);
}

#[tokio::test]
async fn observe_rejects_invalid_input_before_any_update() {
    let (state, service, ids, context) = fixture(&[0.5, f64::NAN]).await;
    for (policy, outcome) in [
        (CreditPolicy::Simple as i32, 1.0),
        (CreditPolicy::Shaped as i32, f64::INFINITY),
        (999, 1.0),
    ] {
        let error = service
            .observe(Request::new(ObserveRequest {
                episode_context_id: context.clone(),
                outcome_value: outcome,
                credit_policy: policy,
                ..Default::default()
            }))
            .await
            .unwrap_err();
        assert_eq!(error.code(), tonic::Code::InvalidArgument);
        assert_eq!(state.get_record(&ids[0]).unwrap().utility_value(), 0.5);
    }
}
