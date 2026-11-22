//! Shared state management for Reckon daemon.
//!
//! Provides thread-safe access to:
//! - RecordStore: High-performance record storage
//! - EpisodeContexts: Tracking retrieved records for credit assignment

use crate::record::Record;
use crate::service::proto::TagValue;
use dashmap::DashMap;
use parking_lot::{Mutex, RwLock};
use std::collections::HashMap;
use std::sync::Arc;
use std::time::Duration;
use tokio::time::Instant;
use uuid::Uuid;

pub const DEFAULT_MAX_CONTEXTS: usize = 10_000;
const CONTEXT_SWEEP_INTERVAL: Duration = Duration::from_secs(30);

#[derive(Debug, PartialEq, Eq)]
pub enum ContextError {
    Full,
    Missing,
    Expired,
}

/// Episode context for tracking retrieved records
#[derive(Debug, Clone)]
pub struct EpisodeContext {
    pub id: String,
    pub episode_id: String,
    pub run_id: Option<String>,
    pub step: i64,
    pub retrieved_record_ids: Vec<String>,
    pub created_at: Instant,
    pub ttl: Duration,
}

impl EpisodeContext {
    /// Create a new episode context
    pub fn new(episode_id: String, ttl_ms: Option<u64>) -> Self {
        Self {
            id: Uuid::new_v4().to_string(),
            episode_id,
            run_id: None,
            step: 0,
            retrieved_record_ids: Vec::new(),
            created_at: Instant::now(),
            ttl: Duration::from_millis(ttl_ms.unwrap_or(300_000)), // 5 min default
        }
    }

    /// Check if context has expired
    pub fn is_expired(&self) -> bool {
        self.created_at.elapsed() >= self.ttl
    }

    /// Add retrieved record IDs
    pub fn add_retrieved(&mut self, ids: Vec<String>) {
        for id in ids {
            if !self.retrieved_record_ids.contains(&id) {
                self.retrieved_record_ids.push(id);
            }
        }
    }
}

/// Shared state for the daemon
pub struct DaemonState {
    /// Serialize capacity admission, replacement, removal and byte accounting.
    mutation: Mutex<()>,
    /// Record storage (record_id -> Record)
    pub records: DashMap<String, Record>,

    /// Episode contexts (context_id -> EpisodeContext)
    contexts: Mutex<HashMap<String, EpisodeContext>>,
    max_contexts: usize,

    /// Current episode ID
    pub current_episode: RwLock<String>,

    /// Current step within episode
    pub current_step: RwLock<i64>,

    /// Maximum slots
    pub max_slots: usize,

    /// Current byte usage
    pub current_bytes: RwLock<i64>,
}

impl DaemonState {
    /// Create new daemon state with given capacity
    pub fn new(max_slots: usize) -> Self {
        Self::with_context_limit(max_slots, DEFAULT_MAX_CONTEXTS)
    }

    pub fn with_context_limit(max_slots: usize, max_contexts: usize) -> Self {
        Self {
            mutation: Mutex::new(()),
            records: DashMap::with_capacity(max_slots),
            contexts: Mutex::new(HashMap::new()),
            max_contexts,
            current_episode: RwLock::new(String::new()),
            current_step: RwLock::new(0),
            max_slots,
            current_bytes: RwLock::new(0),
        }
    }

    /// Insert or replace a record, refusing zero capacity before mutation.
    pub fn write_record(&self, record: Record) -> Result<String, &'static str> {
        let _mutation = self.mutation.lock();
        if self.max_slots == 0 {
            return Err("the daemon requires at least one record slot");
        }
        let id = record.id.clone();
        let bytes = record.cost_bytes();

        // A replacement uses its existing slot and preserves unrelated records.
        if !self.records.contains_key(&id) {
            while self.records.len() >= self.max_slots {
                self.prune_lowest_priority();
            }
        }

        let previous_bytes = self
            .records
            .insert(id.clone(), record)
            .map_or(0, |previous| previous.cost_bytes());
        *self.current_bytes.write() += bytes - previous_bytes;
        Ok(id)
    }

    /// Get a record by ID
    pub fn get_record(&self, id: &str) -> Option<Record> {
        self.records.get(id).map(|r| r.clone())
    }

    /// Touch a record (update last_used, use_count)
    pub fn touch_record(&self, id: &str) -> bool {
        if let Some(mut record) = self.records.get_mut(id) {
            let step = *self.current_step.read();
            let utility = record.utility.get_or_insert_with(Default::default);
            utility.last_used = step;
            utility.use_count += 1;
            true
        } else {
            false
        }
    }

    /// Update utility for a record
    pub fn update_utility(&self, id: &str, utility: f64) -> bool {
        if let Some(mut record) = self.records.get_mut(id) {
            record.utility.get_or_insert_with(Default::default).value = utility;
            true
        } else {
            false
        }
    }

    /// Remove a record
    pub fn remove_record(&self, id: &str) -> Option<Record> {
        let _mutation = self.mutation.lock();
        self.remove_record_locked(id)
    }

    /// Caller holds the mutation lock, including during capacity pruning.
    fn remove_record_locked(&self, id: &str) -> Option<Record> {
        if let Some((_, record)) = self.records.remove(id) {
            *self.current_bytes.write() -= record.cost_bytes();
            Some(record)
        } else {
            None
        }
    }

    /// Prune lowest priority record
    fn prune_lowest_priority(&self) {
        // Match the kernel index's score ordering and record-ID tie break.
        // Release map guards before removing the selected record.
        let lowest_id = self
            .records
            .iter()
            .map(|entry| (entry.key().clone(), entry.value().priority_score()))
            .min_by(|(left_id, left), (right_id, right)| {
                left.total_cmp(right).then_with(|| left_id.cmp(right_id))
            })
            .map(|(id, _)| id);
        if let Some(id) = lowest_id {
            self.remove_record_locked(&id);
        }
    }

    /// Query records by tags
    pub fn query_by_tags(&self, tags: &HashMap<String, TagValue>, limit: usize) -> Vec<Record> {
        let mut results: Vec<_> = self
            .records
            .iter()
            .filter(|entry| {
                tags.iter()
                    .all(|(k, v)| entry.value().tags.get(k).map(|tv| tv == v).unwrap_or(false))
            })
            .map(|entry| entry.value().clone())
            .collect();

        // Sort by utility (highest first)
        results.sort_by(|a, b| {
            b.utility_value()
                .partial_cmp(&a.utility_value())
                .unwrap_or(std::cmp::Ordering::Equal)
        });
        results.truncate(limit);
        results
    }

    /// Query records by IDs
    pub fn query_by_ids(&self, ids: &[String]) -> Vec<Record> {
        ids.iter().filter_map(|id| self.get_record(id)).collect()
    }

    /// Query records by minimum utility
    pub fn query_by_utility(&self, min_utility: f64, limit: usize) -> Vec<Record> {
        let mut results: Vec<_> = self
            .records
            .iter()
            .filter(|entry| entry.value().utility_value() >= min_utility)
            .map(|entry| entry.value().clone())
            .collect();

        results.sort_by(|a, b| {
            b.utility_value()
                .partial_cmp(&a.utility_value())
                .unwrap_or(std::cmp::Ordering::Equal)
        });
        results.truncate(limit);
        results
    }

    /// Admit a retrieval and merge its attribution while holding the context lock.
    /// Live contexts are never evicted to make room. Missing or expired IDs start
    /// a fresh context, as does an omitted ID. The callback must not reenter this
    /// context store; its synchronous work finishes before cleanup can remove it.
    pub fn with_context<T>(
        &self,
        context_id: Option<String>,
        episode_id: Option<String>,
        retrieve: impl FnOnce(&mut EpisodeContext) -> T,
    ) -> Result<T, ContextError> {
        self.try_with_context(context_id, episode_id, None, |context| {
            Ok::<_, std::convert::Infallible>(retrieve(context))
        })
        .map(|result| match result {
            Ok(value) => value,
            Err(never) => match never {},
        })
    }

    /// Commit context attribution only when the operation succeeds. This lets
    /// run-snapshot admission refuse a retrieval before changing its context.
    pub fn try_with_context<T, E>(
        &self,
        context_id: Option<String>,
        episode_id: Option<String>,
        run_id: Option<String>,
        retrieve: impl FnOnce(&mut EpisodeContext) -> Result<T, E>,
    ) -> Result<Result<T, E>, ContextError> {
        let mut contexts = self.contexts.lock();
        contexts.retain(|_, context| !context.is_expired());
        if let Some(context) = context_id.and_then(|id| contexts.get(&id)) {
            let mut candidate = context.clone();
            let result = retrieve(&mut candidate);
            if result.is_ok() {
                contexts.insert(candidate.id.clone(), candidate);
            }
            return Ok(result);
        }
        if contexts.len() >= self.max_contexts {
            return Err(ContextError::Full);
        }
        let episode = episode_id.unwrap_or_else(|| self.current_episode.read().clone());
        let mut context = EpisodeContext::new(episode, None);
        context.run_id = run_id;
        let result = retrieve(&mut context);
        if result.is_ok() {
            contexts.insert(context.id.clone(), context);
        }
        Ok(result)
    }

    /// Snapshot attribution for an observation admitted before expiry.
    pub fn get_context(&self, context_id: &str) -> Result<EpisodeContext, ContextError> {
        let mut contexts = self.contexts.lock();
        let context = contexts.get(context_id).ok_or(ContextError::Missing)?;
        if context.is_expired() {
            contexts.remove(context_id);
            return Err(ContextError::Expired);
        }
        Ok(context.clone())
    }

    /// Set current episode
    pub fn set_episode(&self, episode_id: String) {
        *self.current_episode.write() = episode_id;
        *self.current_step.write() = 0;
    }

    /// Set current step
    pub fn set_step(&self, step: i64) {
        *self.current_step.write() = step;
    }

    /// Get all record IDs
    pub fn all_record_ids(&self) -> Vec<String> {
        self.records.iter().map(|e| e.key().clone()).collect()
    }

    /// Get current stats
    pub fn stats(&self) -> (usize, i64, usize) {
        let _mutation = self.mutation.lock();
        (
            self.records.len(),
            *self.current_bytes.read(),
            self.max_slots,
        )
    }

    /// Reclaim expired contexts even when no requests arrive.
    pub async fn reap_contexts(self: Arc<Self>) {
        let mut interval = tokio::time::interval(CONTEXT_SWEEP_INTERVAL);
        interval.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
        loop {
            interval.tick().await;
            self.cleanup_expired_contexts();
        }
    }

    pub fn cleanup_expired_contexts(&self) {
        self.contexts
            .lock()
            .retain(|_, context| !context.is_expired());
    }
}

impl Default for DaemonState {
    fn default() -> Self {
        Self::new(10000)
    }
}

#[cfg(test)]
#[path = "../tests/state/basic.rs"]
mod tests;

#[cfg(test)]
#[path = "../tests/state/contexts.rs"]
mod context_tests;
