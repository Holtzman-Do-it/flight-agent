import os
import json
import hashlib
from pathlib import Path

import requests


# ============================================================
# הגדרות הנסיעה
# ============================================================

DEPARTURE_DATE = "2026-10-04"
RETURN_DATE = "2026-10-08"

ORIGIN = "TLV"
ADULTS = 2

DESTINATIONS = {
    "קפריסין": {
        "airports": "LCA,PFO",
        "budget_ils": 500,
    },
    "אתונה": {
        "airports": "ATH",
        "budget_ils": 1250,
    },
    "רומא": {
        "airports": "FCO,CIA",
        "budget_ils": 1250,
    },
}


# ============================================================
# Secrets
# ============================================================

SERPAPI_KEY = os.environ.get("SERPAPI_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")


SEEN_FILE = Path("seen_deals.json")

SERPAPI_URL = "https://serpapi.com/search"


# ============================================================
# בדיקת סביבה
# ============================================================

def check_environment():
    missing = []

    if not SERPAPI_KEY:
        missing.append("SERPAPI_KEY")

    if not TELEGRAM_BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")

    if not TELEGRAM_CHAT_ID:
        missing.append("TELEGRAM_CHAT_ID")

    if missing:
        raise RuntimeError(
            "חסרים GitHub Secrets: "
            + ", ".join(missing)
        )


# ============================================================
# Telegram
# ============================================================

def send_telegram(message):
    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    response = requests.post(
        url,
        data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "disable_web_page_preview": True,
        },
        timeout=30,
    )

    response.raise_for_status()


# ============================================================
# SerpApi – חיפוש ראשוני
# ============================================================

def search_flights(arrival_airports):
    params = {
        "engine": "google_flights",
        "api_key": SERPAPI_KEY,

        "departure_id": ORIGIN,
        "arrival_id": arrival_airports,

        "outbound_date": DEPARTURE_DATE,
        "return_date": RETURN_DATE,

        "type": 1,               # Round trip
        "travel_class": 1,       # Economy
        "adults": ADULTS,

        "currency": "ILS",

        # טיסות ישירות בלבד
        "stops": 1,

        # שני תיקי יד – אחד לכל נוסע
        "bags": 2,

        # הזול ביותר קודם
        "sort_by": 2,

        "hl": "en",
        "gl": "il",

        # מאפשר שימוש במטמון של SerpApi
        "no_cache": "false",
    }

    response = requests.get(
        SERPAPI_URL,
        params=params,
        timeout=90,
    )

    response.raise_for_status()

    data = response.json()

    if data.get("error"):
        raise RuntimeError(
            "SerpApi: " + str(data["error"])
        )

    return data


# ============================================================
# SerpApi – קבלת טיסות החזור
# ============================================================

def search_return_flights(departure_token):
    params = {
        "engine": "google_flights",
        "api_key": SERPAPI_KEY,
        "departure_token": departure_token,
        "currency": "ILS",
        "hl": "en",
        "gl": "il",
        "no_cache": "false",
    }

    response = requests.get(
        SERPAPI_URL,
        params=params,
        timeout=90,
    )

    response.raise_for_status()

    data = response.json()

    if data.get("error"):
        raise RuntimeError(
            "SerpApi return search: "
            + str(data["error"])
        )

    return data


# ============================================================
# זיכרון עסקאות שכבר נשלחו
# ============================================================

def load_seen():
    if not SEEN_FILE.exists():
        return set()

    try:
        with open(
            SEEN_FILE,
            "r",
            encoding="utf-8",
        ) as f:
            return set(json.load(f))

    except Exception:
        return set()


def save_seen(seen):
    with open(
        SEEN_FILE,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            sorted(seen),
            f,
            ensure_ascii=False,
            indent=2,
        )


# ============================================================
# מזהה עסקה
# ============================================================

def make_deal_id(result):
    flight_segments = []

    for flight in result.get("flights", []):
        departure = flight.get(
            "departure_airport",
            {},
        )

        arrival = flight.get(
            "arrival_airport",
            {},
        )

        flight_segments.append({
            "flight_number": flight.get(
                "flight_number"
            ),
            "airline": flight.get(
                "airline"
            ),
            "departure_airport": departure.get(
                "id"
            ),
            "departure_time": departure.get(
                "time"
            ),
            "arrival_airport": arrival.get(
                "id"
            ),
            "arrival_time": arrival.get(
                "time"
            ),
        })

    relevant = {
        "price": result.get("price"),
        "flights": flight_segments,
    }

    raw = json.dumps(
        relevant,
        sort_keys=True,
        ensure_ascii=False,
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


# ============================================================
# תיאור טיסה
# ============================================================

def describe_flights(result):
    lines = []

    for flight in result.get("flights", []):
        departure = flight.get(
            "departure_airport",
            {},
        )

        arrival = flight.get(
            "arrival_airport",
            {},
        )

        airline = flight.get(
            "airline",
            ""
        )

        flight_number = flight.get(
            "flight_number",
            ""
        )

        lines.append(
            f"{airline} {flight_number}".strip()
        )

        lines.append(
            f"{departure.get('id', '')} "
            f"→ {arrival.get('id', '')}"
        )

        lines.append(
            f"המראה: {departure.get('time', '')}"
        )

        lines.append(
            f"נחיתה: {arrival.get('time', '')}"
        )

        lines.append("")

    return "\n".join(lines).strip()


# ============================================================
# בחירת הטיסה הזולה ביותר
# ============================================================

def cheapest_result(data):
    results = []

    results.extend(
        data.get("best_flights", [])
    )

    results.extend(
        data.get("other_flights", [])
    )

    results = [
        result
        for result in results
        if isinstance(
            result.get("price"),
            (int, float),
        )
    ]

    if not results:
        return None

    return min(
        results,
        key=lambda result: result["price"],
    )


# ============================================================
# יצירת הודעת Telegram
# ============================================================

def make_message(
    destination_name,
    outbound,
    returning,
    budget,
):
    price = outbound.get("price")

    lines = []

    lines.append(
        "✈️ נמצאה טיסה ישירה בתקציב!"
    )

    lines.append("")

    lines.append(
        f"יעד: {destination_name}"
    )

    lines.append(
        f"תאריכים: "
        f"{DEPARTURE_DATE} → {RETURN_DATE}"
    )

    lines.append(
        f"נוסעים: {ADULTS} מבוגרים"
    )

    lines.append("")

    lines.append(
        f"💰 מחיר הלוך־חזור: {price} ₪"
    )

    lines.append(
        f"🎯 התקציב: {budget} ₪"
    )

    lines.append("")

    lines.append(
        "🛫 טיסה הלוך:"
    )

    lines.append(
        describe_flights(outbound)
    )

    if returning:
        lines.append("")
        lines.append(
            "🛬 טיסה חזור:"
        )

        lines.append(
            describe_flights(returning)
        )

    lines.append("")

    lines.append(
        "🧳 החיפוש הוגדר ל־2 תיקי יד "
        "(אחד לכל נוסע)."
    )

    lines.append("")

    lines.append(
        "המחיר התקבל מ-Google Flights "
        "באמצעות SerpApi."
    )

    lines.append(
        "יש לבדוק את המחיר הסופי ותנאי "
        "הכבודה לפני ההזמנה."
    )

    return "\n".join(lines)


# ============================================================
# בדיקת יעד
# ============================================================

def check_destination(
    destination_name,
    destination_data,
    seen,
):
    airports = destination_data["airports"]
    budget = destination_data["budget_ils"]

    print(
        f"\nמחפש {destination_name} "
        f"({airports})..."
    )

    data = search_flights(airports)

    cheapest = cheapest_result(data)

    if not cheapest:
        print(
            f"{destination_name}: "
            "לא נמצאו תוצאות."
        )
        return

    price = cheapest["price"]

    print(
        f"{destination_name}: "
        f"המחיר הזול ביותר = {price} ₪"
    )

    if price > budget:
        print(
            f"מחוץ לתקציב "
            f"(עד {budget} ₪)."
        )
        return

    deal_id = make_deal_id(cheapest)

    if deal_id in seen:
        print(
            "העסקה כבר נשלחה בעבר."
        )
        return

    # --------------------------------------------------------
    # רק עכשיו, כאשר נמצאה עסקה מעניינת,
    # מבקשים את פרטי החזור.
    # --------------------------------------------------------

    returning = None

    departure_token = cheapest.get(
        "departure_token"
    )

    if departure_token:
        try:
            return_data = search_return_flights(
                departure_token
            )

            return_result = cheapest_result(
                return_data
            )

            if return_result:
                returning = return_result

        except Exception as e:
            print(
                "לא ניתן היה לקבל את "
                f"פרטי החזור: {e}"
            )

    message = make_message(
        destination_name,
        cheapest,
        returning,
        budget,
    )

    send_telegram(message)

    seen.add(deal_id)

    print(
        "נשלחה התראה לטלגרם."
    )


# ============================================================
# הפעלה ראשית
# ============================================================

def main():
    check_environment()

    print("====================================")
    print("Flight Agent – Google Flights")
    print(
        f"{DEPARTURE_DATE} → {RETURN_DATE}"
    )
    print(
        f"{ADULTS} מבוגרים"
    )
    print(
        "טיסות ישירות + 2 תיקי יד"
    )
    print("====================================")

    seen = load_seen()

    errors = []

    for (
        destination_name,
        destination_data,
    ) in DESTINATIONS.items():

        try:
            check_destination(
                destination_name,
                destination_data,
                seen,
            )

        except Exception as e:
            error = (
                f"{destination_name}: {e}"
            )

            print(
                "שגיאה: " + error
            )

            errors.append(error)

    save_seen(seen)

    if errors:
        try:
            send_telegram(
                "⚠️ Flight Agent נתקל בשגיאות:\n\n"
                + "\n".join(errors)
            )

        except Exception as e:
            print(
                "לא ניתן לשלוח הודעת שגיאה: "
                f"{e}"
            )

    print(
        "\nFlight Agent הסתיים."
    )


if __name__ == "__main__":
    main()
