//! Reckon's laboratory daemon: the local gRPC server through which SDKs in other
//! languages reach the Reckon kernel's record store and credit updates.
//!
//! It is a separate, in-memory process that binds to loopback and accepts
//! trusted local callers without authentication or TLS.
//! ExportRun retains bounded observations from a named run; events, metrics
//! and archive attachments remain unimplemented. State lasts only until exit.
//!
//! Provides the CausalMemoryService with 5 verbs:
//! - Write: Store a record
//! - Retrieve: Query records
//! - Observe: Assign credit based on outcome
//! - Probe: Reserved until an episode runner measures both arms
//! - ExportRun: Scoped record observations from named runs
//!
//! # Usage
//!
//! ```bash
//! # Start daemon with default settings
//! reckon-daemon
//!
//! # Start on specific port with custom capacity
//! reckon-daemon --port 50051 --max-slots 10000
//!
//! # Test with grpcurl from daemon/
//! grpcurl -plaintext -import-path ../protos -proto reckon/core/v1/service.proto \
//!     -d '{"payload": "dGVzdA==", "payload_type": 1}' \
//!     127.0.0.1:50051 reckon.core.v1.CausalMemoryService/Write
//! ```

mod record;
mod runs;
mod service;
mod state;

use clap::Parser;
use std::net::SocketAddr;
use std::sync::Arc;
use tonic::transport::Server;
use tracing::{info, Level};
use tracing_subscriber::FmtSubscriber;

use service::proto::causal_memory_service_server::CausalMemoryServiceServer;
use service::ReckonService;
use state::{DaemonState, DEFAULT_MAX_CONTEXTS};

/// Reckon gRPC Daemon
#[derive(Parser, Debug)]
#[command(name = "reckon-daemon")]
#[command(author = "Harsh Joshi <hi@causality.in>")]
#[command(version)]
#[command(about = "Reckon's laboratory daemon: a local gRPC server for SDKs in other languages")]
struct Args {
    /// Loopback address to bind
    #[arg(long, default_value = "127.0.0.1")]
    host: String,

    /// Port to listen on
    #[arg(short, long, default_value_t = 50051)]
    port: u16,

    /// Maximum record slots
    #[arg(long, default_value_t = 10000)]
    max_slots: usize,

    /// Maximum live episode contexts
    #[arg(long, default_value_t = DEFAULT_MAX_CONTEXTS)]
    max_contexts: usize,

    /// Maximum retained run identities (until this daemon exits)
    #[arg(long, default_value_t = runs::DEFAULT_MAX_RUNS)]
    max_runs: usize,

    /// Maximum encoded run snapshots and member keys, excluding allocator overhead
    #[arg(long, default_value_t = runs::DEFAULT_MAX_RUN_BYTES)]
    max_run_bytes: usize,

    /// Log level (trace, debug, info, warn, error)
    #[arg(long, default_value = "info")]
    log_level: String,
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args = Args::parse();
    if args.max_slots == 0 {
        return Err("the daemon requires at least one record slot".into());
    }
    if args.max_contexts == 0 {
        return Err("the daemon requires at least one episode context".into());
    }
    if args.max_runs == 0 || args.max_run_bytes == 0 {
        return Err("run count and snapshot byte limits must be positive".into());
    }
    let addr: SocketAddr = format!("{}:{}", args.host, args.port).parse()?;
    if !addr.ip().is_loopback() {
        return Err("the laboratory daemon requires a loopback address".into());
    }

    // Initialize tracing
    let level = match args.log_level.to_lowercase().as_str() {
        "trace" => Level::TRACE,
        "debug" => Level::DEBUG,
        "info" => Level::INFO,
        "warn" => Level::WARN,
        "error" => Level::ERROR,
        _ => Level::INFO,
    };

    let subscriber = FmtSubscriber::builder()
        .with_max_level(level)
        .with_target(false)
        .with_thread_ids(false)
        .with_file(false)
        .finish();

    tracing::subscriber::set_global_default(subscriber).expect("Failed to set tracing subscriber");

    // Create shared state
    let state = Arc::new(DaemonState::with_context_limit(
        args.max_slots,
        args.max_contexts,
    ));

    // Create service
    let service = ReckonService::with_run_limits(state.clone(), args.max_runs, args.max_run_bytes);

    info!("Starting Reckon daemon v{}", env!("CARGO_PKG_VERSION"));
    info!("  Address: {}", addr);
    info!("  Max slots: {}", args.max_slots);
    info!("  Max contexts: {}", args.max_contexts);
    info!("  Log level: {}", args.log_level);
    info!("");

    // Start server
    let context_cleanup = tokio::spawn(state.reap_contexts());
    let result = Server::builder()
        .add_service(CausalMemoryServiceServer::new(service))
        .serve(addr)
        .await;
    context_cleanup.abort();
    let _ = context_cleanup.await;
    result?;

    Ok(())
}
