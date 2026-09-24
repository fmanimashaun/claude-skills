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
