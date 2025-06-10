import requests
import difflib
import time
import os
from datetime import datetime

# Load API keys from environment
ODDS_API_KEY = os.getenv("ODDS_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

MIN_PROFIT_PCT = 1.0
BANKROLL = 100.0

# --- Notification ---
def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Error sending Telegram message: {e}")

send_telegram_message("✅ Telegram alert test from Railway!")

# --- OddsAPI and Smarkets ---
def get_all_sports():
    url = "https://api.the-odds-api.com/v4/sports/"
    resp = requests.get(url, params={"apiKey": ODDS_API_KEY})
    return resp.json() if resp.status_code == 200 else []

def get_oddsapi_data(sport_key):
    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "uk,eu",
        "markets": "h2h,spreads,totals",
        "oddsFormat": "decimal"
    }
    resp = requests.get(url, params=params)
    return resp.json() if resp.status_code == 200 else []

def get_smarkets_event_ids():
    url = "https://api.smarkets.com/v3/popular_event_ids/"
    return requests.get(url).json().get("popular_event_ids", [])

def get_smarkets_event(event_id):
    url = f"https://api.smarkets.com/v3/events/{event_id}/"
    return requests.get(url).json()

def get_smarkets_quotes(market_id):
    url = f"https://api.smarkets.com/v3/markets/{market_id}/quotes/"
    return requests.get(url).json()

# --- Matching + Arbitrage Logic ---
def match_event_name(name, candidates):
    return difflib.get_close_matches(name, candidates, n=1, cutoff=0.6)

def is_arbitrage(back, lay):
    if back <= 1.01 or lay <= 1.01:
        return False, 0
    margin = (1 / back) + (1 / lay)
    return margin < 1, round((1 - margin) * 100, 2)

# --- Scanner ---
def scan_all_opportunities():
    seen_keys = set()
    sports = get_all_sports()
    smarket_event_ids = get_smarkets_event_ids()

    smarkets = {}
    for eid in smarket_event_ids:
        ed = get_smarkets_event(eid)
        if "event" not in ed:
            continue
        name = ed["event"]["name"]
        for mid in ed["event"].get("markets", []):
            quotes = get_smarkets_quotes(mid)
            for cid, c in quotes.get("contracts", {}).items():
                smarkets[f"{name}|{cid}"] = {
                    "lay": c.get("lay_price", 0),
                    "market_id": mid
                }

    for sport in sports:
        sport_key = sport["key"]
        events = get_oddsapi_data(sport_key)
        for ev in events:
            teams = " vs ".join(ev.get("teams", []))
            kickoff = ev.get("commence_time", "")[:19]
            for book in ev.get("bookmakers", []):
                for market in book.get("markets", []):
                    market_name = market.get("key")
                    for outcome in market.get("outcomes", []):
                        team = outcome["name"]
                        back_odds = outcome["price"]
                        key = match_event_name(team, list(smarkets.keys()))
                        if not key:
                            continue
                        lay_odds = smarkets.get(key[0], {}).get("lay", 0)
                        arb, profit_pct = is_arbitrage(back_odds, lay_odds)
                        if arb and profit_pct >= MIN_PROFIT_PCT:
                            msg_id = f"{sport_key}|{teams}|{team}|{market_name}"
                            if msg_id not in seen_keys:
                                seen_keys.add(msg_id)
                                profit_est = BANKROLL * (profit_pct / 100)
                                message = (
                                    f"*Arbitrage Opportunity*\\n"
                                    f"*Sport:* {sport['title']}\\n"
                                    f"*Teams:* {teams}\\n"
                                    f"*Market:* {market_name}\\n"
                                    f"*Back:* {team} @ {back_odds}\\n"
                                    f"*Lay:* {team} @ {lay_odds}\\n"
                                    f"*Profit:* {profit_pct:.2f}% (~£{profit_est:.2f})\\n"
                                    f"*Kickoff:* {kickoff}"
                                )
                                send_telegram_message(message)

# --- Loop Forever ---
if __name__ == "__main__":
    while True:
        try:
            print("Scanning for arbitrage...")
            scan_all_opportunities()
            time.sleep(60)  # scan every 60 seconds
        except Exception as e:
            send_telegram_message(f"⚠️ Error in arbitrage scanner: {e}")
            time.sleep(120)
