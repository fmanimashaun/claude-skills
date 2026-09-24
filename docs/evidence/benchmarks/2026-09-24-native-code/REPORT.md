# Ruby (YJIT) vs Rust (--release, spawned via IO.popen + JSON) — measured

Machine: Apple M2 Pro, 10 cores, 16 GB. Ruby 4.0.6 `--yjit` (the harness aborts if YJIT is off), rustc/cargo 1.97.1,
libvips 8.18.4 + ruby-vips 2.3.0, prawn 2.4.0, json 2.21.2, csv 3.3.6. Date: 2026-09-24.
Crates: csv 1.4.0, serde_json 1.0.151, serde 1.0.229, image 0.25.10 (jpeg only; zune-jpeg decoder), rayon 1.12.0, pdf-writer 0.15.0.

**Method.** Each cell: one discarded warm-up run in the same process (warms YJIT and the page cache), then 3 timed runs
(5 for the small-heap spawn cell), `GC.start` before each. Numbers are **median (min–max)** in ms.
"End to end" = wall time in Ruby around `IO.popen([bin, *args], &:read)` + `JSON.parse` of the output.
"Inner" = the `elapsed_ms` the Rust binary measures itself (file read included, process start excluded).
Each workload ran in its own `ruby --yjit` process, one after another, nothing else heavy running.

## Results

| # | Workload | Ruby YJIT median | Rust inner | Rust end to end | Ratio Ruby / Rust e2e |
|---|---|---|---|---|---|
| 1 | CSV 1M rows, sum `amount` | 3952 (3865–5077) | 225 (222–251) | 229 (226–256) | **17.3x faster in Rust** |
| 1b | CSV, Rust returns **all 1M rows** as JSON, Ruby parses them | 3952 | 651 (640–756) | 1590 (1453–1695) | 2.5x |
| 2a | JSON parse 200 MB → generic tree (`serde_json::Value`) | 1385 (1380–1410) | 1101 (1002–1780) | 1477 (1363–2391) | **0.94x — no gain** |
| 2a' | JSON parse → typed Rust struct | 1385 | 517 (517–527) | 619 (619–641) | 2.2x |
| 2b | JSON generate 200 MB | 277 (266–294) `JSON.generate`; 280 `to_json` | 607 (599–668) | n/a (see note) | **0.46x — Ruby faster** |
| 3 | 200 JPEG 4000×3000 → 800×600, sequential | 9868 (9746–10644) ruby-vips | 20781 (20609–21287) | 20787 (20617–21301) | **0.47x — Ruby faster** |
| 3' | same, parallel (10 Ruby threads / rayon 10 threads) | 1721 (1645–1771) | 3541 (3518–3641) | 3561 (3541–3668) | **0.48x — Ruby faster** |
| 4 | Levenshtein 2,000×2,000 (4M pairs), 1 thread | 9007 (9005–9027) | 348 (345–349) | 353 (350–353) | **25.5x** |
| 5 | 500-page text PDF | 5638 (5602–5652) prawn | 4.7 (4.5–4.8) pdf-writer | 9.6 (9.3–10.0) | ~590x (not like for like, see note) |
| 6 | Spawn only: 1000 × noop printing `{}` | — | — | 3165 (2955–3390) per 1000 | **3.2 ms per call** |
| 6' | Spawn only, parent holding 1,173 MB RSS (parsed JSON) | — | — | 17290 (13703–17339) per 1000 | **17.3 ms per call** |

Correctness cross-checks (identical in both languages): CSV rows 1,000,000, sum 499901800.31; JSON count 800,000,
sum 3997383098.38, regenerated size 200,179,803 bytes; Levenshtein total 31,679,700; PDF 500 pages; 200 images at 800×600.

An earlier full image run gave ruby-vips sequential 8871 (8865–8889), Rust sequential 20722, Rust rayon 3156; the table uses
the second run because it is the only one that contains the threaded ruby-vips cell. The ratios agree (0.43x / 2.8x).

## Notes that change how to read a row

- **1 vs 1b.** Summing inside Rust is the best case. A real import has to get records back into Ruby (to insert them);
  shipping the rows over stdout as JSON and parsing them costs ~940 ms of the 1590 ms, and cuts the win from 17x to 2.5x.
- **2a.** Ruby's `json` 2.21 C parser is as fast as serde_json into a generic `Value` (a BTreeMap per object). Rust only
  wins when it parses into a typed struct — and the result then still has to come back to Ruby, which is JSON again.
- **2b.** Generating JSON from Ruby objects through a bridge is structurally impossible to win: the Ruby objects must first be
  serialised to hand them to Rust, which is the work itself. Even in isolation serde_json (607 ms) is slower than Ruby's
  generator (277 ms). The 2042 ms e2e cell includes the binary re-reading and parsing the 200 MB file and is not a generate time.
- **3.** ruby-vips `thumbnail` uses libvips shrink-on-load (JPEG DCT scaling) and is internally multithreaded; the Rust
  `image` crate decodes the full 12 MP and resizes with `FilterType::Triangle`. The work in Ruby is already native code.
  Rust would have to call libvips too to compete; that gives no reason to leave Ruby. Outputs differ: vips uses Lanczos3, Rust Triangle.
- **5.** prawn does font metrics, text wrapping and flow per line; the pdf-writer binary places 50 fixed lines per page in
  the standard Helvetica font with no layout. The ratio shows that prawn's layout costs ~11 ms per page, not that a Rust port
  of the same features would be 590x faster. It built with no system dependencies.
- **6 / 6'.** The per-call cost of the bridge grows with the parent's memory: 3.2 ms from a small process, 17.3 ms from one
  holding 1.17 GB (a typical Rails worker size). [Inferred] because Ruby's `IO.popen` forks and the fork has to copy the
  parent's page tables; not verified with a profiler. At 17 ms per call the bridge only makes sense for batch work of
  hundreds of ms or more, never per request or per record.

## Verdict

Rust pays off for **pure-Ruby CPU loops** (Levenshtein 25x, CSV parse 17x) *when the result coming back is small*.
It does not pay off where Ruby already calls C (JSON parse/generate, libvips images), and a big result coming back over
stdout+JSON eats most of the win (CSV rows: 2.5x). The spawn cost (3–17 ms per call) rules out per-request use.

## What could not be measured

- **Rust-backed gem column (osv for CSV): failed to install.** `gem install osv` into the local `GEM_HOME` (osv 0.5.2): the
  prebuilt `arm64-darwin` gem carries bundles only for Ruby 3.2/3.3/3.4 (`required_ruby_version < 3.5.dev`), so RubyGems
  built from source, and magnus 0.7.1 fails against Ruby 4.0 headers: `error[E0609]: no field typed_flag on type &rb_sys::RTypedData`
  and `error[E0308]` on `rb_fiber_raise`. Bumping to magnus 0.8 / serde_magnus 0.10 in a copy (`osv-src/`) left 4 compile errors in
  osv's own code, so no clean install; not measured. No other Rust-backed gem was tried for the other workloads.
- crates.io and rubygems.org were both reachable.
- Side effect to be aware of: the failed osv source build ran before `CARGO_HOME` was pointed at this folder, so cargo
  downloaded its crates into `~/.cargo/registry` (a download cache; nothing installed). Every build after that used `cargo-home/` here.

## Commands

```sh
B=<this folder>
export GEM_HOME=$B/gems CARGO_HOME=$B/cargo-home
ruby --yjit ruby/gen_data.rb data               # CSV 112 MB, JSON 200 MB, word list, PDF text (seeded Random)
ruby ruby/gen_images.rb data/images 200         # 200 deterministic 4000x3000 JPEGs (678 MB)
(cd rs && cargo build --release)
for w in spawn_bigheap csv json_parse json_generate pdf image lev; do ruby --yjit ruby/bench.rb $w 3; done > results.jsonl
ruby --yjit ruby/bench.rb spawn 5
ruby --yjit ruby/bench.rb csv_rows 3
ruby --yjit ruby/bench.rb image 3 > results_image2.jsonl
gem install osv --no-document                   # fails, see above
```

Raw results: `results.jsonl`, `results_image2.jsonl` (the spawn 5-run and csv_rows cells were printed to the terminal:
spawn runs 3057.9, 3164.8, 3390.4, 3219.3, 2955.0 ms; csv_rows e2e 1694.8, 1452.7, 1589.7, inner 756.4, 651.3, 639.5 ms).
Data SHA-1s: `data/SHA1SUMS`.

## Source files

### `ruby/gen_data.rb`

```ruby
# Deterministic data generator. Usage: ruby gen_data.rb DATA_DIR
require "json"
dir = ARGV.fetch(0)
CITIES = %w[Lagos London Berlin Paris Tokyo Austin Toronto Nairobi Madrid Oslo]
STATUS = %w[active pending closed archived]
WORDS = %w[alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima mike november oscar papa]

# 1. CSV: 1,000,000 rows x 10 columns
r = Random.new(42)
File.open(File.join(dir, "import.csv"), "w") do |f|
  f << "id,name,email,amount,qty,city,status,created_at,note,score\n"
  buf = +""
  1.upto(1_000_000) do |i|
    name = "#{WORDS[r.rand(16)]} #{WORDS[r.rand(16)]}"
    note = Array.new(3) { WORDS[r.rand(16)] }.join(" ")
    note = "\"#{note}, #{WORDS[r.rand(16)]}\"" if i % 10 == 0 # some quoted fields with commas
    buf << "#{i},#{name},user#{i}@example.com,#{format('%.2f', r.rand * 1000)},#{r.rand(100)}," \
           "#{CITIES[r.rand(10)]},#{STATUS[r.rand(4)]},2026-0#{1 + r.rand(9)}-1#{r.rand(10)}T12:34:56Z," \
           "#{note},#{r.rand(100_000)}\n"
    if i % 10_000 == 0 then f << buf; buf = +"" end
  end
  f << buf
end

# 2. JSON: array of objects, ~200 MB
r = Random.new(7)
File.open(File.join(dir, "data.json"), "w") do |f|
  f << "["
  n = 800_000
  n.times do |i|
    obj = { "id" => i, "uuid" => format("%08x-%04x-%04x", r.rand(2**32), r.rand(2**16), r.rand(2**16)),
            "name" => "#{WORDS[r.rand(16)]} #{WORDS[r.rand(16)]}", "email" => "user#{i}@example.com",
            "amount" => (r.rand * 10_000).round(2), "active" => r.rand(2) == 1,
            "tags" => Array.new(3) { WORDS[r.rand(16)] },
            "address" => { "city" => CITIES[r.rand(10)], "zip" => format("%05d", r.rand(100_000)) },
            "created_at" => "2026-0#{1 + r.rand(9)}-1#{r.rand(10)}T12:34:56Z", "score" => r.rand(1000) }
    f << "," unless i.zero?
    f << JSON.generate(obj)
  end
  f << "]"
end

# 4. Levenshtein corpus: 2,000 short strings
r = Random.new(99)
alpha = ("a".."z").to_a
File.write(File.join(dir, "words.txt"), Array.new(2000) { Array.new(6 + r.rand(7)) { alpha[r.rand(8)] }.join }.join("\n") + "\n")

# 5. PDF text: 500 pages x 50 lines
r = Random.new(5)
File.write(File.join(dir, "pdf_lines.txt"), Array.new(25_000) { |i| "Line #{i + 1}: " + Array.new(10) { WORDS[r.rand(16)] }.join(" ") }.join("\n") + "\n")
```

### `ruby/gen_images.rb`

```ruby
# Deterministic 4000x3000 JPEGs. Usage: ruby gen_images.rb DIR COUNT
require "vips"
dir, count = ARGV[0], Integer(ARGV[1])
Dir.mkdir(dir) unless Dir.exist?(dir)
count.times do |i|
  x = Vips::Image.xyz(4000, 3000)
  r = (x[0] * (0.05 + i * 0.001)).sin * 100 + 128
  g = (x[1] * (0.03 + i * 0.0007)).cos * 100 + 128
  b = ((x[0] + x[1]) * 0.01 + i).sin * 60 + 128
  n = Vips::Image.gaussnoise(4000, 3000, sigma: 12, mean: 0, seed: i)
  img = Vips::Image.bandjoin([r + n, g + n, b - n]).cast(:uchar)
  img.jpegsave(File.join(dir, format("img_%03d.jpg", i)), Q: 85, strip: true)
end
```

### `ruby/bench.rb`

```ruby
# Usage: ruby --yjit bench.rb WORKLOAD [RUNS]
# Each cell: one discarded warm-up run, then RUNS timed runs; prints one JSON line per cell.
require "json"
require "csv"
require "vips"
require "prawn"
require "fileutils"

ROOT = File.expand_path("..", __dir__)
DATA = File.join(ROOT, "data")
OUT  = File.join(ROOT, "out")
BIN  = File.join(ROOT, "rs/target/release")
W    = ARGV.fetch(0)
RUNS = Integer(ARGV[1] || 3)
abort "YJIT is off" unless defined?(RubyVM::YJIT) && RubyVM::YJIT.enabled?

def now = Process.clock_gettime(Process::CLOCK_MONOTONIC)

# Times the block; the block may return {inner_ms:, check:}.
def cell(name, runs: RUNS)
  GC.start
  yield # warm-up, discarded
  e2e = []; inner = []; check = nil
  runs.times do
    GC.start
    t = now
    r = yield
    e2e << (now - t) * 1000
    inner << r[:inner_ms] if r.is_a?(Hash) && r[:inner_ms]
    check = r.is_a?(Hash) ? r[:check] : r
  end
  stat = ->(a) { s = a.sort; { median: s[s.size / 2], min: s.first, max: s.last, runs: a.map { _1.round(1) } } }
  row = { workload: W, cell: name, e2e_ms: stat.(e2e), check: check }
  row[:inner_ms] = stat.(inner) unless inner.empty?
  puts JSON.generate(row)
  $stdout.flush
end

# The bridge under test: spawn the binary, read its stdout, parse JSON.
def rust(*args)
  out = IO.popen([File.join(BIN, args[0]), *args[1..].map(&:to_s)], &:read)
  raise "rust #{args.inspect} failed: #{$?}" unless $?.success?
  res = JSON.parse(out)
  { inner_ms: res["elapsed_ms"], check: res.except("elapsed_ms") }
end

def lev(a, b, row)
  n = b.size
  j = 0
  while j <= n; row[j] = j; j += 1; end
  i = 0
  while i < a.size
    prev = row[0]; row[0] = i + 1; ca = a[i]; j = 0
    while j < n
      cur = row[j + 1]
      cost = ca == b[j] ? 0 : 1
      v = row[j] + 1
      v = cur + 1 if cur + 1 < v
      v = prev + cost if prev + cost < v
      row[j + 1] = v
      prev = cur; j += 1
    end
    i += 1
  end
  row[n]
end

case W
when "csv"
  path = File.join(DATA, "import.csv")
  cell("ruby CSV.foreach headers:true") do
    sum = 0.0; rows = 0
    CSV.foreach(path, headers: true) { |row| sum += row["amount"].to_f; rows += 1 }
    { check: { rows: rows, sum: sum } }
  end
  cell("rust csv crate via popen") { rust("csvsum", path) }
when "csv_rows"
  # Realistic bridge for an import: Rust parses, returns ALL rows as JSON, Ruby sums from them.
  path = File.join(DATA, "import.csv")
  cell("rust csv -> all rows as JSON -> Ruby JSON.parse") do
    r = rust("csvsum", path, "rows"); rows = r[:check]["rows"]
    { inner_ms: r[:inner_ms], check: { rows: rows.size, sum: rows.sum { _1[3].to_f } } }
  end
when "json_parse"
  path = File.join(DATA, "data.json")
  cell("ruby JSON.parse(File.read)") do
    arr = JSON.parse(File.read(path)); { check: { count: arr.size, sum: arr.sum { _1["amount"] } } }
  end
  cell("rust serde_json Value via popen") { rust("jsonbench", "parse", path) }
  cell("rust serde_json typed struct via popen") { rust("jsonbench", "typed", path) }
when "json_generate"
  path = File.join(DATA, "data.json")
  obj = JSON.parse(File.read(path))
  cell("ruby JSON.generate") { { check: { bytes: JSON.generate(obj).bytesize } } }
  cell("ruby obj.to_json") { { check: { bytes: obj.to_json.bytesize } } }
  cell("rust serde_json to_vec (inner only meaningful) via popen") { rust("jsonbench", "generate", path) }
when "image"
  files = Dir[File.join(DATA, "images/*.jpg")].sort
  dst = File.join(OUT, "img_rb"); FileUtils.mkdir_p(dst)
  cell("ruby-vips thumbnail, sequential loop") do
    files.each { |f| Vips::Image.thumbnail(f, 800, height: 600).write_to_file(File.join(dst, File.basename(f)), Q: 80) }
    { check: { files: files.size } }
  end
  cell("ruby-vips thumbnail, 10 Ruby threads") do
    q = Queue.new; files.each { q << _1 }; q.close
    Array.new(10) { Thread.new { while (f = q.pop); Vips::Image.thumbnail(f, 800, height: 600).write_to_file(File.join(dst, File.basename(f)), Q: 80); end } }.each(&:join)
    { check: { files: files.size } }
  end
  rdst = File.join(OUT, "img_rs"); FileUtils.mkdir_p(rdst)
  cell("rust image crate, sequential, via popen") { rust("imgresize", "seq", File.join(DATA, "images"), rdst) }
  cell("rust image crate, rayon 10 threads, via popen") { rust("imgresize", "par", File.join(DATA, "images"), rdst) }
when "lev"
  path = File.join(DATA, "words.txt")
  cell("ruby pure Levenshtein") do
    words = File.readlines(path, chomp: true).map(&:bytes)
    row = []; total = 0
    words.each { |a| words.each { |b| total += lev(a, b, row) } }
    { check: { pairs: words.size**2, total: total } }
  end
  cell("rust Levenshtein via popen") { rust("lev", path) }
when "pdf"
  path = File.join(DATA, "pdf_lines.txt")
  cell("ruby prawn 2.4 text") do
    lines = File.readlines(path, chomp: true)
    pdf = Prawn::Document.new(page_size: "A4", margin: 36)
    pdf.font("Helvetica", size: 10)
    lines.each_slice(50).with_index do |chunk, i|
      pdf.start_new_page unless i.zero?
      chunk.each { |l| pdf.text l, leading: 1 }
    end
    file = File.join(OUT, "rb.pdf"); pdf.render_file(file)
    { check: { pages: pdf.page_count, bytes: File.size(file) } }
  end
  cell("rust pdf-writer via popen") { rust("pdfgen", path, File.join(OUT, "rs.pdf")) }
when "spawn"
  noop = File.join(BIN, "noop")
  cell("1000 x IO.popen(noop) + JSON.parse") do
    1000.times { JSON.parse(IO.popen([noop], &:read)) }
    { check: "1000 calls" }
  end
when "spawn_bigheap"
  # Same bridge, but from a process holding the parsed 200 MB JSON (~ a large Rails worker's heap).
  big = JSON.parse(File.read(File.join(DATA, "data.json")))
  noop = File.join(BIN, "noop")
  cell("1000 x IO.popen(noop) + JSON.parse, parent RSS #{`ps -o rss= -p #{$$}`.to_i / 1024} MB") do
    1000.times { JSON.parse(IO.popen([noop], &:read)) }
    { check: big.size }
  end
else abort "unknown workload #{W}"
end
```

### `rs/Cargo.toml`

```toml
[package]
name = "rs"
version = "0.1.0"
edition = "2024"

[dependencies]
csv = "1.4.0"
image = { version = "0.25.10", default-features = false, features = ["jpeg"] }
pdf-writer = "0.15.0"
rayon = "1.12.0"
serde = { version = "1.0.229", features = ["derive"] }
serde_json = "1.0.151"
```

### `rs/src/bin/noop.rs`

```rust
fn main() { println!("{{}}"); }
```

### `rs/src/bin/csvsum.rs`

```rust
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
```

### `rs/src/bin/jsonbench.rs`

```rust
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
```

### `rs/src/bin/imgresize.rs`

```rust
// Resize every JPEG in DIR to 800x600 into OUT. mode: seq | par (rayon, all cores).
use image::{codecs::jpeg::JpegEncoder, imageops::FilterType};
use rayon::prelude::*;
use std::{fs, io::BufWriter, path::PathBuf, time::Instant};
fn one(p: &PathBuf, out: &str) {
    let img = image::open(p).unwrap();
    let small = img.resize_exact(800, 600, FilterType::Triangle).to_rgb8();
    let f = BufWriter::new(fs::File::create(PathBuf::from(out).join(p.file_name().unwrap())).unwrap());
    JpegEncoder::new_with_quality(f, 80).encode_image(&small).unwrap();
}
fn main() {
    let a: Vec<String> = std::env::args().collect();
    let (mode, dir, out) = (&a[1], &a[2], &a[3]);
    let t = Instant::now();
    let mut files: Vec<PathBuf> = fs::read_dir(dir).unwrap().map(|e| e.unwrap().path())
        .filter(|p| p.extension().map_or(false, |e| e == "jpg")).collect();
    files.sort();
    if mode == "par" { files.par_iter().for_each(|p| one(p, out)); } else { files.iter().for_each(|p| one(p, out)); }
    println!("{}", serde_json::json!({"files": files.len(), "elapsed_ms": t.elapsed().as_secs_f64()*1000.0}));
}
```

### `rs/src/bin/lev.rs`

```rust
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
```

### `rs/src/bin/pdfgen.rs`

```rust
// 500-page text PDF with pdf-writer: 50 lines/page, Helvetica 10pt (standard font, no embedding,
// no wrapping / font metrics — prawn does more work per line than this).
use pdf_writer::{Content, Finish, Name, Pdf, Rect, Ref, Str};
use std::time::Instant;
fn main() {
    let a: Vec<String> = std::env::args().collect();
    let t = Instant::now();
    let text = std::fs::read_to_string(&a[1]).unwrap();
    let lines: Vec<&str> = text.lines().collect();
    let pages: Vec<&[&str]> = lines.chunks(50).collect();
    let mut pdf = Pdf::new();
    let (catalog, tree, font) = (Ref::new(1), Ref::new(2), Ref::new(3));
    let mut next = 4;
    let mut page_ids = vec![];
    pdf.catalog(catalog).pages(tree);
    pdf.type1_font(font).base_font(Name(b"Helvetica"));
    for chunk in &pages {
        let (pid, cid) = (Ref::new(next), Ref::new(next + 1)); next += 2;
        page_ids.push(pid);
        let mut c = Content::new();
        c.begin_text(); c.set_font(Name(b"F1"), 10.0); c.set_leading(14.0); c.next_line(36.0, 800.0);
        for l in chunk.iter() { c.show(Str(l.as_bytes())); c.next_line_using_leading(); }
        c.end_text();
        pdf.stream(cid, &c.finish());
        let mut page = pdf.page(pid);
        page.media_box(Rect::new(0.0, 0.0, 595.0, 842.0)).parent(tree).contents(cid);
        page.resources().fonts().pair(Name(b"F1"), font);
        page.finish();
    }
    let n = page_ids.len();
    pdf.pages(tree).kids(page_ids).count(n as i32);
    let bytes = pdf.finish();
    std::fs::write(&a[2], &bytes).unwrap();
    println!("{}", serde_json::json!({"pages": n, "bytes": bytes.len(), "elapsed_ms": t.elapsed().as_secs_f64()*1000.0}));
}
```
