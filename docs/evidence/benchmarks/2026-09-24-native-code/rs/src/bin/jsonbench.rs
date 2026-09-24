// parse: read + parse into a generic Value (like Ruby's Hash/Array), sum "amount".
// typed: parse into a struct instead.   generate: parse (untimed), then serialise (timed).
use serde::Deserialize;
use serde_json::Value;
use std::time::Instant;
#[derive(Deserialize)]
#[allow(dead_code)]
struct Addr { city: String, zip: String }
#[derive(Deserialize)]
#[allow(dead_code)]
struct Rec { id: u64, uuid: String, name: String, email: String, amount: f64, active: bool,
             tags: Vec<String>, address: Addr, created_at: String, score: u64 }
fn main() {
    let mode = std::env::args().nth(1).expect("mode");
    let path = std::env::args().nth(2).expect("path");
    let out = match mode.as_str() {
        "parse" => {
            let t = Instant::now();
            let bytes = std::fs::read(&path).unwrap();
            let v: Value = serde_json::from_slice(&bytes).unwrap();
            let arr = v.as_array().unwrap();
            let sum: f64 = arr.iter().map(|o| o["amount"].as_f64().unwrap()).sum();
            serde_json::json!({"count": arr.len(), "sum": sum, "elapsed_ms": t.elapsed().as_secs_f64()*1000.0})
        }
        "typed" => {
            let t = Instant::now();
            let bytes = std::fs::read(&path).unwrap();
            let v: Vec<Rec> = serde_json::from_slice(&bytes).unwrap();
            let sum: f64 = v.iter().map(|o| o.amount).sum();
            serde_json::json!({"count": v.len(), "sum": sum, "elapsed_ms": t.elapsed().as_secs_f64()*1000.0})
        }
        "generate" => {
            let bytes = std::fs::read(&path).unwrap();
            let v: Value = serde_json::from_slice(&bytes).unwrap();
            let t = Instant::now();
            let s = serde_json::to_vec(&v).unwrap();
            let ms = t.elapsed().as_secs_f64()*1000.0;
            serde_json::json!({"bytes": s.len(), "elapsed_ms": ms})
        }
        _ => panic!("mode"),
    };
    println!("{}", out);
}
