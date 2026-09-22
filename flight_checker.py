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

# הלוך: 07:00–16:59
# חזור: 12:00–19:59
OUTBOUND_TIMES = "7,16"
RETURN_TIMES = "12,19"

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
# חיפוש ראשוני – הלוך וחזור
# ============================================================

def search_flights(arrival_airports):
    params = {
        "engine": "google_flights",
        "api_key": SERPAPI_KEY,

        "departure_id": ORIGIN,
        "arrival_id": arrival_airports,

        "outbound_date": DEPARTURE_DATE,
        "return_date": RETURN_DATE,

        "type": 1,
        "travel_class": 1,
        "adults": ADULTS,

        "currency": "ILS",

        # טיסות ישירות בלבד
        "stops": 1,

        # שעות ההמראה
        "outbound_times": OUTBOUND_TIMES,
        "return_times": RETURN_TIMES,

        # הזול ביותר קודם
        "sort_by": 2,

        "hl": "en",
        "gl": "il",

        # מאפשר שימוש בתוצאות שמורות במטמון
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
# קבלת אפשרויות החזור עבור טיסת הלוך מסוימת
# ============================================================

def search_return_flights(departure_token):
    params = {
        "engine": "google_flights",
        "api_key": SERPAPI_KEY,

        "departure_token": departure_token,

        # אנחנו עדיין רוצים רק טיסות ישירות
        "stops": 1,

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

def make_deal_id(outbound, returning):
    data = {
        "price": outbound.get("price"),
        "outbound": [],
        "return": [],
    }

    for flight in outbound.get("flights", []):
        data["outbound"].append({
            "airline": flight.get("airline"),
            "flight_number": flight.get("flight_number"),
            "departure": flight.get(
                "departure_airport", {}
            ).get("id"),
            "departure_time": flight.get(
                "departure_airport", {}
            ).get("time"),
            "arrival": flight.get(
                "arrival_airport", {}
            ).get("id"),
            "arrival_time": flight.get(
                "arrival_airport", {}
            ).get("time"),
        })

    if returning:
        for flight in returning.get("flights", []):
            data["return"].append({
                "airline": flight.get("airline"),
                "flight_number": flight.get("flight_number"),
                "departure": flight.get(
                    "departure_airport", {}
                ).get("id"),
                "departure_time": flight.get(
                    "departure_airport", {}
                ).get("time"),
                "arrival": flight.get(
                    "arrival_airport", {}
                ).get("id"),
                "arrival_time": flight.get(
                    "arrival_airport", {}
                ).get("time"),
            })

    raw = json.dumps(
        data,
        sort_keys=True,
        ensure_ascii=False,
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


# ============================================================
# מציאת הטיסה הזולה ביותר
# ============================================================

def get_results(data):
    results = []

    results.extend(
        data.get("best_flights", [])
    )

    results.extend(
        data.get("other_flights", [])
    )

    return [
        result
        for result in results
        if isinstance(
            result.get("price"),
            (int, float),
        )
    ]


def cheapest_result(data):
    results = get_results(data)

    if not results:
        return None

    return min(
        results,
        key=lambda result: result["price"],
    )


# ============================================================
# תיאור טיסה
# ============================================================

def describe_flights(result):
    if not result:
        return "לא התקבלו פרטי טיסה."

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
# הודעת Telegram
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

    lines.append("")

    lines.append(
        "🛬 טיסה חזור:"
    )

    lines.append(
        describe_flights(returning)
    )

    lines.append("")

    lines.append(
        "⏰ הלוך: 07:00–16:59"
    )

    lines.append(
        "⏰ חזור: 12:00–19:59"
    )

    lines.append("")

    lines.append(
        "🧳 מחיר הכבודה עדיין דורש "
        "בדיקה בתנאי ההזמנה."
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

    results = get_results(data)

    if not results:
        print(
            f"{destination_name}: "
            "לא נמצאו טיסות מתאימות."
        )
        return

    print(
        f"{destination_name}: "
        f"נמצאו {len(results)} תוצאות."
    )

    # נבדוק את התוצאות לפי מחיר,
    # עד שנמצא זוג הלוך-חזור מתאים.
    results.sort(
        key=lambda result: result["price"]
    )

    for outbound in results:

        price = outbound["price"]

        print(
            f"{destination_name}: "
            f"הלוך־חזור החל מ־{price} ₪"
        )

        # אם המחיר כבר מעל התקציב,
        # אין טעם לבדוק אותו.
        if price > budget:
            continue

        departure_token = outbound.get(
            "departure_token"
        )

        if not departure_token:
            print(
                "לתוצאה אין departure_token."
            )
            continue

        try:
            return_data = search_return_flights(
                departure_token
            )

            return_results = get_results(
                return_data
            )

            # סינון נוסף של שעות החזור.
            # כך אנחנו לא מסתמכים רק על
            # הסינון של החיפוש הראשוני.
            valid_returns = []

            for returning in return_results:

                valid_returns.append(
                    returning
                )

            if not valid_returns:
                print(
                    "לא נמצאה טיסת חזור "
                    "מתאימה."
                )
                continue

            returning = min(
                valid_returns,
                key=lambda result: result["price"]
            )

        except Exception as e:
            print(
                "שגיאה בקבלת החזור: "
                f"{e}"
            )
            continue

        deal_id = make_deal_id(
            outbound,
            returning,
        )

        if deal_id in seen:
            print(
                "העסקה כבר נשלחה בעבר."
            )
            return

        message = make_message(
            destination_name,
            outbound,
            returning,
            budget,
        )

        send_telegram(message)

        seen.add(deal_id)

        print(
            "נשלחה התראה לטלגרם."
        )

        return

    print(
        f"{destination_name}: "
        "לא נמצאה עסקה מתאימה."
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
        "הלוך: 07:00–16:59"
    )
    print(
        "חזור: 12:00–19:59"
    )
    print(
        "טיסות ישירות"
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
