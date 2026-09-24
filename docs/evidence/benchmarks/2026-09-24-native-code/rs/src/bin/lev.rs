// All-pairs Levenshtein over the word list (2,000 x 2,000), single thread; sum of distances.
use std::time::Instant;
fn lev(a: &[u8], b: &[u8], row: &mut Vec<usize>) -> usize {
    row.clear(); row.extend(0..=b.len());
    for (i, &ca) in a.iter().enumerate() {
        let mut prev = row[0]; row[0] = i + 1;
        for (j, &cb) in b.iter().enumerate() {
            let cur = row[j + 1];
            let cost = if ca == cb { 0 } else { 1 };
            row[j + 1] = (row[j] + 1).min(cur + 1).min(prev + cost);
            prev = cur;
        }
    }
    row[b.len()]
}
fn main() {
    let path = std::env::args().nth(1).expect("path");
    let t = Instant::now();
    let text = std::fs::read_to_string(&path).unwrap();
    let words: Vec<&[u8]> = text.lines().map(|l| l.as_bytes()).collect();
    let mut row = Vec::with_capacity(32);
    let mut total: u64 = 0;
    for a in &words { for b in &words { total += lev(a, b, &mut row) as u64; } }
    println!("{}", serde_json::json!({"pairs": words.len()*words.len(), "total": total, "elapsed_ms": t.elapsed().as_secs_f64()*1000.0}));
}
