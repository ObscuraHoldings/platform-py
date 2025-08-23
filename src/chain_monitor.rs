use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyDict;

// Alloy replaces ethers for transaction decoding and signer recovery.
use alloy_consensus::transaction::{EthereumTxEnvelope, SignerRecoverable, Transaction, TxEip4844};
use alloy_rlp::Decodable;

#[pyfunction]
fn decode_transaction(py: Python<'_>, tx_hex: &str) -> PyResult<PyObject> {
    // Strip optional 0x and decode hex
    let raw = tx_hex.trim_start_matches("0x");
    let bytes = hex::decode(raw).map_err(|e| PyValueError::new_err(format!("invalid hex: {e}")))?;
    let mut slice: &[u8] = &bytes;

    // Decode as EIP-2718 envelope (supports legacy/1559/2930/7702/4844)
    let envelope: EthereumTxEnvelope<TxEip4844> = Decodable::decode(&mut slice)
        .map_err(|e| PyValueError::new_err(format!("rlp decode failed: {e}")))?;

    // Recover sender (requires alloy-consensus k256 feature)
    let from = envelope
        .recover_signer()
        .map_err(|e| PyValueError::new_err(format!("failed to recover signer: {e}")))?;

    let out = PyDict::new(py);
    // Sender
    out.set_item("from", format!("{:#x}", from))?;
    // Recipient (or None for contract creation)
    match envelope.to() {
        Some(to) => out.set_item("to", format!("{:#x}", to))?,
        None => out.set_item("to", Option::<String>::None)?,
    }
    // Nonce
    out.set_item("nonce", envelope.nonce())?;
    // Gas limit as string to preserve width
    out.set_item("gas", envelope.gas_limit().to_string())?;
    // Gas price normalization: legacy has price; dynamic fee uses fee cap
    if let Some(price) = envelope.gas_price() {
        out.set_item("gas_price", price.to_string())?;
    } else {
        let fee_cap = envelope.max_fee_per_gas();
        out.set_item("gas_price", fee_cap.to_string())?;
    }
    // Value
    out.set_item("value", envelope.value().to_string())?;
    // Input data hex
    let input = envelope.input();
    out.set_item("input", format!("0x{}", hex::encode(input.as_ref())))?;
    // Transaction hash
    let hash = envelope.tx_hash();
    out.set_item("hash", format!("{:#x}", hash))?;
    Ok(out.unbind().into_any())
}

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(decode_transaction, m)?)?;
    Ok(())
}
