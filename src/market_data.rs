// market_data.rs
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use pyo3::exceptions::{PyTypeError, PyKeyError};

#[pyfunction]
pub fn aggregate_order_books(py: Python, books: &Bound<'_, PyList>) -> PyResult<PyObject> {
    let mut bids: Vec<(i64, i64)> = Vec::new();
    let mut asks: Vec<(i64, i64)> = Vec::new();

    for any in books.iter() {
        let d: &Bound<PyDict> = any.downcast()?;
        let side: String = d.get_item("side")?
            .ok_or_else(|| PyKeyError::new_err("missing 'side'"))?
            .extract()?;
        let price: i64 = d.get_item("price")?
            .ok_or_else(|| PyKeyError::new_err("missing 'price'"))?
            .extract()?;
        let size: i64 = d.get_item("size")?
            .ok_or_else(|| PyKeyError::new_err("missing 'size'"))?
            .extract()?;
        match side.as_str() {
            "bid" => bids.push((price, size)),
            "ask" => asks.push((price, size)),
            _ => return Err(PyTypeError::new_err("side must be 'bid' or 'ask'")),
        }
    }
    // simple aggregate by price
    use std::collections::BTreeMap;
    let mut bid_map = BTreeMap::new();
    let mut ask_map = BTreeMap::new();
    for (p, s) in bids { *bid_map.entry(p).or_insert(0) += s; }
    for (p, s) in asks { *ask_map.entry(p).or_insert(0) += s; }

    let out = PyDict::new(py);
    let bids_vec: Vec<(i64, i64)> = bid_map.into_iter().collect();
    let asks_vec: Vec<(i64, i64)> = ask_map.into_iter().collect();
    let bids_list = PyList::new(py, &bids_vec);
    let asks_list = PyList::new(py, &asks_vec);
    out.set_item("bids", &bids_list)?;
    out.set_item("asks", &asks_list)?;
    Ok(out.into_py(py))
}

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(aggregate_order_books, m)?)?;
    Ok(())
}