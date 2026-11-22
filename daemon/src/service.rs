//! gRPC service implementation for Reckon CausalMemoryService.
//!
//! Implements the 5-verb API: Write, Retrieve, Observe, Probe, ExportRun

use crate::runs::{Runs, DEFAULT_MAX_RUNS, DEFAULT_MAX_RUN_BYTES};
use parking_lot::Mutex;
use reckon_kernel::credit::{self, CreditInput, CreditPolicy as KernelCreditPolicy};
#[cfg(test)]
use std::collections::HashMap;
use std::sync::Arc;
use tonic::{Request, Response, Status};
use uuid::Uuid;

use crate::state::{ContextError, DaemonState};

fn context_status(error: ContextError) -> Status {
    match error {
        ContextError::Full => Status::resource_exhausted("episode context capacity reached"),
        ContextError::Missing => Status::not_found("Episode context not found"),
        ContextError::Expired => Status::failed_precondition("Episode context has expired"),
    }
}

// Include generated protobuf code
pub mod proto {
    tonic::include_proto!("reckon.core.v1");
}

use proto::causal_memory_service_server::CausalMemoryService;
use proto::*;

/// Reckon gRPC service implementation
pub struct ReckonService {
    state: Arc<DaemonState>,
    // All public store operations serialize with run snapshot admission.
    runs: Mutex<Runs>,
}

impl ReckonService {
    /// Create a new service with shared state
    pub fn new(state: Arc<DaemonState>) -> Self {
        Self::with_run_limits(state, DEFAULT_MAX_RUNS, DEFAULT_MAX_RUN_BYTES)
    }

    pub fn with_run_limits(state: Arc<DaemonState>, max_runs: usize, max_bytes: usize) -> Self {
        Self {
            state,
            runs: Mutex::new(Runs::new(max_runs, max_bytes)),
        }
    }
}

#[tonic::async_trait]
impl CausalMemoryService for ReckonService {
    /// Write a record to memory
    async fn write(
        &self,
        request: Request<WriteRequest>,
    ) -> Result<Response<WriteResponse>, Status> {
        let req = request.into_inner();
        let mut runs = self.runs.lock();

        // Generate record ID
        let record_id = Uuid::new_v4().to_string();
        let timestamp = *self.state.current_step.read();
        let episode_id = self.state.current_episode.read().clone();

        let run_id = req.run_id.clone();
        let record = Record::from_write(record_id.clone(), timestamp, episode_id.clone(), req);
        let cost = record.cost.clone();
        let prepared = if run_id.is_empty() {
            None
        } else {
            Some(runs.prepare(&run_id, std::slice::from_ref(&record), true, false)?)
        };
        self.state
            .write_record(record)
            .map_err(Status::resource_exhausted)?;
        if let Some(run) = prepared {
            runs.commit(run_id, run);
        }

        Ok(Response::new(WriteResponse {
            record_id,
            timestamp,
            episode_id,
            cost,
            api_version: Some(CoreApiVersion {
                version: "1.0".to_string(),
            }),
        }))
    }

    /// Retrieve records by query
    async fn retrieve(
        &self,
        request: Request<RetrieveRequest>,
    ) -> Result<Response<RetrieveResponse>, Status> {
        let req = request.into_inner();
        let mut runs = self.runs.lock();
        let run_id = if req.run_id.is_empty() {
            None
        } else {
            Runs::validate_id(&req.run_id)?;
            Some(req.run_id.clone())
        };
        let limit = if req.limit > 0 {
            req.limit as usize
        } else {
            10
        };

        // Get or create context
        let context_ref = req.context;
        let (context_id, new_episode_id) = context_ref
            .map(|c| (c.context_id, c.new_episode_id))
            .unwrap_or((None, None));

        let (context_id, records) = self
            .state
            .try_with_context(context_id, new_episode_id, run_id.clone(), |ctx| {
                if ctx.run_id != run_id {
                    return Err(Status::failed_precondition(
                        "episode context belongs to a different run",
                    ));
                }
                // Execute query
                let records: Vec<Record> = match req.query {
                    Some(retrieve_request::Query::ByTags(tag_query)) => {
                        self.state.query_by_tags(&tag_query.tags, limit)
                    }
                    Some(retrieve_request::Query::ByIds(id_query)) => {
                        self.state.query_by_ids(&id_query.ids)
                    }
                    Some(retrieve_request::Query::ByUtility(util_query)) => {
                        self.state.query_by_utility(util_query.min_utility, limit)
                    }
                    None => {
                        // Return recent records
                        self.state.query_by_utility(0.0, limit)
                    }
                };

                let prepared = run_id
                    .as_ref()
                    .map(|id| runs.prepare(id, &records, false, true))
                    .transpose()?;

                // Snapshot admission succeeds before records or attribution change.
                let record_ids: Vec<String> = records.iter().map(|r| r.id.clone()).collect();
                for id in &record_ids {
                    self.state.touch_record(id);
                }

                // Update context
                ctx.add_retrieved(record_ids);
                if let Some(run) = prepared {
                    runs.commit(req.run_id, run);
                }
                Ok((ctx.id.clone(), records))
            })
            .map_err(context_status)??;

        Ok(Response::new(RetrieveResponse {
            records,
            episode_context_id: context_id,
            api_version: Some(CoreApiVersion {
                version: "1.0".to_string(),
            }),
        }))
    }

    /// Observe outcome and assign credit
    async fn observe(
        &self,
        request: Request<ObserveRequest>,
    ) -> Result<Response<ObserveResponse>, Status> {
        let req = request.into_inner();
        let mut runs = self.runs.lock();

        // Get context
        let ctx = self
            .state
            .get_context(&req.episode_context_id)
            .map_err(context_status)?;

        if ctx.retrieved_record_ids.is_empty() {
            return Ok(Response::new(ObserveResponse {
                credits: vec![],
                policy_used: req.credit_policy,
                api_version: Some(CoreApiVersion {
                    version: "1.0".to_string(),
                }),
            }));
        }

        let policy = match CreditPolicy::try_from(req.credit_policy) {
            Ok(CreditPolicy::None) => KernelCreditPolicy::None,
            Ok(CreditPolicy::Simple) => KernelCreditPolicy::Simple,
            Ok(CreditPolicy::Shaped) => KernelCreditPolicy::Shaped,
            Ok(CreditPolicy::Ablation) => KernelCreditPolicy::Ablation,
            _ => {
                return Err(Status::invalid_argument(
                    "a known credit policy is required",
                ))
            }
        };
        let records = ctx
            .retrieved_record_ids
            .iter()
            .map(|id| self.state.get_record(id))
            .collect::<Vec<_>>();
        let inputs = records
            .iter()
            .map(|record| CreditInput {
                utility: record.as_ref().map_or(0.5, Record::utility_value),
                ablation_delta: record.as_ref().and_then(Record::ablation_delta),
            })
            .collect::<Vec<_>>();
        let weights = credit::compute_credit(
            &inputs,
            req.outcome_value,
            policy,
            credit::DEFAULT_SHAPED_SCALE,
        )
        .map_err(|error| Status::invalid_argument(error.to_string()))?;
        let credits = ctx
            .retrieved_record_ids
            .iter()
            .zip(weights)
            .map(|(id, weight)| CreditAssignment {
                record_id: id.clone(),
                credit: weight,
                policy: req.credit_policy,
            })
            .collect::<Vec<_>>();

        // Validate every update before changing any record.
        let mut updates = Vec::new();
        let mut snapshots = Vec::new();
        for (assignment, record) in credits.iter().zip(records) {
            if let Some(mut record) = record {
                let utility = credit::update_utility(
                    record.utility_value(),
                    assignment.credit,
                    req.outcome_value,
                    credit::DEFAULT_ETA,
                    credit::DEFAULT_U_MIN,
                    credit::DEFAULT_U_MAX,
                )
                .map_err(|error| Status::invalid_argument(error.to_string()))?;
                record.utility.get_or_insert_with(Default::default).value = utility;
                updates.push((record.id.clone(), utility));
                snapshots.push(record);
            }
        }
        let prepared = ctx
            .run_id
            .as_ref()
            .map(|id| runs.prepare(id, &snapshots, false, false))
            .transpose()?;
        for (id, utility) in updates {
            self.state.update_utility(&id, utility);
        }
        if let (Some(id), Some(run)) = (ctx.run_id, prepared) {
            runs.commit(id, run);
        }

        Ok(Response::new(ObserveResponse {
            credits,
            policy_used: req.credit_policy,
            api_version: Some(CoreApiVersion {
                version: "1.0".to_string(),
            }),
        }))
    }

    /// Refuse probes until an episode runner can measure both comparison arms.
    async fn probe(
        &self,
        _request: Request<ProbeRequest>,
    ) -> Result<Response<ProbeResponse>, Status> {
        Err(Status::unimplemented(
            "probing requires an episode runner for measured baseline and intervention trials",
        ))
    }

    /// Export the last observations made by this run, independently of the store.
    async fn export_run(
        &self,
        request: Request<ExportRunRequest>,
    ) -> Result<Response<ExportRunResponse>, Status> {
        let export = self.runs.lock().export(request.into_inner())?;
        Ok(Response::new(ExportRunResponse {
            export: Some(export),
        }))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_write_and_retrieve() {
        let state = Arc::new(DaemonState::new(100));
        let service = ReckonService::new(state.clone());

        // Write a record
        let write_req = Request::new(WriteRequest {
            payload: b"test data".to_vec(),
            payload_type: 1,
            tags: HashMap::new(),
            links: vec![],
            initial_utility: 0.5,
            run_id: String::new(),
        });

        let write_resp = service.write(write_req).await.unwrap();
        let record_id = write_resp.into_inner().record_id;

        // Retrieve by ID
        let retrieve_req = Request::new(RetrieveRequest {
            query: Some(retrieve_request::Query::ByIds(IdQuery {
                ids: vec![record_id.clone()],
            })),
            limit: 10,
            context: None,
            run_id: String::new(),
        });

        let retrieve_resp = service.retrieve(retrieve_req).await.unwrap();
        let records = retrieve_resp.into_inner().records;

        assert_eq!(records.len(), 1);
        assert_eq!(records[0].id, record_id);
    }

    #[tokio::test]
    async fn export_cannot_return_unattributed_records() {
        let state = Arc::new(DaemonState::new(100));
        let service = ReckonService::new(state);
        service
            .write(Request::new(WriteRequest {
                payload: b"unattributed record".to_vec(),
                ..Default::default()
            }))
            .await
            .unwrap();

        let result = service
            .export_run(Request::new(ExportRunRequest {
                run_id: "unknown-run".into(),
                record_scope: RecordScope::All as i32,
                ..Default::default()
            }))
            .await;

        assert_eq!(result.unwrap_err().code(), tonic::Code::NotFound);
    }
}

#[cfg(test)]
#[path = "../tests/service/probe.rs"]
mod probe_tests;

#[cfg(test)]
#[path = "../tests/service/credit.rs"]
mod credit_tests;

#[cfg(test)]
#[path = "../tests/service/retention.rs"]
mod retention_tests;

#[cfg(test)]
#[path = "../tests/service/capacity.rs"]
mod capacity_tests;

#[cfg(test)]
#[path = "../tests/service/contexts.rs"]
mod context_tests;

#[cfg(test)]
#[path = "../tests/service/exports.rs"]
mod export_tests;

#[cfg(test)]
#[path = "../tests/service/records.rs"]
mod record_tests;
