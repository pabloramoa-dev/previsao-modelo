"""Atendimento de texto no Instagram para os perfis da rede."""
import hashlib
import hmac
import json
import os
import re
import sqlite3
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from threading import BoundedSemaphore, Lock
from time import monotonic
from zoneinfo import ZoneInfo

import requests
from flask import Flask, abort, request


@dataclass(frozen=True)
class Account:
    instagram_id: str
    access_token: str
    app_secret: str
    verify_token: str


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 256 * 1024
CATALOG = json.loads(Path(__file__).with_name("catalogos.json").read_text())
ACCOUNTS = {handle: Account(**data) for handle, data in
            json.loads(os.getenv("INSTAGRAM_CONTAS", "{}")).items()}
if ACCOUNTS.keys() - CATALOG.keys():
    raise ValueError("Perfil sem catálogo")
if len({a.instagram_id for a in ACCOUNTS.values()}) != len(ACCOUNTS):
    raise ValueError("IDs de Instagram duplicados")

HANDLES_BY_ID = {a.instagram_id: handle for handle, a in ACCOUNTS.items()}

TIME_ZONE = ZoneInfo("America/Sao_Paulo")
GRAPH = "https://graph.instagram.com/" + os.getenv("META_GRAPH_VERSION", "v27.0")
EXECUTOR = ThreadPoolExecutor(max_workers=4)
QUEUE_SLOTS = BoundedSemaphore(64)
DATABASE = os.getenv("ATENDIMENTO_DB", "/tmp/atendimento-rede.sqlite3")
with sqlite3.connect(DATABASE) as db:
    db.execute("""CREATE TABLE IF NOT EXISTS eventos (
        perfil TEXT, tipo TEXT, id TEXT, status INTEGER,
        criado TEXT DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (perfil, tipo, id))""")
    db.execute("DELETE FROM eventos WHERE criado < datetime('now', '-8 days')")

FORECAST_LOCKS = [Lock() for _ in range(32)]


def normalize(text):
    plain = unicodedata.normalize("NFKD", text.casefold())
    ascii_text = "".join(char for char in plain if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z0-9]+", ascii_text))


def places(handle, text):
    query = " " + normalize(re.sub(r"@[\w.]+", "", text)) + " "
    matches = []
    for name, lat, lon, aliases in CATALOG[handle]:
        for alias in {normalize(label) for label in [name, *aliases]} - {""}:
            for match in re.finditer(r"(?<= )" + re.escape(alias) + r"(?= )", query):
                matches.append((match.start(), match.end(), (name, lat, lon)))
    # Sobradinho II deve ganhar de Sobradinho na mesma posição.
    return sorted({location for start, end, location in matches if not any(
        other_start <= start and end <= other_end
        and (other_start, other_end) != (start, end)
        for other_start, other_end, _ in matches)})


@lru_cache(maxsize=512)
def forecast_points(lat, lon, cache_period):
    response = requests.get(
        "https://api.met.no/weatherapi/locationforecast/2.0/compact",
        params={"lat": lat, "lon": lon},
        headers={"User-Agent": os.environ["MET_USER_AGENT"]},
        timeout=8,
    )
    response.raise_for_status()
    return response.json()["properties"]["timeseries"]


def forecast(location):
    name, lat, lon = location
    lat, lon = (int(value * 10000) / 10000 for value in (lat, lon))
    with FORECAST_LOCKS[hash((lat, lon)) % len(FORECAST_LOCKS)]:
        points = forecast_points(lat, lon, int(monotonic() // 10800))
    days = {}
    for point in points:
        local = datetime.fromisoformat(point["time"]).astimezone(TIME_ZONE)
        days.setdefault(local.date(), []).append(point["data"])
    today = datetime.now(TIME_ZONE).date()
    lines = [f"📍 {name}"]
    for label, day in (("Hoje", today), ("Amanhã", today + timedelta(days=1))):
        samples = days.get(day)
        if not samples:
            lines.append(f"{label} ({day:%d/%m}): previsão indisponível.")
            continue
        temperatures = [item["instant"]["details"]["air_temperature"] for item in samples]
        rain = [item.get("next_1_hours", {}).get("details", {}).get("precipitation_amount")
                for item in samples]
        if any(value and value > 0 for value in rain):
            rain_text = ", com chuva prevista"
        elif all(value is not None for value in rain):
            rain_text = ", sem chuva nas horas disponíveis"
        else:
            rain_text = ""
        lines.append(f"{label} ({day:%d/%m}): {min(temperatures):.0f} a "
                     f"{max(temperatures):.0f} °C nas horas previstas{rain_text}.")
    return "\n".join([*lines, "Fonte: MET Norway."])


def graph_post(account, path, payload):
    response = requests.post(
        GRAPH + "/" + path,
        headers={"Authorization": "Bearer " + account.access_token},
        json=payload,
        timeout=10,
    )
    response.raise_for_status()


def process(handle, kind, event_id, recipient, message):
    account = ACCOUNTS[handle]
    options = places(handle, message)
    if not options and kind == "comments":
        return
    key = (handle, kind, event_id)
    with sqlite3.connect(DATABASE) as db:
        db.execute("DELETE FROM eventos WHERE criado < datetime('now', '-8 days')")
        claim = db.execute("INSERT OR IGNORE INTO eventos (perfil,tipo,id,status) VALUES (?,?,?,0)", key)
        if not claim.rowcount:
            return
    try:
        if len(options) == 1:
            try:
                answer = forecast(options[0])
            except (requests.RequestException, KeyError, ValueError):
                app.logger.warning("Previsão indisponível para %s", handle)
                answer = "A previsão está temporariamente indisponível. Tente mais tarde."
        elif options:
            answer = "Qual destes locais você quer consultar? " + ", ".join(p[0] for p in options)
        else:
            answer = "Me diga o nome de uma cidade ou bairro da cobertura deste perfil."
        graph_post(account, f"{account.instagram_id}/messages",
                   {"recipient": recipient, "message": {"text": answer[:1000]}})
        if kind == "comments":
            graph_post(account, f"{event_id}/replies",
                       {"message": "Enviei os detalhes no direct. ☔"})
        with sqlite3.connect(DATABASE) as db:
            db.execute("UPDATE eventos SET status=1 WHERE perfil=? AND tipo=? AND id=?", key)
    except requests.RequestException as error:
        status = error.response.status_code if error.response is not None else None
        app.logger.warning("Falha no atendimento de %s (%s), HTTP %s", handle, kind, status)


def enqueue(handle, kind, event_id, recipient, message):
    if not message or not event_id.isascii() or not re.fullmatch(r"[\w.:-]{1,200}", event_id):
        return True
    if not QUEUE_SLOTS.acquire(blocking=False):
        return False
    future = EXECUTOR.submit(process, handle, kind, event_id, recipient, message)
    future.add_done_callback(finished)
    return True


def finished(future):
    QUEUE_SLOTS.release()
    if future.exception():
        app.logger.error("Erro interno ao processar evento", exc_info=future.exception())


@app.get("/ping")
def ping():
    return {"ok": True, "perfis_configurados": len(ACCOUNTS)}


@app.route("/webhook/<handle>", methods=["GET", "POST"])
def webhook(handle):
    account = ACCOUNTS.get(handle)
    if account is None:
        abort(404)
    if request.method == "GET":
        if (request.args.get("hub.mode") != "subscribe" or not hmac.compare_digest(
                request.args.get("hub.verify_token", ""), account.verify_token)):
            abort(403)
        return request.args.get("hub.challenge", "")

    expected = "sha256=" + hmac.new(account.app_secret.encode(), request.get_data(),
                                    hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, request.headers.get("X-Hub-Signature-256", "")):
        abort(403)
    payload = request.get_json()
    if payload.get("object") != "instagram":
        return "", 204
    for entry in payload.get("entry", []):
        target = HANDLES_BY_ID.get(str(entry.get("id", "")))
        if target is None or ACCOUNTS[target].app_secret != account.app_secret:
            continue
        instagram_id = ACCOUNTS[target].instagram_id
        for change in entry.get("changes", []):
            value = change.get("value", {})
            author = value.get("from") or {}
            if (change.get("field") == "comments" and author
                    and str(author.get("id", "")) != instagram_id
                    and (author.get("username") or "").casefold() != target):
                event_id = str(value.get("id", ""))
                if not enqueue(target, "comments", event_id, {"comment_id": event_id},
                               value.get("text", "")):
                    abort(503)
        for item in entry.get("messaging", []):
            message = item.get("message") or {}
            sender = str(item.get("sender", {}).get("id", ""))
            if (sender and sender != instagram_id and not message.get("is_echo")
                    and not message.get("is_self")):
                if not enqueue(target, "messages", str(message.get("mid", "")),
                               {"id": sender}, message.get("text", "")):
                    abort(503)
    return "", 204
