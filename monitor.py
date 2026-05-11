"""
Monitor multiple Dofus servers on leskamas.com.

For each configured target, alerts when the Morocco (Dhs/M) price falls
within the given [min, max] range. State per server is tracked in
state.json so it only emails when a server *enters* its range
(plus a daily reminder while still in range).

Environment variables required (set as GitHub Actions secrets):
    GMAIL_USER           sending Gmail address
    GMAIL_APP_PASSWORD   16-character Gmail App Password (not normal password)
    GMAIL_RECIPIENT      email address to receive alerts
"""
from __future__ import annotations

import json
import os
import re
import smtplib
import sys
from datetime import datetime, timezone
from email.mime.text import MIMEText
from pathlib import Path

from curl_cffi import requests
from bs4 import BeautifulSoup

# ---------- Config ----------
URL = "https://www.leskamas.com/en-gb/sell-kamas.html"

# Each target: server name (as shown on the site), min Dhs/M, max Dhs/M
# max=999 means "no upper bound" — alert for any price at or above min.
TARGETS = [
    {"server": "Imagiro",  "min": 6.5,  "max": 999},
    {"server": "TalKasha", "min": 6.0,  "max": 999},
    {"server": "Dakal",    "min": 12.0, "max": 999},
]

REMINDER_HOURS = 24          # Re-send while still in range, at most every N hours
STATE_FILE = Path("state.json")
TIMEOUT_SECONDS = 30
# ----------------------------


def fetch_all_prices() -> dict:
    """Return {server_name: {"price": float, "status": str}} for every row."""
    resp = requests.get(URL, impersonate="chrome120", timeout=TIMEOUT_SECONDS)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    result: dict = {}
    for row in soup.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 7:
            continue
        name = cells[0].get_text(strip=True)
        dhs_text = cells[4].get_text(strip=True)
        site_status = cells[6].get_text(strip=True)
        m = re.search(r"([\d]+(?:[.,]\d+)?)", dhs_text)
        if not m:
            continue
        try:
            price = float(m.group(1).replace(",", "."))
        except ValueError:
            continue
        result[name] = {"price": price, "status": site_status}
    return result


def load_state() -> dict:
    if STATE_FILE.exists():
        data = json.loads(STATE_FILE.read_text())
        if "servers" in data:
            return data
    return {"servers": {}, "last_checked_iso": None}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n")


def send_email(subject: str, body: str) -> None:
    sender = os.environ["GMAIL_USER"]
    password = os.environ["GMAIL_APP_PASSWORD"]
    recipient = os.environ["GMAIL_RECIPIENT"]

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient

    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=TIMEOUT_SECONDS) as smtp:
        smtp.login(sender, password)
        smtp.send_message(msg)


def build_and_send(alerts: list, now: datetime) -> None:
    if len(alerts) == 1:
        a = alerts[0]
        subject = (
            f"{a['server']} kamas at {a['price']} Dhs/M "
            f"(target {a['min']}-{a['max']})"
        )
    else:
        parts = [f"{a['server']} {a['price']}" for a in alerts]
        subject = "Kamas alerts: " + ", ".join(parts) + " Dhs/M"

    lines = [f"Checked at: {now.isoformat()}", ""]
    for a in alerts:
        lines.append(f"[{a['server']}] {a['reason']}")
        lines.append(f"  Price:        {a['price']} Dhs/M")
        lines.append(f"  Target range: {a['min']}-{a['max']} Dhs/M")
        lines.append(f"  Site status:  {a['site_status']}")
        lines.append("")
    lines.append(f"Source: {URL}")
    send_email(subject, "\n".join(lines))


def main() -> None:
    now = datetime.now(timezone.utc)
    prices = fetch_all_prices()
    state = load_state()

    alerts: list = []

    for target in TARGETS:
        server = target["server"]
        lo, hi = target["min"], target["max"]

        if server not in prices:
            print(f"WARNING: {server} not found on page (skipping)")
            continue

        price = prices[server]["price"]
        site_status = prices[server]["status"]

        if lo <= price <= hi:
            status = "in_range"
        elif price > hi:
            status = "above_range"
        else:
            status = "below_range"

        prev = state["servers"].get(server, {})
        prev_status = prev.get("last_status", "unknown")
        last_alert_iso = prev.get("last_alert_iso")

        print(
            f"  {server}: {price} Dhs/M [{site_status}] "
            f"target {lo}-{hi} -> {status}"
        )

        should_alert = False
        reason = ""
        if status == "in_range":
            if prev_status != "in_range":
                should_alert = True
                reason = f"entered target range ({prev_status} -> in_range)"
            elif last_alert_iso:
                hours = (now - datetime.fromisoformat(last_alert_iso)).total_seconds() / 3600
                if hours >= REMINDER_HOURS:
                    should_alert = True
                    reason = f"still in range ({hours:.1f}h since last alert)"

        if should_alert:
            alerts.append({
                "server": server,
                "price": price,
                "site_status": site_status,
                "min": lo,
                "max": hi,
                "reason": reason,
            })

        state["servers"][server] = {
            "last_status": status,
            "last_price": price,
            "last_site_status": site_status,
            "last_alert_iso": now.isoformat() if should_alert else last_alert_iso,
            "last_checked_iso": now.isoformat(),
        }

    if alerts:
        build_and_send(alerts, now)
        print(f"Sent email covering {len(alerts)} server(s).")
    else:
        print("No alerts needed.")

    state["last_checked_iso"] = now.isoformat()
    save_state(state)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
