"""Shared CostOptimizer360 dashboard assets and standalone HTML builder.

The canonical browser assets live in ``lambda/web`` so the Lambda export, cloud
frontend, and local frontend all use the same renderer and visual system.
"""

from datetime import datetime, timezone
from html import escape
from pathlib import Path


_ASSET_DIR = Path(__file__).with_name("web")
DASHBOARD_CSS = (_ASSET_DIR / "dashboard.css").read_text(encoding="utf-8")
DASHBOARD_JS = (_ASSET_DIR / "dashboard.js").read_text(encoding="utf-8")


def build_standalone_html(data_json, client_name):
    """Return a self-contained, dependency-free HTML results dashboard."""
    safe_client = escape(client_name or "Client", quote=True)
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Keep embedded JSON inside its script element even when recommendation data
    # contains hostile HTML/script characters. JSON.parse restores these escapes.
    safe_data = (
        data_json.replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )

    return (
        "<!doctype html><html lang=\"en\"><head>"
        "<meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<meta name=\"theme-color\" content=\"#071a2b\">"
        "<title>CostOptimizer360 · " + safe_client + "</title>"
        "<style>"
        ":root{color-scheme:light}*{box-sizing:border-box}body{margin:0;min-width:320px;padding:32px;"
        "color:#162635;background:radial-gradient(circle at 8% 0%,rgba(22,131,232,.08),transparent 30rem),#f3f6f9;"
        "font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}"
        ".report-shell{width:min(1440px,100%);margin:auto}.report-head{display:flex;align-items:center;justify-content:space-between;"
        "gap:24px;margin-bottom:24px;padding:24px 26px;color:#fff;border-radius:18px;background:linear-gradient(145deg,#071a2b,#103b5d);"
        "box-shadow:0 18px 35px rgba(7,26,43,.14)}.report-brand{display:flex;align-items:center;gap:13px}.report-mark{width:44px;height:44px;"
        "display:grid;place-items:center;border:1px solid rgba(255,255,255,.16);border-radius:13px;background:rgba(22,131,232,.18);font-weight:800}"
        ".report-head h1{margin:0;font-size:1.35rem;letter-spacing:-.03em}.report-head p{margin:4px 0 0;color:#b8cfdf;font-size:.75rem}"
        ".report-meta{text-align:right;color:#b8cfdf;font-size:.7rem}.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;"
        "clip:rect(0,0,0,0);white-space:nowrap;border:0}@media(max-width:620px){body{padding:14px}.report-head{align-items:flex-start;flex-direction:column;"
        "padding:20px}.report-meta{text-align:left}}@media print{body{padding:0;background:#fff}.report-head{box-shadow:none}}"
        + DASHBOARD_CSS
        + "</style></head><body><main class=\"report-shell\"><header class=\"report-head\"><div class=\"report-brand\">"
        "<span class=\"report-mark\">C360</span><div><h1>CostOptimizer360 · AWS cost optimization</h1><p>" + safe_client + "</p></div></div>"
        "<div class=\"report-meta\">Generated " + generated + "<br>Read-only assessment · Validate before implementation</div></header>"
        "<div id=\"dashboard\"></div></main><script>const DATA=" + safe_data + ";</script><script>"
        + DASHBOARD_JS
        + "</script><script>window.addEventListener('DOMContentLoaded',function(){CostOpt360.renderDashboard(DATA,'dashboard');});</script></body></html>"
    )
