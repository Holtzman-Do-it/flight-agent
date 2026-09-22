import os
import json
import hashlib
from decimal import Decimal, InvalidOperation
from pathlib import Path

import requests


# ============================================================
# הגדרות הנסיעה
# ============================================================

DEPARTURE_DATE = "2026-10-04"
RETURN_DATE = "2026-10-08"

ORIGIN = "TLV"

PASSENGERS = [
    {"type": "adult"},
    {"type": "adult"},
]

DESTINATIONS = {
    "קפריסין": {
        "airports": ["LCA", "PFO"],
        "budget_ils": Decimal("500"),
    },

    "אתונה": {
        "airports": ["ATH"],
        "budget_ils": Decimal("1250"),
    },

    "רומא": {
        "airports": ["FCO", "CIA"],
        "budget_ils": Decimal("1250"),
    },
}

MAX_CONNECTIONS = 1

MAX_OFFERS_TO_CHECK = 10


# ============================================================
# משתני סביבה
# ============================================================

DUFFEL_ACCESS_TOKEN = os.environ.get(
    "DUFFEL_ACCESS_TOKEN"
)

TELEGRAM_BOT_TOKEN = os.environ.get(
    "TELEGRAM_BOT_TOKEN"
)

TELEGRAM_CHAT_ID = os.environ.get(
    "TELEGRAM_CHAT_ID"
)


# ============================================================
# כתובות API
# ============================================================

DUFFEL_API = "https://api.duffel.com"

ECB_API = "https://api.frankfurter.app"


# ============================================================
# קובץ זיכרון
# ============================================================

SEEN_FILE = Path("seen_deals.json")


# ============================================================
# בדיקת משתנים
# ============================================================

def check_environment():

    missing = []

    if not DUFFEL_ACCESS_TOKEN:
        missing.append("DUFFEL_ACCESS_TOKEN")

    if not TELEGRAM_BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")

    if not TELEGRAM_CHAT_ID:
        missing.append("TELEGRAM_CHAT_ID")

    if missing:
        raise RuntimeError(
            "חסרים Secrets: "
            + ", ".join(missing)
        )

    # אסור לעבוד עם Test Token
    if DUFFEL_ACCESS_TOKEN.startswith(
        "duffel_test_"
    ):
        raise RuntimeError(
            "הטוקן שהוגדר הוא Duffel TEST token. "
            "נדרש Live Token כדי לקבל מחירי טיסות אמיתיים."
        )


# ============================================================
# Headers של Duffel
# ============================================================

def duffel_headers():

    return {
        "Authorization":
            f"Bearer {DUFFEL_ACCESS_TOKEN}",

        "Accept": "application/json",

        "Content-Type": "application/json",

        "Accept-Encoding": "gzip",

        "Duffel-Version": "v2",
    }


# ============================================================
# Telegram
# ============================================================

def send_telegram(message):

    url = (
        "https://api.telegram.org/"
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
# חיפוש טיסות
# ============================================================

def search_flights(destination):

    payload = {
        "data": {

            "slices": [

                {
                    "origin": ORIGIN,
                    "destination": destination,
                    "departure_date": DEPARTURE_DATE,
                },

                {
                    "origin": destination,
                    "destination": ORIGIN,
                    "departure_date": RETURN_DATE,
                },

            ],

            "passengers": PASSENGERS,

            "cabin_class": "economy",

            "max_connections": MAX_CONNECTIONS,
        }
    }

    response = requests.post(
        f"{DUFFEL_API}/air/offer_requests",

        headers=duffel_headers(),

        params={
            "return_offers": "true",
            "supplier_timeout": "20000",
        },

        json=payload,

        timeout=60,
    )

    if not response.ok:

        raise RuntimeError(
            f"Duffel error "
            f"{response.status_code}: "
            f"{response.text[:1000]}"
        )

    result = response.json()

    data = result.get(
        "data",
        {}
    )

    if data.get("live_mode") is False:

        raise RuntimeError(
            "Duffel החזיר תוצאות TEST ולא LIVE."
        )

    return data.get(
        "offers",
        []
    )


# ============================================================
# קבלת Offer מעודכן
# ============================================================

def get_offer(offer_id):

    response = requests.get(

        f"{DUFFEL_API}/air/offers/{offer_id}",

        headers=duffel_headers(),

        params={
            "return_available_services": "true",
        },

        timeout=45,
    )

    if not response.ok:

        raise RuntimeError(
            f"Offer error "
            f"{response.status_code}: "
            f"{response.text[:1000]}"
        )

    return response.json().get(
        "data",
        {}
    )


# ============================================================
# המרת מטבע
# ============================================================

def get_exchange_rate(currency):

    currency = currency.upper()

    if currency == "ILS":
        return Decimal("1")

    response = requests.get(

        f"{ECB_API}/latest",

        params={
            "from": currency,
            "to": "ILS",
        },

        timeout=20,
    )

    if not response.ok:

        raise RuntimeError(
            f"שגיאה בקבלת שער "
            f"{currency}/ILS"
        )

    data = response.json()

    rate = data.get(
        "rates",
        {}
    ).get("ILS")

    if rate is None:

        raise RuntimeError(
            f"לא נמצא שער "
            f"{currency}/ILS"
        )

    return Decimal(
        str(rate)
    )


def to_ils(amount, currency):

    try:

        amount = Decimal(
            str(amount)
        )

    except InvalidOperation:

        raise RuntimeError(
            f"מחיר לא תקין: {amount}"
        )

    return (
        amount *
        get_exchange_rate(currency)
    )


# ============================================================
# כבודה הכלולה
# ============================================================

def get_included_baggage(offer):

    result = []

    for slice_data in offer.get(
        "slices",
        []
    ):

        for segment in slice_data.get(
            "segments",
            []
        ):

            for passenger in segment.get(
                "passengers",
                []
            ):

                for baggage in passenger.get(
                    "baggages",
                    []
                ):

                    result.append(
                        baggage
                    )

    return result


def describe_included_baggage(offer):

    baggages = get_included_baggage(
        offer
    )

    if not baggages:

        return (
            "לא התקבל מידע על כבודה כלולה"
        )

    descriptions = []

    for baggage in baggages:

        parts = []

        quantity = baggage.get(
            "quantity"
        )

        baggage_type = baggage.get(
            "type"
        )

        weight = baggage.get(
            "weight"
        )

        weight_unit = baggage.get(
            "weight_unit"
        )

        if quantity is not None:

            parts.append(
                f"כמות {quantity}"
            )

        if baggage_type:

            parts.append(
                f"סוג: {baggage_type}"
            )

        if weight is not None:

            parts.append(
                f"{weight} "
                f"{weight_unit or ''}"
            )

        if parts:

            descriptions.append(
                " / ".join(parts)
            )

    if not descriptions:

        return (
            "קיימת כבודה כלולה "
            "(פרטים לא מלאים)"
        )

    return "; ".join(
        descriptions
    )


# ============================================================
# שירותי כבודה שניתן לרכוש
# ============================================================

def get_baggage_services(offer):

    services = offer.get(
        "available_services",
        []
    )

    return [
        service
        for service in services
        if service.get("type")
        == "baggage"
    ]


def cheapest_baggage_service_ils(offer):

    services = get_baggage_services(
        offer
    )

    if not services:

        return None

    prices = []

    for service in services:

        amount = service.get(
            "total_amount"
        )

        currency = service.get(
            "total_currency"
        )

        if amount is None:
            continue

        if not currency:
            continue

        try:

            price_ils = to_ils(
                amount,
                currency
            )

            prices.append(
                (
                    price_ils,
                    service
                )
            )

        except Exception as e:

            print(
                f"לא ניתן להמיר מחיר כבודה: {e}"
            )

    if not prices:

        return None

    prices.sort(
        key=lambda x: x[0]
    )

    return prices[0]


# ============================================================
# פרטי הטיסה
# ============================================================

def get_flight_details(offer):

    details = []

    for slice_data in offer.get(
        "slices",
        []
    ):

        segments = slice_data.get(
            "segments",
            []
        )

        if not segments:
            continue

        first = segments[0]

        last = segments[-1]

        origin = slice_data.get(
            "origin",
            {}
        ).get(
            "iata_code",
            ""
        )

        destination = slice_data.get(
            "destination",
            {}
        ).get(
            "iata_code",
            ""
        )

        segment_details = []

        for segment in segments:

            operating_carrier = segment.get(
                "operating_carrier",
                {}
            )

            segment_details.append(
                {
                    "airline": operating_carrier.get(
                        "iata_code",
                        ""
                    ),

                    "airline_name":
                        operating_carrier.get(
                            "name",
                            ""
                        ),

                    "flight_number":
                        segment.get(
                            "operating_carrier_flight_number",
                            ""
                        ),

                    "departure":
                        segment.get(
                            "departing_at",
                            ""
                        ),

                    "arrival":
                        segment.get(
                            "arriving_at",
                            ""
                        ),

                    "origin":
                        segment.get(
                            "origin",
                            {}
                        ).get(
                            "iata_code",
                            ""
                        ),

                    "destination":
                        segment.get(
                            "destination",
                            {}
                        ).get(
                            "iata_code",
                            ""
                        ),
                }
            )

        details.append(
            {
                "origin": origin,

                "destination": destination,

                "departure":
                    first.get(
                        "departing_at",
                        ""
                    ),

                "arrival":
                    last.get(
                        "arriving_at",
                        ""
                    ),

                "segments":
                    len(segments),

                "segment_details":
                    segment_details,
            }
        )

    return details


# ============================================================
# זיהוי עסקה
#
# חשוב:
# לא משתמשים ב-offer.id.
#
# אותו מסלול + אותן טיסות + אותו מחיר
# = אותה עסקה.
#
# מחיר חדש = עסקה חדשה.
# ============================================================

def make_deal_id(offer):

    flights = get_flight_details(
        offer
    )

    relevant = {

        "total_amount":
            offer.get(
                "total_amount"
            ),

        "total_currency":
            offer.get(
                "total_currency"
            ),

        "slices": flights,
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
# זיכרון
# ============================================================

def load_seen():

    if not SEEN_FILE.exists():

        return set()

    try:

        with open(
            SEEN_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            return set(
                json.load(f)
            )

    except Exception:

        return set()


def save_seen(seen):

    with open(
        SEEN_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            sorted(seen),
            f,
            ensure_ascii=False,
            indent=2,
        )


# ============================================================
# הודעת Telegram
# ============================================================

def make_message(
    destination_name,
    airport,
    offer,
    flight_price_ils,
    baggage_service,
    budget,
):

    flights = get_flight_details(
        offer
    )

    airlines = []

    for flight in flights:

        for segment in flight[
            "segment_details"
        ]:

            name = segment[
                "airline_name"
            ]

            if name and name not in airlines:

                airlines.append(
                    name
                )

    lines = []

    lines.append(
        "✈️ נמצאה טיסה בתקציב"
    )

    lines.append("")

    lines.append(
        f"יעד: {destination_name}"
    )

    lines.append(
        f"שדה תעופה: {airport}"
    )

    if airlines:

        lines.append(
            "חברה: "
            + ", ".join(airlines)
        )

    lines.append("")

    lines.append(
        f"מחיר הטיסה: "
        f"{flight_price_ils:.0f} ₪"
    )

    lines.append(
        f"תקציב: {budget:.0f} ₪"
    )

    lines.append("")

    lines.append(
        "כבודה הכלולה בתעריף:"
    )

    lines.append(
        describe_included_baggage(
            offer
        )
    )

    if baggage_service:

        baggage_price = (
            baggage_service[0]
        )

        lines.append("")

        lines.append(
            "כבודה נוספת הזמינה לרכישה:"
        )

        lines.append(
            f"{baggage_price:.0f} ₪"
        )

    lines.append("")

    for index, flight in enumerate(
        flights
    ):

        if index == 0:

            lines.append(
                f"הלוך — {DEPARTURE_DATE}"
            )

        else:

            lines.append(
                f"חזור — {RETURN_DATE}"
            )

        lines.append(
            f"{flight['origin']} → "
            f"{flight['destination']}"
        )

        for segment in flight[
            "segment_details"
        ]:

            flight_number = segment[
                "flight_number"
            ]

            airline = segment[
                "airline"
            ]

            lines.append(
                f"{airline} "
                f"{flight_number}"
            )

            lines.append(
                f"המראה: "
                f"{segment['departure']}"
            )

            lines.append(
                f"נחיתה: "
                f"{segment['arrival']}"
            )

    lines.append("")

    lines.append(
        "⚠️ המחיר התקבל מ-Duffel "
        "בזמן הבדיקה."
    )

    lines.append(
        "יש לאמת את המחיר שוב לפני הזמנה."
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

    budget = destination_data[
        "budget_ils"
    ]

    for airport in destination_data[
        "airports"
    ]:

        print(
            f"\nמחפש "
            f"{destination_name} "
            f"({airport})..."
        )

        offers = search_flights(
            airport
        )

        print(
            f"נמצאו {len(offers)} הצעות"
        )

        offers = sorted(

            offers,

            key=lambda offer:
                Decimal(
                    str(
                        offer.get(
                            "total_amount",
                            "999999999"
                        )
                    )
                )
        )

        checked = 0

        for offer in offers:

            if checked >= MAX_OFFERS_TO_CHECK:

                break

            offer_id = offer.get(
                "id"
            )

            if not offer_id:

                continue

            checked += 1

            try:

                current_offer = get_offer(
                    offer_id
                )

            except Exception as e:

                print(
                    f"שגיאה בקבלת offer: {e}"
                )

                continue

            if current_offer.get(
                "live_mode"
            ) is False:

                print(
                    "ה-offer אינו Live."
                )

                continue

            amount = current_offer.get(
                "total_amount"
            )

            currency = current_offer.get(
                "total_currency"
            )

            if amount is None:
                continue

            if not currency:
                continue

            try:

                flight_price_ils = to_ils(
                    amount,
                    currency
                )

            except Exception as e:

                print(
                    f"שגיאת המרת מטבע: {e}"
                )

                continue

            print(
                f"{airport}: "
                f"{flight_price_ils:.0f} ₪"
            )

            if flight_price_ils > budget:

                continue

            baggage_service = None

            try:

                baggage_service = (
                    cheapest_baggage_service_ils(
                        current_offer
                    )
                )

            except Exception as e:

                print(
                    f"שגיאה בבדיקת כבודה: {e}"
                )

            deal_id = make_deal_id(
                current_offer
            )

            if deal_id in seen:

                continue

            message = make_message(

                destination_name,

                airport,

                current_offer,

                flight_price_ils,

                baggage_service,

                budget,
            )

            send_telegram(
                message
            )

            seen.add(
                deal_id
            )

            print(
                "נשלחה התראה לטלגרם."
            )


# ============================================================
# MAIN
# ============================================================

def main():

    check_environment()

    print(
        "======================================"
    )

    print(
        "Flight Agent מתחיל"
    )

    print(
        f"תאריכים: "
        f"{DEPARTURE_DATE} → "
        f"{RETURN_DATE}"
    )

    print(
        "נוסעים: 2 מבוגרים"
    )

    print(
        f"יציאה: {ORIGIN}"
    )

    print(
        "======================================"
    )

    seen = load_seen()

    errors = []

    for (
        destination_name,
        destination_data
    ) in DESTINATIONS.items():

        try:

            check_destination(
                destination_name,
                destination_data,
                seen,
            )

        except Exception as e:

            message = (
                f"שגיאה ביעד "
                f"{destination_name}: "
                f"{e}"
            )

            print(message)

            errors.append(
                message
            )

    save_seen(
        seen
    )

    if errors:

        send_telegram(

            "⚠️ Flight Agent הסתיים "
            "עם שגיאות:\n\n"
            + "\n".join(errors)
        )

    print(
        "\nFlight Agent הסתיים."
    )


if __name__ == "__main__":

    main()
