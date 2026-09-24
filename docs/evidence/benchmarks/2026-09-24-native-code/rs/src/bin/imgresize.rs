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
