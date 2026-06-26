#!/usr/bin/env python3
"""Post-process the freshly built widget into two fully-offline files:
   output/ufc_skill_explorer.html        -> desktop, no external loads
   output/ufc_skill_explorer_phone.html  -> + mobile CSS, badge, title
Run after build_widget.py (which re-adds the CDN + font links from the template)."""
from pathlib import Path

HERE = Path(__file__).parent
SRC = HERE / "output" / "ufc_skill_explorer.html"
CHARTJS = HERE / "vendor" / "chart.umd.js"

CDN = '<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>'
FONT_LINKS = [
    '<link rel="preconnect" href="https://fonts.googleapis.com">',
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>',
    '<link href="https://fonts.googleapis.com/css2?family=Saira+Condensed:wght@500;600;700&family=Inter:wght@400;500;600&family=Saira:wght@500;600&display=swap" rel="stylesheet">',
]
FONT_SUBS = [
    ('"Saira Condensed",sans-serif', '"Saira Condensed","Helvetica Neue Condensed","Arial Narrow",system-ui,sans-serif'),
    ('"Inter",sans-serif', '"Inter",-apple-system,system-ui,"Segoe UI",sans-serif'),
    ('"Saira",sans-serif', '"Saira",-apple-system,system-ui,sans-serif'),
]

MOBILE_CSS = """
<style id="phone-css">
@media (max-width:760px){
  body{font-size:15px}
  /* iOS Safari auto-zooms when a focused form field is <16px; 16px stops it */
  select,input[type=text],textarea{font-size:16px!important}
  /* safe-area insets so content clears the notch / Dynamic Island / home bar */
  .wrap,main{
    padding-left:max(12px,env(safe-area-inset-left))!important;
    padding-right:max(12px,env(safe-area-inset-right))!important;
  }
  .wrap{padding-bottom:max(48px,env(safe-area-inset-bottom))!important}
  .grid,.cols,.compare{display:block!important}
  .panel,.card,.col{width:auto!important;margin:0 0 14px!important}
  table{font-size:13px}
  h1{font-size:24px}
  .slot{flex-wrap:wrap}
  /* Chart.js (maintainAspectRatio:false) sizes the canvas to fill .chartbox;
     don't force height:auto here or the radar collapses. Just cap width. */
  #radar{max-width:100%!important}
  .chartbox{height:300px}
  /* let any wide blocks scroll instead of forcing the page sideways */
  .tott{overflow-x:auto;-webkit-overflow-scrolling:touch}
}
@media (max-width:400px){
  .chartbox{height:264px}
  .totrow,.tott-h{grid-template-columns:1fr 76px 1fr!important}
}
.phone-badge{display:inline-block;margin:6px 0 0;padding:3px 10px;border-radius:999px;
  background:#c0102b;color:#fff;font:600 12px/1.4 system-ui,sans-serif;letter-spacing:.02em}
</style>
"""
BADGE = '<div class="phone-badge">\U0001F4F1 Phone layout</div>'


def main():
    html = SRC.read_text()
    chart = CHARTJS.read_text()

    # 1. inline Chart.js
    assert CDN in html, "CDN script tag not found — did the template change?"
    html = html.replace(CDN, f"<script>{chart}</script>")
    # 2. drop Google Font links
    for link in FONT_LINKS:
        assert link in html, f"font link not found: {link[:40]}"
        html = html.replace(link, "")
    # 3. system-font fallbacks
    for a, b in FONT_SUBS:
        html = html.replace(a, b)

    assert "cdnjs.cloudflare" not in html and "fonts.google" not in html and "gstatic" not in html
    SRC.write_text(html)
    print(f"desktop offline: {len(html)//1024} KB, 0 external loads")

    # phone variant
    phone = html.replace("</head>", MOBILE_CSS + "</head>", 1)
    phone = phone.replace("<title>UFC Skill Profiles — data-driven</title>",
                          "<title>UFC Skill Profiles — PHONE layout</title>", 1)
    phone = phone.replace("<h1>UFC Skill Profiles</h1>",
                          "<h1>UFC Skill Profiles</h1>" + BADGE, 1)
    (HERE / "output" / "ufc_skill_explorer_phone.html").write_text(phone)
    print(f"phone offline:   {len(phone)//1024} KB")


if __name__ == "__main__":
    main()
