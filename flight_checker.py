import urllib.request
import json
import os

# הגדרות הטיול והדרישות הנוקשות שלך
DEPARTURE_DATE = "2026-10-04"
RETURN_DATE = "2026-10-08"
PASSENGERS_COUNT = 4  # 2 הורים + 2 צעירים

MAX_BUDGET_EUROPE = 2500  # לכל ה-4 יחד, כולל טרולי
MAX_BUDGET_CYPRUS = 1000  # לקפריסין

# קריאת מפתחות הטלגרם מהסודות המאובטחים של GitHub
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("מפתחות הטלגרם אינם מוגדרים.")
        return
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, 
        data=data, 
        headers={"Content-Type": "application/json"}
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            if response.status == 200:
                print("ההודעה נשלחה בהצלחה לטלגרם!")
            else:
                print(f"שגיאה בשליחת הודעה: {response.status}")
    except Exception as e:
        print(f"שגיאה בהתחברות לטלגרם: {e}")

print(f"--- מריץ סוכן טיסות עבור {PASSENGERS_COUNT} נוסעים ---")
print(f"תאריכים: הלוך {DEPARTURE_DATE}, חזור {RETURN_DATE}")

# בדיקה ראשונית: שליחת הודעת סטטוס כדי לוודא שהחיבור עובד
test_message = "🤖 *סוכן הטיסות הופעל בהצלחה!*\\nהסוכן מוכן ועוקב אחר הטיסות לתאריכים 4–8 באוקטובר 2026 עבור 4 נוסעים."
send_telegram_message(test_message)

print("הבדיקה הסתיימה.")
