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
