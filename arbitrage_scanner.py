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

    print("🟢 Fetching Smarkets lay odds...")

    # Build a simple lookup: (event name, contract name) → lay odds
    for eid in smarket_event_ids:
        event_data = get_smarkets_event(eid)
        if "event" not in event_data:
            continue

        name = event_data["event"]["name"]
        for market_id in event_data["event"].get("markets", []):
            quotes = get_smarkets_quotes(market_id)
            for cid, contract in quotes.get("contracts", {}).items():
                contract_name = contract.get("name", "").strip()
                lay_price = contract.get("lay_price", 0)
                if lay_price and contract_name:
                    smarkets[(name.strip(), contract_name)] = lay_price

    print(f"✅ Loaded {len(smarkets)} lay odds from Smarkets")

    for sport in sports:
        sport_key = sport["key"]
        print(f"⚽ Scanning sport: {sport_key} ({sport['title']})")
        events = get_oddsapi_data(sport_key)

        for ev in events:
            event_name = ev.get("home_team", "") + " vs " + ev.get("away_team", "")
            commence_time = ev.get("commence_time", "")[:19]

            for bookmaker in ev.get("bookmakers", []):
                for market in bookmaker.get("markets", []):
                    for outcome in market.get("outcomes", []):
                        team = outcome["name"].strip()
                        back_odds = outcome["price"]

                        key = (event_name.strip(), team)
                        lay_odds = smarkets.get(key, 0)

                        if lay_odds == 0:
                            print(f"❌ No lay odds for {key}")
                            continue

                        margin = (1 / back_odds) + (1 / lay_odds)
                        profit_pct = round((1 - margin) * 100, 2)

                        print(f"🔍 {key} → Back: {back_odds}, Lay: {lay_odds}, Margin: {margin:.4f}, Profit: {profit_pct}%")

                        if margin < 1 and profit_pct >= MIN_PROFIT_PCT:
                            alert_id = f"{sport_key}|{event_name}|{team}"
                            if alert_id not in seen_keys:
                                seen_keys.add(alert_id)
                                estimated_profit = round(BANKROLL * profit_pct / 100, 2)
                                msg = (
                                    f"💰 *Arbitrage Opportunity*\n"
                                    f"*Sport:* {sport['title']}\n"
                                    f"*Match:* {event_name}\n"
                                    f"*Market:* {market['key']}\n"
                                    f"*Back:* {team} @ {back_odds}\n"
                                    f"*Lay:* {team} @ {lay_odds}\n"
                                    f"*Profit:* {profit_pct:.2f}% (~£{estimated_profit})\n"
                                    f"*Start:* {commence_time}"
                                )
                                send_telegram_message(msg)

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
