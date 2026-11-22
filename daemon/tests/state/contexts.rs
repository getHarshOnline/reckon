use super::*;

#[tokio::test(start_paused = true)]
async fn expiry_is_exact_and_observation_removes_expired_contexts() {
    let state = DaemonState::with_context_limit(1, 1);
    let original = state.with_context(None, None, |ctx| ctx.clone()).unwrap();
    tokio::time::advance(original.ttl - Duration::from_nanos(1)).await;
    assert!(state.get_context(&original.id).is_ok());
    tokio::time::advance(Duration::from_nanos(1)).await;
    assert_eq!(
        state.get_context(&original.id).unwrap_err(),
        ContextError::Expired
    );
    assert!(state.contexts.lock().is_empty());
    assert_eq!(
        state.get_context(&original.id).unwrap_err(),
        ContextError::Missing
    );
}

#[tokio::test(start_paused = true)]
async fn sustained_creation_reclaims_expiry_without_evicting_live_contexts() {
    let state = DaemonState::with_context_limit(1, 2);
    for _ in 0..100 {
        let first = state
            .with_context(None, Some("episode".into()), |ctx| {
                ctx.add_retrieved(vec!["record".into()]);
                ctx.clone()
            })
            .unwrap();
        state.with_context(None, None, |_| ()).unwrap();
        assert_eq!(
            state.with_context(None, None, |_| ()).unwrap_err(),
            ContextError::Full
        );
        tokio::time::advance(Duration::from_secs(299)).await;
        let reused = state
            .with_context(Some(first.id.clone()), Some("ignored".into()), |ctx| {
                ctx.clone()
            })
            .unwrap();
        assert_eq!(reused.episode_id, "episode");
        assert_eq!(reused.created_at, first.created_at);
        assert_eq!(reused.retrieved_record_ids, ["record"]);
        tokio::time::advance(Duration::from_secs(1)).await;
        let replacement = state
            .with_context(Some(first.id.clone()), None, |ctx| ctx.clone())
            .unwrap();
        assert_ne!(replacement.id, first.id);
        assert!(replacement.retrieved_record_ids.is_empty());
        assert_eq!(state.contexts.lock().len(), 1);
        tokio::time::advance(replacement.ttl).await;
    }
}

#[test]
fn concurrent_creation_and_reuse_preserve_capacity_and_all_attribution() {
    let state = DaemonState::with_context_limit(1, 3);
    let id = state
        .with_context(None, None, |ctx| ctx.id.clone())
        .unwrap();
    let start = std::sync::Barrier::new(16);
    std::thread::scope(|scope| {
        for worker in 0..16 {
            let state = &state;
            let id = &id;
            let start = &start;
            scope.spawn(move || {
                start.wait();
                for step in 0..30 {
                    let _ = state.with_context(None, None, |_| ());
                    state
                        .with_context(Some(id.clone()), None, |ctx| {
                            ctx.add_retrieved(vec![format!("{worker}-{step}")]);
                        })
                        .unwrap();
                    state.cleanup_expired_contexts();
                    assert!(state.contexts.lock().len() <= 3);
                }
            });
        }
    });
    assert_eq!(
        state.get_context(&id).unwrap().retrieved_record_ids.len(),
        480
    );
    assert_eq!(state.contexts.lock().len(), 3);
}

#[tokio::test(start_paused = true)]
async fn lifecycle_sweep_reclaims_idle_contexts_and_preserves_live_ones() {
    let state = Arc::new(DaemonState::with_context_limit(1, 2));
    let old = state
        .with_context(None, None, |ctx| ctx.id.clone())
        .unwrap();
    let sweep = tokio::spawn(state.clone().reap_contexts());
    tokio::task::yield_now().await;
    tokio::time::advance(Duration::from_secs(150)).await;
    let live = state
        .with_context(None, None, |ctx| ctx.id.clone())
        .unwrap();
    tokio::time::advance(Duration::from_secs(180)).await;
    tokio::task::yield_now().await;
    {
        let contexts = state.contexts.lock();
        assert!(!contexts.contains_key(&old));
        assert!(contexts.contains_key(&live));
        assert_eq!(contexts.len(), 1);
    }
    sweep.abort();
    assert!(sweep.await.unwrap_err().is_cancelled());
}
