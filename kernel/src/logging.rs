//! The kernel's event log: where a run's memory operations are recorded so
//! that the debugger can show them and a run can be replayed.
//!
//! It is a lock-free ring buffer that logs memory events with minimal
//! performance overhead. Events can be periodically flushed to disk or
//! streamed to the debugger.
//!
//! # Canonical Ordering
//!
//! Events are assigned monotonically increasing sequence numbers per (episode_id, step)
//! for deterministic canonical ordering. The canonical key is (episode_id, step, sequence).
//! Wall-clock timestamps are for display only; sequence is authoritative for ordering.
//! See docs/12-Reproducibility.md for specification.

use parking_lot::Mutex;
#[cfg(feature = "python")]
use pyo3::prelude::*;
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, VecDeque};
use std::sync::atomic::{AtomicU64, Ordering};

/// Type of memory operation.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum OpType {
    Write,
    Read,
    Prune,
    UpdateScore,
    Compress,
    BudgetCheck,
}

impl OpType {
    /// Convert to string representation.
    pub fn as_str(&self) -> &'static str {
        match self {
            OpType::Write => "write",
            OpType::Read => "read",
            OpType::Prune => "prune",
            OpType::UpdateScore => "update_score",
            OpType::Compress => "compress",
            OpType::BudgetCheck => "budget_check",
        }
    }
}

/// A logged memory event.
///
/// The canonical ordering key is (episode_id, timestamp, sequence).
/// sequence is deterministic and monotonically increasing per (episode_id, timestamp).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LogEvent {
    /// Unique event ID (monotonic)
    pub event_id: u64,
    /// Operation type
    pub op_type: OpType,
    /// Timestamp (step) - part of canonical ordering key
    pub timestamp: i64,
    /// Episode ID - part of canonical ordering key
    pub episode_id: String,
    /// Sequence number within (episode_id, timestamp) - part of canonical ordering key.
    /// Monotonically increasing; deterministic given the same run.
    pub sequence: u64,
    /// Record ID (if applicable)
    pub record_id: Option<String>,
    /// Duration in microseconds
    pub duration_us: u64,
    /// Current slot usage after operation
    pub slots_after: u64,
    /// Current byte usage after operation
    pub bytes_after: u64,
    /// Additional details (JSON string)
    pub details: Option<String>,
}

impl LogEvent {
    /// Create a new log event.
    ///
    /// The sequence field is part of the canonical ordering key (episode_id, timestamp, sequence).
    pub fn new(
        event_id: u64,
        op_type: OpType,
        timestamp: i64,
        episode_id: String,
        sequence: u64,
    ) -> Self {
        Self {
            event_id,
            op_type,
            timestamp,
            episode_id,
            sequence,
            record_id: None,
            duration_us: 0,
            slots_after: 0,
            bytes_after: 0,
            details: None,
        }
    }

    /// Set record ID.
    pub fn with_record(mut self, record_id: String) -> Self {
        self.record_id = Some(record_id);
        self
    }

    /// Set duration.
    pub fn with_duration(mut self, duration_us: u64) -> Self {
        self.duration_us = duration_us;
        self
    }

    /// Set resource usage after operation.
    pub fn with_usage(mut self, slots: u64, bytes: u64) -> Self {
        self.slots_after = slots;
        self.bytes_after = bytes;
        self
    }

    /// Set additional details.
    pub fn with_details(mut self, details: String) -> Self {
        self.details = Some(details);
        self
    }
}

/// High-performance ring buffer for event logging.
///
/// Uses a fixed-size buffer that overwrites oldest events when full.
/// Thread-safe with minimal contention.
///
/// # Canonical Ordering
///
/// Events are assigned sequence numbers per (episode_id, step) key.
/// The sequence counter is thread-safe and deterministic given the same run.
/// The canonical ordering key is (episode_id, step, sequence).
pub struct EventLogger {
    /// Ring buffer of events
    buffer: Mutex<VecDeque<LogEvent>>,
    /// Maximum buffer size
    capacity: usize,
    /// Monotonic event counter (global event ID)
    counter: AtomicU64,
    /// Current episode ID
    episode_id: Mutex<String>,
    /// Count of dropped events due to buffer overflow
    dropped_count: AtomicU64,
    /// Sequence counters keyed by (episode_id, step) for canonical ordering.
    /// Thread-safe via Mutex; deterministic given the same run.
    sequence_counters: Mutex<HashMap<(String, i64), u64>>,
}

impl EventLogger {
    /// Create a new event logger with given capacity.
    pub fn new(capacity: usize) -> Self {
        Self {
            buffer: Mutex::new(VecDeque::with_capacity(capacity)),
            capacity,
            counter: AtomicU64::new(0),
            episode_id: Mutex::new(String::new()),
            dropped_count: AtomicU64::new(0),
            sequence_counters: Mutex::new(HashMap::new()),
        }
    }

    /// Get the next sequence number for the given (episode_id, step) key.
    /// Thread-safe and deterministic given the same run.
    fn next_sequence(&self, episode_id: &str, step: i64) -> u64 {
        let mut counters = self.sequence_counters.lock();
        let key = (episode_id.to_string(), step);
        let seq = counters.entry(key).or_insert(0);
        let result = *seq;
        *seq += 1;
        result
    }

    /// Set the current episode ID.
    pub fn set_episode(&self, episode_id: String) {
        *self.episode_id.lock() = episode_id;
    }

    /// Get the current episode ID.
    pub fn episode_id(&self) -> String {
        self.episode_id.lock().clone()
    }

    /// Log an event.
    ///
    /// Assigns a deterministic sequence number per (episode_id, step) key.
    pub fn log(&self, op_type: OpType, timestamp: i64) -> u64 {
        let event_id = self.counter.fetch_add(1, Ordering::Relaxed);
        let episode_id = self.episode_id.lock().clone();
        let sequence = self.next_sequence(&episode_id, timestamp);

        let event = LogEvent::new(event_id, op_type, timestamp, episode_id, sequence);

        let mut buffer = self.buffer.lock();
        if buffer.len() >= self.capacity {
            buffer.pop_front();
            self.dropped_count.fetch_add(1, Ordering::Relaxed);
        }
        buffer.push_back(event);

        event_id
    }

    /// Log a full event with details.
    pub fn log_full(&self, event: LogEvent) -> u64 {
        let event_id = event.event_id;

        let mut buffer = self.buffer.lock();
        if buffer.len() >= self.capacity {
            buffer.pop_front();
            self.dropped_count.fetch_add(1, Ordering::Relaxed);
        }
        buffer.push_back(event);

        event_id
    }

    /// Create a new event with auto-assigned ID and deterministic sequence.
    pub fn create_event(&self, op_type: OpType, timestamp: i64) -> LogEvent {
        let event_id = self.counter.fetch_add(1, Ordering::Relaxed);
        let episode_id = self.episode_id.lock().clone();
        let sequence = self.next_sequence(&episode_id, timestamp);
        LogEvent::new(event_id, op_type, timestamp, episode_id, sequence)
    }

    /// Drain all events from the buffer.
    pub fn drain(&self) -> Vec<LogEvent> {
        let mut buffer = self.buffer.lock();
        buffer.drain(..).collect()
    }

    /// Get events since a given event ID.
    pub fn since(&self, event_id: u64) -> Vec<LogEvent> {
        let buffer = self.buffer.lock();
        buffer
            .iter()
            .filter(|e| e.event_id > event_id)
            .cloned()
            .collect()
    }

    /// Get the most recent N events.
    pub fn recent(&self, n: usize) -> Vec<LogEvent> {
        let buffer = self.buffer.lock();
        let len = buffer.len();
        let start = len.saturating_sub(n);
        buffer.iter().skip(start).cloned().collect()
    }

    /// Current number of events in buffer.
    pub fn len(&self) -> usize {
        self.buffer.lock().len()
    }

    /// Check if buffer is empty.
    pub fn is_empty(&self) -> bool {
        self.buffer.lock().is_empty()
    }

    /// Get buffer capacity.
    pub fn capacity(&self) -> usize {
        self.capacity
    }

    /// Get next event ID that will be assigned.
    pub fn next_event_id(&self) -> u64 {
        self.counter.load(Ordering::Relaxed)
    }

    /// Get the count of events dropped due to buffer overflow.
    pub fn dropped_count(&self) -> u64 {
        self.dropped_count.load(Ordering::Relaxed)
    }

    /// Peek at all events without draining.
    ///
    /// Returns a copy of all events currently in the buffer.
    pub fn peek(&self) -> Vec<LogEvent> {
        self.buffer.lock().iter().cloned().collect()
    }

    /// Read one retained event without draining the ring. Recent IDs are found first.
    pub fn get_event(&self, event_id: u64) -> Option<LogEvent> {
        self.buffer
            .lock()
            .iter()
            .rev()
            .find(|event| event.event_id == event_id)
            .cloned()
    }

    /// Clear the buffer.
    pub fn clear(&self) {
        self.buffer.lock().clear();
    }

    /// Export events as JSON lines.
    pub fn to_jsonl(&self) -> String {
        let buffer = self.buffer.lock();
        buffer
            .iter()
            .filter_map(|e| serde_json::to_string(e).ok())
            .collect::<Vec<_>>()
            .join("\n")
    }
}

impl Default for EventLogger {
    fn default() -> Self {
        Self {
            buffer: Mutex::new(VecDeque::with_capacity(10000)),
            capacity: 10000,
            counter: AtomicU64::new(0),
            episode_id: Mutex::new(String::new()),
            dropped_count: AtomicU64::new(0),
            sequence_counters: Mutex::new(HashMap::new()),
        }
    }
}

// Python bindings

/// Python-exposed event logger.
#[cfg(feature = "python")]
#[pyclass(name = "EventLogger")]
pub struct PyEventLogger {
    inner: EventLogger,
}

#[cfg(feature = "python")]
#[pymethods]
impl PyEventLogger {
    #[new]
    #[pyo3(signature = (capacity=10000))]
    fn new(capacity: usize) -> Self {
        Self {
            inner: EventLogger::new(capacity),
        }
    }

    /// Set the current episode ID.
    fn set_episode(&self, episode_id: String) {
        self.inner.set_episode(episode_id);
    }

    /// Log a write event.
    fn log_write(&self, timestamp: i64, record_id: &str, bytes: i64) -> u64 {
        let mut event = self.inner.create_event(OpType::Write, timestamp);
        event = event.with_record(record_id.to_string());
        event.bytes_after = bytes as u64;
        self.inner.log_full(event)
    }

    /// Log a read event.
    fn log_read(&self, timestamp: i64, record_ids: Vec<String>) -> u64 {
        let mut event = self.inner.create_event(OpType::Read, timestamp);
        event = event.with_details(serde_json::to_string(&record_ids).unwrap_or_default());
        self.inner.log_full(event)
    }

    /// Log a prune event.
    fn log_prune(&self, timestamp: i64, record_id: &str, reason: &str) -> u64 {
        let mut event = self.inner.create_event(OpType::Prune, timestamp);
        event = event.with_record(record_id.to_string());
        event = event.with_details(format!("{{\"reason\": \"{}\"}}", reason));
        self.inner.log_full(event)
    }

    /// Log a score update event.
    fn log_update_score(
        &self,
        timestamp: i64,
        record_id: &str,
        score_type: &str,
        old_value: f64,
        new_value: f64,
        signal_source: &str,
    ) -> u64 {
        let mut event = self.inner.create_event(OpType::UpdateScore, timestamp);
        event = event.with_record(record_id.to_string());
        event = event.with_details(format!(
            "{{\"score_type\": \"{}\", \"old\": {}, \"new\": {}, \"signal_source\": \"{}\"}}",
            score_type, old_value, new_value, signal_source
        ));
        self.inner.log_full(event)
    }

    /// Return one retained event as JSON without draining the ring.
    fn get_event(&self, event_id: u64) -> Option<String> {
        self.inner
            .get_event(event_id)
            .and_then(|event| serde_json::to_string(&event).ok())
    }

    /// Drain all events from the buffer.
    fn drain(&self) -> Vec<PyObject> {
        Python::with_gil(|py| {
            self.inner
                .drain()
                .into_iter()
                .filter_map(|e| {
                    let dict = pyo3::types::PyDict::new(py);
                    dict.set_item("event_id", e.event_id).ok()?;
                    dict.set_item("op_type", e.op_type.as_str()).ok()?;
                    dict.set_item("timestamp", e.timestamp).ok()?;
                    dict.set_item("episode_id", &e.episode_id).ok()?;
                    dict.set_item("sequence", e.sequence).ok()?;
                    dict.set_item("record_id", e.record_id.as_deref()).ok()?;
                    dict.set_item("duration_us", e.duration_us).ok()?;
                    dict.set_item("slots_after", e.slots_after).ok()?;
                    dict.set_item("bytes_after", e.bytes_after).ok()?;
                    dict.set_item("details", e.details.as_deref()).ok()?;
                    Some(dict.into())
                })
                .collect()
        })
    }

    /// Get events since a given event ID.
    fn since(&self, event_id: u64) -> String {
        let events = self.inner.since(event_id);
        events
            .iter()
            .filter_map(|e| serde_json::to_string(e).ok())
            .collect::<Vec<_>>()
            .join("\n")
    }

    /// Get recent events as JSON lines.
    fn recent(&self, n: usize) -> String {
        let events = self.inner.recent(n);
        events
            .iter()
            .filter_map(|e| serde_json::to_string(e).ok())
            .collect::<Vec<_>>()
            .join("\n")
    }

    /// Number of events in buffer.
    fn __len__(&self) -> usize {
        self.inner.len()
    }

    /// Buffer capacity.
    #[getter]
    fn capacity(&self) -> usize {
        self.inner.capacity()
    }

    /// Clear the buffer.
    fn clear(&self) {
        self.inner.clear();
    }

    /// Export as JSON lines.
    fn to_jsonl(&self) -> String {
        self.inner.to_jsonl()
    }

    /// Get count of dropped events due to buffer overflow.
    #[getter]
    fn dropped_count(&self) -> u64 {
        self.inner.dropped_count()
    }

    /// Peek at all events without draining.
    fn peek(&self) -> String {
        let events = self.inner.peek();
        events
            .iter()
            .filter_map(|e| serde_json::to_string(e).ok())
            .collect::<Vec<_>>()
            .join("\n")
    }

    fn __repr__(&self) -> String {
        format!(
            "EventLogger(len={}, capacity={}, dropped={})",
            self.inner.len(),
            self.inner.capacity(),
            self.inner.dropped_count()
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_event_logger_basic() {
        let logger = EventLogger::new(100);
        logger.set_episode("ep1".to_string());

        let id1 = logger.log(OpType::Write, 1);
        let id2 = logger.log(OpType::Read, 2);

        assert_eq!(id1, 0);
        assert_eq!(id2, 1);
        assert_eq!(logger.len(), 2);
    }

    #[test]
    fn test_ring_buffer_overflow() {
        let logger = EventLogger::new(3);
        logger.set_episode("ep1".to_string());

        logger.log(OpType::Write, 1);
        logger.log(OpType::Write, 2);
        logger.log(OpType::Write, 3);
        logger.log(OpType::Write, 4); // Should evict first

        assert_eq!(logger.len(), 3);

        let events = logger.drain();
        assert_eq!(events[0].timestamp, 2); // First event (t=1) was evicted
    }

    #[test]
    fn test_since() {
        let logger = EventLogger::new(100);
        logger.set_episode("ep1".to_string());

        logger.log(OpType::Write, 1);
        logger.log(OpType::Write, 2);
        logger.log(OpType::Write, 3);

        let since_1 = logger.since(0);
        assert_eq!(since_1.len(), 2); // Events with id > 0

        let since_2 = logger.since(1);
        assert_eq!(since_2.len(), 1); // Events with id > 1
    }

    #[test]
    fn test_jsonl_export() {
        let logger = EventLogger::new(100);
        logger.set_episode("ep1".to_string());

        logger.log(OpType::Write, 1);
        logger.log(OpType::Read, 2);

        let jsonl = logger.to_jsonl();
        let lines: Vec<_> = jsonl.lines().collect();
        assert_eq!(lines.len(), 2);

        // Verify JSON is parseable
        let _: LogEvent = serde_json::from_str(lines[0]).unwrap();
    }
}
