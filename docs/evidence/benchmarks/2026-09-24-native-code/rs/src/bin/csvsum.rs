// Parse the CSV with headers and sum the `amount` column.
use std::time::Instant;
fn main() {
    let path = std::env::args().nth(1).expect("path");
    // "rows" mode: hand every row back to Ruby as JSON (what an import that inserts records needs).
    if std::env::args().nth(2).as_deref() == Some("rows") {
        let t = Instant::now();
        let mut rdr = csv::Reader::from_path(&path).unwrap();
        let rows: Vec<Vec<String>> = rdr.records().map(|r| r.unwrap().iter().map(String::from).collect()).collect();
        let body = serde_json::to_string(&rows).unwrap();
        let ms = t.elapsed().as_secs_f64() * 1000.0;
        println!("{{\"elapsed_ms\":{},\"rows\":{}}}", ms, body);
        return;
    }
    let t = Instant::now();
    let mut rdr = csv::Reader::from_path(&path).unwrap();
    let idx = rdr.headers().unwrap().iter().position(|h| h == "amount").unwrap();
    let (mut sum, mut rows) = (0f64, 0u64);
    for rec in rdr.records() {
        let rec = rec.unwrap();
        sum += rec[idx].parse::<f64>().unwrap();
        rows += 1;
    }
    let ms = t.elapsed().as_secs_f64() * 1000.0;
    println!("{}", serde_json::json!({"rows": rows, "sum": sum, "elapsed_ms": ms}));
}
