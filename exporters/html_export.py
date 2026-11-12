"""Автономный HTML-отчёт в тёмной стилистике Lead Hunter.

Никаких CDN, шрифтов из интернета и серверов: файл открывается двойным кликом.
Фильтрация, поиск, сортировка и счётчики работают на встроенном JavaScript.
"""

from __future__ import annotations

import html
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from config import APP_EDITION, APP_NAME, STATUSES, TAGLINE, VERSION
from core.utils import clean_text, fmt_datetime, map_links, normalize_phone
from exporters.common import clean_phone_href, lead_search_text


def _esc(value: Any) -> str:
    return html.escape(clean_text(str(value or "")))


def _phone_html(phone: str) -> str:
    clean = clean_text(phone)
    if not clean:
        return '<span class="muted">—</span>'
    href = clean_phone_href(clean)
    return f'<a class="phone" href="tel:{html.escape(href)}">{_esc(clean)}</a>'


def _email_html(email: str) -> str:
    clean = clean_text(email)
    if not clean:
        return ""
    return (
        f'<a class="mail" href="mailto:{html.escape(clean)}">{_esc(clean)}</a>'
    )


def _contact_extra(lead: dict[str, Any]) -> str:
    extra = lead.get("extra") or {}
    contacts = extra.get("contacts") or {}
    if not contacts:
        return ""
    parts = []
    for key, value in contacts.items():
        if not value:
            continue
        value = clean_text(str(value))
        if value.startswith("http"):
            parts.append(
                f'<a href="{html.escape(value)}" target="_blank" rel="noopener">{html.escape(key)}</a>'
            )
        else:
            parts.append(f"<span>{html.escape(key)}: {html.escape(value)}</span>")
    return '<div class="socials">' + " · ".join(parts) + "</div>"


def _row(lead: dict[str, Any]) -> str:
    links = map_links(lead)
    city = clean_text(lead.get("city"))
    niche = clean_text(lead.get("niche"))
    status_key = str(lead.get("status") or "new")
    status_label = STATUSES.get(status_key, status_key)
    source = clean_text(lead.get("source"))
    address = clean_text(lead.get("address"))
    website = clean_text(lead.get("website"))
    opening = clean_text(lead.get("opening_hours"))
    phone = clean_text(lead.get("phone"))
    email = clean_text(lead.get("email"))
    name = clean_text(lead.get("name"))
    lead_type = clean_text(lead.get("lead_type"))
    found = fmt_datetime(lead.get("found_at"))
    contact_html = _phone_html(phone) + ("<br>" + _email_html(email) if email else "")
    meta_parts = []
    if lead_type:
        meta_parts.append(f'<span class="type">{_esc(lead_type)}</span>')
    if opening:
        meta_parts.append(f'<span class="hours">{_esc(opening)}</span>')
    meta = " ".join(meta_parts)
    links_html = (
        f'<a class="map-link" href="{html.escape(links["yandex"])}" target="_blank" rel="noopener">Яндекс</a>'
        f'<a class="map-link" href="{html.escape(links["2gis"])}" target="_blank" rel="noopener">2ГИС</a>'
    )
    if website:
        href = website if website.startswith(("http://", "https://")) else "https://" + website
        links_html += (
            f'<a class="map-link site" href="{html.escape(href)}" target="_blank" rel="noopener">Сайт</a>'
        )
    return f"""
        <tr data-text="{html.escape(lead_search_text(lead))}"
            data-city="{_esc(city)}" data-niche="{_esc(niche)}"
            data-status="{_esc(status_key)}" data-phone="{_esc(normalize_phone(phone))}"
            data-sort-name="{_esc(name.lower())}" data-sort-city="{_esc(city.lower())}"
            data-sort-niche="{_esc(niche.lower())}" data-sort-status="{_esc(status_key)}"
            data-sort-found="{html.escape(str(lead.get('found_at') or ''))}">
          <td class="name-cell">
            <div class="lead-name">{_esc(name)}</div>
            <div class="lead-meta">{meta}{_contact_extra(lead)}</div>
          </td>
          <td class="contacts">{contact_html}</td>
          <td>{_esc(city)}</td>
          <td><span class="niche">{_esc(niche)}</span></td>
          <td class="address">{_esc(address) or '<span class="muted">—</span>'}</td>
          <td><span class="source-badge source-{_esc(source.split('/')[0].strip().lower().replace(' ', '-'))}">{_esc(source)}</span></td>
          <td><span class="status status-{_esc(status_key)}">{_esc(status_label)}</span></td>
          <td class="date">{_esc(found)}</td>
          <td class="links">{links_html}</td>
        </tr>
        """


def _stat_card(value: int | str, label: str, accent: bool = False) -> str:
    css = "stat accent" if accent else "stat"
    return f'<div class="{css}"><div class="stat-value">{_esc(value)}</div><div class="stat-label">{_esc(label)}</div></div>'


def _build_options(values: Iterable[str]) -> str:
    items = sorted({clean_text(value) for value in values if clean_text(value)})
    return "".join(
        f'<option value="{html.escape(value)}">{html.escape(value)}</option>' for value in items
    )


def export_html(
    leads: Iterable[dict[str, Any]],
    path: str | Path,
    title: str = "Отчёт по лидам",
    subtitle: str = "",
    generated_at: str | None = None,
) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = list(leads)
    total = len(rows)
    with_phone = sum(1 for lead in rows if clean_text(lead.get("phone")))
    with_email = sum(1 for lead in rows if clean_text(lead.get("email")))
    cities = len({clean_text(lead.get("city")) for lead in rows if clean_text(lead.get("city"))})
    niches = len({clean_text(lead.get("niche")) for lead in rows if clean_text(lead.get("niche"))})
    sources = Counter(clean_text(lead.get("source")) for lead in rows if clean_text(lead.get("source")))
    generated = generated_at or datetime.now().astimezone().strftime("%d.%m.%Y %H:%M")
    rows_html = "\n".join(_row(lead) for lead in rows) if rows else ""
    empty_html = (
        ""
        if rows
        else '<div class="empty"><div class="empty-glyph">☠</div>'
        "<h2>Лидов пока нет</h2><p>Выполни поиск в Lead Hunter, чтобы наполнить отчёт.</p></div>"
    )
    source_text = " · ".join(f"{name} — {count}" for name, count in sources.most_common()) or "—"
    city_options = _build_options(clean_text(lead.get("city")) for lead in rows)
    niche_options = _build_options(clean_text(lead.get("niche")) for lead in rows)
    status_options = "".join(
        f'<option value="{key}">{html.escape(label)}</option>'
        for key, label in STATUSES.items()
    )

    document = f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(APP_NAME)} — {html.escape(title)}</title>
<style>
:root {{
  --bg: #08080a;
  --surface: #101014;
  --surface-2: #15151b;
  --graphite: #1c1c23;
  --line: #2a2a33;
  --blood: #7d0a1b;
  --crimson: #c8102e;
  --red: #ff2d46;
  --smoke: #8a8a95;
  --white: #ececf0;
  --green: #79c39a;
  --amber: #e0a95a;
}}
* {{ box-sizing: border-box; }}
html {{ background: var(--bg); }}
body {{
  margin: 0;
  color: var(--white);
  background:
    radial-gradient(1000px 500px at 85% -10%, rgba(200,16,46,.16), transparent 65%),
    radial-gradient(800px 400px at 0% 100%, rgba(125,10,27,.10), transparent 60%),
    var(--bg);
  font-family: "Segoe UI", "Inter", Arial, sans-serif;
  min-height: 100vh;
}}
.shell {{ max-width: 1480px; margin: 0 auto; padding: 28px 24px 60px; }}
header {{
  border: 1px solid var(--line);
  border-left: 3px solid var(--crimson);
  background: linear-gradient(120deg, rgba(200,16,46,.08), transparent 45%), var(--surface);
  padding: 26px 30px;
  display: flex;
  justify-content: space-between;
  gap: 24px;
  align-items: flex-start;
  box-shadow: 0 20px 60px rgba(0,0,0,.35);
}}
.brand-kicker {{ color: var(--red); font: 600 11px/1.4 Consolas, monospace; letter-spacing: .32em; text-transform: uppercase; }}
h1 {{ margin: 8px 0 4px; font: 700 clamp(30px, 5vw, 52px)/1 "Arial Black", Impact, sans-serif; letter-spacing: .06em; }}
h1 span {{ color: var(--red); }}
.edition {{ color: var(--smoke); font: 500 12px/1.4 Consolas, monospace; letter-spacing: .28em; text-transform: uppercase; }}
.tagline {{ margin: 18px 0 0; color: #b9b9c2; font-size: 15px; }}
.subtitle {{ margin: 8px 0 0; color: #6c6c78; font: 11px/1.6 Consolas, monospace; letter-spacing: .06em; }}
.header-right {{ text-align: right; color: var(--smoke); font: 12px/1.7 Consolas, monospace; white-space: nowrap; }}
.header-right b {{ color: var(--white); }}
.rule {{ height: 1px; margin: 22px 0; background: linear-gradient(90deg, var(--crimson), var(--line) 34%, transparent); }}
.stats {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-top: 18px; }}
.stat {{ background: var(--surface); border: 1px solid var(--line); padding: 18px 18px 14px; }}
.stat.accent {{ border-color: rgba(200,16,46,.45); background: linear-gradient(180deg, rgba(200,16,46,.10), var(--surface)); }}
.stat-value {{ font: 700 32px/1 Consolas, monospace; color: var(--white); }}
.stat.accent .stat-value {{ color: var(--red); }}
.stat-label {{ margin-top: 8px; color: var(--smoke); font: 600 10px/1.4 Consolas, monospace; letter-spacing: .18em; text-transform: uppercase; }}
.toolbar {{
  margin: 22px 0 0; padding: 16px;
  border: 1px solid var(--line); background: var(--surface-2);
  display: flex; flex-wrap: wrap; gap: 10px; align-items: center;
}}
.toolbar input[type=search], .toolbar select {{
  background: #0b0b0e; color: var(--white); border: 1px solid var(--line);
  padding: 11px 13px; font: 13px/1.3 Consolas, monospace; outline: none; min-width: 170px;
}}
.toolbar input[type=search] {{ flex: 1 1 280px; }}
.toolbar input:focus, .toolbar select:focus {{ border-color: var(--crimson); box-shadow: 0 0 0 2px rgba(200,16,46,.15); }}
.check {{ display: flex; align-items: center; gap: 8px; color: var(--smoke); font: 12px Consolas, monospace; cursor: pointer; }}
.check input {{ accent-color: var(--crimson); }}
.btn {{
  border: 1px solid var(--line); color: var(--white); background: transparent;
  padding: 10px 14px; cursor: pointer; font: 600 11px/1 Consolas, monospace;
  letter-spacing: .1em; text-transform: uppercase;
}}
.btn:hover {{ border-color: var(--crimson); color: var(--red); }}
.btn.primary {{ background: var(--blood); border-color: var(--blood); }}
.btn.primary:hover {{ background: var(--crimson); color: #fff; }}
.count {{ margin-left: auto; color: var(--smoke); font: 12px Consolas, monospace; }}
.count b {{ color: var(--red); }}
.table-wrap {{ border: 1px solid var(--line); border-top: 0; overflow: auto; max-height: 72vh; background: var(--surface); }}
table {{ width: 100%; border-collapse: collapse; min-width: 1180px; }}
thead th {{
  position: sticky; top: 0; z-index: 2; background: #121217;
  color: var(--smoke); text-align: left; padding: 12px 12px;
  border-bottom: 1px solid var(--line); font: 600 10px/1.3 Consolas, monospace;
  letter-spacing: .14em; text-transform: uppercase; cursor: pointer; white-space: nowrap;
}}
thead th:hover {{ color: var(--red); }}
thead th[data-sort]::after {{ content: " ↕"; color: #4a4a55; }}
tbody tr {{ border-bottom: 1px solid #1d1d24; }}
tbody tr:nth-child(even) {{ background: rgba(255,255,255,.012); }}
tbody tr:hover {{ background: rgba(200,16,46,.055); }}
td {{ padding: 12px; vertical-align: top; font-size: 13px; color: #c7c7cf; }}
.lead-name {{ color: var(--white); font-weight: 700; font-size: 14px; margin-bottom: 4px; }}
.lead-meta {{ color: var(--smoke); font-size: 11px; line-height: 1.6; }}
.type {{ color: var(--red); }}
.hours {{ color: var(--amber); }}
.socials {{ margin-top: 4px; font: 11px Consolas, monospace; }}
.socials a {{ color: var(--red); text-decoration: none; }}
.phone {{ color: var(--red); font: 600 13px Consolas, monospace; text-decoration: none; white-space: nowrap; }}
.phone:hover {{ text-decoration: underline; }}
.mail {{ color: #9cb7d8; font-size: 11px; text-decoration: none; }}
.address {{ max-width: 220px; font-size: 12px; }}
.niche {{ color: #c9c9d3; border: 1px solid #31313b; padding: 2px 7px; font-size: 11px; white-space: nowrap; }}
.source-badge {{ color: #9b9ba6; font: 10px Consolas, monospace; white-space: nowrap; }}
.status {{ display: inline-block; padding: 3px 8px; border: 1px solid var(--line); font: 10px Consolas, monospace; white-space: nowrap; }}
.status-new {{ color: #a8a8b4; border-color: #34343e; }}
.status-contacted {{ color: #6fa9d8; border-color: #27455e; }}
.status-interested {{ color: #e0a95a; border-color: #5c4522; }}
.status-proposal {{ color: #b9a1ec; border-color: #46386a; }}
.status-won {{ color: var(--green); border-color: #2e5741; }}
.status-rejected {{ color: #8b6470; border-color: #4a2a33; }}
.date {{ color: var(--smoke); font: 11px Consolas, monospace; white-space: nowrap; }}
.links {{ white-space: nowrap; }}
.map-link {{ display: inline-block; color: var(--smoke); text-decoration: none; border-bottom: 1px dotted #555; margin-right: 8px; font: 11px Consolas, monospace; }}
.map-link:hover {{ color: var(--red); border-color: var(--red); }}
.muted {{ color: #565660; }}
.empty {{ border: 1px solid var(--line); border-top: 0; padding: 80px 20px; text-align: center; background: var(--surface); }}
.empty-glyph {{ font-size: 52px; color: var(--blood); }}
.empty h2 {{ margin: 12px 0 6px; }}
.empty p {{ color: var(--smoke); }}
footer {{ margin-top: 18px; display: flex; justify-content: space-between; gap: 18px; color: #55555f; font: 10px/1.6 Consolas, monospace; }}
footer b {{ color: #8a8a95; }}
@media (max-width: 900px) {{
  .stats {{ grid-template-columns: repeat(2, 1fr); }}
  header {{ flex-direction: column; }}
  .header-right {{ text-align: left; }}
  .shell {{ padding: 16px 12px 40px; }}
}}
@media print {{
  body {{ background: #fff; color: #111; }}
  header, .stat, .toolbar, .table-wrap {{ background: #fff; border-color: #ccc; }}
  .toolbar, footer .noprint {{ display: none; }}
  .table-wrap {{ max-height: none; overflow: visible; }}
  td, .lead-name, .stat-value {{ color: #111; }}
}}
</style>
</head>
<body>
<div class="shell">
  <header>
    <div>
      <div class="brand-kicker">Local intelligence · lead hunting</div>
      <h1>LEAD <span>HUNTER</span></h1>
      <div class="edition">{APP_EDITION} · v{VERSION}</div>
      <p class="tagline">{html.escape(TAGLINE)}</p>
      {f'<p class="subtitle">{html.escape(subtitle)}</p>' if subtitle else ''}
    </div>
    <div class="header-right">
      <div>ОТЧЁТ: <b>{html.escape(title)}</b></div>
      <div>СОЗДАН: <b>{html.escape(generated)}</b></div>
      <div>ЛИДОВ: <b>{total}</b></div>
      <div>ИСТОЧНИКИ: <b>{html.escape(source_text)}</b></div>
    </div>
  </header>

  <div class="stats">
    {_stat_card(total, "Всего лидов", True)}
    {_stat_card(with_phone, "С телефоном")}
    {_stat_card(with_email, "С email")}
    {_stat_card(cities, "Городов")}
    {_stat_card(niches, "Ниш")}
  </div>

  <div class="toolbar">
    <input id="q" type="search" placeholder="Поиск: название, телефон, адрес, ниша…" autocomplete="off">
    <select id="fCity"><option value="">Все города</option>{city_options}</select>
    <select id="fNiche"><option value="">Все ниши</option>{niche_options}</select>
    <select id="fStatus"><option value="">Все статусы</option>{status_options}</select>
    <label class="check"><input id="fPhone" type="checkbox"> только с телефоном</label>
    <button class="btn" id="reset" type="button">Сброс</button>
    <span class="count">Показано: <b id="visible">{total}</b> / {total}</span>
  </div>

  <div class="table-wrap">
    <table id="leads">
      <thead>
        <tr>
          <th data-sort="name">Название / контакты</th>
          <th>Телефон / email</th>
          <th data-sort="city">Город</th>
          <th data-sort="niche">Ниша</th>
          <th>Адрес</th>
          <th>Источник</th>
          <th data-sort="status">Статус</th>
          <th data-sort="found">Найден</th>
          <th>Ссылки</th>
        </tr>
      </thead>
      <tbody>
        {rows_html}
      </tbody>
    </table>
    {empty_html}
  </div>

  <footer>
    <div>Отчёт создан локально приложением <b>Lead Hunter Local Edition</b>. Для просмотра интернет не требуется.</div>
    <div class="noprint">Данные: OpenStreetMap contributors (ODbL). Ссылки на карты открываются в браузере.</div>
  </footer>
</div>
<script>
(function () {{
  var rows = Array.prototype.slice.call(document.querySelectorAll('#leads tbody tr'));
  var q = document.getElementById('q');
  var fCity = document.getElementById('fCity');
  var fNiche = document.getElementById('fNiche');
  var fStatus = document.getElementById('fStatus');
  var fPhone = document.getElementById('fPhone');
  var visible = document.getElementById('visible');
  var reset = document.getElementById('reset');
  function apply() {{
    var term = (q.value || '').trim().toLowerCase();
    var city = fCity.value, niche = fNiche.value, status = fStatus.value, phone = fPhone.checked;
    var shown = 0;
    rows.forEach(function (row) {{
      var ok = true;
      if (term && (row.getAttribute('data-text') || '').indexOf(term) === -1) ok = false;
      if (city && row.getAttribute('data-city') !== city) ok = false;
      if (niche && row.getAttribute('data-niche') !== niche) ok = false;
      if (status && row.getAttribute('data-status') !== status) ok = false;
      if (phone && !row.getAttribute('data-phone')) ok = false;
      row.style.display = ok ? '' : 'none';
      if (ok) shown++;
    }});
    visible.textContent = shown;
  }}
  [q, fCity, fNiche, fStatus, fPhone].forEach(function (el) {{
    el.addEventListener(el.tagName === 'INPUT' && el.type === 'search' ? 'input' : 'change', apply);
  }});
  q.addEventListener('keydown', function (e) {{ if (e.key === 'Escape') {{ q.value = ''; apply(); }} }});
  reset.addEventListener('click', function () {{
    q.value = ''; fCity.value = ''; fNiche.value = ''; fStatus.value = ''; fPhone.checked = false; apply();
  }});
  var sortState = {{}};
  document.querySelectorAll('th[data-sort]').forEach(function (th) {{
    th.addEventListener('click', function () {{
      var key = th.getAttribute('data-sort');
      var direction = sortState[key] === 'asc' ? 'desc' : 'asc';
      sortState = {{}}; sortState[key] = direction;
      var tbody = document.querySelector('#leads tbody');
      var sorted = rows.slice().sort(function (a, b) {{
        var av = (a.getAttribute('data-sort-' + key) || '').toLowerCase();
        var bv = (b.getAttribute('data-sort-' + key) || '').toLowerCase();
        if (av < bv) return direction === 'asc' ? -1 : 1;
        if (av > bv) return direction === 'asc' ? 1 : -1;
        return 0;
      }});
      sorted.forEach(function (row) {{ tbody.appendChild(row); }});
      rows = sorted;
    }});
  }});
  apply();
}})();
</script>
</body>
</html>
"""
    output.write_text(document, encoding="utf-8")
    return output
