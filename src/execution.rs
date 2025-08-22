// execution.rs
use std::collections::HashMap;
use std::sync::{Arc, RwLock};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

#[derive(Clone, Debug)]
struct Token { address: String, symbol: String }

#[derive(Clone, Debug)]
struct Pool {
    address: String,
    token0: Token,
    token1: Token,
    fee: u32,
    liquidity: u128,
}

struct Route { path: Vec<String>, output_amount: u128 }

#[pyclass]
pub struct ExecutionEngine {
    #[pyo3(get)]
    engine_id: String,
    pools: Arc<RwLock<HashMap<String, Pool>>>, // address -> Pool
}

#[pymethods]
impl ExecutionEngine {
    #[new]
    fn new() -> Self {
        Self {
            engine_id: uuid::Uuid::new_v4().to_string(),
            pools: Arc::new(RwLock::new(HashMap::new())),
        }
    }

    #[pyo3(text_signature = "($self, params)")]
    fn optimize_route(&self, py: Python, params: &Bound<'_, PyDict>) -> PyResult<PyObject> {
        // Parse inputs
        let token_in: String = params.get_item("token_in")?
            .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err("missing 'token_in'"))?
            .extract()?;
        let token_out: String = params.get_item("token_out")?
            .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err("missing 'token_out'"))?
            .extract()?;
        let amount_in: u128 = params.get_item("amount_in")?
            .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err("missing 'amount_in'"))?
            .extract()?;

        // Compute without the GIL
        let pools_snapshot: Vec<Pool> = {
            let guard = self.pools.read().map_err(|_| {
                pyo3::exceptions::PyRuntimeError::new_err("pools lock poisoned")
            })?;
            guard.values().cloned().collect()
        };

        let route = py.allow_threads(|| {
            // Dijkstra-like maximization. Use addresses, not symbols.
            use std::cmp::Ordering;
            use std::collections::{BinaryHeap, HashMap};

            #[derive(Eq, PartialEq)]
            struct Node { amt: u128, token: String }
            impl Ord for Node {
                fn cmp(&self, other: &Self) -> Ordering { self.amt.cmp(&other.amt) }
            }
            impl PartialOrd for Node {
                fn partial_cmp(&self, other: &Self) -> Option<Ordering> { Some(self.cmp(other)) }
            }

            let mut dist: HashMap<String, u128> = HashMap::new();
            let mut prev: HashMap<String, String> = HashMap::new();
            let mut pq: BinaryHeap<Node> = BinaryHeap::new();

            dist.insert(token_in.clone(), amount_in);
            pq.push(Node { amt: amount_in, token: token_in.clone() });

            while let Some(Node { amt, token }) = pq.pop() {
                if amt < *dist.get(&token).unwrap_or(&0) { continue; }

                for pool in &pools_snapshot {
                    // Determine direction by matching address or symbol if address missing
                    let mut nexts = Vec::new();
                    if pool.token0.address == token || pool.token0.symbol == token {
                        let out = Self::calculate_amount_out(pool, amt);
                        nexts.push((&pool.token1, out));
                    }
                    if pool.token1.address == token || pool.token1.symbol == token {
                        let out = Self::calculate_amount_out(pool, amt);
                        nexts.push((&pool.token0, out));
                    }
                    for (nt, out_amt) in nexts {
                        if out_amt > *dist.get(&nt.address).unwrap_or(&0) {
                            dist.insert(nt.address.clone(), out_amt);
                            prev.insert(nt.address.clone(), token.clone());
                            pq.push(Node { amt: out_amt, token: nt.address.clone() });
                        }
                    }
                }
            }

            // Reconstruct path by addresses
            if !dist.contains_key(&token_out) {
                return None;
            }
            let mut path = Vec::new();
            let mut cur = token_out.clone();
            while let Some(p) = prev.get(&cur) {
                path.push(cur.clone());
                cur = p.clone();
            }
            path.push(token_in.clone());
            path.reverse();
            Some(Route { path, output_amount: *dist.get(&token_out).unwrap_or(&0) })
        });

        match route {
            Some(r) => {
                let out = PyDict::new(py);
                let path_list = PyList::new(py, &r.path);
                out.set_item("path", &path_list)?;
                out.set_item("output_amount", r.output_amount)?;
                Ok(out.into_py(py))
            }
            None => Ok(py.None().into_py(py)),
        }
    }

    #[pyo3(text_signature = "($self, pools_data)")]
    fn update_pools(&self, _py: Python, pools_data: &Bound<'_, PyList>) -> PyResult<()> {
        let mut map = self.pools.write().map_err(|_| {
            pyo3::exceptions::PyRuntimeError::new_err("pools lock poisoned")
        })?;
        map.clear();
        for pool_any in pools_data.iter() {
            let pool_dict: &Bound<PyDict> = pool_any.downcast()?;
            let token0_item = pool_dict.get_item("token0")?
                .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err("missing token0"))?;
            let token0: &Bound<PyDict> = token0_item.downcast()?;
            let token1_item = pool_dict.get_item("token1")?
                .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err("missing token1"))?;
            let token1: &Bound<PyDict> = token1_item.downcast()?;
            let pool = Pool {
                address: pool_dict.get_item("address")?.ok_or_else(|| pyo3::exceptions::PyKeyError::new_err("missing address"))?.extract()?,
                token0: Token {
                    address: token0.get_item("address")?.ok_or_else(|| pyo3::exceptions::PyKeyError::new_err("missing token0.address"))?.extract()?,
                    symbol:  token0.get_item("symbol")?.ok_or_else(|| pyo3::exceptions::PyKeyError::new_err("missing token0.symbol"))?.extract()?,
                },
                token1: Token {
                    address: token1.get_item("address")?.ok_or_else(|| pyo3::exceptions::PyKeyError::new_err("missing token1.address"))?.extract()?,
                    symbol:  token1.get_item("symbol")?.ok_or_else(|| pyo3::exceptions::PyKeyError::new_err("missing token1.symbol"))?.extract()?,
                },
                fee: pool_dict.get_item("fee")?.ok_or_else(|| pyo3::exceptions::PyKeyError::new_err("missing fee"))?.extract()?,
                liquidity: pool_dict.get_item("liquidity")?.ok_or_else(|| pyo3::exceptions::PyKeyError::new_err("missing liquidity"))?.extract()?,
            };
            map.insert(pool.address.clone(), pool);
        }
        Ok(())
    }
}

// Pure Rust helper
impl ExecutionEngine {
    #[inline]
    fn calculate_amount_out(pool: &Pool, amount_in: u128) -> u128 {
        // Replace with correct AMM formula later
        amount_in.saturating_sub((amount_in as u128 * pool.fee as u128) / 1_000_000u128)
    }
}

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<ExecutionEngine>()?;
    Ok(())
}