import os
import requests
import time
from datetime import datetime
import pytz
from dotenv import load_dotenv

# Load .env variables if present
load_dotenv()

API_KEY = os.getenv("ODDS_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

UK_BOOKMAKERS = {
    "williamhill", "ladbrokes_uk", "coral", "skybet", "betway", "sport888",
    "betvictor", "paddypower", "boylesports", "unibet_uk", "casumo",
    "virginbet", "livescorebet", "leovegas", "grosvenor"
}

LAY_EXCHANGES = {"betfair_ex_uk", "matchbook", "smarkets"}

ODDS_API_URL = "https://api.the-odds-api.com/v4/sports/upcoming/odds"
MINIMUM_MARGIN = 0.02  # 2%

def fetch_all_events():
    params = {
        "apiKey": API_KEY,
        "regions": "uk",
        "markets": "h2h,h2h_lay",
        "oddsFormat": "decimal",
        "dateFormat": "iso",
    }
    response = requests.get(ODDS_API_URL, params=params)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error: {response.status_code} - {response.text}")
        return []

def send_telegram_message(message):
    url = (
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        f"?chat_id={TELEGRAM_CHAT_ID}&text={requests.utils.quote(message)}"
    )
    requests.get(url)

def find_arb_opportunities(events):
    for event in events:
        event_name = f"{event['home_team']} vs {event['away_team']}"
        start_time_utc = datetime.fromisoformat(event["commence_time"].replace("Z", "+00:00"))
        start_time_local = start_time_utc.astimezone(pytz.timezone("Europe/London")).strftime("%Y-%m-%d %H:%M")

        best_lay = {}
        for book in event.get("bookmakers", []):
            for market in book.get("markets", []):
                if market["key"] == "h2h_lay" and book["key"] in LAY_EXCHANGES:
                    for outcome in market.get("outcomes", []):
                        name = outcome["name"]
                        price = float(outcome["price"])
                        if name not in best_lay or price < best_lay[name]["price"]:
                            best_lay[name] = {"price": price, "bookmaker": book["title"]}

        if not best_lay:
            continue  # Skip if no lay prices available

        for book in event.get("bookmakers", []):
            if book["key"] not in UK_BOOKMAKERS:
                continue
            for market in book.get("markets", []):
                if market["key"] != "h2h":
                    continue
                for outcome in market.get("outcomes", []):
                    name = outcome["name"]
                    back_price = float(outcome["price"])
                    if name in best_lay:
                        lay_price = best_lay[name]["price"]
                        margin = (1 / lay_price) - (1 / back_price)
                        if margin > MINIMUM_MARGIN:
                            message = (
                                f"📈 Arb Opportunity:\n"
                                f"🏟 {event_name}\n"
                                f"🕒 {start_time_local}\n"
                                f"🔁 Team: {name}\n"
                                f"✅ Back @ {back_price} ({book['title']})\n"
                                f"❌ Lay @ {lay_price} ({best_lay[name]['bookmaker']})\n"
                                f"📊 Margin: {round(margin * 100, 2)}%"
                            )
                            send_telegram_message(message)

def main():
    while True:
        print("🔄 Scanning for arbitrage opportunities...")
        try:
            events = fetch_all_events()
            find_arb_opportunities(events)
        except Exception as e:
            print(f"❌ Error: {e}")
        time.sleep(600)  # Wait 10 minutes

if __name__ == "__main__":
    main()
