//! Reckon's record store, retention rules, credit updates and event buffer: the
//! laboratory's account of which records mattered under a resource budget.
//!
//! The daemon and the Python package build on this kernel, and HENA's and Q-HENA's
//! kernels take its record protocol for their swarm stores.
//!
//! [`RecordStore`] and [`PriorityIndex`] hold records and select pruning
//! candidates. [`RetentionPolicy`] controls retention and [`EventLogger`]
//! records events in a bounded ring buffer.
//!
//! # Python Integration
//!
//! Default Rust builds do not require Python. The `extension-module` feature
//! enables the PyO3 binding used by the Python package. Import via:
//!
//! ```python
//! from reckon._rust import RecordStore, EventLogger
//! ```
//!
// Suppress PyO3 non-local impl warnings (expected with current PyO3 version)
#![allow(non_local_definitions)]

#[cfg(feature = "python")]
use pyo3::prelude::*;

pub mod credit;
mod logging;
mod policies;
#[cfg(feature = "python")]
mod policy_bindings;
pub mod record;
#[cfg(feature = "python")]
mod record_bindings;
mod record_exchange;
mod record_wire;
mod store;

// Re-export main types
pub use logging::{EventLogger, LogEvent, OpType};
pub use policies::{
    select_retention, DiversityPolicy, FifoPolicy, LruPolicy, RetentionError, RetentionPolicy,
    RetentionRule, UtilityPolicy, WeightedEvidencePolicy,
};
pub use record_wire::RecordWireError;
pub use store::{retention_priority, PriorityIndex, Record, RecordStore, RecordStoreError};

// Include prost-generated types
pub mod proto {
    include!(concat!(env!("OUT_DIR"), "/reckon.rs"));
}

/// Reckon Core Python module
///
/// Provides high-performance Rust implementations for:
/// - RecordStore: Memory record storage
/// - EventLogger: Event ring buffer
/// - Retention policies
#[cfg(feature = "python")]
#[pymodule]
fn _rust(_py: Python<'_>, m: &PyModule) -> PyResult<()> {
    // Register classes
    m.add_class::<store::PyRecordStore>()?;
    m.add_class::<store::PyRecord>()?;
    record_bindings::register(m)?;
    m.add_class::<logging::PyEventLogger>()?;
    m.add_class::<policy_bindings::PyRetentionPolicy>()?;
    m.add_function(wrap_pyfunction!(policy_bindings::py_select_retention, m)?)?;
    m.add_function(wrap_pyfunction!(credit::py_compute_credit, m)?)?;
    m.add_function(wrap_pyfunction!(credit::py_update_utility, m)?)?;
    m.add("DEFAULT_ETA", credit::DEFAULT_ETA)?;
    m.add("DEFAULT_U_MIN", credit::DEFAULT_U_MIN)?;
    m.add("DEFAULT_U_MAX", credit::DEFAULT_U_MAX)?;
    m.add("DEFAULT_SHAPED_SCALE", credit::DEFAULT_SHAPED_SCALE)?;

    // Module metadata
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add("__doc__", "High-performance Rust core for Reckon")?;

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_record_store_basic() {
        let store = RecordStore::new(100);
        assert_eq!(store.len(), 0);
        assert!(store.is_empty());
    }
}
