#!/usr/bin/env python3
"""Fragt den Status der Zingelistrasse (Weggis) ab und schreibt ihn in status.json.

Laeuft per GitHub Actions alle 5 Minuten. Die Webseite zeigt nur den aktuellen
Zustand; der Verlauf entsteht, indem jede Abfrage in status.json nachgefuehrt
wird (Zustandsabschnitte statt Einzelmesswerte, damit die Datei klein bleibt).

    python collect.py pfad/zu/status.json
"""

import html
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

SOURCE_URL = "https://weggis.info.geoprevent.com/"
TZ = ZoneInfo("Europe/Zurich")
GAP_LIMIT = timedelta(minutes=45)  # GitHub-Zeitplaene verspaeten sich oft
MAX_ERRORS = 50

WEEKDAYS = {"montag": 0, "dienstag": 1, "mittwoch": 2, "donnerstag": 3,
            "freitag": 4, "samstag": 5, "sonntag": 6}
MONTHS = {"januar": 1, "jänner": 1, "februar": 2, "märz": 3, "maerz": 3,
          "april": 4, "mai": 5, "juni": 6, "juli": 7, "august": 8,
          "september": 9, "oktober": 10, "november": 11, "dezember": 12}


# --------------------------------------------------------------------------
# Abfrage und Auswertung der Webseite
# --------------------------------------------------------------------------

def fetch_page(url=SOURCE_URL, timeout=30):
    req = urllib.request.Request(url, headers={
        "User-Agent": "WeggisMonitor/1.0 (Statusaufzeichnung)",
        "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _text(fragment):
    return html.unescape(re.sub(r"<[^>]+>", "", fragment or "")).strip()


def parse_since(text, now):
    """Wandelt 'Seit heute um 05:00' / 'Seit letzten Montag um 09:58' /
    'Seit 12.10.2026 um 08:15' in einen Zeitpunkt (Schweizer Zeit) um."""
    if not text:
        return None
    t = text.lower()
    times = re.findall(r"\b(\d{1,2}):(\d{2})\b", t)
    hh, mm = (int(times[-1][0]), int(times[-1][1])) if times else (0, 0)

    day = None
    if "vorgestern" in t:
        day = now.date() - timedelta(days=2)
    elif "gestern" in t:
        day = now.date() - timedelta(days=1)
    elif "heute" in t:
        day = now.date()
    else:
        d = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{2,4})?", t)
        if d:
            year = int(d.group(3)) if d.group(3) else now.year
            if year < 100:
                year += 2000
            try:
                day = datetime(year, int(d.group(2)), int(d.group(1))).date()
            except ValueError:
                day = None
        if day is None:
            d = re.search(r"(\d{1,2})\.\s*([a-zäöü]+)\s*(\d{4})?", t)
            if d and d.group(2) in MONTHS:
                year = int(d.group(3)) if d.group(3) else now.year
                try:
                    day = datetime(year, MONTHS[d.group(2)], int(d.group(1))).date()
                except ValueError:
                    day = None
        if day is None:
            for name, wd in WEEKDAYS.items():
                if name in t:
                    if re.search(r"letzte[nmr]?\s", t):
                        # 'letzten Montag' = Montag der vorherigen Kalenderwoche
                        monday = now.date() - timedelta(days=now.weekday())
                        day = monday - timedelta(days=7 - wd)
                    else:
                        delta = (now.weekday() - wd) % 7 or 7
                        day = now.date() - timedelta(days=delta)
                    break
    if day is None:
        return None
    result = datetime(day.year, day.month, day.day, hh, mm, tzinfo=TZ)
    # Datum ohne Jahr, das in der Zukunft laege, gehoert ins Vorjahr
    if result > now + timedelta(minutes=5) and not re.search(r"\d{4}", t):
        result = result.replace(year=result.year - 1)
    return result


def parse_status(page, now):
    """Extrahiert Ampel und Gefahrenstufe aus dem HTML."""
    data = {"ampel_color": None, "ampel_text": None, "ampel_since_raw": None,
            "stufe": None, "stufe_since_raw": None}
    for b in re.findall(r'<div class="block">(.*?)</div>', page, re.S):
        label = re.search(r'class="block-label"[^>]*>(.*?)</span>', b, re.S)
        label = _text(label.group(1)).lower() if label else ""
        since = re.search(r'class="date-tag"[^>]*>(.*?)</span>', b, re.S)
        since = _text(since.group(1)) if since else None
        if "ampel" in label:
            c = re.search(r'traffic-circle[^>]*background:\s*([^;"]+)', b)
            s = re.search(r'class="status-text"[^>]*>(.*?)</span>', b, re.S)
            data["ampel_color"] = c.group(1).strip().upper() if c else None
            data["ampel_text"] = _text(s.group(1)) if s else None
            data["ampel_since_raw"] = since
        elif "gefahr" in label:
            n = re.search(r'class="danger-number"[^>]*>(.*?)</span>', b, re.S)
            val = _text(n.group(1)) if n else None
            data["stufe"] = int(val) if val and val.lstrip("-").isdigit() else None
            data["stufe_since_raw"] = since
    if data["ampel_text"] is None and data["stufe"] is None:
        raise ValueError("Status konnte nicht aus der Webseite gelesen werden "
                         "(Seitenaufbau geaendert?)")
    data["ampel_since"] = parse_since(data["ampel_since_raw"], now)
    data["stufe_since"] = parse_since(data["stufe_since_raw"], now)
    return data


# --------------------------------------------------------------------------
# Nachfuehren von status.json
# --------------------------------------------------------------------------

def iso(dt):
    return dt.isoformat(timespec="seconds")


def load_state(path):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)  # bewusst ohne try: kaputte Datei nie ueberschreiben
    return {"source": SOURCE_URL, "first_poll": None, "last_poll": None,
            "last_ok": None, "polls_ok": 0, "polls_total": 0, "current": None,
            "ampel": [], "stufe": [], "coverage": [], "errors": []}


def add_segment(segments, key, now, since, prev_ok, extra):
    """Fuehrt die Zustandsabschnitte nach.

    Startzeit eines Abschnitts: 'Seit'-Angabe der Webseite, aber nie vor der
    letzten Abfrage, die noch den vorherigen Zustand zeigte ('floor').
    Gleicher Zustand mit einer 'Seit'-Angabe nach der letzten Abfrage bedeutet,
    dass der Zustand zwischenzeitlich unterbrochen war -> neuer Abschnitt."""
    cur = segments[-1] if segments else None
    floor = datetime.fromisoformat(prev_ok) if prev_ok and cur else None
    since = since if since and since <= now else None
    if cur and cur["key"] == key:
        if not (since and floor and since > floor):
            # Beginn des laufenden Abschnitts anhand der Webseite praezisieren
            cur_floor = cur.get("floor")
            if since and since < datetime.fromisoformat(cur["start"]) and \
                    (cur_floor is None or since >= datetime.fromisoformat(cur_floor)):
                cur["start"] = iso(since)
            return
    start = max(since or now, floor) if floor else (since or now)
    segments.append({"key": key, "start": iso(start),
                     "floor": iso(floor) if floor else None, **extra})


def update(state, data, now):
    prev_ok = state["last_ok"]
    add_segment(state["ampel"], f'{data["ampel_color"]}|{data["ampel_text"]}',
                now, data["ampel_since"], prev_ok,
                {"color": data["ampel_color"], "text": data["ampel_text"]})
    add_segment(state["stufe"], str(data["stufe"]), now, data["stufe_since"],
                prev_ok, {"value": data["stufe"]})
    cov = state["coverage"]
    if cov and now - datetime.fromisoformat(cov[-1][1]) <= GAP_LIMIT:
        cov[-1][1] = iso(now)
    else:
        cov.append([iso(now), iso(now)])
    state["last_ok"] = iso(now)
    state["polls_ok"] += 1
    state["current"] = {k: data[k] for k in ("ampel_color", "ampel_text",
                        "ampel_since_raw", "stufe", "stufe_since_raw")}


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "status.json"
    state = load_state(path)
    now = datetime.now(TZ).replace(microsecond=0)
    state["first_poll"] = state["first_poll"] or iso(now)
    state["last_poll"] = iso(now)
    state["polls_total"] += 1
    try:
        data = parse_status(fetch_page(), now)
        update(state, data, now)
        print(f"{now:%d.%m.%Y %H:%M} {data['ampel_text']} | Gefahrenstufe {data['stufe']}")
    except Exception as exc:  # Fehler festhalten, Workflow aber nicht scheitern lassen
        state["errors"] = (state["errors"] + [{"ts": iso(now), "error": str(exc)[:300]}])[-MAX_ERRORS:]
        print(f"FEHLER: {exc}")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


if __name__ == "__main__":
    main()
