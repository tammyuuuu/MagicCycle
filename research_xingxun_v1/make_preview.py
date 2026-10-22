# -*- coding: utf-8 -*-
"""生成第五轮的独立预览页（只用于测试，不参与网站发布）。"""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent
SITE = ROOT.parent
OUT = ROOT / "out_site_test"
OUT.mkdir(exist_ok=True)

partial = (SITE / "archive" / "legacy_ui" / "templates" / "_portfolio_v1.html").read_text(encoding="utf-8")
data = (SITE / "docs" / "portfolio_data.json").read_text(encoding="utf-8")
html = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>星循 V1 预览</title>
<style>
body{{font-family:-apple-system,Segoe UI,Microsoft YaHei,sans-serif;background:#f5f6f8;color:#22303f;margin:0;padding:16px}}
.card{{background:#fff;border:1px solid #e6e9ee;border-radius:12px;padding:16px;margin:0 0 14px;max-width:900px}}
h2{{font-size:17px;margin:0 0 8px}}
.muted{{color:#6b7684;font-size:13px}}
label{{display:block;font-size:13px;margin:6px 0}}
input{{padding:7px;border:1px solid #d6dbe3;border-radius:7px;font:inherit}}
.grid{{display:grid;gap:10px}} .g2{{grid-template-columns:1fr 1fr}}
.btn{{padding:8px 14px;border:1px solid #345a8b;background:#345a8b;color:#fff;border-radius:7px;cursor:pointer}}
.btn.gray{{background:#fff;color:#345a8b}}
[role=status]{{font-size:13px;min-height:18px}}
</style></head><body>
<div class="page-section" id="invest-plan">{partial}</div>
<script>window.PORTFOLIO_DATA = {data};</script>
<script src="../../portfolio_store.js"></script>
<script src="../../capital_pool.js"></script>
<script src="../../archive/legacy_ui/portfolio_v1.js"></script>
</body></html>"""
(OUT / "preview.html").write_text(html, encoding="utf-8")
print("saved", OUT / "preview.html")
