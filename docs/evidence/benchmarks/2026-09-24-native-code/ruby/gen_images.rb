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
