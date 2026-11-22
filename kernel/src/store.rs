//! The kernel's store of Reckon's records, and the order in which to prune them
//! when a byte, token or slot budget is full.
//!
//! The daemon and the Python package keep their records here. The
//! [`RecordStore`], a HashMap with a BinaryHeap-backed priority index, provides
//! O(1) record lookup and O(log n) priority-based operations for efficient
//! pruning selection.
//!
//! # Lock Ordering
//!
//! To prevent deadlocks, always acquire locks in this order:
//! 1. `records` (RwLock)
//! 2. `priority_index` (RwLock)
//! 3. `current_bytes` (RwLock)
//! 4. `current_tokens` (RwLock)
//!
//! Never hold `priority_index` while acquiring `records`.

use hashbrown::HashMap;
use parking_lot::RwLock;
#[cfg(feature = "python")]
use pyo3::prelude::*;
use serde::{Deserialize, Serialize};
use std::cmp::Ordering;
use std::collections::BinaryHeap;
#[cfg(feature = "python")]
use std::sync::Arc;
use tracing::{debug, instrument};

/// A memory record stored in the CMM.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Record {
    /// Unique identifier
    pub id: String,
    /// Creation timestamp (step)
    pub timestamp: i64,
    /// Episode identifier
    pub episode_id: String,
    /// Payload type (as string)
    pub payload_type: String,
    /// Opaque payload bytes; interpretation belongs to the producer.
    pub payload: Vec<u8>,
    /// Cost in bytes
    pub cost_bytes: i64,
    /// Cost in tokens
    pub cost_tokens: i64,
    /// Number of slots
    pub cost_slots: i32,
    /// Categorical tags
    pub tags: Vec<String>,
    /// Utility value estimate
    pub utility: f64,
    /// Utility uncertainty
    pub utility_uncertainty: f64,
    /// Last access timestamp
    pub last_used: i64,
    /// Number of times accessed
    pub use_count: i32,
    /// Causal ablation delta (optional)
    pub ablation_delta: Option<f64>,
    /// Counterfactual delta (optional)
    pub counterfactual_delta: Option<f64>,
    /// Influence proxy (optional)
    pub influence_proxy: Option<f64>,
    /// Source operation, ordered inputs and content hash, when supplied.
    pub provenance: Option<crate::proto::RecordOrigin>,
    /// Opaque producer metadata; the store does not parse these bytes.
    #[serde(default)]
    pub metadata: Vec<u8>,
    /// Payload compression is described, not performed, by the store.
    #[serde(default)]
    pub compressed: bool,
    #[serde(default)]
    pub encoding: String,
    /// Step of the last supplied score measurement.
    #[serde(default = "unevaluated_step")]
    pub last_evaluated: i64,
    /// Producer-supplied creation position, independent of event ordering.
    pub created_at_step: Option<i64>,
    pub created_at_sequence: Option<i64>,
}

fn unevaluated_step() -> i64 {
    -1
}

impl Record {
    /// Create a new record with default utility values.
    pub fn new(
        id: String,
        timestamp: i64,
        episode_id: String,
        payload_type: String,
        payload: Vec<u8>,
        cost_bytes: i64,
    ) -> Self {
        Self {
            id,
            timestamp,
            episode_id,
            payload_type,
            payload,
            cost_bytes,
            cost_tokens: 0,
            cost_slots: 1,
            tags: Vec::new(),
            utility: 0.0,
            utility_uncertainty: 1.0,
            last_used: timestamp,
            use_count: 0,
            ablation_delta: None,
            counterfactual_delta: None,
            influence_proxy: None,
            provenance: None,
            metadata: Vec::new(),
            compressed: false,
            encoding: String::new(),
            last_evaluated: -1,
            created_at_step: None,
            created_at_sequence: None,
        }
    }

    /// Get effective priority score for pruning decisions.
    /// Lower scores are pruned first.
    ///
    /// NaN values in causal scores are treated as 0.0.
    /// If the final score is NaN, returns NEG_INFINITY (lowest priority for pruning).
    pub fn priority_score(&self) -> f64 {
        retention_priority(self.utility, self.ablation_delta, self.counterfactual_delta)
    }
}

/// Store priority shared by the kernel index and daemon capacity pruning.
///
/// Utility is independent of the bonus from beneficial measured effects. Missing
/// or NaN measurements add nothing; a NaN total has the lowest priority. Proxy
/// magnitude and byte cost belong to other named retention policies.
pub fn retention_priority(utility: f64, ablation: Option<f64>, counterfactual: Option<f64>) -> f64 {
    let bonus = ablation.unwrap_or(0.0).max(0.0) + counterfactual.unwrap_or(0.0).max(0.0);
    let score = utility + bonus * 0.5;
    if score.is_nan() {
        f64::NEG_INFINITY
    } else {
        score
    }
}

/// Reference to a record for the priority queue.
/// Ordered by priority score (lower = prune first).
#[derive(Debug, Clone)]
pub struct RecordRef {
    pub id: String,
    pub priority: f64,
}

impl PartialEq for RecordRef {
    fn eq(&self, other: &Self) -> bool {
        self.cmp(other) == Ordering::Equal
    }
}

impl Eq for RecordRef {}

impl PartialOrd for RecordRef {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

impl Ord for RecordRef {
    fn cmp(&self, other: &Self) -> Ordering {
        // Reverse order: we want lowest priority at the top for pruning
        // BinaryHeap is a max-heap, so we flip the comparison
        other
            .priority
            .total_cmp(&self.priority)
            .then_with(|| other.id.cmp(&self.id))
    }
}

/// Priority index backed by a BinaryHeap.
/// Provides O(log n) selection of lowest-priority records for pruning.
///
/// Uses lazy deletion with configurable auto-rebuild when staleness exceeds threshold.
#[derive(Debug, Clone)]
pub struct PriorityIndex {
    heap: BinaryHeap<RecordRef>,
    /// Current priority for each live record, independent of stale heap entries.
    priorities: HashMap<String, f64>,
    /// Rebuild when the stale fraction exceeds this threshold (default 0.5).
    rebuild_threshold: f64,
}

impl Default for PriorityIndex {
    fn default() -> Self {
        Self {
            heap: BinaryHeap::new(),
            priorities: HashMap::new(),
            rebuild_threshold: 0.5,
        }
    }
}

impl PriorityIndex {
    /// Create a new priority index with default rebuild threshold (50%).
    pub fn new() -> Self {
        Self::default()
    }

    /// Create with custom rebuild threshold (0.0 to 1.0).
    pub fn with_rebuild_threshold(threshold: f64) -> Self {
        Self {
            heap: BinaryHeap::new(),
            priorities: HashMap::new(),
            rebuild_threshold: threshold.clamp(0.1, 0.9),
        }
    }

    fn compact_if_needed(&mut self) {
        if self.staleness_ratio() > self.rebuild_threshold {
            self.rebuild_heap();
        }
    }

    /// Get the fraction of heap entries in excess of the live record count.
    pub fn staleness_ratio(&self) -> f64 {
        if self.heap.is_empty() {
            0.0
        } else {
            (self.heap.len() - self.priorities.len()) as f64 / self.heap.len() as f64
        }
    }

    /// Insert a record reference.
    pub fn insert(&mut self, id: String, priority: f64) {
        let priority = Self::normalize(priority);
        if self.priorities.get(&id) != Some(&priority) {
            self.priorities.insert(id.clone(), priority);
            self.heap.push(RecordRef { id, priority });
            self.compact_if_needed();
        }
    }

    /// Update the authoritative priority for a record.
    pub fn update(&mut self, id: &str, new_priority: f64) {
        self.insert(id.to_string(), new_priority);
    }

    /// Remove a record from the index.
    pub fn remove(&mut self, id: &str) {
        self.priorities.remove(id);
        self.compact_if_needed();
    }

    /// Pop the lowest-priority record (for pruning).
    /// Returns None if heap is empty or all entries are invalidated.
    pub fn pop_lowest(&mut self) -> Option<String> {
        self.discard_stale_head();
        let entry = self.heap.pop()?;
        self.priorities.remove(&entry.id);
        Some(entry.id)
    }

    /// Peek at the lowest-priority record without removing.
    /// Returns a cloned ID to avoid borrow checker issues.
    pub fn peek_lowest(&mut self) -> Option<String> {
        self.discard_stale_head();
        self.heap.peek().map(|entry| entry.id.clone())
    }

    fn discard_stale_head(&mut self) {
        while self
            .heap
            .peek()
            .is_some_and(|entry| self.priorities.get(&entry.id) != Some(&entry.priority))
        {
            self.heap.pop();
        }
    }

    /// Number of live records.
    pub fn len(&self) -> usize {
        self.priorities.len()
    }

    /// Check if empty.
    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }

    /// Rebuild the heap from scratch (use periodically to reclaim space).
    pub fn rebuild(&mut self, records: impl Iterator<Item = (String, f64)>) {
        self.priorities = records
            .map(|(id, score)| (id, Self::normalize(score)))
            .collect();
        self.rebuild_heap();
    }

    fn rebuild_heap(&mut self) {
        self.heap = BinaryHeap::from(
            self.priorities
                .iter()
                .map(|(id, &priority)| RecordRef {
                    id: id.clone(),
                    priority,
                })
                .collect::<Vec<_>>(),
        );
    }

    fn normalize(priority: f64) -> f64 {
        if priority.is_nan() {
            f64::NEG_INFINITY
        } else if priority == 0.0 {
            0.0
        } else {
            priority
        }
    }

    /// Get rebuild threshold.
    pub fn rebuild_threshold(&self) -> f64 {
        self.rebuild_threshold
    }

    /// Set rebuild threshold.
    pub fn set_rebuild_threshold(&mut self, threshold: f64) {
        self.rebuild_threshold = threshold.clamp(0.1, 0.9);
    }
}

/// Thread-safe record store with HashMap storage and priority indexing.
pub struct RecordStore {
    /// Record storage
    records: RwLock<HashMap<String, Record>>,
    /// Priority index for pruning
    priority_index: RwLock<PriorityIndex>,
    /// Declared slot capacity; the caller enforces admission limits.
    max_slots: usize,
    /// Current byte usage
    current_bytes: RwLock<i64>,
    /// Sum of declared token costs; zero does not estimate a tokenizer's output.
    current_tokens: RwLock<i64>,
}

/// A mutation refused before stored records or accounting change.
#[derive(Debug, Clone, Copy, PartialEq, Eq, thiserror::Error)]
pub enum RecordStoreError {
    #[error("record byte cost must be non-negative")]
    NegativeByteCost,
    #[error("record-store byte total exceeds the signed 64-bit range")]
    ByteTotalOverflow,
    #[error("record token cost must be non-negative")]
    NegativeTokenCost,
    #[error("record-store token total exceeds the signed 64-bit range")]
    TokenTotalOverflow,
    #[error("record use count exceeds the signed 32-bit range")]
    UseCountOverflow,
}

#[cfg(feature = "python")]
impl From<RecordStoreError> for PyErr {
    fn from(error: RecordStoreError) -> Self {
        match error {
            RecordStoreError::NegativeByteCost | RecordStoreError::NegativeTokenCost => {
                pyo3::exceptions::PyValueError::new_err(error.to_string())
            }
            RecordStoreError::ByteTotalOverflow
            | RecordStoreError::TokenTotalOverflow
            | RecordStoreError::UseCountOverflow => {
                pyo3::exceptions::PyOverflowError::new_err(error.to_string())
            }
        }
    }
}

impl RecordStore {
    /// Copy records, priorities and accounting under the mutation lock.
    /// Later writes to either store are independent; this is an in-memory copy.
    pub fn fork(&self) -> Self {
        let records = self.records.read();
        Self {
            records: RwLock::new(records.clone()),
            priority_index: RwLock::new(self.priority_index.read().clone()),
            max_slots: self.max_slots,
            current_bytes: RwLock::new(*self.current_bytes.read()),
            current_tokens: RwLock::new(*self.current_tokens.read()),
        }
    }

    /// Reserve storage for a declared slot capacity; admission stays with the caller.
    pub fn new(max_slots: usize) -> Self {
        Self {
            records: RwLock::new(HashMap::with_capacity(max_slots)),
            priority_index: RwLock::new(PriorityIndex::new()),
            max_slots,
            current_bytes: RwLock::new(0),
            current_tokens: RwLock::new(0),
        }
    }

    /// Insert a record.
    ///
    /// Returns the previously stored record on replacement, or None for a new ID.
    /// The caller selects any removals required by its admission policy. Zero
    /// byte cost is allowed; each record still occupies one slot.
    ///
    /// # Errors
    /// Refuses a negative byte/token cost or an unrepresentable final total before
    /// changing a record, its priority or the total. Replacements deduct the old
    /// cost before checking the new total, under the same mutation lock.
    #[instrument(skip(self, record), fields(id = %record.id, bytes = record.cost_bytes))]
    pub fn insert(&self, record: Record) -> Result<Option<Record>, RecordStoreError> {
        if record.cost_bytes < 0 {
            return Err(RecordStoreError::NegativeByteCost);
        }
        if record.cost_tokens < 0 {
            return Err(RecordStoreError::NegativeTokenCost);
        }
        debug!(id = %record.id, "inserting record");
        let id = record.id.clone();
        let priority = record.priority_score();
        let bytes = record.cost_bytes;

        let mut records = self.records.write();
        let old_bytes = records.get(&id).map_or(0, |old| old.cost_bytes);
        let old_tokens = records.get(&id).map_or(0, |old| old.cost_tokens);
        let next_bytes = self
            .current_bytes
            .read()
            .checked_sub(old_bytes)
            .and_then(|current| current.checked_add(bytes))
            .ok_or(RecordStoreError::ByteTotalOverflow)?;
        let next_tokens = self
            .current_tokens
            .read()
            .checked_sub(old_tokens)
            .and_then(|current| current.checked_add(record.cost_tokens))
            .ok_or(RecordStoreError::TokenTotalOverflow)?;
        let mut index = self.priority_index.write();
        let mut current = self.current_bytes.write();
        let mut tokens = self.current_tokens.write();
        let old_record = records.insert(id.clone(), record);
        index.insert(id, priority);
        *current = next_bytes;
        *tokens = next_tokens;
        Ok(old_record)
    }

    /// Get a record by ID.
    #[instrument(skip(self))]
    pub fn get(&self, id: &str) -> Option<Record> {
        let records = self.records.read();
        records.get(id).cloned()
    }

    /// Update utility for a record.
    /// Automatically rebuilds priority index if staleness exceeds threshold.
    pub fn update_utility(&self, id: &str, utility: f64) -> bool {
        let mut records = self.records.write();
        let Some(record) = records.get_mut(id) else {
            return false;
        };
        record.utility = utility;
        self.priority_index
            .write()
            .update(id, record.priority_score());
        true
    }

    /// Update last_used and use_count for a record.
    /// Refuse count overflow before changing either field; a missing ID returns false.
    pub fn touch(&self, id: &str, timestamp: i64) -> Result<bool, RecordStoreError> {
        let mut records = self.records.write();
        if let Some(record) = records.get_mut(id) {
            let use_count = record
                .use_count
                .checked_add(1)
                .ok_or(RecordStoreError::UseCountOverflow)?;
            record.last_used = timestamp;
            record.use_count = use_count;
            Ok(true)
        } else {
            Ok(false)
        }
    }

    /// Remove a record by ID.
    #[instrument(skip(self))]
    pub fn remove(&self, id: &str) -> Option<Record> {
        debug!(id = %id, "removing record");
        let mut records = self.records.write();
        let record = records.remove(id)?;
        let mut index = self.priority_index.write();
        index.remove(id);
        *self.current_bytes.write() -= record.cost_bytes;
        *self.current_tokens.write() -= record.cost_tokens;
        Some(record)
    }

    /// Select records for pruning to free at least `target_bytes` without removing them.
    #[instrument(skip(self))]
    pub fn select_for_pruning(&self, target_bytes: i64) -> Vec<String> {
        debug!(target_bytes = target_bytes, "selecting records for pruning");
        let mut to_prune = Vec::new();
        let mut freed = 0i64;

        let records = self.records.read();
        let mut index = self.priority_index.write();

        while freed < target_bytes {
            if let Some(id) = index.pop_lowest() {
                if let Some(record) = records.get(&id) {
                    freed += record.cost_bytes;
                    to_prune.push(id);
                }
            } else {
                break;
            }
        }

        for id in &to_prune {
            index.insert(id.clone(), records[id].priority_score());
        }

        to_prune
    }

    /// Current number of records.
    pub fn len(&self) -> usize {
        self.records.read().len()
    }

    /// Check if store is empty.
    pub fn is_empty(&self) -> bool {
        self.records.read().is_empty()
    }

    /// Current byte usage.
    pub fn current_bytes(&self) -> i64 {
        *self.current_bytes.read()
    }

    /// Sum of declared token costs in the store.
    pub fn current_tokens(&self) -> i64 {
        *self.current_tokens.read()
    }

    /// Declared slot capacity, without automatic pruning or admission enforcement.
    pub fn capacity(&self) -> usize {
        self.max_slots
    }

    /// Get all record IDs.
    pub fn ids(&self) -> Vec<String> {
        self.records.read().keys().cloned().collect()
    }

    /// Iterate over all records.
    pub fn iter(&self) -> Vec<Record> {
        self.records.read().values().cloned().collect()
    }

    /// Get current staleness ratio of the priority index.
    pub fn staleness_ratio(&self) -> f64 {
        self.priority_index.read().staleness_ratio()
    }

    /// Get rebuild threshold.
    pub fn rebuild_threshold(&self) -> f64 {
        self.priority_index.read().rebuild_threshold()
    }

    /// Set rebuild threshold (0.1 to 0.9).
    pub fn set_rebuild_threshold(&self, threshold: f64) {
        self.priority_index.write().set_rebuild_threshold(threshold);
    }

    /// Force rebuild of priority index.
    pub fn force_rebuild(&self) {
        let records = self.records.read();
        let priorities = records
            .iter()
            .map(|(id, record)| (id.clone(), record.priority_score()));
        self.priority_index.write().rebuild(priorities);
    }
}

// Python bindings

/// Python-exposed Record type.
#[cfg(feature = "python")]
#[pyclass(name = "Record")]
#[derive(Clone)]
pub struct PyRecord {
    inner: Record,
}

#[cfg(feature = "python")]
#[pymethods]
impl PyRecord {
    /// Decode a complete laboratory record without interpreting its payload.
    #[staticmethod]
    fn from_wire(data: &[u8]) -> PyResult<Self> {
        use prost::Message;
        let value = crate::proto::MemoryRecord::decode(data)
            .map_err(|error| pyo3::exceptions::PyValueError::new_err(error.to_string()))?;
        Ok(Self {
            inner: Record::try_from(value)
                .map_err(|error| pyo3::exceptions::PyValueError::new_err(error.to_string()))?,
        })
    }

    /// Encode the current native value as a laboratory MemoryRecord.
    fn to_wire<'py>(&self, py: Python<'py>) -> PyResult<&'py pyo3::types::PyBytes> {
        use prost::Message;
        let value = crate::proto::MemoryRecord::try_from(&self.inner)
            .map_err(|error| pyo3::exceptions::PyValueError::new_err(error.to_string()))?;
        Ok(pyo3::types::PyBytes::new(py, &value.encode_to_vec()))
    }

    #[getter]
    fn id(&self) -> &str {
        &self.inner.id
    }

    #[getter]
    fn timestamp(&self) -> i64 {
        self.inner.timestamp
    }

    #[getter]
    fn episode_id(&self) -> &str {
        &self.inner.episode_id
    }

    #[getter]
    fn payload_type(&self) -> &str {
        &self.inner.payload_type
    }

    #[getter]
    fn cost_bytes(&self) -> i64 {
        self.inner.cost_bytes
    }

    #[getter]
    fn cost_tokens(&self) -> i64 {
        self.inner.cost_tokens
    }

    #[getter]
    fn utility(&self) -> f64 {
        self.inner.utility
    }

    #[getter]
    fn last_used(&self) -> i64 {
        self.inner.last_used
    }

    #[getter]
    fn use_count(&self) -> i32 {
        self.inner.use_count
    }

    fn __repr__(&self) -> String {
        format!(
            "Record(id={}, utility={:.3}, bytes={})",
            self.inner.id, self.inner.utility, self.inner.cost_bytes
        )
    }
}

/// Python-exposed RecordStore.
#[cfg(feature = "python")]
#[pyclass(name = "RecordStore")]
pub struct PyRecordStore {
    inner: Arc<RecordStore>,
    /// Live native Python records; the inner store retains admitted accounting.
    objects: Py<pyo3::types::PyDict>,
}

#[cfg(feature = "python")]
impl PyRecordStore {
    fn ensure_byte_route(&self, py: Python<'_>, id: &str) -> PyResult<()> {
        if self.objects.as_ref(py).contains(id)? {
            return Err(pyo3::exceptions::PyValueError::new_err(
                "byte insertion cannot replace an object-backed record",
            ));
        }
        Ok(())
    }
}

#[cfg(feature = "python")]
#[pymethods]
impl PyRecordStore {
    fn __traverse__(
        &self,
        visit: pyo3::class::gc::PyVisit<'_>,
    ) -> Result<(), pyo3::class::gc::PyTraverseError> {
        visit.call(&self.objects)
    }

    fn __clear__(&mut self, py: Python<'_>) {
        self.objects = pyo3::types::PyDict::new(py).into();
    }

    /// Make an independent in-memory copy of the complete native store.
    fn fork(&self, py: Python<'_>) -> PyResult<Self> {
        let objects = py
            .import("copy")?
            .call_method1("deepcopy", (&self.objects,))?
            .extract()?;
        Ok(Self {
            inner: Arc::new(self.inner.fork()),
            objects,
        })
    }

    #[new]
    #[pyo3(signature = (max_slots=10000))]
    fn new(py: Python<'_>, max_slots: usize) -> Self {
        Self {
            inner: Arc::new(RecordStore::new(max_slots)),
            objects: pyo3::types::PyDict::new(py).into(),
        }
    }

    #[getter]
    fn _record_objects(&self, py: Python<'_>) -> Py<pyo3::types::PyDict> {
        self.objects.clone_ref(py)
    }

    /// Validate an admission projection before the caller chooses any removals.
    fn prepare_object(
        &self,
        py: Python<'_>,
        object: PyObject,
        payload: Vec<u8>,
    ) -> PyResult<PyRecord> {
        let record = object.extract::<PyRef<crate::record_bindings::PyMemoryRecord>>(py)?;
        let mut admission = record.snapshot(py, payload, Vec::new())?;
        // Unknown tokens contribute nothing to the known total. The live value
        // keeps None, and the manager separately records uncounted admissions.
        admission.cost.tokens = Some(admission.cost.tokens.unwrap_or(0));
        let admission = Record::try_from(admission)
            .map_err(|error| pyo3::exceptions::PyValueError::new_err(error.to_string()))?;
        Ok(PyRecord { inner: admission })
    }

    /// Retain the live value with the already validated, fixed admission snapshot.
    fn insert_object(
        &self,
        py: Python<'_>,
        object: PyObject,
        admission: &PyRecord,
    ) -> PyResult<()> {
        let record = object.extract::<PyRef<crate::record_bindings::PyMemoryRecord>>(py)?;
        let id = admission.inner.id.clone();
        if record.inner.id != id {
            return Err(pyo3::exceptions::PyValueError::new_err(
                "admission identity differs from record",
            ));
        }
        self.inner.insert(admission.inner.clone())?;
        drop(record);
        self.objects.as_ref(py).set_item(id, object)?;
        Ok(())
    }

    /// Increment both access views only after both counts can be represented.
    fn touch_object(&self, py: Python<'_>, id: &str, timestamp: i64) -> PyResult<bool> {
        let Some(object) = self.objects.as_ref(py).get_item(id)? else {
            return Ok(false);
        };
        let record = object.extract::<PyRef<crate::record_bindings::PyMemoryRecord>>()?;
        let mut utility = record
            .inner
            .utility
            .extract::<PyRefMut<crate::record_bindings::PyUtilityEstimate>>(py)?;
        let next = utility
            .inner
            .use_count
            .checked_add(1)
            .ok_or(RecordStoreError::UseCountOverflow)?;
        if !self.inner.touch(id, timestamp)? {
            return Ok(false);
        }
        utility.inner.last_used = timestamp;
        utility.inner.use_count = next;
        Ok(true)
    }

    /// Insert a new record.
    #[pyo3(signature = (id, timestamp, episode_id, payload_type, payload, cost_bytes, cost_tokens=0))]
    fn insert(
        &self,
        py: Python<'_>,
        id: String,
        timestamp: i64,
        episode_id: String,
        payload_type: String,
        payload: Vec<u8>,
        cost_bytes: i64,
        cost_tokens: i64,
    ) -> PyResult<()> {
        self.ensure_byte_route(py, &id)?;
        let mut record = Record::new(id, timestamp, episode_id, payload_type, payload, cost_bytes);
        record.cost_tokens = cost_tokens;
        self.inner.insert(record).map(|_| ()).map_err(Into::into)
    }

    /// Store every field of a decoded laboratory record, including opaque bytes.
    fn insert_record(&self, py: Python<'_>, record: &PyRecord) -> PyResult<()> {
        self.ensure_byte_route(py, &record.inner.id)?;
        self.inner
            .insert(record.inner.clone())
            .map(|_| ())
            .map_err(Into::into)
    }

    /// Get a record by ID.
    fn get(&self, id: &str) -> Option<PyRecord> {
        self.inner.get(id).map(|r| PyRecord { inner: r })
    }

    /// Update utility value for a record.
    fn update_utility(&self, id: &str, utility: f64) -> bool {
        self.inner.update_utility(id, utility)
    }

    /// Mark record as accessed.
    fn touch(&self, id: &str, timestamp: i64) -> PyResult<bool> {
        self.inner.touch(id, timestamp).map_err(Into::into)
    }

    /// Remove a record.
    fn remove(&self, py: Python<'_>, id: &str) -> PyResult<Option<PyRecord>> {
        let objects = self.objects.as_ref(py);
        if objects.contains(id)? {
            objects.del_item(id)?;
        }
        Ok(self.inner.remove(id).map(|r| PyRecord { inner: r }))
    }

    /// Select records for pruning.
    fn select_for_pruning(&self, target_bytes: i64) -> Vec<String> {
        self.inner.select_for_pruning(target_bytes)
    }

    /// Number of records stored.
    fn __len__(&self) -> usize {
        self.inner.len()
    }

    /// Current byte usage.
    #[getter]
    fn current_bytes(&self) -> i64 {
        self.inner.current_bytes()
    }

    #[getter]
    fn current_tokens(&self) -> i64 {
        self.inner.current_tokens()
    }

    /// Maximum capacity.
    #[getter]
    fn capacity(&self) -> usize {
        self.inner.capacity()
    }

    /// Get all record IDs.
    fn ids(&self) -> Vec<String> {
        self.inner.ids()
    }

    /// Get current staleness ratio of priority index (for monitoring).
    #[getter]
    fn staleness_ratio(&self) -> f64 {
        self.inner.staleness_ratio()
    }

    /// Get rebuild threshold (default 0.5 = 50%).
    #[getter]
    fn rebuild_threshold(&self) -> f64 {
        self.inner.rebuild_threshold()
    }

    /// Set rebuild threshold (0.1 to 0.9).
    #[setter]
    fn set_rebuild_threshold(&self, threshold: f64) {
        self.inner.set_rebuild_threshold(threshold);
    }

    /// Force rebuild of priority index (for maintenance).
    fn force_rebuild(&self) {
        self.inner.force_rebuild();
    }

    fn __repr__(&self) -> String {
        format!(
            "RecordStore(len={}, bytes={}, capacity={})",
            self.inner.len(),
            self.inner.current_bytes(),
            self.inner.capacity()
        )
    }
}
