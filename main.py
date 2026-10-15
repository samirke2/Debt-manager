# -*- coding: utf-8 -*-
"""
Debt Manager - Kivy  (v3)
Arabic / English interface (switch from the header button),
right-to-left layout in Arabic.

Features
- Debts (creditors / debtors) with date + priority
- Monthly salary entry, expenses (with categories), debt payments
- Every operation is stored with its date
- Financial month starts on pay day (default: the 14th)
- Statistics per pay period or for a specific date range
- Debt repayment plan with priorities and payoff timeline

Requirements (pip install):
    kivy
    arabic_reshaper
    python-bidi
"""

import os
import re
import sqlite3
from datetime import date, datetime, timedelta

# =====================================================================
#                        CORE LOGIC (no UI)
# =====================================================================
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dettes.db")

PAY_DAY = 14
PRIORITIES = (1, 2, 3)          # 1 = high, 2 = medium, 3 = low
CATEGORIES = ["Food", "Transport", "Bills", "Rent", "Health", "Family",
              "Education", "Shopping", "Other"]
STRATEGIES = ["Priority", "Smallest first", "Largest first"]
KINDS = ("salary", "expense", "debt_paid", "debt_received",
         "debt_borrowed", "debt_lent")

# ---------- Arabic text shaping (letters joining + right-to-left order) ----------
try:
    import arabic_reshaper
    try:
        from bidi.algorithm import get_display      # python-bidi 0.4.x
    except ImportError:
        from bidi import get_display                # python-bidi >= 0.5

    def reshape_ar(text):
        return get_display(arabic_reshaper.reshape(str(text)))
except ImportError:
    def reshape_ar(text):
        return str(text)

ARABIC_RE = re.compile(u"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]")


def has_arabic(text):
    return bool(ARABIC_RE.search(text or ""))


def display_name(text):
    """User text (names, notes): shape only if it contains Arabic letters."""
    return reshape_ar(text) if has_arabic(text) else (text or "")


# ---------- Language ----------
LANG = "ar"


def set_language(code):
    global LANG
    LANG = "ar" if code == "ar" else "en"


def get_language():
    return LANG


def is_rtl():
    return LANG == "ar"


# key: (English, Arabic).  Placeholders {} are filled with plain (unshaped) values.
STR = {
    # ---- app / navigation ----
    "app_title": ("Debt Manager", u"مدير الديون"),
    "nav_home": ("Debts", u"الديون"),
    "nav_ledger": ("Ledger", u"السجل"),
    "nav_stats": ("Stats", u"الإحصائيات"),
    "nav_plan": ("Plan", u"الخطة"),
    "title_home": ("Debts", u"الديون"),
    "title_ledger": ("Operations", u"العمليات"),
    "title_stats": ("Statistics", u"الإحصائيات"),
    "title_plan": ("Repayment Plan", u"خطة التسديد"),
    # ---- home ----
    "debt_position": ("Debt Position", u"وضعية الديون"),
    "owed_to_you": ("Owed to you", u"ديون لك"),
    "you_owe": ("You owe", u"ديون عليك"),
    "salary_missing": ("Salary not recorded for this period - tap to record",
                       u"لم يُسجَّل راتب هذه الفترة - اضغط للتسجيل"),
    "salary_set": ("Set your monthly salary - tap here",
                   u"حدّد راتبك الشهري - اضغط هنا"),
    "this_period": ("This pay period  ({})", u"فترة الراتب الحالية ({})"),
    "salary": ("Salary", u"الراتب"),
    "spent": ("Spent", u"المصروف"),
    "left": ("Left", u"المتبقي"),
    "debts": ("Debts", u"الديون"),
    "f_all": ("All", u"الكل"),
    "no_debts": ("No debts recorded. Tap + to add",
                 u"لا توجد ديون مسجلة. اضغط + للإضافة"),
    "due": ("Due: {}", u"المستحق: {}"),
    "paid": ("Paid: {}", u"المدفوع: {}"),
    "kind_creditor": ("Owed to you", u"دين لك"),
    "kind_debtor": ("You owe", u"دين عليك"),
    "priority_lbl": ("Priority: {}", u"الأولوية: {}"),
    "prio_1": ("High", u"عالية"),
    "prio_2": ("Medium", u"متوسطة"),
    "prio_3": ("Low", u"منخفضة"),
    # ---- ledger ----
    "in": ("In", u"الداخل"),
    "out": ("Out", u"الخارج"),
    "net": ("Net", u"الصافي"),
    "no_ops": ("No operations in this period", u"لا توجد عمليات في هذه الفترة"),
    "k_salary": ("Salary", u"راتب"),
    "k_expense": ("Expense", u"مصروف"),
    "k_debt_paid": ("Debt payment", u"تسديد دين"),
    "k_debt_received": ("Payment received", u"دفعة مستلمة"),
    "k_debt_borrowed": ("New debt (you owe)", u"دين جديد (عليك)"),
    "k_debt_lent": ("New debt (owed to you)", u"دين جديد (لك)"),
    # ---- stats ----
    "overview": ("Overview", u"نظرة عامة"),
    "payments_received": ("Payments received", u"دفعات مستلمة"),
    "expenses": ("Expenses", u"المصاريف"),
    "debts_paid": ("Debts paid", u"ديون مسددة"),
    "new_debts_owe": ("New debts (you owe)", u"ديون جديدة (عليك)"),
    "new_debts_lent": ("New debts (owed to you)", u"ديون جديدة (لك)"),
    "salary_usage": ("Salary usage", u"استهلاك الراتب"),
    "exp_by_cat": ("Expenses by category", u"المصاريف حسب الفئة"),
    "last6": ("Last 6 pay periods", u"آخر 6 فترات راتب"),
    "out_vs_salary": ("Out {} / Salary {}", u"المصروف {} / الراتب {}"),
    # ---- categories ----
    "c_Food": ("Food", u"طعام"),
    "c_Transport": ("Transport", u"مواصلات"),
    "c_Bills": ("Bills", u"فواتير"),
    "c_Rent": ("Rent", u"إيجار"),
    "c_Health": ("Health", u"صحة"),
    "c_Family": ("Family", u"عائلة"),
    "c_Education": ("Education", u"تعليم"),
    "c_Shopping": ("Shopping", u"تسوق"),
    "c_Other": ("Other", u"أخرى"),
    # ---- plan ----
    "plan_title": ("Repayment plan", u"خطة التسديد"),
    "budget_period": ("Budget / period", u"المبلغ / الفترة"),
    "budget_hint": ("Amount per pay period", u"المبلغ لكل فترة راتب"),
    "order": ("Order", u"الترتيب"),
    "s_Priority": ("Priority", u"حسب الأولوية"),
    "s_Smallest first": ("Smallest first", u"الأصغر أولاً"),
    "s_Largest first": ("Largest first", u"الأكبر أولاً"),
    "suggested": ("Suggested: {}  (salary - expenses so far)",
                  u"المقترح: {}  (الراتب - المصاريف حتى الآن)"),
    "use_suggestion": ("Use suggestion", u"استعمال المقترح"),
    "calc_plan": ("Calculate plan", u"احسب الخطة"),
    "no_debts_repay": ("You have no debts to repay.", u"ليس عليك ديون للتسديد."),
    "set_priority": ("Set priority per debt", u"حدّد أولوية كل دين"),
    "enter_budget": ("Enter a budget and tap Calculate to see your plan.",
                     u"أدخل المبلغ واضغط «احسب الخطة» لعرض الخطة."),
    "pay_this_period": ("Pay this period  ({})", u"ادفع في هذه الفترة ({})"),
    "total": ("Total", u"المجموع"),
    "payoff": ("Payoff timeline", u"جدول السداد"),
    "months_fmt": ("{}  ({} mo.)", u"{}  ({} شهر)"),
    "not_20": ("Not within 20 years", u"أكثر من 20 سنة"),
    "debt_free": ("Debt-free in {} pay periods (about {} years)",
                  u"تتحرر من الديون بعد {} فترة (حوالي {} سنة)"),
    "increase_budget": ("Increase the budget to finish sooner.",
                        u"زد المبلغ لتنتهي أسرع."),
    # ---- popups: common ----
    "save": ("Save", u"حفظ"),
    "cancel": ("Cancel", u"إلغاء"),
    "delete": ("Delete", u"حذف"),
    "close": ("Close", u"إغلاق"),
    "apply": ("Apply", u"تطبيق"),
    "date": ("Date", u"التاريخ"),
    "amount": ("Amount", u"المبلغ"),
    "err_amount": ("Enter a valid amount", u"أدخل مبلغاً صحيحاً"),
    "err_date": ("Date format: YYYY-MM-DD", u"صيغة التاريخ: YYYY-MM-DD"),
    # ---- add menu ----
    "add": ("Add", u"إضافة"),
    "new_debt": ("New debt", u"دين جديد"),
    "expense": ("Expense", u"مصروف"),
    # ---- add debt ----
    "add_debt_title": ("Add New Debt", u"إضافة دين جديد"),
    "name": ("Name", u"الاسم"),
    "name_hint": ("Name (Arabic or Latin)", u"الاسم (عربي أو لاتيني)"),
    "type": ("Type", u"النوع"),
    "type_debtor": ("Debtor (you owe)", u"دين عليك"),
    "type_creditor": ("Creditor (owed to you)", u"دين لك"),
    "amount_due": ("Amount due", u"المبلغ"),
    "paid_lbl": ("Paid", u"المدفوع"),
    "paid_hint": ("Already paid (optional)", u"المدفوع مسبقاً (اختياري)"),
    "priority": ("Priority", u"الأولوية"),
    "err_name": ("Enter a name", u"أدخل الاسم"),
    # ---- debt details ----
    "debt_details": ("Debt Details", u"تفاصيل الدين"),
    "debt_head": ("{}  -  Remaining {}  -  Added {}",
                  u"{}  -  المتبقي {}  -  أُضيف {}"),
    "payment_lbl": ("Payment", u"الدفعة"),
    "received_lbl": ("Received", u"المستلم"),
    "err_enter_amount": ("Enter the amount", u"أدخل المبلغ"),
    "err_nothing_left": ("Nothing left to pay", u"لا يوجد مبلغ متبقٍ"),
    "rec_payment": ("Record payment", u"تسجيل دفعة"),
    "rec_receipt": ("Record receipt", u"تسجيل استلام"),
    "save_changes": ("Save changes", u"حفظ التعديلات"),
    # ---- expense ----
    "add_expense": ("Add Expense", u"إضافة مصروف"),
    "category": ("Category", u"الفئة"),
    "note": ("Note", u"ملاحظة"),
    "note_hint": ("Note (optional)", u"ملاحظة (اختياري)"),
    # ---- salary ----
    "record_salary": ("Record Salary", u"تسجيل الراتب"),
    "salary_hint": ("Monthly salary", u"الراتب الشهري"),
    "pay_day": ("Pay day (1-28)", u"يوم الراتب (1-28)"),
    "received_on": ("Received on", u"تاريخ الاستلام"),
    "err_salary": ("Enter the salary", u"أدخل الراتب"),
    "err_payday": ("Pay day must be between 1 and 28",
                   u"يوم الراتب يجب أن يكون بين 1 و 28"),
    # ---- operation / range ----
    "operation": ("Operation", u"العملية"),
    "specific_period": ("Specific period", u"فترة محددة"),
    "specific_title": ("Specific Period", u"فترة محددة"),
    "from": ("From", u"من"),
    "to": ("To", u"إلى"),
    "range_hint": ("Format: YYYY-MM-DD. Applies to Ledger and Stats.",
                   u"الصيغة: YYYY-MM-DD. تُطبَّق على السجل والإحصائيات."),
    "err_range": ("'From' must be before 'To'",
                  u"تاريخ البداية يجب أن يسبق تاريخ النهاية"),
    "pay_periods": ("Pay periods", u"فترات الراتب"),
    "back_to_periods": ("Back to pay periods", u"العودة لفترات الراتب"),
}

MONTHS_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
             "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MONTHS_AR = [u"جانفي", u"فيفري", u"مارس", u"أفريل", u"ماي", u"جوان",
             u"جويلية", u"أوت", u"سبتمبر", u"أكتوبر", u"نوفمبر", u"ديسمبر"]


def tr(key, *args):
    """Logical (not shaped) text in the current language."""
    en, ar = STR[key]
    s = ar if LANG == "ar" else en
    return s.format(*args) if args else s


def shape(s):
    """Prepare a logical string for display."""
    return reshape_ar(s) if LANG == "ar" else s


def T(key, *args):
    """Display-ready text in the current language."""
    return shape(tr(key, *args))


def cat_raw(cat):
    key = "c_" + (cat or "")
    return tr(key) if key in STR else (cat or "")


def cat_disp(cat):
    return shape(cat_raw(cat))


def month_name(m):
    return (MONTHS_AR if LANG == "ar" else MONTHS_EN)[m - 1]


def fmt_dm(d):
    return "{:02d} {}".format(d.day, month_name(d.month))


def fmt_dmy(d):
    return "{:02d} {} {}".format(d.day, month_name(d.month), d.year)


def fmt_my(d):
    return "{} {}".format(month_name(d.month), d.year)


def fmt(n):
    try:
        return "{:,.0f}".format(float(n)).replace(",", " ")
    except (ValueError, TypeError):
        return str(n)


def fmt_plain(n):
    n = float(n)
    return str(int(n)) if n.is_integer() else str(n)


def money_raw(n):
    """Money for use INSIDE a template (the template gets shaped afterwards)."""
    return u"{} دج".format(fmt(n)) if LANG == "ar" else "DA " + fmt(n)


def M(n, sign=""):
    """Money for direct display (already in display order)."""
    if LANG == "ar":
        return reshape_ar(u"دج") + " " + sign + fmt(n)
    return "{}DA {}".format(sign, fmt(n))


def period_start_for(d, pay_day=PAY_DAY):
    """Start date of the financial month that contains date d."""
    if d.day >= pay_day:
        return date(d.year, d.month, pay_day)
    y, m = (d.year, d.month - 1) if d.month > 1 else (d.year - 1, 12)
    return date(y, m, pay_day)


def shift_month(d, n):
    m = d.month - 1 + n
    return date(d.year + m // 12, m % 12 + 1, min(d.day, 28))


def period_end(start):
    return shift_month(start, 1) - timedelta(days=1)


def period_label(start):
    """Logical text (shape it before display)."""
    return "{} - {}".format(fmt_dm(start), fmt_dmy(period_end(start)))


def parse_float(text):
    try:
        return float((text or "").replace(",", ".").strip() or 0)
    except ValueError:
        return None


def parse_date(text):
    try:
        return datetime.strptime((text or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


class Database:
    def __init__(self, path=DB_PATH):
        self.conn = sqlite3.connect(path)
        c = self.conn
        c.execute("""
            CREATE TABLE IF NOT EXISTS dettes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nom TEXT NOT NULL,
                type TEXT NOT NULL,
                montant_du REAL NOT NULL DEFAULT 0,
                montant_paye REAL NOT NULL DEFAULT 0
            )""")
        c.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                debt_id INTEGER,
                kind TEXT NOT NULL,
                amount REAL NOT NULL,
                note TEXT DEFAULT '',
                date TEXT NOT NULL,
                category TEXT DEFAULT ''
            )""")
        c.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )""")
        # ---- migrate older versions ----
        cols = [r[1] for r in c.execute("PRAGMA table_info(dettes)")]
        if "created_at" not in cols:
            c.execute("ALTER TABLE dettes ADD COLUMN created_at TEXT")
        if "priority" not in cols:
            c.execute("ALTER TABLE dettes ADD COLUMN priority INTEGER NOT NULL DEFAULT 2")
        c.execute("UPDATE dettes SET created_at=? WHERE created_at IS NULL OR created_at=''",
                  (date.today().isoformat(),))
        c.execute("UPDATE dettes SET type='creditor' WHERE type='دائن'")
        c.execute("UPDATE dettes SET type='debtor' WHERE type='مدين'")
        c.commit()

    # ---- settings ----
    def get_setting(self, key, default=None):
        r = self.conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return r[0] if r else default

    def set_setting(self, key, value):
        self.conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)",
                          (key, str(value)))
        self.conn.commit()

    # ---- transactions ----
    def add_txn(self, kind, amount, note, date_str, category="", debt_id=None):
        self.conn.execute(
            "INSERT INTO transactions (debt_id, kind, amount, note, date, category) "
            "VALUES (?,?,?,?,?,?)",
            (debt_id, kind, amount, note, date_str, category))
        self.conn.commit()

    def delete_txn(self, id_):
        self.conn.execute("DELETE FROM transactions WHERE id=?", (id_,))
        self.conn.commit()

    def txns_between(self, start, end):
        return self.conn.execute(
            "SELECT id, debt_id, kind, amount, note, date, category FROM transactions "
            "WHERE date>=? AND date<=? ORDER BY date DESC, id DESC",
            (start.isoformat(), end.isoformat())).fetchall()

    def totals(self, start, end):
        t = {k: 0.0 for k in KINDS}
        for kind, s in self.conn.execute(
                "SELECT kind, SUM(amount) FROM transactions "
                "WHERE date>=? AND date<=? GROUP BY kind",
                (start.isoformat(), end.isoformat())):
            t[kind] = s or 0.0
        t["net"] = (t["salary"] + t["debt_received"]
                    - t["expense"] - t["debt_paid"] - t["debt_lent"])
        return t

    def expense_categories(self, start, end):
        return self.conn.execute(
            "SELECT COALESCE(NULLIF(category,''),'Other'), SUM(amount) FROM transactions "
            "WHERE kind='expense' AND date>=? AND date<=? "
            "GROUP BY 1 ORDER BY 2 DESC",
            (start.isoformat(), end.isoformat())).fetchall()

    # ---- debts ----
    def add_debt(self, nom, type_, du, paye, date_str, priority=2):
        cur = self.conn.execute(
            "INSERT INTO dettes (nom, type, montant_du, montant_paye, created_at, priority) "
            "VALUES (?,?,?,?,?,?)", (nom, type_, du, 0, date_str, priority))
        id_ = cur.lastrowid
        self.conn.commit()
        self.add_txn("debt_borrowed" if type_ == "debtor" else "debt_lent",
                     du, nom, date_str, debt_id=id_)
        if paye > 0:
            self.pay_debt(id_, paye, date_str)
        return id_

    def pay_debt(self, id_, amount, date_str):
        """Record a payment (debtor) or a receipt (creditor). Returns the amount applied."""
        r = self.conn.execute(
            "SELECT nom, type, montant_du, montant_paye FROM dettes WHERE id=?",
            (id_,)).fetchone()
        if not r:
            return 0
        nom, type_, du, paye = r
        actual = min(amount, max(du - paye, 0))
        if actual <= 0:
            return 0
        self.conn.execute("UPDATE dettes SET montant_paye=? WHERE id=?", (paye + actual, id_))
        self.conn.commit()
        self.add_txn("debt_paid" if type_ == "debtor" else "debt_received",
                     actual, nom, date_str, debt_id=id_)
        return actual

    def update_debt(self, id_, du, priority):
        r = self.conn.execute("SELECT montant_paye FROM dettes WHERE id=?", (id_,)).fetchone()
        if not r:
            return
        du = max(du, r[0])
        self.conn.execute("UPDATE dettes SET montant_du=?, priority=? WHERE id=?",
                          (du, priority, id_))
        self.conn.commit()

    def set_priority(self, id_, priority):
        self.conn.execute("UPDATE dettes SET priority=? WHERE id=?", (priority, id_))
        self.conn.commit()

    def delete_debt(self, id_):
        self.conn.execute("DELETE FROM dettes WHERE id=?", (id_,))
        self.conn.execute("UPDATE transactions SET debt_id=NULL WHERE debt_id=?", (id_,))
        self.conn.commit()

    def get_debts(self):
        return self.conn.execute(
            "SELECT id, nom, type, montant_du, montant_paye, created_at, priority "
            "FROM dettes ORDER BY id DESC").fetchall()

    def summary(self):
        # 'creditor' = owed to me, 'debtor' = I owe
        return self.conn.execute("""
            SELECT
                COALESCE(SUM(CASE WHEN type='creditor' THEN montant_du END),0),
                COALESCE(SUM(CASE WHEN type='creditor' THEN montant_paye END),0),
                COALESCE(SUM(CASE WHEN type='debtor' THEN montant_du END),0),
                COALESCE(SUM(CASE WHEN type='debtor' THEN montant_paye END),0)
            FROM dettes""").fetchone()


def build_plan(debts, budget, strategy, cur_start, max_months=240):
    """
    Repayment plan for the debts I owe.
    debts: rows from Database.get_debts()
    Returns dict(first=[(name, pay)], timeline=[(name, months, end_date)], months=int, items=int)
    """
    items = []
    for id_, nom, type_, du, paye, created, prio in debts:
        rem = du - paye
        if type_ == "debtor" and rem > 0.005:
            items.append({"id": id_, "nom": nom, "rem": rem, "prio": prio})

    if strategy == "Smallest first":
        items.sort(key=lambda x: (x["rem"], x["prio"]))
    elif strategy == "Largest first":
        items.sort(key=lambda x: (-x["rem"], x["prio"]))
    else:
        items.sort(key=lambda x: (x["prio"], x["rem"]))

    plan = {"first": [], "timeline": [], "months": 0, "items": len(items)}
    if not items or budget <= 0:
        return plan

    rem = {it["id"]: it["rem"] for it in items}
    done = {}
    month = 0
    while month < max_months and any(v > 0.005 for v in rem.values()):
        avail = budget
        for it in items:
            if avail <= 0:
                break
            r = rem[it["id"]]
            if r <= 0.005:
                continue
            pay = min(avail, r)
            rem[it["id"]] = r - pay
            avail -= pay
            if month == 0:
                plan["first"].append((it["nom"], pay))
            if rem[it["id"]] <= 0.005 and it["id"] not in done:
                done[it["id"]] = month + 1
        month += 1

    plan["months"] = month if all(v <= 0.005 for v in rem.values()) else -1
    for it in items:
        k = done.get(it["id"])
        if k:
            plan["timeline"].append(
                (it["nom"], k, period_end(shift_month(cur_start, k - 1))))
        else:
            plan["timeline"].append((it["nom"], None, None))
    return plan


def txn_title(kind, note, cat):
    """Display-ready title of an operation."""
    if kind == "salary" and note == "Salary":      # rows written by older versions
        note = ""
    if note:
        return display_name(note)
    if cat:
        return cat_disp(cat)
    return T("k_" + kind)


# =====================================================================
#                              UI
# =====================================================================
from kivy.app import App
from kivy.clock import Clock
from kivy.lang import Builder
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.widget import Widget
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner, SpinnerOption
from kivy.uix.scrollview import ScrollView
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import ScreenManager, Screen, NoTransition
from kivy.uix.behaviors import ButtonBehavior
from kivy.properties import ListProperty, NumericProperty, BooleanProperty
from kivy.metrics import dp
from kivy.core.text import LabelBase
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle
from kivy.utils import platform

# ---------- Fonts ----------
# fonts/DejaVuSans*.ttf is bundled with the app: it has Arabic AND Latin glyphs,
# so Arabic text, numbers and Latin names all render correctly on every phone.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_FONT_CANDIDATES = [
    (os.path.join(BASE_DIR, "fonts", "DejaVuSans.ttf"),
     os.path.join(BASE_DIR, "fonts", "DejaVuSans-Bold.ttf")),
    ("/system/fonts/NotoNaskhArabic-Regular.ttf", "/system/fonts/NotoNaskhArabic-Bold.ttf"),
    ("/system/fonts/NotoSansArabic-Regular.ttf", "/system/fonts/NotoSansArabic-Bold.ttf"),
    ("C:/Windows/Fonts/tahoma.ttf", "C:/Windows/Fonts/tahomabd.ttf"),
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
]
ARABIC_FONT_NAME = "Roboto"
for _reg, _bold in _FONT_CANDIDATES:
    if os.path.exists(_reg):
        LabelBase.register(name="ArabicFont", fn_regular=_reg,
                           fn_bold=_bold if os.path.exists(_bold) else None)
        ARABIC_FONT_NAME = "ArabicFont"
        break

UI_FONT = "Roboto"


def name_font(text):
    """Font able to render the given (display-ready) text."""
    return ARABIC_FONT_NAME if has_arabic(text) else UI_FONT


# ---------- Colors ----------
COL_BG = (0.95, 0.96, 0.97, 1)
COL_HEADER = (0.11, 0.27, 0.33, 1)
COL_GOLD = (0.93, 0.78, 0.35, 1)
COL_CARD = (1, 1, 1, 1)
COL_GREEN = (0.20, 0.66, 0.33, 1)
COL_RED = (0.87, 0.31, 0.31, 1)
COL_ORANGE = (0.93, 0.55, 0.15, 1)
COL_BLUE = (0.22, 0.47, 0.78, 1)
COL_TEXT = (0.18, 0.20, 0.23, 1)
COL_MUTED = (0.55, 0.58, 0.62, 1)
COL_LINE = (0.88, 0.88, 0.90, 1)
COL_WHITE = (1, 1, 1, 1)

PRIO_COLOR = {1: COL_RED, 2: COL_ORANGE, 3: COL_BLUE}
KIND_COLOR = {
    "salary": COL_GREEN, "debt_received": COL_GREEN,
    "expense": COL_RED, "debt_paid": COL_RED, "debt_lent": COL_RED,
    "debt_borrowed": COL_ORANGE,
}
KIND_SIGN = {
    "salary": "+", "debt_received": "+", "debt_borrowed": "+",
    "expense": "-", "debt_paid": "-", "debt_lent": "-",
}

KV = """
<RoundedCard>:
    canvas.before:
        Color:
            rgba: root.bg_color
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [16,]

<FlatBg>:
    canvas.before:
        Color:
            rgba: root.bg_color
        Rectangle:
            pos: self.pos
            size: self.size

<CircleAvatar>:
    canvas.before:
        Color:
            rgba: root.bg_color
        Ellipse:
            pos: self.pos
            size: self.size

<ProgressTrack>:
    canvas:
        Color:
            rgba: 0.90, 0.90, 0.91, 1
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [5,]
        Color:
            rgba: root.fill_color
        RoundedRectangle:
            pos: (self.x + self.width * (1 - root.ratio), self.y) if root.rtl else self.pos
            size: (self.width * root.ratio, self.height)
            radius: [5,]

<FabButton>:
    canvas.before:
        Color:
            rgba: root.bg_color
        Ellipse:
            pos: self.pos
            size: self.size
    Label:
        text: "+"
        font_size: dp(34)
        bold: True
        color: 1,1,1,1
        center: root.center
"""
Builder.load_string(KV)


class RoundedCard(BoxLayout):
    bg_color = ListProperty(COL_CARD)


class FlatBg(BoxLayout):
    bg_color = ListProperty(COL_HEADER)


class CircleAvatar(Widget):
    bg_color = ListProperty(COL_GREEN)


class ProgressTrack(Widget):
    ratio = NumericProperty(0)
    fill_color = ListProperty(COL_GREEN)
    rtl = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.rtl = is_rtl()


class FabButton(ButtonBehavior, Widget):
    bg_color = ListProperty(COL_GOLD)


class TapCard(ButtonBehavior, RoundedCard):
    pass


class Divider(Widget):
    def __init__(self, **kwargs):
        super().__init__(size_hint_y=None, height=dp(1), **kwargs)
        self.bind(pos=self._draw, size=self._draw)

    def _draw(self, *args):
        self.canvas.clear()
        with self.canvas:
            Color(*COL_LINE)
            Rectangle(pos=self.pos, size=self.size)


# ---------- small UI helpers ----------
def L(text, size=14, color=COL_TEXT, bold=False, halign="left", font=None,
      h=None, hx=None):
    """Label. `text` must be display-ready (T(), M(), N() ...)."""
    lb = Label(text=text, font_size=dp(size), color=color, bold=bold,
               halign=halign, valign="middle", font_name=font or name_font(text))
    if h:
        lb.size_hint_y = None
        lb.height = dp(h)
    if hx is not None:
        lb.size_hint_x = hx
    lb.bind(size=lambda i, v: setattr(i, "text_size", v))
    return lb


def N(text, size=15, color=COL_TEXT, bold=False, halign="left", h=None, hx=None):
    """Label for user text (names, notes) that may be Arabic."""
    return L(display_name(text), size, color, bold, halign, None, h, hx)


def set_text(label, text):
    label.text = text
    label.font_name = name_font(text)


def card(h, **kw):
    return RoundedCard(orientation="vertical", size_hint_y=None, height=dp(h),
                       padding=dp(14), spacing=dp(6), **kw)


def section_title(text):
    return L(text, 15, COL_HEADER, True, h=26)


def kv_row(label, value, color=COL_TEXT, h=26):
    r = BoxLayout(size_hint_y=None, height=dp(h))
    r.add_widget(L(label, 14, COL_MUTED, hx=0.55))
    r.add_widget(L(value, 15, color, True, "right"))
    return r


def bar_row(label, value_text, ratio, color, h=40):
    r = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(h),
                  spacing=dp(3))
    top = BoxLayout(size_hint_y=None, height=dp(20))
    top.add_widget(L(label, 13, COL_TEXT))
    top.add_widget(L(value_text, 13, COL_MUTED, halign="right", hx=0.6))
    r.add_widget(top)
    r.add_widget(ProgressTrack(ratio=max(0, min(ratio, 1)), fill_color=color,
                               size_hint_y=None, height=dp(8)))
    return r


class SmartInput(TextInput):
    """TextInput whose font follows its content (or its hint while empty),
    so Arabic hints and Latin text both render without missing-glyph boxes."""

    def __init__(self, **kw):
        kw.setdefault("font_name", UI_FONT)
        if is_rtl():
            kw.setdefault("halign", "right")
        super().__init__(**kw)
        self._sync_font()
        self.bind(text=self._sync_font, hint_text=self._sync_font)

    def _sync_font(self, *args):
        probe = self.text or self.hint_text
        f = ARABIC_FONT_NAME if has_arabic(probe) else UI_FONT
        if self.font_name != f:
            self.font_name = f


def tinput(text="", hint="", numeric=False):
    return SmartInput(text=text, hint_text=hint,
                      input_filter="float" if numeric else None,
                      multiline=False, write_tab=False)


def form_row(label, widget, h=44):
    r = BoxLayout(spacing=dp(8), size_hint_y=None, height=dp(h))
    r.add_widget(L(label, 13, COL_MUTED, hx=0.38))
    r.add_widget(widget)
    return r


class ArOption(SpinnerOption):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.font_name = name_font(self.text)


class KeySpinner(Spinner):
    """Spinner that shows translated labels but exposes the underlying key."""

    def __init__(self, keys, labels, selected, **kw):
        keys, labels = list(keys), list(labels)
        sel = labels[keys.index(selected)] if selected in keys else labels[0]
        super().__init__(text=sel, values=labels, option_cls=ArOption,
                         font_name=name_font(sel), **kw)
        self._keys = keys
        self._labels = labels
        self.bind(text=lambda inst, t: setattr(inst, "font_name", name_font(t)))

    @property
    def key(self):
        try:
            return self._keys[self._labels.index(self.text)]
        except ValueError:
            return self._keys[0]


def mkbtn(text, color=COL_HEADER, fg=COL_WHITE, bold=False, size=None, **kw):
    if size:
        kw["font_size"] = dp(size)
    return Button(text=text, font_name=name_font(text), background_normal="",
                  background_color=color, color=fg, bold=bold, **kw)


def mirror(widget):
    """Flip a freshly built widget tree for right-to-left layout:
    horizontal boxes are reversed and left/right text alignment is swapped."""
    if not is_rtl():
        return
    for child in list(widget.children):
        mirror(child)
    if isinstance(widget, BoxLayout) and widget.orientation == "horizontal":
        kids = list(widget.children)
        widget.clear_widgets()
        for k in kids:
            widget.add_widget(k)
    if isinstance(widget, Label) and not isinstance(widget, Button):
        if widget.halign == "left":
            widget.halign = "right"
        elif widget.halign == "right":
            widget.halign = "left"


def make_popup(title, rows, buttons):
    """rows: widgets with fixed height; buttons: [(text, color, callback(popup))]"""
    content = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(14))
    for r in rows:
        content.add_widget(r)
    msg = L("", 12, COL_RED, h=18)
    content.add_widget(msg)
    content.add_widget(Widget())
    nbars = (len(buttons) + 1) // 2
    total_h = (dp(110) + sum(r.height + dp(8) for r in rows) + nbars * dp(52))
    popup = Popup(title=title, content=content, size_hint=(0.92, None),
                  height=min(total_h, Window.height * 0.95),
                  title_font=name_font(title),
                  title_align="right" if is_rtl() else "left",
                  separator_color=COL_GOLD)
    popup.msg = msg
    for i in range(0, len(buttons), 2):
        bar = BoxLayout(spacing=dp(8), size_hint_y=None, height=dp(44))
        for text, color, cb in buttons[i:i + 2]:
            b = mkbtn(text, color)
            b.bind(on_release=lambda inst, cb=cb: cb(popup))
            bar.add_widget(b)
        content.add_widget(bar)
    mirror(content)
    popup.open()
    return popup


def show_err(popup, key):
    set_text(popup.msg, T(key))


def today_str():
    return date.today().isoformat()


# ---------- Debt card ----------
class PersonCard(ButtonBehavior, RoundedCard):
    def __init__(self, row, app, **kwargs):
        super().__init__(orientation="vertical", size_hint_y=None, height=dp(138),
                         padding=(dp(14), dp(12)), spacing=dp(6),
                         bg_color=COL_CARD, **kwargs)
        self.row = row
        self.app = app
        id_, nom, type_, du, paye, created, prio = row
        restant = max(du - paye, 0)
        ratio = 0 if du <= 0 else min(paye / du, 1.0)
        main_color = COL_GREEN if type_ == "creditor" else COL_RED
        if restant <= 0:
            main_color = COL_MUTED

        top = BoxLayout(spacing=dp(10), size_hint_y=None, height=dp(46))
        avatar = CircleAvatar(bg_color=main_color, size_hint=(None, None),
                              size=(dp(46), dp(46)))
        letter_txt = display_name(nom[:1] if nom else "?")
        letter = Label(text=letter_txt, font_name=name_font(letter_txt),
                       bold=True, color=COL_WHITE, font_size=dp(18))
        avatar.bind(pos=lambda *a: setattr(letter, "center", avatar.center),
                    size=lambda *a: setattr(letter, "center", avatar.center))
        avatar.add_widget(letter)
        top.add_widget(avatar)
        top.add_widget(N(nom, 17, COL_TEXT, True))
        top.add_widget(L(M(restant), 17, main_color, True, "right", hx=0.42))
        self.add_widget(top)

        self.add_widget(ProgressTrack(ratio=ratio, fill_color=main_color,
                                      size_hint_y=None, height=dp(8)))

        mid = BoxLayout(size_hint_y=None, height=dp(20))
        mid.add_widget(L(T("due", money_raw(du)), 13, COL_MUTED))
        mid.add_widget(L(T("paid", money_raw(paye)), 13, COL_MUTED, halign="right"))
        self.add_widget(mid)

        bot = BoxLayout(size_hint_y=None, height=dp(20))
        kind = tr("kind_creditor") if type_ == "creditor" else tr("kind_debtor")
        bot.add_widget(L(shape("{}  -  {}".format(kind, created or "")), 12, COL_MUTED))
        if type_ == "debtor" and restant > 0:
            bot.add_widget(L(T("priority_lbl", tr("prio_%d" % prio)), 12,
                             PRIO_COLOR.get(prio, COL_MUTED), True, "right", hx=0.6))
        self.add_widget(bot)

        self.bind(on_release=lambda *a: open_debt_popup(self.app, self.row))


# ---------- Transaction row ----------
class TxnRow(ButtonBehavior, RoundedCard):
    def __init__(self, row, app, **kwargs):
        super().__init__(orientation="horizontal", size_hint_y=None, height=dp(62),
                         padding=(dp(14), dp(8)), spacing=dp(8), bg_color=COL_CARD,
                         **kwargs)
        self.row = row
        self.app = app
        id_, debt_id, kind, amount, note, d, cat = row
        color = KIND_COLOR.get(kind, COL_TEXT)

        left = BoxLayout(orientation="vertical")
        left.add_widget(L(txn_title(kind, note, cat), 15, COL_TEXT, True))
        label = cat_raw(cat) if (kind == "expense" and cat) else tr("k_" + kind)
        left.add_widget(L(shape("{}  -  {}".format(d, label)), 12, COL_MUTED))
        self.add_widget(left)
        self.add_widget(L(M(amount, KIND_SIGN.get(kind, "")), 16, color, True,
                          "right", hx=0.45))
        self.bind(on_release=lambda *a: open_txn_popup(self.app, self.row))


# ---------- Period navigator ----------
class PeriodNav(RoundedCard):
    """Pay-period navigator + 'Specific period' (custom date range) button."""

    def __init__(self, app, **kwargs):
        super().__init__(orientation="vertical", size_hint_y=None, height=dp(96),
                         padding=dp(6), spacing=dp(4), bg_color=COL_CARD, **kwargs)
        custom = app.custom_range is not None
        start, end = app.get_range()
        prev_t, next_t = (">", "<") if is_rtl() else ("<", ">")

        row = BoxLayout(spacing=dp(6), size_hint_y=None, height=dp(48))
        nav_col = COL_MUTED if custom else COL_HEADER
        prev_b = Button(text=prev_t, font_name=UI_FONT, bold=True, size_hint_x=None,
                        width=dp(48), background_normal="", disabled=custom,
                        background_color=nav_col, color=COL_WHITE)
        next_b = Button(text=next_t, font_name=UI_FONT, bold=True, size_hint_x=None,
                        width=dp(48), background_normal="", disabled=custom,
                        background_color=nav_col, color=COL_WHITE)
        prev_b.bind(on_release=lambda *a: app.shift_period(-1))
        next_b.bind(on_release=lambda *a: app.shift_period(1))
        label = ("{} - {}".format(fmt_dmy(start), fmt_dmy(end)) if custom
                 else period_label(start))
        row.add_widget(prev_b)
        row.add_widget(L(shape(label), 15, COL_ORANGE if custom else COL_HEADER,
                         True, "center"))
        row.add_widget(next_b)
        self.add_widget(row)

        btns = BoxLayout(spacing=dp(6), size_hint_y=None, height=dp(34))
        pick = mkbtn(T("specific_period"), COL_GOLD, COL_HEADER, True, 13)
        pick.bind(on_release=lambda *a: open_range_popup(app))
        btns.add_widget(pick)
        if custom:
            back = mkbtn(T("back_to_periods"), COL_MUTED, COL_WHITE, True, 13)
            back.bind(on_release=lambda *a: app.clear_range())
            btns.add_widget(back)
        self.add_widget(btns)


# =====================================================================
#                              PAGES
# =====================================================================
class BasePage(Screen):
    def __init__(self, app, **kw):
        super().__init__(**kw)
        self.app = app
        scroll = ScrollView(bar_width=dp(3))
        self.box = BoxLayout(orientation="vertical", size_hint_y=None,
                             padding=dp(14), spacing=dp(12))
        self.box.bind(minimum_height=self.box.setter("height"))
        scroll.add_widget(self.box)
        self.add_widget(scroll)

    def refresh(self):
        self.box.clear_widgets()
        self.build()
        self.box.add_widget(Widget(size_hint_y=None, height=dp(80)))  # room for the FAB
        mirror(self.box)

    def build(self):
        pass


class HomePage(BasePage):
    filter_mode = "all"

    def build(self):
        app, db = self.app, self.app.db
        c_du, c_paye, d_du, d_paye = db.summary()
        c_rest, d_rest = c_du - c_paye, d_du - d_paye
        net = c_rest - d_rest

        # ---- debts summary ----
        s = card(150)
        s.add_widget(L(T("debt_position"), 14, COL_MUTED, h=22))
        s.add_widget(L(M(net), 30, COL_GREEN if net >= 0 else COL_RED, True, h=46))
        s.add_widget(Divider())
        cols = BoxLayout(size_hint_y=None, height=dp(48), padding=(0, dp(6), 0, 0))
        for title, val, col in ((T("owed_to_you"), c_rest, COL_GREEN),
                                (T("you_owe"), d_rest, COL_RED)):
            c = BoxLayout(orientation="vertical")
            c.add_widget(L(title, 12, COL_MUTED, halign="center"))
            c.add_widget(L(M(val), 17, col, True, "center"))
            cols.add_widget(c)
        s.add_widget(cols)
        self.box.add_widget(s)

        # ---- salary banner ----
        cur = app.current_period_start()
        t = db.totals(cur, period_end(cur))
        if t["salary"] <= 0:
            saved = parse_float(db.get_setting("salary_amount", "0")) or 0
            msg = T("salary_missing") if saved > 0 else T("salary_set")
            b = TapCard(orientation="vertical", size_hint_y=None, height=dp(56),
                        padding=dp(14), bg_color=COL_GOLD)
            b.add_widget(L(msg, 14, COL_HEADER, True, "center"))
            b.bind(on_release=lambda *a: open_salary_popup(app))
            self.box.add_widget(b)

        # ---- current period ----
        spent = t["expense"] + t["debt_paid"]
        p = card(112)
        p.add_widget(L(T("this_period", period_label(cur)), 13, COL_MUTED, h=22))
        row = BoxLayout(size_hint_y=None, height=dp(56))
        for title, val, col in ((T("salary"), t["salary"], COL_GREEN),
                                (T("spent"), spent, COL_RED),
                                (T("left"), t["net"], COL_GREEN if t["net"] >= 0 else COL_RED)):
            c = BoxLayout(orientation="vertical")
            c.add_widget(L(title, 12, COL_MUTED, halign="center"))
            c.add_widget(L(M(val), 15, col, True, "center"))
            row.add_widget(c)
        p.add_widget(row)
        self.box.add_widget(p)

        # ---- filter ----
        fr = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(8))
        fr.add_widget(section_title(T("debts")))
        sp = KeySpinner(["all", "creditor", "debtor"],
                        [T("f_all"), T("owed_to_you"), T("you_owe")],
                        HomePage.filter_mode)
        sp.size_hint_x = 0.5
        sp.bind(text=lambda inst, t_: self._on_filter(inst.key))
        fr.add_widget(sp)
        self.box.add_widget(fr)

        rows = db.get_debts()
        mode = HomePage.filter_mode
        if mode == "creditor":
            rows = [r for r in rows if r[2] == "creditor"]
        elif mode == "debtor":
            rows = [r for r in rows if r[2] == "debtor"]
        rows.sort(key=lambda r: (r[3] - r[4] <= 0, r[6], -r[0]))
        if not rows:
            self.box.add_widget(L(T("no_debts"), 14, COL_MUTED, halign="center", h=60))
        for r in rows:
            self.box.add_widget(PersonCard(r, app))

    def _on_filter(self, key):
        HomePage.filter_mode = key
        Clock.schedule_once(lambda dt: self.refresh(), 0)


class LedgerPage(BasePage):
    def build(self):
        app, db = self.app, self.app.db
        start, end = app.get_range()
        self.box.add_widget(PeriodNav(app))

        t = db.totals(start, end)
        inflow = t["salary"] + t["debt_received"]
        outflow = t["expense"] + t["debt_paid"] + t["debt_lent"]
        s = card(78)
        row = BoxLayout()
        for title, val, col in ((T("in"), inflow, COL_GREEN), (T("out"), outflow, COL_RED),
                                (T("net"), t["net"], COL_GREEN if t["net"] >= 0 else COL_RED)):
            c = BoxLayout(orientation="vertical")
            c.add_widget(L(title, 12, COL_MUTED, halign="center"))
            c.add_widget(L(M(val), 16, col, True, "center"))
            row.add_widget(c)
        s.add_widget(row)
        self.box.add_widget(s)

        rows = db.txns_between(start, end)
        if not rows:
            self.box.add_widget(L(T("no_ops"), 14, COL_MUTED, halign="center", h=60))
        for r in rows:
            self.box.add_widget(TxnRow(r, app))


class StatsPage(BasePage):
    def build(self):
        app, db = self.app, self.app.db
        start, end = app.get_range()
        self.box.add_widget(PeriodNav(app))
        t = db.totals(start, end)

        # ---- overview ----
        c = card(228)
        c.add_widget(section_title(T("overview")))
        c.add_widget(kv_row(T("salary"), M(t["salary"]), COL_GREEN))
        c.add_widget(kv_row(T("payments_received"), M(t["debt_received"]), COL_GREEN))
        c.add_widget(kv_row(T("expenses"), M(t["expense"]), COL_RED))
        c.add_widget(kv_row(T("debts_paid"), M(t["debt_paid"]), COL_RED))
        c.add_widget(kv_row(T("new_debts_owe"), M(t["debt_borrowed"]), COL_ORANGE))
        c.add_widget(kv_row(T("new_debts_lent"), M(t["debt_lent"]), COL_ORANGE))
        c.add_widget(Divider())
        c.add_widget(kv_row(T("net"), M(t["net"]), COL_GREEN if t["net"] >= 0 else COL_RED))
        self.box.add_widget(c)

        # ---- usage of salary ----
        sal = t["salary"]
        out = t["expense"] + t["debt_paid"]
        u = card(130)
        u.add_widget(section_title(T("salary_usage")))
        base = sal if sal > 0 else max(out, 1)
        u.add_widget(bar_row(T("expenses"), "{}  ({:.0f}%)".format(
            fmt(t["expense"]), 100 * t["expense"] / base), t["expense"] / base, COL_RED))
        u.add_widget(bar_row(T("debts_paid"), "{}  ({:.0f}%)".format(
            fmt(t["debt_paid"]), 100 * t["debt_paid"] / base), t["debt_paid"] / base, COL_ORANGE))
        self.box.add_widget(u)

        # ---- categories ----
        cats = db.expense_categories(start, end)
        if cats:
            total = sum(v for _, v in cats) or 1
            cc = card(46 + 44 * len(cats))
            cc.add_widget(section_title(T("exp_by_cat")))
            for cat, val in cats:
                cc.add_widget(bar_row(cat_disp(cat),
                                      "{}  ({:.0f}%)".format(fmt(val), 100 * val / total),
                                      val / total, COL_BLUE))
            self.box.add_widget(cc)

        # ---- history (always by pay period) ----
        hist = []
        for i in range(5, -1, -1):
            s0 = shift_month(app.period_start, -i)
            tt = db.totals(s0, period_end(s0))
            hist.append((s0, tt["salary"], tt["expense"] + tt["debt_paid"]))
        peak = max([max(h[1], h[2]) for h in hist] + [1])
        hh = card(46 + 44 * len(hist))
        hh.add_widget(section_title(T("last6")))
        for s0, sal_, out_ in hist:
            hh.add_widget(bar_row(shape(fmt_dmy(s0)),
                                  T("out_vs_salary", fmt(out_), fmt(sal_)),
                                  out_ / peak, COL_RED if out_ > sal_ > 0 else COL_GREEN))
        self.box.add_widget(hh)


class PlanPage(BasePage):
    def build(self):
        app, db = self.app, self.app.db
        cur = app.current_period_start()
        t = db.totals(cur, period_end(cur))
        salary = t["salary"] or (parse_float(db.get_setting("salary_amount", "0")) or 0)
        suggested = max(salary - t["expense"], 0)
        budget = parse_float(db.get_setting("plan_budget", "0")) or 0
        strategy = db.get_setting("plan_strategy", "Priority")
        if strategy not in STRATEGIES:
            strategy = "Priority"

        # ---- settings card ----
        c = card(222)
        c.add_widget(section_title(T("plan_title")))
        self.ti_budget = tinput(fmt_plain(budget) if budget > 0 else "",
                                hint=T("budget_hint"), numeric=True)
        c.add_widget(form_row(T("budget_period"), self.ti_budget))
        sp = KeySpinner(STRATEGIES, [T("s_" + s_) for s_ in STRATEGIES], strategy)
        sp.bind(text=lambda inst, t_: self._on_strategy(inst.key))
        c.add_widget(form_row(T("order"), sp))
        c.add_widget(L(T("suggested", money_raw(suggested)), 12, COL_MUTED, h=22))
        if suggested > 0:
            use = mkbtn(T("use_suggestion"), COL_MUTED, size_hint_y=None, height=dp(38))
            use.bind(on_release=lambda *a: self._calc(suggested))
        else:
            use = Widget(size_hint_y=None, height=dp(1))
        calc = mkbtn(T("calc_plan"), COL_GREEN, size_hint_y=None, height=dp(42))
        calc.bind(on_release=lambda *a: self._calc(parse_float(self.ti_budget.text) or 0))
        c.add_widget(calc)
        c.add_widget(use)
        c.height = dp(250) if suggested > 0 else dp(210)
        self.box.add_widget(c)

        debts = [r for r in db.get_debts() if r[2] == "debtor" and r[3] - r[4] > 0.005]
        if not debts:
            self.box.add_widget(L(T("no_debts_repay"), 14, COL_MUTED, halign="center", h=60))
            return

        # ---- priorities ----
        pc = card(50 + 50 * len(debts))
        pc.add_widget(section_title(T("set_priority")))
        for r in sorted(debts, key=lambda r: (r[6], r[3] - r[4])):
            row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
            col = BoxLayout(orientation="vertical")
            col.add_widget(N(r[1], 14, COL_TEXT, True))
            col.add_widget(L(M(r[3] - r[4]), 12, COL_MUTED))
            row.add_widget(col)
            ps = KeySpinner(PRIORITIES, [T("prio_%d" % p_) for p_ in PRIORITIES], r[6])
            ps.size_hint_x = 0.45
            ps.bind(text=lambda inst, t_, id_=r[0]: self._on_priority(id_, inst.key))
            row.add_widget(ps)
            pc.add_widget(row)
        self.box.add_widget(pc)

        # ---- result ----
        if budget <= 0:
            self.box.add_widget(L(T("enter_budget"), 14, COL_MUTED, halign="center", h=50))
            return
        plan = build_plan(db.get_debts(), budget, strategy, cur)

        fc = card(76 + 36 * len(plan["first"]))
        fc.add_widget(section_title(T("pay_this_period", period_label(cur))))
        for nom, pay in plan["first"]:
            r = BoxLayout(size_hint_y=None, height=dp(30))
            r.add_widget(N(nom, 14))
            r.add_widget(L(M(pay), 15, COL_RED, True, "right", hx=0.5))
            fc.add_widget(r)
        fc.add_widget(Divider())
        fc.add_widget(kv_row(T("total"), M(sum(p for _, p in plan["first"])), COL_HEADER))
        self.box.add_widget(fc)

        tc = card(86 + 40 * len(plan["timeline"]))
        tc.add_widget(section_title(T("payoff")))
        for nom, months, end in plan["timeline"]:
            r = BoxLayout(size_hint_y=None, height=dp(36))
            r.add_widget(N(nom, 14))
            if months:
                r.add_widget(L(T("months_fmt", fmt_my(end), months), 13, COL_GREEN,
                               True, "right", hx=0.6))
            else:
                r.add_widget(L(T("not_20"), 13, COL_RED, True, "right", hx=0.6))
            tc.add_widget(r)
        tc.add_widget(Divider())
        if plan["months"] > 0:
            tc.add_widget(L(T("debt_free", plan["months"],
                              "{:.1f}".format(plan["months"] / 12.0)),
                            13, COL_HEADER, True, h=26))
        else:
            tc.add_widget(L(T("increase_budget"), 13, COL_RED, True, h=26))
        self.box.add_widget(tc)

    def _calc(self, amount):
        self.app.db.set_setting("plan_budget", fmt_plain(amount))
        self.refresh()

    def _on_strategy(self, key):
        self.app.db.set_setting("plan_strategy", key)
        Clock.schedule_once(lambda dt: self.refresh(), 0)

    def _on_priority(self, id_, key):
        self.app.db.set_priority(id_, key)
        Clock.schedule_once(lambda dt: self.app.refresh(), 0)


# =====================================================================
#                             POPUPS
# =====================================================================
def open_add_menu(app):
    make_popup(T("add"), [], [
        (T("new_debt"), COL_HEADER, lambda p: (p.dismiss(), open_add_debt_popup(app))),
        (T("expense"), COL_RED, lambda p: (p.dismiss(), open_expense_popup(app))),
        (T("salary"), COL_GREEN, lambda p: (p.dismiss(), open_salary_popup(app))),
        (T("cancel"), COL_MUTED, lambda p: p.dismiss()),
    ])


def open_add_debt_popup(app):
    ti_nom = tinput(hint=T("name_hint"))
    sp_type = KeySpinner(["debtor", "creditor"],
                         [T("type_debtor"), T("type_creditor")], "debtor")
    ti_du = tinput(hint=T("amount"), numeric=True)
    ti_paye = tinput(hint=T("paid_hint"), numeric=True)
    sp_pri = KeySpinner(PRIORITIES, [T("prio_%d" % p_) for p_ in PRIORITIES], 2)
    ti_date = tinput(today_str())
    rows = [form_row(T("name"), ti_nom), form_row(T("type"), sp_type),
            form_row(T("amount_due"), ti_du), form_row(T("paid_lbl"), ti_paye),
            form_row(T("priority"), sp_pri), form_row(T("date"), ti_date)]

    def save(p):
        nom = ti_nom.text.strip()
        du = parse_float(ti_du.text)
        paye = parse_float(ti_paye.text) or 0
        d = parse_date(ti_date.text)
        if not nom:
            show_err(p, "err_name")
        elif not du or du <= 0:
            show_err(p, "err_amount")
        elif d is None:
            show_err(p, "err_date")
        else:
            app.db.add_debt(nom, sp_type.key, du, min(paye, du), d.isoformat(), sp_pri.key)
            p.dismiss()
            app.refresh()

    make_popup(T("add_debt_title"), rows, [(T("save"), COL_GREEN, save),
                                           (T("cancel"), COL_MUTED, lambda p: p.dismiss())])


def open_debt_popup(app, row):
    id_, nom, type_, du, paye, created, prio = row
    rem = max(du - paye, 0)
    is_owe = type_ == "debtor"
    ti_du = tinput(fmt_plain(du), numeric=True)
    sp_pri = KeySpinner(PRIORITIES, [T("prio_%d" % p_) for p_ in PRIORITIES], prio)
    ti_amt = tinput(hint=T("amount"), numeric=True)
    ti_date = tinput(today_str())

    head = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(48))
    head.add_widget(N(nom, 17, COL_TEXT, True, h=26))
    kind = tr("kind_debtor") if is_owe else tr("kind_creditor")
    head.add_widget(L(T("debt_head", kind, money_raw(rem), created or ""), 12,
                      COL_MUTED, h=20))
    rows = [head, form_row(T("amount_due"), ti_du)]
    if is_owe:
        rows.append(form_row(T("priority"), sp_pri))
    rows += [form_row(T("payment_lbl") if is_owe else T("received_lbl"), ti_amt),
             form_row(T("date"), ti_date)]

    def pay(p):
        amt = parse_float(ti_amt.text)
        d = parse_date(ti_date.text)
        if not amt or amt <= 0:
            show_err(p, "err_enter_amount")
        elif d is None:
            show_err(p, "err_date")
        elif app.db.pay_debt(id_, amt, d.isoformat()) <= 0:
            show_err(p, "err_nothing_left")
        else:
            p.dismiss()
            app.refresh()

    def save(p):
        v = parse_float(ti_du.text)
        if not v or v <= 0:
            show_err(p, "err_amount")
            return
        app.db.update_debt(id_, v, sp_pri.key if is_owe else prio)
        p.dismiss()
        app.refresh()

    def delete(p):
        app.db.delete_debt(id_)
        p.dismiss()
        app.refresh()

    make_popup(T("debt_details"), rows, [
        (T("rec_payment") if is_owe else T("rec_receipt"), COL_GREEN, pay),
        (T("save_changes"), COL_HEADER, save),
        (T("delete"), COL_RED, delete),
        (T("cancel"), COL_MUTED, lambda p: p.dismiss()),
    ])


def open_expense_popup(app):
    ti_amt = tinput(hint=T("amount"), numeric=True)
    sp_cat = KeySpinner(CATEGORIES, [cat_disp(c_) for c_ in CATEGORIES], "Food")
    ti_note = tinput(hint=T("note_hint"))
    ti_date = tinput(today_str())
    rows = [form_row(T("amount"), ti_amt), form_row(T("category"), sp_cat),
            form_row(T("note"), ti_note), form_row(T("date"), ti_date)]

    def save(p):
        amt = parse_float(ti_amt.text)
        d = parse_date(ti_date.text)
        if not amt or amt <= 0:
            show_err(p, "err_amount")
        elif d is None:
            show_err(p, "err_date")
        else:
            app.db.add_txn("expense", amt, ti_note.text.strip(), d.isoformat(), sp_cat.key)
            p.dismiss()
            app.refresh()

    make_popup(T("add_expense"), rows, [(T("save"), COL_GREEN, save),
                                        (T("cancel"), COL_MUTED, lambda p: p.dismiss())])


def open_salary_popup(app):
    saved = parse_float(app.db.get_setting("salary_amount", "0")) or 0
    ti_amt = tinput(fmt_plain(saved) if saved > 0 else "", hint=T("salary_hint"), numeric=True)
    ti_day = tinput(str(app.pay_day), numeric=True)
    ti_date = tinput(today_str())
    rows = [form_row(T("salary"), ti_amt), form_row(T("pay_day"), ti_day),
            form_row(T("received_on"), ti_date)]

    def save(p):
        amt = parse_float(ti_amt.text)
        day = parse_float(ti_day.text)
        d = parse_date(ti_date.text)
        if not amt or amt <= 0:
            show_err(p, "err_salary")
        elif not day or not (1 <= int(day) <= 28):
            show_err(p, "err_payday")
        elif d is None:
            show_err(p, "err_date")
        else:
            app.db.set_setting("salary_amount", fmt_plain(amt))
            app.db.set_setting("pay_day", int(day))
            app.pay_day = int(day)
            app.db.add_txn("salary", amt, "", d.isoformat())
            app.period_start = period_start_for(date.today(), app.pay_day)
            p.dismiss()
            app.refresh()

    make_popup(T("record_salary"), rows, [(T("save"), COL_GREEN, save),
                                          (T("cancel"), COL_MUTED, lambda p: p.dismiss())])


def open_txn_popup(app, row):
    id_, debt_id, kind, amount, note, d, cat = row
    head = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(76))
    head.add_widget(L(txn_title(kind, note, cat), 17, COL_TEXT, True, h=26))
    head.add_widget(L(M(amount, KIND_SIGN.get(kind, "")), 16,
                      KIND_COLOR.get(kind, COL_TEXT), True, h=24))
    head.add_widget(L(shape("{}  -  {}".format(d, tr("k_" + kind))), 12, COL_MUTED, h=20))
    buttons = []
    if kind in ("salary", "expense"):
        def delete(p):
            app.db.delete_txn(id_)
            p.dismiss()
            app.refresh()
        buttons.append((T("delete"), COL_RED, delete))
    buttons.append((T("close"), COL_MUTED, lambda p: p.dismiss()))
    make_popup(T("operation"), [head], buttons)


def open_range_popup(app):
    start, end = app.get_range()
    ti_from = tinput(start.isoformat())
    ti_to = tinput(end.isoformat())
    rows = [form_row(T("from"), ti_from), form_row(T("to"), ti_to),
            L(T("range_hint"), 12, COL_MUTED, h=20)]

    def apply(p):
        a, b = parse_date(ti_from.text), parse_date(ti_to.text)
        if a is None or b is None:
            show_err(p, "err_date")
        elif a > b:
            show_err(p, "err_range")
        else:
            app.set_range(a, b)
            p.dismiss()

    def reset(p):
        app.clear_range()
        p.dismiss()

    make_popup(T("specific_title"), rows, [
        (T("apply"), COL_GREEN, apply),
        (T("pay_periods"), COL_HEADER, reset),
        (T("cancel"), COL_MUTED, lambda p: p.dismiss()),
    ])


# =====================================================================
#                           MAIN APP
# =====================================================================
class DebtApp(App):
    def build(self):
        # On Android the app folder is replaced on every update, so keep the
        # database in the persistent user data directory instead.
        if platform == "android":
            self.db = Database(os.path.join(self.user_data_dir, "dettes.db"))
        else:
            self.db = Database()
        set_language(self.db.get_setting("lang", "ar"))
        self.pay_day = int(self.db.get_setting("pay_day", PAY_DAY))
        self.period_start = period_start_for(date.today(), self.pay_day)
        self.custom_range = None  # (start, end) when a specific period is chosen
        return self._make_ui("home")

    def _make_ui(self, start_page):
        self.title = tr("app_title")

        outer = FloatLayout()
        outer.add_widget(FlatBg(bg_color=COL_BG, size_hint=(1, 1),
                                pos_hint={"x": 0, "y": 0}))
        root = BoxLayout(orientation="vertical")

        # ---- header: [spacer | title | language button] ----
        header = FlatBg(bg_color=COL_HEADER, size_hint_y=None, height=dp(56),
                        padding=(dp(8), 0), spacing=dp(8))
        header.add_widget(Widget(size_hint_x=None, width=dp(64)))
        self.header_lbl = L(T("title_home"), 20, COL_GOLD, True, "center")
        header.add_widget(self.header_lbl)
        lang_text = "EN" if is_rtl() else reshape_ar(u"عربي")
        lang_btn = Button(text=lang_text, font_name=name_font(lang_text), bold=True,
                          font_size=dp(14), size_hint=(None, None), size=(dp(64), dp(36)),
                          pos_hint={"center_y": 0.5}, background_normal="",
                          background_color=(1, 1, 1, 0.15), color=COL_GOLD)
        lang_btn.bind(on_release=lambda *a: Clock.schedule_once(
            lambda dt: self.toggle_language(), 0))
        header.add_widget(lang_btn)
        mirror(header)
        root.add_widget(header)

        # ---- pages ----
        self.sm = ScreenManager(transition=NoTransition())
        self.pages = {
            "home": HomePage(self, name="home"),
            "ledger": LedgerPage(self, name="ledger"),
            "stats": StatsPage(self, name="stats"),
            "plan": PlanPage(self, name="plan"),
        }
        for p in self.pages.values():
            self.sm.add_widget(p)
        root.add_widget(self.sm)

        # ---- bottom navigation ----
        nav = FlatBg(bg_color=COL_HEADER, size_hint_y=None, height=dp(56))
        self.nav_btns = {}
        for name in ("home", "ledger", "stats", "plan"):
            text = T("nav_" + name)
            b = Button(text=text, font_name=name_font(text), bold=True, font_size=dp(14),
                       background_normal="", background_color=(0, 0, 0, 0))
            b.bind(on_release=lambda inst, n=name: self.switch(n))
            nav.add_widget(b)
            self.nav_btns[name] = b
        mirror(nav)
        root.add_widget(nav)
        outer.add_widget(root)

        hint = {"x": 0.04, "y": 0.11} if is_rtl() else {"right": 0.96, "y": 0.11}
        fab = FabButton(bg_color=COL_GOLD, size_hint=(None, None),
                        size=(dp(58), dp(58)), pos_hint=hint)
        fab.bind(on_release=lambda *a: open_add_menu(self))
        outer.add_widget(fab)

        self.switch(start_page)
        return outer

    # ---- language ----
    def toggle_language(self):
        current = self.sm.current
        set_language("en" if is_rtl() else "ar")
        self.db.set_setting("lang", get_language())
        old = self.root
        new = self._make_ui(current)
        Window.remove_widget(old)
        Window.add_widget(new)
        self.root = new

    # ---- navigation ----
    def switch(self, name):
        self.sm.current = name
        set_text(self.header_lbl, T("title_" + name))
        for n, b in self.nav_btns.items():
            b.color = COL_GOLD if n == name else (0.8, 0.85, 0.88, 1)
        self.refresh()

    def current_period_start(self):
        return period_start_for(date.today(), self.pay_day)

    def get_range(self):
        """(start, end) used by Ledger and Stats: custom range or selected pay period."""
        if self.custom_range:
            return self.custom_range
        return self.period_start, period_end(self.period_start)

    def set_range(self, a, b):
        self.custom_range = (a, b)
        self.refresh()

    def clear_range(self):
        self.custom_range = None
        self.refresh()

    def shift_period(self, n):
        if self.custom_range:
            return
        new = shift_month(self.period_start, n)
        if new > self.current_period_start():
            return
        self.period_start = new
        self.refresh()

    def refresh(self):
        self.pages[self.sm.current].refresh()


if __name__ == "__main__":
    Window.softinput_mode = "below_target"
    Window.clearcolor = COL_BG
    DebtApp().run()
