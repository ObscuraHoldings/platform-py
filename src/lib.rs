// lib.rs
use once_cell::sync::{Lazy, OnceCell};
use pyo3::prelude::*;
use tokio::runtime::{Builder, Runtime};

mod chain_monitor;
mod execution;
mod market_data;
mod transaction;

static GLOBAL_RUNTIME: Lazy<Runtime> = Lazy::new(|| {
    Builder::new_multi_thread()
        .enable_all()
        .thread_name("platform-rt")
        .max_blocking_threads(1024)
        .build()
        .expect("tokio runtime")
});

static TRACING_INIT: OnceCell<()> = OnceCell::new();

#[pyfunction]
pub fn initialize_rust_runtime() -> PyResult<()> {
    // Idempotent, no env-filter feature required
    let _ = TRACING_INIT.get_or_init(|| {
        let _ = tracing_subscriber::fmt::try_init();
        ()
    });
    Lazy::force(&GLOBAL_RUNTIME);
    Ok(())
}

#[inline]
pub fn runtime_handle() -> &'static tokio::runtime::Handle {
    GLOBAL_RUNTIME.handle()
}

#[pymodule]
fn platform_rust(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(initialize_rust_runtime, m)?)?;
    execution::register(m)?;
    chain_monitor::register(m)?;
    market_data::register(m)?;
    transaction::register(m)?;
    Ok(())
}
