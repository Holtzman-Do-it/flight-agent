import urllib.request
import json
import datetime

# הגדרות הטיול והדרישות הנוקשות שלך
DEPARTURE_DATE = "2026-10-04"
RETURN_DATE = "2026-10-08"
PASSENGERS_COUNT = 4  # 2 הורים + 2 צעירים (18, 19)

MAX_BUDGET_EUROPE = 2500  # לכל ה-4 יחד, כולל טרולי
MAX_BUDGET_CYPRUS = 1000  # לקפריסין

# הגדרות שעות מותרות
DEPARTURE_EARLIEST = 7   # 07:00
DEPARTURE_LATEST = 17    # 17:00

print(f"--- מריץ סוכן טיסות עבור {PASSENGERS_COUNT} נוסעים ---")
print(f"תאריכים: הלוך {DEPARTURE_DATE}, חזור {RETURN_DATE}")
print(f"דרישות: טיסות ישירות, כולל טרולי, שעות הלוך {DEPARTURE_EARLIEST}:00-{DEPARTURE_LATEST}:00.")
print(f"תקציב מקסימלי לכל ה-4: {MAX_BUDGET_EUROPE} ש\"ח (לאירופה) / {MAX_BUDGET_CYPRUS} ש\"ח (לקפריסין).")

# כאן ירוץ הלולאה שסורקת יעדים ומחילה את כל התנאים הללו על כל ה-4 כרטיסים יחד
# בשלבים הבאים נחבר מנוע חיפוש אמיתי ונתחבר לטלגרם.

print("הבדיקה הסתיימה. ממתינים לפעימה הבאה של הסוכן בענן.")
