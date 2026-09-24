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
