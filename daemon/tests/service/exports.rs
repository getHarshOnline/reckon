use super::*;

async fn write_run(service: &ReckonService, run: &str, payload: &[u8]) -> String {
    service
        .write(Request::new(WriteRequest {
            payload: payload.to_vec(),
            run_id: run.into(),
            ..Default::default()
        }))
        .await
        .unwrap()
        .into_inner()
        .record_id
}

async fn read_run(
    service: &ReckonService,
    run: &str,
    ids: Vec<String>,
    context: Option<String>,
) -> Result<RetrieveResponse, Status> {
    service
        .retrieve(Request::new(RetrieveRequest {
            run_id: run.into(),
            query: Some(retrieve_request::Query::ByIds(IdQuery { ids })),
            context: context.map(|id| EpisodeContextRef {
                context_id: Some(id),
                new_episode_id: None,
            }),
            ..Default::default()
        }))
        .await
        .map(Response::into_inner)
}

async fn export_run(service: &ReckonService, run: &str, scope: RecordScope) -> RunExport {
    service
        .export_run(Request::new(ExportRunRequest {
            run_id: run.into(),
            record_scope: scope as i32,
            ..Default::default()
        }))
        .await
        .unwrap()
        .into_inner()
        .export
        .unwrap()
}

fn rows(export: &RunExport) -> Vec<serde_json::Value> {
    serde_json::from_slice(export.records_snapshot_json.as_ref().unwrap()).unwrap()
}

#[tokio::test]
async fn overlapping_runs_export_only_their_last_observations_even_after_pruning() {
    let state = Arc::new(DaemonState::new(2));
    let service = ReckonService::new(state.clone());
    let shared = write_run(&service, "a", b"shared").await;
    let secret = write_run(&service, "b", b"b-only").await;
    let a_before = export_run(&service, "a", RecordScope::Touched).await;
    read_run(&service, "b", vec![shared.clone()], None)
        .await
        .unwrap();
    let b_written = export_run(&service, "b", RecordScope::Written).await;
    let b_read = export_run(&service, "b", RecordScope::Retrieved).await;
    assert_eq!(
        rows(&b_written)
            .iter()
            .map(|r| r["id"].as_str().unwrap())
            .collect::<Vec<_>>(),
        [secret]
    );
    assert_eq!(rows(&b_read)[0]["id"], shared);
    assert_eq!(
        export_run(&service, "a", RecordScope::Touched)
            .await
            .records_snapshot_json,
        a_before.records_snapshot_json
    );
    // Store-only changes, including deletion and unrelated insertion, cannot
    // rewrite a run's previously observed payload or inflate its membership.
    state.remove_record(&shared);
    write_run(&service, "", b"unattributed").await;
    let a_after = export_run(&service, "a", RecordScope::Touched).await;
    assert_eq!(
        a_after.records_snapshot_json,
        a_before.records_snapshot_json
    );
    assert_eq!(a_after.source_revision, a_before.source_revision);
    assert!(a_after.summary.is_none());
}

#[tokio::test]
async fn scope_revision_flags_and_limits_are_explicit() {
    let service = ReckonService::new(Arc::new(DaemonState::new(4)));
    read_run(&service, "empty", vec![], None).await.unwrap();
    assert_eq!(
        rows(&export_run(&service, "empty", RecordScope::Written).await),
        Vec::<serde_json::Value>::new()
    );
    assert!(export_run(&service, "empty", RecordScope::None)
        .await
        .records_snapshot_json
        .is_none());
    let mut ids = vec![
        write_run(&service, "a", b"1").await,
        write_run(&service, "a", b"2").await,
    ];
    ids.sort();
    let export = export_run(&service, "a", RecordScope::Written).await;
    let request = ExportRunRequest {
        run_id: "a".into(),
        record_scope: RecordScope::Written as i32,
        max_records: 1,
        expected_revision: Some(export.source_revision),
        ..Default::default()
    };
    let limited = service
        .export_run(Request::new(request.clone()))
        .await
        .unwrap()
        .into_inner()
        .export
        .unwrap();
    assert_eq!(rows(&limited).len(), 1);
    assert_eq!(rows(&limited)[0]["id"], ids[0]);
    assert_eq!(
        service
            .export_run(Request::new(request.clone()))
            .await
            .unwrap()
            .into_inner()
            .export
            .unwrap()
            .records_snapshot_json,
        limited.records_snapshot_json
    );
    read_run(&service, "a", vec![], None).await.unwrap();
    assert_eq!(
        service
            .export_run(Request::new(request))
            .await
            .unwrap_err()
            .code(),
        tonic::Code::FailedPrecondition
    );
    for scope in [0, 5, 99] {
        let error = service
            .export_run(Request::new(ExportRunRequest {
                run_id: "a".into(),
                record_scope: scope,
                ..Default::default()
            }))
            .await
            .unwrap_err();
        assert_eq!(error.code(), tonic::Code::InvalidArgument);
    }
    for flag in 0..3 {
        let error = service
            .export_run(Request::new(ExportRunRequest {
                run_id: "a".into(),
                record_scope: RecordScope::None as i32,
                include_events: flag == 0,
                include_metrics_csv: flag == 1,
                include_artifacts_tar: flag == 2,
                ..Default::default()
            }))
            .await
            .unwrap_err();
        assert_eq!(error.code(), tonic::Code::Unimplemented);
    }
    let error = service
        .export_run(Request::new(ExportRunRequest {
            run_id: "unknown".into(),
            ..Default::default()
        }))
        .await
        .unwrap_err();
    assert_eq!(error.code(), tonic::Code::NotFound);
    let error = service
        .export_run(Request::new(ExportRunRequest {
            run_id: "a".into(),
            record_scope: 3,
            max_records: -1,
            ..Default::default()
        }))
        .await
        .unwrap_err();
    assert_eq!(error.code(), tonic::Code::InvalidArgument);
}

#[tokio::test]
async fn mismatched_context_and_full_provenance_refuse_before_effects() {
    let state = Arc::new(DaemonState::with_context_limit(2, 2));
    let service = ReckonService::with_run_limits(state.clone(), 1, 4096);
    let record = write_run(&service, "a", b"record").await;
    let context = read_run(&service, "a", vec![record.clone()], None)
        .await
        .unwrap()
        .episode_context_id;
    let count = state
        .get_record(&record)
        .unwrap()
        .utility
        .unwrap()
        .use_count;
    let before = export_run(&service, "a", RecordScope::Touched).await;
    for run in ["b", ""] {
        let error = read_run(&service, run, vec![record.clone()], Some(context.clone()))
            .await
            .unwrap_err();
        assert_eq!(error.code(), tonic::Code::FailedPrecondition);
    }
    assert_eq!(
        read_run(&service, "b", vec![record.clone()], None)
            .await
            .unwrap_err()
            .code(),
        tonic::Code::ResourceExhausted
    );
    assert_eq!(
        state
            .get_record(&record)
            .unwrap()
            .utility
            .unwrap()
            .use_count,
        count
    );
    let error = service
        .write(Request::new(WriteRequest {
            run_id: "b".into(),
            payload: b"other".to_vec(),
            ..Default::default()
        }))
        .await
        .unwrap_err();
    assert_eq!(error.code(), tonic::Code::ResourceExhausted);
    let error = service
        .write(Request::new(WriteRequest {
            run_id: "a".into(),
            payload: vec![1; 10_000],
            ..Default::default()
        }))
        .await
        .unwrap_err();
    assert_eq!(error.code(), tonic::Code::ResourceExhausted);
    assert_eq!(state.stats().0, 1);
    let error = service
        .write(Request::new(WriteRequest {
            run_id: "a".into(),
            initial_utility: f64::NAN,
            ..Default::default()
        }))
        .await
        .unwrap_err();
    assert_eq!(error.code(), tonic::Code::InvalidArgument);
    let after = export_run(&service, "a", RecordScope::Touched).await;
    assert_eq!(after.records_snapshot_json, before.records_snapshot_json);
    assert_eq!(after.source_revision, before.source_revision);
    // A failed admission did not consume the remaining context slot.
    read_run(&service, "a", vec![], None).await.unwrap();
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn concurrent_run_operations_keep_membership_and_observation_revision() {
    let service = Arc::new(ReckonService::new(Arc::new(DaemonState::new(32))));
    let mut tasks = Vec::new();
    for i in 0..16 {
        let service = service.clone();
        tasks.push(tokio::spawn(async move {
            let run = if i % 2 == 0 { "a" } else { "b" };
            let id = write_run(&service, run, &[i]).await;
            (run, id)
        }));
    }
    let mut expected: HashMap<&str, Vec<String>> = HashMap::new();
    for task in tasks {
        let (run, id) = task.await.unwrap();
        expected.entry(run).or_default().push(id);
    }
    for (run, mut ids) in expected {
        ids.sort();
        let export = export_run(&service, run, RecordScope::Written).await;
        assert_eq!(
            rows(&export)
                .iter()
                .map(|r| r["id"].as_str().unwrap().to_owned())
                .collect::<Vec<_>>(),
            ids
        );
        assert_eq!(export.source_revision, 8);
        let context = read_run(&service, run, vec![ids[0].clone()], None)
            .await
            .unwrap()
            .episode_context_id;
        service
            .observe(Request::new(ObserveRequest {
                episode_context_id: context,
                outcome_value: 1.0,
                credit_policy: CreditPolicy::Simple as i32,
                ..Default::default()
            }))
            .await
            .unwrap();
        let observed = export_run(&service, run, RecordScope::Retrieved).await;
        assert_eq!(observed.source_revision, 10);
        assert!(rows(&observed)[0]["utility"]["value"].as_f64().unwrap() > 0.0);
    }
}
