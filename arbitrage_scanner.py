import os
import requests
import time
from datetime import datetime
import pytz
import logging
from telegram import Bot

# --- Config ---
ODDS_API_KEY = os.getenv("ODDS_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

EXCHANGES = {"betfair_ex_uk", "smarkets", "matchbook"}
API_BASE = "https://api.the-odds-api.com/v4"
BOOKMAKER_BACK_THRESHOLD = 1.01
SCAN_INTERVAL = 600
TIMEZONE = pytz.utc

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# --- Telegram ---
bot = Bot(token=TELEGRAM_TOKEN)


def get_all_sports():
    url = f"{API_BASE}/sports?apiKey={ODDS_API_KEY}"
    resp = requests.get(url)
    resp.raise_for_status()
    return [s["key"] for s in resp.json() if s["active"]]


def get_events(sport_key):
    url = f"{API_BASE}/sports/{sport_key}/odds"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "uk",
        "markets": "h2h",
        "oddsFormat": "decimal",
        "dateFormat": "iso",
    }
    try:
        resp = requests.get(url, params=params)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logging.warning(f"❌ Could not fetch odds for {sport_key}: {e}")
        return []


def scan_events():
    logging.info("🔎 Scanning for arbitrage opportunities...")
    sports = get_all_sports()
    for sport_key in sports:
        events = get_events(sport_key)
        for event in events:
            match_title = f"{event['home_team']} vs {event['away_team']}"
            lay_odds = {}
            back_odds = {}

            for bookmaker in event.get("bookmakers", []):
                bookie_key = bookmaker["key"]
                markets = {m["key"]: m for m in bookmaker.get("markets", [])}

                if "h2h" not in markets:
                    continue

                for outcome in markets["h2h"]["outcomes"]:
                    name, price = outcome["name"], float(outcome["price"])
                    if name not in back_odds or price > back_odds[name][0]:
                        back_odds[name] = (price, bookmaker["title"])

                if bookie_key in EXCHANGES and "h2h_lay" in markets:
                    for outcome in markets["h2h_lay"]["outcomes"]:
                        name, price = outcome["name"], float(outcome["price"])
                        if name not in lay_odds or price < lay_odds[name][0]:
                            lay_odds[name] = (price, bookmaker["title"])

            for runner in set(back_odds) & set(lay_odds):
                back_price, back_bookie = back_odds[runner]
                lay_price, lay_bookie = lay_odds[runner]

                if back_price > lay_price:
                    profit = (back_price - lay_price) / lay_price * 100
                    message = (
                        f"💰 Arbitrage Opportunity!\n\n"
                        f"🏟️ Match: {match_title}\n"
                        f"🔹 Runner: {runner}\n"
                        f"🔙 Back @ {back_price:.2f} ({back_bookie})\n"
                        f"🔄 Lay @ {lay_price:.2f} ({lay_bookie})\n"
                        f"📈 Profit Margin: {profit:.2f}%"
                    )
                    logging.info(message)
                    try:
                        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
                    except Exception as e:
                        logging.warning(f"Telegram send failed: {e}")


def main_loop():
    while True:
        try:
            scan_events()
        except Exception as e:
            logging.error(f"Scan failed: {e}")
        time.sleep(SCAN_INTERVAL)


if __name__ == "__main__":
    main_loop()
