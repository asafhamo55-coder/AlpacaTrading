"""Generate the agent-explanation PDFs (English + Hebrew).

Usage:
    pip install reportlab python-bidi
    python docs/generate_pdfs.py

Outputs:
    docs/agent-explanation-en.pdf
    docs/agent-explanation-he.pdf
"""

import os
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

try:
    from bidi.algorithm import get_display as bidi_get_display
except ImportError:
    bidi_get_display = None

DOCS_DIR = os.path.dirname(os.path.abspath(__file__))

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",     # macOS fallback
    "/Library/Fonts/Arial Unicode.ttf",                          # older macOS
]
BOLD_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]


def _first_existing(paths):
    for p in paths:
        if os.path.exists(p):
            return p
    raise FileNotFoundError(f"None of these fonts exist: {paths}")


def _register_fonts():
    pdfmetrics.registerFont(TTFont("BodyFont", _first_existing(FONT_CANDIDATES)))
    try:
        pdfmetrics.registerFont(TTFont("BodyFont-Bold", _first_existing(BOLD_CANDIDATES)))
    except FileNotFoundError:
        pdfmetrics.registerFont(TTFont("BodyFont-Bold", _first_existing(FONT_CANDIDATES)))


def _styles(rtl: bool):
    base = getSampleStyleSheet()
    align_title = 2 if rtl else 0  # TA_RIGHT / TA_LEFT
    align_body = 2 if rtl else 4  # TA_RIGHT / TA_JUSTIFY
    s = {
        "title": ParagraphStyle(
            "title", parent=base["Title"], fontName="BodyFont-Bold",
            fontSize=22, leading=28, spaceAfter=14, alignment=align_title,
            textColor=HexColor("#1a1a1a"),
        ),
        "h2": ParagraphStyle(
            "h2", parent=base["Heading2"], fontName="BodyFont-Bold",
            fontSize=14, leading=18, spaceBefore=14, spaceAfter=6,
            alignment=align_title, textColor=HexColor("#1a1a1a"),
        ),
        "body": ParagraphStyle(
            "body", parent=base["BodyText"], fontName="BodyFont",
            fontSize=11, leading=16, alignment=align_body,
            spaceAfter=6, textColor=HexColor("#222"),
        ),
        "bullet": ParagraphStyle(
            "bullet", parent=base["BodyText"], fontName="BodyFont",
            fontSize=11, leading=16, alignment=align_body,
            leftIndent=18 if not rtl else 0,
            rightIndent=18 if rtl else 0,
            bulletIndent=4, spaceAfter=3, textColor=HexColor("#222"),
        ),
    }
    return s


def _shape(text: str, rtl: bool) -> str:
    if rtl and bidi_get_display is not None:
        return bidi_get_display(text)
    return text


def _build(flows, content_blocks, styles, rtl: bool):
    for kind, text in content_blocks:
        if kind == "title":
            flows.append(Paragraph(_shape(text, rtl), styles["title"]))
        elif kind == "h2":
            flows.append(Paragraph(_shape(text, rtl), styles["h2"]))
        elif kind == "p":
            flows.append(Paragraph(_shape(text, rtl), styles["body"]))
        elif kind == "bullet":
            bullet = "•"
            formatted = f"{bullet}  {text}" if not rtl else f"{text}  {bullet}"
            flows.append(Paragraph(_shape(formatted, rtl), styles["bullet"]))
        elif kind == "space":
            flows.append(Spacer(1, 0.3 * cm))


# --- Content ---------------------------------------------------------------

EN_CONTENT = [
    ("title", "How the Congress-Trade Agent Works"),
    ("p", "This document explains, in plain language, what the automated trading agent does, how it picks stocks, how it enters and exits positions, and what safety limits are in place. All trading happens on an Alpaca paper-trading account — no real money is at risk."),

    ("h2", "1. What the agent does"),
    ("p", "Every 15 minutes during US market hours, the agent looks up recent stock trades disclosed by members of the US Congress (via the Quiver Quantitative API). If a politician bought a stock that matches our criteria, the agent mirrors the buy in the paper account with a fixed $500 position. It then attaches a 5% trailing-stop sell order that automatically closes the position if the price drops 5% from its peak."),

    ("h2", "2. How signals are picked"),
    ("p", "A disclosure becomes an actionable signal only if it passes all of these filters:"),
    ("bullet", "Transaction type is Purchase (sales, exchanges, and partial sales are ignored)."),
    ("bullet", "Asset is a regular US-listed stock (options, bonds, mutual funds, and ETFs are skipped)."),
    ("bullet", "The disclosed dollar range is at least $15,001 (the smallest SEC disclosure bucket is skipped)."),
    ("bullet", "The disclosure was filed within the last 7 days."),
    ("bullet", "The ticker is tradable on Alpaca."),

    ("h2", "3. How trades are executed"),
    ("bullet", "Position size: $500 per new signal, placed as a notional market order (fractional shares)."),
    ("bullet", "Max open positions: 10 at a time."),
    ("bullet", "Max total exposure: $10,000 deployed at any moment."),
    ("bullet", "If you hold a stock already — agent or manual — the agent will not double-buy it."),

    ("h2", "4. How positions exit"),
    ("p", "Once the buy fills, the agent attaches a 5% trailing-stop sell order. A trailing stop follows the stock's peak price: if the price keeps rising, the stop rises with it; if the price drops 5% from the highest point reached, the stop triggers and sells. The trailing stop is held server-side by Alpaca, so it works even when the agent is not running."),

    ("h2", "5. How duplicates are avoided"),
    ("p", "Each disclosure has a deterministic 20-character ID. When the agent places a buy, it tags the Alpaca order with \"buy-<id>\". Before acting on a new signal, it checks the last 60 days of Alpaca orders — if it already placed a buy for this disclosure, it skips. This works across agent runs without needing a local database."),

    ("h2", "6. Which positions get trailing stops"),
    ("p", "The trailing stop is only attached to positions the agent itself bought (matched by the \"buy-\" prefix on the client order ID). Positions you bought manually in the Alpaca dashboard are left untouched."),

    ("h2", "7. What you will see"),
    ("bullet", "Email on every buy placed."),
    ("bullet", "Email when a trailing stop is attached."),
    ("bullet", "Email when a trailing stop triggers and the position sells."),
    ("bullet", "Portfolio summary on every GitHub Actions run (account equity, positions, pending orders, recent fills)."),
    ("bullet", "Daily digest email at 4:30 PM ET on trading days."),

    ("h2", "8. Safety rails"),
    ("bullet", "Only runs on an Alpaca paper account — not real money."),
    ("bullet", "Skips all orders when the US market is closed (no weekend trading)."),
    ("bullet", "Hard caps on position count, position size, and total exposure."),
    ("bullet", "All credentials are stored as GitHub Actions encrypted secrets, never in the code."),

    ("space", ""),
    ("p", "<i>Disclaimer: This is an educational project. Published research on \"follow Congress\" strategies is mixed — some politicians show alpha, many do not. Results on a paper account do not translate directly to live trading.</i>"),
]


HE_CONTENT = [
    ("title", "כיצד פועל סוכן מסחר הקונגרס"),
    ("p", "מסמך זה מסביר בשפה פשוטה מה עושה סוכן המסחר האוטומטי, איך הוא בוחר מניות, איך הוא פותח וסוגר פוזיציות, ואילו מגבלות בטיחות קיימות. כל המסחר מתבצע בחשבון נייר (paper) של Alpaca — אין סיכון כספי אמיתי."),

    ("h2", "1. מה הסוכן עושה"),
    ("p", "כל 15 דקות במהלך שעות המסחר בארה\"ב, הסוכן בודק עסקאות מניות שדווחו לאחרונה על ידי חברי הקונגרס האמריקאי (דרך ה-API של Quiver Quantitative). אם פוליטיקאי קנה מניה שעומדת בקריטריונים שלנו, הסוכן משקף את הקנייה בחשבון הנייר עם פוזיציה קבועה של 500 דולר. לאחר מכן הוא מצרף הוראת מכירה מסוג trailing stop של 5% אשר סוגרת את הפוזיציה אוטומטית אם המחיר יורד ב-5% מהשיא שלו."),

    ("h2", "2. איך נבחרים איתותים"),
    ("p", "דיווח עסקה הופך לאיתות פעיל רק אם הוא עובר את כל המסננים הבאים:"),
    ("bullet", "סוג העסקה הוא קנייה (מכירות, החלפות ומכירות חלקיות מתעלמים מהן)."),
    ("bullet", "הנכס הוא מניה אמריקאית רגילה (אופציות, אג\"ח, קרנות נאמנות ו-ETF לא נכנסים)."),
    ("bullet", "טווח הדולר המדווח הוא לפחות 15,001 דולר (הדלי הנמוך ביותר של SEC לא נכנס)."),
    ("bullet", "הדיווח הוגש ב-7 הימים האחרונים."),
    ("bullet", "הטיקר זמין למסחר ב-Alpaca."),

    ("h2", "3. איך מבוצעות העסקאות"),
    ("bullet", "גודל פוזיציה: 500 דולר לכל איתות חדש, כהוראת שוק לפי ערך כספי (מניות שבריות)."),
    ("bullet", "מקסימום פוזיציות פתוחות: 10 בו-זמנית."),
    ("bullet", "מקסימום חשיפה כוללת: 10,000 דולר בכל רגע נתון."),
    ("bullet", "אם אתה כבר מחזיק במניה — בין אם דרך הסוכן או באופן ידני — הסוכן לא יקנה אותה פעמיים."),

    ("h2", "4. איך פוזיציות נסגרות"),
    ("p", "לאחר ביצוע הקנייה, הסוכן מצרף הוראת trailing stop sell של 5%. Trailing stop עוקב אחרי מחיר השיא של המניה: אם המחיר ממשיך לעלות, הסטופ עולה איתו; אם המחיר יורד ב-5% מהשיא שהושג, הסטופ מופעל והמניה נמכרת. הוראת ה-trailing stop נשמרת בשרתי Alpaca, כך שהיא עובדת גם כשהסוכן לא רץ."),

    ("h2", "5. איך נמנעות כפילויות"),
    ("p", "לכל דיווח יש מזהה דטרמיניסטי של 20 תווים. כשהסוכן מבצע קנייה, הוא מתייג את הוראת ה-Alpaca עם \"-buy<מזהה>\". לפני פעולה על איתות חדש, הוא בודק את 60 הימים האחרונים של הוראות ב-Alpaca — אם הוא כבר ביצע קנייה לדיווח הזה, הוא מדלג. זה עובד בין ריצות של הסוכן בלי צורך במסד נתונים מקומי."),

    ("h2", "6. על אילו פוזיציות יוצמד trailing stop"),
    ("p", "ה-trailing stop מוצמד רק לפוזיציות שהסוכן בעצמו קנה (מזוהות על ידי הקידומת \"-buy\" במזהה הוראת הלקוח). פוזיציות שקנית באופן ידני בממשק של Alpaca נותרות ללא שינוי."),

    ("h2", "7. מה תראה"),
    ("bullet", "אימייל על כל קנייה שמתבצעת."),
    ("bullet", "אימייל כאשר trailing stop מוצמד."),
    ("bullet", "אימייל כאשר trailing stop מופעל והפוזיציה נמכרת."),
    ("bullet", "סיכום תיק בכל ריצה של GitHub Actions (הון, פוזיציות, הוראות בהמתנה, מילויים אחרונים)."),
    ("bullet", "אימייל תקציר יומי בשעה 16:30 זמן מזרח ארה\"ב בימי מסחר."),

    ("h2", "8. מעקות בטיחות"),
    ("bullet", "רץ רק על חשבון נייר של Alpaca — לא בכסף אמיתי."),
    ("bullet", "מדלג על כל ההוראות כאשר שוק ארה\"ב סגור (אין מסחר בסופי שבוע)."),
    ("bullet", "מגבלות קשיחות על מספר פוזיציות, גודל פוזיציה וחשיפה כוללת."),
    ("bullet", "כל הסודות נשמרים כ-secrets מוצפנים ב-GitHub Actions, לעולם לא בקוד."),

    ("space", ""),
    ("p", "<i>הבהרה: זהו פרויקט חינוכי. מחקרים פורסמו על אסטרטגיות \"מעקב אחר הקונגרס\" — לחלק מהפוליטיקאים יש אלפא, לרבים אין. תוצאות בחשבון נייר לא מתורגמות ישירות למסחר אמיתי.</i>"),
]


def _generate(path: str, content, rtl: bool, title: str):
    doc = SimpleDocTemplate(
        path,
        pagesize=A4,
        title=title,
        leftMargin=2.2 * cm, rightMargin=2.2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
    )
    styles = _styles(rtl)
    flows = []
    _build(flows, content, styles, rtl)
    doc.build(flows)
    print(f"Wrote {path}")


def main():
    _register_fonts()
    _generate(
        os.path.join(DOCS_DIR, "agent-explanation-en.pdf"),
        EN_CONTENT, rtl=False,
        title="How the Congress-Trade Agent Works",
    )
    _generate(
        os.path.join(DOCS_DIR, "agent-explanation-he.pdf"),
        HE_CONTENT, rtl=True,
        title="כיצד פועל סוכן מסחר הקונגרס",
    )


if __name__ == "__main__":
    main()
