"""Render local, evidence-based portfolio graphics with Playwright."""
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "assets"

STYLE = """
*{box-sizing:border-box}body{margin:0;background:#091522;color:#eaf4f5;font-family:'Segoe UI',Arial,sans-serif}
.canvas{width:1600px;height:900px;padding:72px 82px;background:radial-gradient(circle at 86% 13%,#173c4d 0,#091522 45%)}
.eyebrow{color:#66dfcf;letter-spacing:4px;font-size:19px;font-weight:700;margin-bottom:18px}
h1{font-size:56px;line-height:1.08;margin:0 0 18px;font-weight:750;letter-spacing:-1.8px}
.sub{font-size:23px;color:#a9c0c7;line-height:1.45;margin:0}
.panel{background:#12293a;border:1px solid #285164;border-radius:22px;box-shadow:0 16px 32px #00121d55}
.small{font-size:17px;color:#9dbac3}.label{font-size:20px;color:#65dfcd;font-weight:700;letter-spacing:.5px}
.footer{position:absolute;bottom:44px;left:82px;color:#86a9b4;font-size:17px}
"""

OVERVIEW = """
<div class="canvas">
  <div class="eyebrow">PUBLIC WEB DATA · PORTFOLIO SCENARIO</div>
  <h1>From public pages to<br>usable change records</h1>
  <p class="sub">A bounded collection pipeline with two source paths and one clear output.</p>
  <div class="flow">
    <div class="panel step"><div class="number">01</div><div class="label">Public demo pages</div><p>Book listings<br>Quote listings</p></div>
    <div class="arrow">→</div>
    <div class="panel step paths"><div class="number">02</div><div class="label">Collect & parse</div><p><b>Static HTML</b> · httpx<br><b>Rendered JS</b> · Playwright</p></div>
    <div class="arrow">→</div>
    <div class="panel step"><div class="number">03</div><div class="label">Clean & verify</div><p>Normalize · validate<br>Deduplicate</p></div>
    <div class="arrow">→</div>
    <div class="panel step"><div class="number">04</div><div class="label">Store & compare</div><p>SQLite snapshot<br>Four change classes</p></div>
    <div class="arrow">→</div>
    <div class="panel step"><div class="number">05</div><div class="label">Deliver</div><p>Current CSV / JSON<br>Changes + run summary</p></div>
  </div>
  <div class="facts">
    <div class="fact"><strong>2</strong><span>collection methods</span></div>
    <div class="fact"><strong>CSV</strong><span>current data + change history</span></div>
    <div class="fact"><strong>JSON</strong><span>records + collection status</span></div>
  </div>
  <div class="footer">Public practice sites · fixed page scope · incomplete collection preserves prior records</div>
</div>
<style>
.flow{display:flex;align-items:center;gap:12px;margin-top:72px}
.step{height:245px;flex:1;padding:27px 22px}.step p{font-size:18px;line-height:1.62;color:#d6e5e9;margin:28px 0 0}.step b{color:white}
.number{font-size:18px;color:#86a9b4;margin-bottom:22px}.arrow{font-size:38px;color:#63ddcc;flex:none}
.paths{border-color:#62d9c7;background:#153648}.facts{display:flex;gap:18px;margin-top:48px}
.fact{width:33.33%;padding:20px 26px;background:#0e2231;border-radius:16px;border:1px solid #22465a;display:flex;align-items:baseline;gap:17px}
.fact strong{color:#6be0d0;font-size:42px}.fact span{color:#c6d9dd;font-size:18px}
</style>
"""

CHANGES = """
<div class="canvas">
  <div class="eyebrow">DETERMINISTIC FIXTURE DEMONSTRATION</div>
  <h1>See exactly what changed</h1>
  <p class="sub">Two local fixture runs. No live-site change or customer dashboard is implied.</p>
  <div class="comparison">
    <div class="panel run"><div class="runhead">RUN 1 <span>initial snapshot</span></div>
      <div class="record"><b>Alpha Book</b><span>£12.30</span></div>
      <div class="record"><b>Beta Book</b><span>£20.00</span></div>
      <div class="record"><b>Example Writer quote</b><span>same text</span></div>
    </div>
    <div class="bigarrow">→</div>
    <div class="panel run"><div class="runhead">RUN 2 <span>compared snapshot</span></div>
      <div class="record changed"><b>Alpha Book</b><span>£13.30 · price changed</span></div>
      <div class="record new"><b>Gamma Book</b><span>£3.45 · added</span></div>
      <div class="record"><b>Example Writer quote</b><span>unchanged</span></div>
      <div class="removed">Beta Book absent from the complete fixture scope</div>
    </div>
  </div>
  <div class="metrics">
    <div class="metric new"><strong>1</strong><span>NEW</span></div>
    <div class="metric changed"><strong>1</strong><span>CHANGED</span></div>
    <div class="metric"><strong>1</strong><span>UNCHANGED</span></div>
    <div class="metric removedmetric"><strong>1</strong><span>REMOVED</span></div>
  </div>
  <div class="footer">Fixture-derived CSV and JSON are included in docs/demo/ · removed rows keep their prior snapshot</div>
</div>
<style>
.comparison{display:flex;gap:26px;align-items:center;margin-top:56px}.run{width:670px;height:338px;padding:28px 32px}
.runhead{font-weight:800;color:#6be0d0;font-size:24px;letter-spacing:1px;margin-bottom:20px}.runhead span{font-weight:400;color:#a8c0c7;font-size:18px;margin-left:16px;letter-spacing:0}
.record{background:#0b1e2d;border:1px solid #2b4b5d;border-radius:12px;padding:14px 18px;margin-top:11px;display:flex;justify-content:space-between;align-items:center;font-size:19px}
.record span{color:#b5cbd1;font-size:17px}.record.changed{border-color:#e5ab62}.record.new{border-color:#64d8c0}
.removed{margin-top:12px;color:#ef9c9c;font-size:17px}.bigarrow{font-size:46px;color:#67ddcc}
.metrics{display:flex;gap:18px;margin-top:45px}.metric{flex:1;background:#12293a;border:1px solid #355465;border-radius:16px;padding:20px 26px;display:flex;align-items:baseline;gap:18px}
.metric strong{font-size:47px;color:#dbeaf0}.metric span{font-size:19px;letter-spacing:1px;color:#dbeaf0;font-weight:700}
.metric.new strong{color:#6be0d0}.metric.changed strong{color:#f5bf78}.metric.removedmetric strong{color:#ef9c9c}
</style>
"""


def render(name: str, body: str, page) -> None:
    page.set_content("<html><head><meta charset='utf-8'><style>" + STYLE + "</style></head><body>" + body + "</body></html>")
    page.screenshot(path=str(ASSETS / name), full_page=False, animations="disabled")


if __name__ == "__main__":
    ASSETS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1600, "height": 900}, device_scale_factor=1)
            render("pipeline-overview.png", OVERVIEW, page)
            render("change-detection-proof.png", CHANGES, page)
        finally:
            browser.close()
    print("Rendered two local proof images")
