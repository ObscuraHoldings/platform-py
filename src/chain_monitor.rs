use pyo3::prelude::*;
use pyo3::types::PyDict;
use pyo3::exceptions::PyValueError;
use ethers::types::Transaction;
use rlp;

#[pyfunction]
fn decode_transaction(py: Python, tx_hex: &str) -> PyResult<PyObject> {
    let bytes = hex::decode(tx_hex.trim_start_matches("0x"))
        .map_err(|e| PyValueError::new_err(format!("invalid hex: {e}")))?;
    let tx: Transaction = rlp::decode(&bytes)
        .map_err(|e| PyValueError::new_err(format!("rlp decode failed: {e}")))?;

    let out = PyDict::new(py);
    out.set_item("from", format!("{:#x}", tx.from))?;
    if let Some(to) = tx.to {
        out.set_item("to", format!("{:#x}", to))?;
    } else {
        out.set_item("to", Option::<String>::None)?;
    }
    out.set_item("nonce", tx.nonce.as_u64())?;
    
    // Use strings for big ints to avoid extra features
    out.set_item("gas", tx.gas.to_string())?;
    if let Some(p) = tx.gas_price { out.set_item("gas_price", p.to_string())?; }
    else { out.set_item("gas_price", Option::<String>::None)?; }
    out.set_item("value", tx.value.to_string())?;
    out.set_item("input", format!("0x{}", hex::encode(tx.input)))?;
    out.set_item("hash", format!("{:#x}", tx.hash))?;
    Ok(out.into_any().unbind().into())
}

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(decode_transaction, m)?)?;
    Ok(())
}