use super::*;

fn retrieval(id: &str, context: Option<String>) -> Request<RetrieveRequest> {
    Request::new(RetrieveRequest {
        query: Some(retrieve_request::Query::ByIds(IdQuery {
            ids: vec![id.into()],
        })),
        context: context.map(|id| EpisodeContextRef {
            context_id: Some(id),
            new_episode_id: None,
        }),
        ..Default::default()
    })
}

#[tokio::test(start_paused = true)]
async fn refusal_has_no_record_effect_and_expiry_restores_admission() {
    let state = Arc::new(DaemonState::with_context_limit(1, 1));
    let service = ReckonService::new(state.clone());
    let record = service
        .write(Request::new(WriteRequest::default()))
        .await
        .unwrap()
        .into_inner()
        .record_id;
    let context = service
        .retrieve(retrieval(&record, None))
        .await
        .unwrap()
        .into_inner()
        .episode_context_id;
    let error = service
        .retrieve(retrieval(&record, None))
        .await
        .unwrap_err();
    assert_eq!(error.code(), tonic::Code::ResourceExhausted);
    assert_eq!(
        state
            .get_record(&record)
            .unwrap()
            .utility
            .unwrap()
            .use_count,
        1
    );
    assert_eq!(
        state.get_context(&context).unwrap().retrieved_record_ids,
        [record.clone()]
    );
    tokio::time::advance(std::time::Duration::from_secs(300)).await;
    let error = service
        .observe(Request::new(ObserveRequest {
            episode_context_id: context.clone(),
            credit_policy: CreditPolicy::Simple as i32,
            outcome_value: 1.0,
            ..Default::default()
        }))
        .await
        .unwrap_err();
    assert_eq!(error.code(), tonic::Code::FailedPrecondition);
    let replacement = service
        .retrieve(retrieval(&record, Some(context.clone())))
        .await
        .unwrap()
        .into_inner()
        .episode_context_id;
    assert_ne!(replacement, context);
    assert_eq!(
        state
            .get_record(&record)
            .unwrap()
            .utility
            .unwrap()
            .use_count,
        2
    );
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn parallel_retrievals_keep_one_context_and_credit_every_returned_record_once() {
    let state = Arc::new(DaemonState::with_context_limit(32, 1));
    let service = Arc::new(ReckonService::new(state.clone()));
    let context = service
        .retrieve(retrieval("absent", None))
        .await
        .unwrap()
        .into_inner()
        .episode_context_id;
    let mut ids = Vec::new();
    for _ in 0..32 {
        ids.push(
            service
                .write(Request::new(WriteRequest::default()))
                .await
                .unwrap()
                .into_inner()
                .record_id,
        );
    }
    let start = Arc::new(tokio::sync::Barrier::new(ids.len()));
    let mut tasks = Vec::new();
    for id in &ids {
        let (id, context, service, start) =
            (id.clone(), context.clone(), service.clone(), start.clone());
        tasks.push(tokio::spawn(async move {
            start.wait().await;
            for _ in 0..2 {
                let result = service
                    .retrieve(retrieval(&id, Some(context.clone())))
                    .await
                    .unwrap()
                    .into_inner();
                assert_eq!(result.episode_context_id, context);
                assert_eq!(result.records[0].id, id);
            }
        }));
    }
    for task in tasks {
        task.await.unwrap();
    }
    let observation = service
        .observe(Request::new(ObserveRequest {
            episode_context_id: context,
            credit_policy: CreditPolicy::Simple as i32,
            outcome_value: 1.0,
            ..Default::default()
        }))
        .await
        .unwrap()
        .into_inner();
    assert_eq!(observation.credits.len(), ids.len());
    for id in ids {
        let assignments: Vec<_> = observation
            .credits
            .iter()
            .filter(|credit| credit.record_id == id)
            .collect();
        assert_eq!(assignments.len(), 1);
        assert_eq!(assignments[0].credit, 1.0 / 32.0);
        assert_eq!(state.get_record(&id).unwrap().utility.unwrap().use_count, 2);
    }
}
