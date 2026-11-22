use super::*;

#[tokio::test]
async fn capacity_prunes_harmful_record_without_changing_its_measurements() {
    let state = Arc::new(DaemonState::new(2));
    let service = ReckonService::new(state.clone());
    let mut ids = Vec::new();
    for _ in 0..2 {
        ids.push(
            service
                .write(Request::new(WriteRequest {
                    initial_utility: 0.5,
                    ..Default::default()
                }))
                .await
                .unwrap()
                .into_inner()
                .record_id,
        );
    }
    {
        let mut harmful = state.records.get_mut(&ids[0]).unwrap();
        harmful.causal_score.as_mut().unwrap().ablation_delta = Some(-100.0);
        harmful.causal_score.as_mut().unwrap().counterfactual_delta = Some(-200.0);
        harmful.causal_score.as_mut().unwrap().influence_proxy = Some(1000.0);
        assert_eq!(harmful.priority_score(), 0.5);
        assert_eq!(
            harmful.causal_score.as_mut().unwrap().ablation_delta,
            Some(-100.0)
        );
        assert_eq!(
            harmful.causal_score.as_mut().unwrap().counterfactual_delta,
            Some(-200.0)
        );
    }
    state
        .records
        .get_mut(&ids[1])
        .unwrap()
        .causal_score
        .as_mut()
        .unwrap()
        .ablation_delta = Some(1.0);
    service
        .write(Request::new(WriteRequest::default()))
        .await
        .unwrap();
    assert!(state.get_record(&ids[0]).is_none());
    assert!(state.get_record(&ids[1]).is_some());
    assert_eq!(state.records.len(), 2);
}

#[tokio::test]
async fn capacity_orders_nan_first_and_breaks_infinite_ties_by_id() {
    for utilities in [[f64::NAN, 1.0], [f64::INFINITY, f64::INFINITY]] {
        let state = Arc::new(DaemonState::new(2));
        let service = ReckonService::new(state.clone());
        let mut ids = Vec::new();
        for utility in utilities {
            ids.push(
                service
                    .write(Request::new(WriteRequest {
                        initial_utility: utility,
                        ..Default::default()
                    }))
                    .await
                    .unwrap()
                    .into_inner()
                    .record_id,
            );
        }
        let expected = if utilities[0].is_nan() {
            ids[0].clone()
        } else {
            ids.iter().min().unwrap().clone()
        };
        service
            .write(Request::new(WriteRequest::default()))
            .await
            .unwrap();
        assert!(state.get_record(&expected).is_none());
        assert_eq!(state.records.len(), 2);
    }
}
