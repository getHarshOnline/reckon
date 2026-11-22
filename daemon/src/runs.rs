//! Retain only observations made by an identified run, independently of later
//! mutations and pruning in the shared record store. Admission precedes effects.

use std::collections::BTreeMap;
use tonic::Status;

use crate::service::proto::{ExportRunRequest, Record, RecordScope, RunExport};

pub const DEFAULT_MAX_RUNS: usize = 1_000;
pub const DEFAULT_MAX_RUN_BYTES: usize = 64 * 1024 * 1024;

#[derive(Clone)]
struct Member {
    snapshot: serde_json::Value,
    written: bool,
    retrieved: bool,
}

#[derive(Clone, Default)]
pub struct Run {
    revision: u64,
    members: BTreeMap<String, Member>,
    bytes: usize,
}

pub struct Runs {
    runs: BTreeMap<String, Run>,
    bytes: usize,
    max_runs: usize,
    max_bytes: usize,
}

impl Runs {
    pub fn new(max_runs: usize, max_bytes: usize) -> Self {
        Self {
            runs: BTreeMap::new(),
            bytes: 0,
            max_runs,
            max_bytes,
        }
    }

    pub fn validate_id(id: &str) -> Result<(), Status> {
        if id.is_empty()
            || id.len() > 128
            || !id
                .bytes()
                .all(|c| c.is_ascii_alphanumeric() || b"._-".contains(&c))
        {
            return Err(Status::invalid_argument(
                "run_id requires 1–128 ASCII letters, digits, dots, underscores or hyphens",
            ));
        }
        Ok(())
    }

    /// Prepare a complete replacement before the corresponding store effects.
    /// The caller holds the registry lock through preparation and commit.
    pub fn prepare(
        &self,
        id: &str,
        records: &[Record],
        written: bool,
        retrieved: bool,
    ) -> Result<Run, Status> {
        Self::validate_id(id)?;
        let previous = self.runs.get(id);
        if previous.is_none() && self.runs.len() >= self.max_runs {
            return Err(Status::resource_exhausted("run capacity reached"));
        }
        let mut run = previous.cloned().unwrap_or_default();
        run.revision = run
            .revision
            .checked_add(1)
            .ok_or_else(|| Status::resource_exhausted("run revision exhausted"))?;
        for record in records {
            let utility_finite = record.utility.as_ref().map_or(true, |utility| {
                utility.value.is_finite() && utility.uncertainty.is_finite()
            });
            let scores_finite = record.causal_score.as_ref().map_or(true, |score| {
                [
                    score.ablation_delta,
                    score.counterfactual_delta,
                    score.influence_proxy,
                ]
                .into_iter()
                .flatten()
                .all(f64::is_finite)
            });
            if !utility_finite || !scores_finite {
                return Err(Status::invalid_argument(
                    "run snapshots require finite record values",
                ));
            }
            let snapshot = serde_json::to_value(record)
                .map_err(|_| Status::internal("record snapshot could not be encoded"))?;
            // Value's object maps sort keys, so exported bytes do not depend on
            // the protobuf tag map's iteration order.
            let member = run.members.entry(record.id.clone()).or_insert(Member {
                snapshot: snapshot.clone(),
                written: false,
                retrieved: false,
            });
            member.snapshot = snapshot;
            member.written |= written;
            member.retrieved |= retrieved;
        }
        // Include keys and fixed member overhead in the retained-data budget.
        // This bounds retained logical data, not allocator overhead or RSS.
        run.bytes = id.len();
        for (key, member) in &run.members {
            let size = serde_json::to_vec(&member.snapshot)
                .map_err(|_| Status::internal("record snapshot could not be encoded"))?
                .len();
            run.bytes = run
                .bytes
                .checked_add(key.len())
                .and_then(|n| n.checked_add(size))
                .and_then(|n| n.checked_add(2))
                .ok_or_else(|| Status::resource_exhausted("run snapshot budget exceeded"))?;
        }
        let total = self.bytes - previous.map_or(0, |run| run.bytes);
        if total
            .checked_add(run.bytes)
            .map_or(true, |total| total > self.max_bytes)
        {
            return Err(Status::resource_exhausted("run snapshot budget exceeded"));
        }
        Ok(run)
    }

    pub fn commit(&mut self, id: String, run: Run) {
        self.bytes -= self.runs.get(&id).map_or(0, |old| old.bytes);
        self.bytes += run.bytes;
        self.runs.insert(id, run);
    }

    pub fn export(&self, request: ExportRunRequest) -> Result<RunExport, Status> {
        Self::validate_id(&request.run_id)?;
        let run = self
            .runs
            .get(&request.run_id)
            .ok_or_else(|| Status::not_found("run not found"))?;
        if request
            .expected_revision
            .is_some_and(|revision| revision != run.revision)
        {
            return Err(Status::failed_precondition("run revision changed"));
        }
        if request.include_events || request.include_metrics_csv || request.include_artifacts_tar {
            return Err(Status::unimplemented(
                "daemon run export has no event, metric or archive producer",
            ));
        }
        if request.max_records < 0 {
            return Err(Status::invalid_argument("max_records cannot be negative"));
        }
        let scope = RecordScope::try_from(request.record_scope)
            .map_err(|_| Status::invalid_argument("unknown record scope"))?;
        if matches!(scope, RecordScope::Unspecified | RecordScope::All) {
            return Err(Status::invalid_argument(
                "select NONE, WRITTEN, RETRIEVED or TOUCHED; store-wide export is refused",
            ));
        }
        let records_snapshot_json = if scope == RecordScope::None {
            None
        } else {
            let limit = if request.max_records == 0 {
                usize::MAX
            } else {
                request.max_records as usize
            };
            let records: Vec<_> = run
                .members
                .values()
                .filter(|member| match scope {
                    RecordScope::Written => member.written,
                    RecordScope::Retrieved => member.retrieved,
                    RecordScope::Touched => member.written || member.retrieved,
                    _ => false,
                })
                .take(limit)
                .map(|member| &member.snapshot)
                .collect();
            Some(
                serde_json::to_vec(&records)
                    .map_err(|_| Status::internal("run snapshot could not be encoded"))?,
            )
        };
        Ok(RunExport {
            run_id: request.run_id,
            source_revision: run.revision,
            records_snapshot_json,
            core_api_version: "1.0".into(),
            // No invented task, configuration, results or finish time.
            ..Default::default()
        })
    }
}
