//! Python object adapters over the laboratory model. Opaque values and mutable
//! containers remain Python references; reading a field never copies a list.

use crate::record;
use pyo3::class::gc::{PyTraverseError, PyVisit};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

macro_rules! adapter {
    ($name:ident, $python:literal, $model:ty, $constructor:item,
        $(($field:ident, $setter:ident, $kind:ty)),+ $(,)? $(; $($extra:item)*)?) => {
        #[pyclass(subclass, name = $python, module = "reckon._rust")]
        pub struct $name { pub inner: $model }

        #[pymethods]
        impl $name {
            $constructor

            $(
                #[getter]
                fn $field(&self) -> $kind { self.inner.$field.clone() }

                #[setter($field)]
                fn $setter(&mut self, value: $kind) { self.inner.$field = value; }
            )+

            fn _field_values<'py>(&self, py: Python<'py>) -> PyResult<&'py PyDict> {
                let values = PyDict::new(py);
                $(values.set_item(stringify!($field), self.inner.$field.clone())?;)+
                Ok(values)
            }

            #[staticmethod]
            fn _field_names() -> Vec<&'static str> { vec![$(stringify!($field)),+] }

            $($($extra)*)?
        }
    };
}

adapter!(
    PyRecordCost,
    "RecordCost",
    record::RecordCost,
    #[new]
    #[pyo3(signature = (bytes=1, tokens=None, slots=1))]
    fn new(bytes: i64, tokens: Option<i64>, slots: i32) -> Self {
        Self {
            inner: record::RecordCost {
                bytes,
                tokens,
                slots,
            },
        }
    },
    (bytes, set_bytes, i64),
    (tokens, set_tokens, Option<i64>),
    (slots, set_slots, i32),
);

adapter!(
    PyUtilityEstimate,
    "UtilityEstimate",
    record::UtilityEstimate,
    #[new]
    #[pyo3(signature = (value=0.0, uncertainty=1.0, last_used=-1, use_count=0))]
    fn new(value: f64, uncertainty: f64, last_used: i64, use_count: i32) -> Self {
        Self {
            inner: record::UtilityEstimate {
                value,
                uncertainty,
                last_used,
                use_count,
            },
        }
    },
    (value, set_value, f64),
    (uncertainty, set_uncertainty, f64),
    (last_used, set_last_used, i64),
    (use_count, set_use_count, i32),
);

adapter!(
    PyCausalScore,
    "CausalScore",
    record::CausalScore,
    #[new]
    #[pyo3(signature = (ablation_delta=None, counterfactual_delta=None, influence_proxy=None, last_evaluated=-1))]
    fn new(
        ablation_delta: Option<f64>,
        counterfactual_delta: Option<f64>,
        influence_proxy: Option<f64>,
        last_evaluated: i64,
    ) -> Self {
        Self {
            inner: record::CausalScore {
                ablation_delta,
                counterfactual_delta,
                influence_proxy,
                last_evaluated,
            },
        }
    },
    (ablation_delta, set_ablation_delta, Option<f64>),
    (counterfactual_delta, set_counterfactual_delta, Option<f64>),
    (influence_proxy, set_influence_proxy, Option<f64>),
    (last_evaluated, set_last_evaluated, i64),
);

adapter!(PyRecordOrigin, "RecordOrigin", record::RecordOrigin<PyObject>,
    #[new]
    #[pyo3(signature = (source_op=String::new(), input_ids=None, hash=String::new()))]
    fn new(py: Python<'_>, source_op: String, input_ids: Option<PyObject>, hash: String) -> Self {
        Self { inner: record::RecordOrigin { source_op, hash,
            input_ids: input_ids.unwrap_or_else(|| PyList::empty(py).into()) } }
    },
    (source_op, set_source_op, String), (input_ids, set_input_ids, PyObject),
    (hash, set_hash, String),
    ;
    fn __traverse__(&self, visit: PyVisit<'_>) -> Result<(), PyTraverseError> {
        visit.call(&self.inner.input_ids)
    }
    fn __clear__(&mut self, py: Python<'_>) { self.inner.input_ids = py.None(); }
);

pub type ObjectRecord = record::MemoryRecord<
    PyObject,
    PyObject,
    PyObject,
    PyObject,
    PyObject,
    PyObject,
    PyObject,
    PyObject,
>;

adapter!(PyMemoryRecord, "MemoryRecord", ObjectRecord,
    #[new]
    #[pyo3(signature = (id, timestamp, payload_type, payload, cost, tags, provenance,
        utility, causal_score, episode_id, metadata, compressed=false, encoding=String::new(),
        created_at_step=None, created_at_sequence=None))]
    #[allow(clippy::too_many_arguments)]
    fn new(id: String, timestamp: i64, payload_type: PyObject, payload: PyObject,
        cost: PyObject, tags: PyObject, provenance: PyObject, utility: PyObject,
        causal_score: PyObject, episode_id: String, metadata: PyObject,
        compressed: bool, encoding: String, created_at_step: Option<i64>,
        created_at_sequence: Option<i64>) -> Self {
        Self { inner: record::MemoryRecord { id, timestamp, payload_type, payload,
            cost, tags, provenance, utility, causal_score, episode_id, metadata,
            compressed, encoding, created_at_step, created_at_sequence } }
    },
    (id, set_id, String), (timestamp, set_timestamp, i64),
    (payload_type, set_payload_type, PyObject), (payload, set_payload, PyObject),
    (cost, set_cost, PyObject), (tags, set_tags, PyObject),
    (provenance, set_provenance, PyObject), (utility, set_utility, PyObject),
    (causal_score, set_causal_score, PyObject), (episode_id, set_episode_id, String),
    (metadata, set_metadata, PyObject), (compressed, set_compressed, bool),
    (encoding, set_encoding, String), (created_at_step, set_created_at_step, Option<i64>),
    (created_at_sequence, set_created_at_sequence, Option<i64>),
    ;
    fn _snapshot_json(&self, py: Python<'_>, payload: Vec<u8>, metadata: Vec<u8>) -> PyResult<String> {
        self.snapshot(py, payload, metadata)?.to_json().map_err(pyo3::exceptions::PyValueError::new_err)
    }

    fn _snapshot_wire<'py>(&self, py: Python<'py>, payload: Vec<u8>, metadata: Vec<u8>) -> PyResult<&'py pyo3::types::PyBytes> {
        use prost::Message;
        let value = crate::Record::try_from(self.snapshot(py, payload, metadata)?)
            .and_then(|record| crate::proto::MemoryRecord::try_from(&record))
            .map_err(|error| pyo3::exceptions::PyValueError::new_err(error.to_string()))?;
        Ok(pyo3::types::PyBytes::new(py, &value.encode_to_vec()))
    }

    fn __traverse__(&self, visit: PyVisit<'_>) -> Result<(), PyTraverseError> {
        for value in [&self.inner.payload_type, &self.inner.payload, &self.inner.cost,
            &self.inner.tags, &self.inner.provenance, &self.inner.utility,
            &self.inner.causal_score, &self.inner.metadata] { visit.call(value)?; }
        Ok(())
    }
    fn __clear__(&mut self, py: Python<'_>) {
        self.inner.payload_type = py.None(); self.inner.payload = py.None();
        self.inner.cost = py.None(); self.inner.tags = py.None();
        self.inner.provenance = py.None(); self.inner.utility = py.None();
        self.inner.causal_score = py.None(); self.inner.metadata = py.None();
    }
);

impl PyMemoryRecord {
    pub fn snapshot(
        &self,
        py: Python<'_>,
        payload: Vec<u8>,
        metadata: Vec<u8>,
    ) -> PyResult<record::ByteRecord> {
        let value = &self.inner;
        let kind: String = value.payload_type.as_ref(py).getattr("value")?.extract()?;
        let provenance = if value.provenance.is_none(py) {
            None
        } else {
            let origin = value.provenance.extract::<PyRef<PyRecordOrigin>>(py)?;
            Some(record::RecordOrigin {
                source_op: origin.inner.source_op.clone(),
                input_ids: origin.inner.input_ids.extract(py)?,
                hash: origin.inner.hash.clone(),
            })
        };
        Ok(record::MemoryRecord {
            id: value.id.clone(),
            timestamp: value.timestamp,
            episode_id: value.episode_id.clone(),
            payload_type: record::PayloadType::parse(&kind).ok_or_else(|| {
                pyo3::exceptions::PyValueError::new_err(format!("unsupported payload type: {kind}"))
            })?,
            payload: payload.into_iter().map(record::Byte).collect(),
            metadata: metadata.into_iter().map(record::Byte).collect(),
            tags: value.tags.extract(py)?,
            provenance,
            cost: value.cost.extract::<PyRef<PyRecordCost>>(py)?.inner.clone(),
            utility: value
                .utility
                .extract::<PyRef<PyUtilityEstimate>>(py)?
                .inner
                .clone(),
            causal_score: value
                .causal_score
                .extract::<PyRef<PyCausalScore>>(py)?
                .inner
                .clone(),
            compressed: value.compressed,
            encoding: value.encoding.clone(),
            created_at_step: value.created_at_step,
            created_at_sequence: value.created_at_sequence,
        })
    }
}

pub fn register(module: &PyModule) -> PyResult<()> {
    module.add_class::<PyMemoryRecord>()?;
    module.add_class::<PyRecordCost>()?;
    module.add_class::<PyRecordOrigin>()?;
    module.add_class::<PyUtilityEstimate>()?;
    module.add_class::<PyCausalScore>()?;
    module.add_function(wrap_pyfunction!(payload_types, module)?)?;
    module.add_function(wrap_pyfunction!(record_schema, module)?)?;
    Ok(())
}

#[pyfunction]
fn payload_types() -> std::collections::HashMap<String, &'static str> {
    record::PayloadType::members().into_iter().collect()
}

#[pyfunction]
fn record_schema() -> PyResult<String> {
    serde_json::to_string(&record::json_schema())
        .map_err(|error| pyo3::exceptions::PyValueError::new_err(error.to_string()))
}
