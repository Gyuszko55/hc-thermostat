"""hcd's page (Home Assistant add-on ingress, or any browser on the LAN): the decision and the shadow comparison."""

from __future__ import annotations

import html
import json
from typing import Any, Callable

from aiohttp import web

PAGE = """<!doctype html><html lang="hu"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>hcd</title><style>
:root{--bg:#f5f6f4;--fg:#1b1f1d;--soft:#56605b;--line:#cdd3ce;--panel:#e9ece8;--ok:#3d7547;--bad:#b4462a}
@media (prefers-color-scheme:dark){:root{--bg:#141816;--fg:#e8ece9;--soft:#a5b0aa;--line:#34403a;--panel:#1d2320;--ok:#84c48f;--bad:#e98a68}}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,sans-serif;padding:16px}
h1{font-size:1.2rem;margin:0 0 .2rem}.muted{color:var(--soft)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;margin:12px 0}
.tile{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:10px}
.tile b{display:block;font-size:1.3rem;font-variant-numeric:tabular-nums}
table{border-collapse:collapse;width:100%;font-size:.85rem}th,td{border:1px solid var(--line);padding:4px 6px;text-align:left}
th{background:var(--panel)}.scroll{overflow-x:auto}.bad{color:var(--bad)}.ok{color:var(--ok)}
</style></head><body>__BODY__<script>setTimeout(()=>location.reload(),60000)</script></body></html>"""


def _fmt(v: Any) -> str:
    if v is None:
        return "–"
    if isinstance(v, float):
        return f"{v:.1f}"
    return html.escape(str(v))


def render(status: dict[str, Any]) -> str:
    d = status.get("decision") or {}
    today = status.get("today") or {}
    tiles = [
        ("Döntés (hcd)", d.get("reason")), ("Kimenet (hcd)", "BE" if d.get("output") else "KI"),
        ("Cél", d.get("target")), ("Bent", d.get("indoor")), ("Kint", d.get("outdoor")),
        ("Döntés egyezés ma", f"{today.get('reason_agree_pct', '–')} %"),
        ("Kimenet egyezés ma", f"{today.get('output_agree_pct', '–')} %"),
        ("Égés ma hcd / HA", f"{_fmt(today.get('hcd_burn_min'))} / {_fmt(today.get('ha_burn_min'))} perc"),
    ]
    body = [f"<h1>hcd – {html.escape(status.get('name', ''))}</h1>",
            f"<div class='muted'>v{html.escape(status.get('version', ''))} · hc-core {html.escape(status.get('core', ''))} · "
            f"árnyék mód (nem kapcsol) · {html.escape(d.get('text_hu') or '')}</div>",
            "<div class='grid'>" + "".join(f"<div class='tile'><span class='muted'>{html.escape(k)}</span><b>{_fmt(v)}</b></div>"
                                           for k, v in tiles) + "</div>"]
    feeds = status.get("feeds") or {}
    body.append("<p class='muted'>Források: " + ", ".join(f"{html.escape(k)}: {'✔' if v else '✖'}" for k, v in feeds.items())
                + (f" · nem támogatott beállítás: {html.escape(', '.join(status['unsupported']))}" if status.get("unsupported") else "")
                + "</p>")
    rows = status.get("recent") or []
    body.append("<h2>Utolsó lépések</h2><div class='scroll'><table><tr><th>idő (UTC)</th><th>hcd</th><th>HA</th>"
                "<th>hcd ki/be</th><th>HA relé</th><th>hcd igény</th><th>HA igény</th><th>cél hcd/HA</th></tr>")
    for r in rows[:40]:
        same = r["hcd_reason"] == r["ha_reason"] and r["hcd_output"] == r["ha_relay"]
        body.append(f"<tr class='{'' if same else 'bad'}'><td>{_fmt(r['ts'][11:19])}</td><td>{_fmt(r['hcd_reason'])}</td>"
                    f"<td>{_fmt(r['ha_reason'])}</td><td>{_fmt(r['hcd_output'])}</td><td>{_fmt(r['ha_relay'])}</td>"
                    f"<td>{_fmt(r['hcd_demand'])}</td><td>{_fmt(r['ha_demand'])}</td>"
                    f"<td>{_fmt(r['hcd_target'])} / {_fmt(r['ha_target'])}</td></tr>")
    body.append("</table></div>")
    days = status.get("days") or []
    if days:
        body.append("<h2>Napok</h2><div class='scroll'><table><tr><th>nap</th><th>lépés</th><th>döntés egyezés</th>"
                    "<th>kimenet egyezés</th><th>égés hcd</th><th>égés HA</th><th>eltérés</th></tr>")
        for s in days:
            body.append(f"<tr><td>{_fmt(s['day'])}</td><td>{_fmt(s.get('steps'))}</td><td>{_fmt(s.get('reason_agree_pct'))} %</td>"
                        f"<td>{_fmt(s.get('output_agree_pct'))} %</td><td>{_fmt(s.get('hcd_burn_min'))}</td>"
                        f"<td>{_fmt(s.get('ha_burn_min'))}</td><td>{_fmt(s.get('burn_diff_pct'))} %</td></tr>")
        body.append("</table></div>")
    return PAGE.replace("__BODY__", "\n".join(body))


def _ip(text: str) -> str | None:
    """An address in one form (an IPv4-mapped IPv6 address as IPv4); None when it is not an address."""
    import ipaddress
    try:
        ip = ipaddress.ip_address(text.split("%", 1)[0])
    except ValueError:
        return None
    mapped = getattr(ip, "ipv4_mapped", None)
    return str(mapped or ip)


def make_app(status: Callable[[], dict[str, Any]],
             disagreements: Callable[[str | None], list[dict[str, Any]]] | None = None,
             allow: list[str] | None = None) -> web.Application:
    """allow (0.1.3): when given, only these remote addresses get an answer (the add-on: the Supervisor's ingress
    proxy, 172.30.32.2) – the page has no login of its own."""
    async def page(_request):
        return web.Response(text=render(status()), content_type="text/html")

    async def api(_request):
        return web.Response(text=json.dumps(status(), default=str), content_type="application/json")

    async def diff(request):
        """The steps where hcd and the integration differ (reason or output): `?day=YYYY-MM-DD`, today by default."""
        day = request.query.get("day")
        rows = disagreements(day) if disagreements else []
        return web.Response(text=json.dumps(rows, default=str), content_type="application/json")

    allowed = [str(a).strip() for a in (allow or ()) if str(a).strip()]
    resolved: dict[str, tuple[float | None, set[str]]] = {}  # a host name -> (when, its addresses)

    async def addresses() -> set[str]:
        """The allowed addresses; a host name (another add-on, e.g. `local-xyz`) is resolved, kept for 5 minutes –
        a container's address may change when it restarts."""
        import asyncio
        import socket
        import time
        out: set[str] = set()
        loop = asyncio.get_running_loop()
        for a in allowed:
            if _ip(a) is not None:
                out.add(_ip(a))
                continue
            when, ips = resolved.get(a, (None, set()))
            # never resolved yet -> resolve now (monotonic() is the uptime: it can be below 300 s after a boot)
            if when is None or time.monotonic() - when > 300:
                try:
                    infos = await loop.getaddrinfo(a, None, type=socket.SOCK_STREAM)
                    ips = {_ip(i[4][0]) for i in infos} - {None}
                except OSError:
                    ips = set()
                resolved[a] = (time.monotonic(), ips)
            out |= ips
        return out

    @web.middleware
    async def only_allowed(request, handler):
        if allowed and _ip(request.remote or "") not in await addresses():
            return web.Response(status=403, text="forbidden")
        return await handler(request)

    app = web.Application(middlewares=[only_allowed])
    app.router.add_get("/", page)
    app.router.add_get("/api/status", api)
    app.router.add_get("/api/disagreements", diff)
    return app
