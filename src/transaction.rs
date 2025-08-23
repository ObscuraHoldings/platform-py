// transaction.rs
use pyo3::prelude::*;
use pyo3::types::PyList;

#[pyclass]
pub struct TransactionBatcher {
    max_batch_size: usize,
}

#[pymethods]
impl TransactionBatcher {
    #[new]
    #[pyo3(signature = (max_batch_size=None))]
    fn new(max_batch_size: Option<usize>) -> Self {
        Self {
            max_batch_size: max_batch_size.unwrap_or(100),
        }
    }

    fn batch_transactions(&self, py: Python, transactions: Vec<String>) -> PyResult<PyObject> {
        let chunks: Vec<Vec<String>> = transactions
            .chunks(self.max_batch_size)
            .map(|c| c.to_vec())
            .collect();
        let py_list = PyList::new(py, chunks)?;
        Ok(py_list.unbind().into_any())
    }
}

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<TransactionBatcher>()?;
    Ok(())
}
