# -*- coding: utf-8 -*-
"""
Debt Manager - Kivy  (v2)
English UI, supports Arabic names / notes.

Features
- Debts (creditors / debtors) with date + priority
- Monthly salary entry, expenses (with categories), debt payments
- Every operation is stored with its date
- Financial month starts on pay day (default: the 14th)
- Monthly statistics + history of the last 6 periods
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
PRIORITIES = {1: "High", 2: "Medium", 3: "Low"}
PRIORITY_BY_NAME = {v: k for k, v in PRIORITIES.items()}
CATEGORIES = ["Food", "Transport", "Bills", "Rent", "Health", "Family",
              "Education", "Shopping", "Other"]
STRATEGIES = ["Priority", "Smallest first", "Largest first"]

KIND_LABEL = {
    "salary": "Salary",
    "expense": "Expense",
    "debt_paid": "Debt payment",
    "debt_received": "Payment received",
    "debt_borrowed": "New debt (you owe)",
    "debt_lent": "New debt (owed to you)",
}


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
    e = period_end(start)
    return "{} - {}".format(start.strftime("%d %b"), e.strftime("%d %b %Y"))


def fmt(n):
    try:
        return "{:,.0f}".format(float(n)).replace(",", " ")
    except (ValueError, TypeError):
        return str(n)


def fmt_plain(n):
    n = float(n)
    return str(int(n)) if n.is_integer() else str(n)


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
        t = {k: 0.0 for k in KIND_LABEL}
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
from kivy.uix.spinner import Spinner
from kivy.uix.scrollview import ScrollView
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import ScreenManager, Screen, NoTransition
from kivy.uix.behaviors import ButtonBehavior
from kivy.properties import ListProperty, NumericProperty
from kivy.metrics import dp
from kivy.core.text import LabelBase
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle
from kivy.utils import platform

# ---------- Arabic text support (used ONLY for Arabic text) ----------
try:
    import arabic_reshaper
    from bidi.algorithm import get_display

    def reshape_ar(text):
        return get_display(arabic_reshaper.reshape(str(text)))
except ImportError:
    def reshape_ar(text):
        return str(text)

ARABIC_RE = re.compile(r"[\u0600-\u06FF]")


def has_arabic(text):
    return bool(ARABIC_RE.search(text or ""))


def display_name(text):
    return reshape_ar(text) if has_arabic(text) else (text or "")


ARABIC_FONT = None
for _f in [
    "/system/fonts/NotoNaskhArabic-Regular.ttf",
    "/system/fonts/NotoSansArabic-Regular.ttf",
    "C:/Windows/Fonts/tahoma.ttf",
    "C:/Windows/Fonts/arial.ttf",
]:
    if os.path.exists(_f):
        ARABIC_FONT = _f
        break

if ARABIC_FONT:
    LabelBase.register(name="ArabicFont", fn_regular=ARABIC_FONT)
    ARABIC_FONT_NAME = "ArabicFont"
else:
    ARABIC_FONT_NAME = "Roboto"

UI_FONT = "Roboto"


def name_font(text):
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
            pos: self.pos
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
    lb = Label(text=text, font_size=dp(size), color=color, bold=bold,
               halign=halign, valign="middle", font_name=font or UI_FONT)
    if h:
        lb.size_hint_y = None
        lb.height = dp(h)
    if hx is not None:
        lb.size_hint_x = hx
    lb.bind(size=lambda i, v: setattr(i, "text_size", v))
    return lb


def N(text, size=15, color=COL_TEXT, bold=False, halign="left", h=None, hx=None):
    """Label for user text (may be Arabic)."""
    return L(display_name(text), size, color, bold, halign, name_font(text), h, hx)


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
    top.add_widget(L(display_name(label), 13, COL_TEXT, font=name_font(label)))
    top.add_widget(L(value_text, 13, COL_MUTED, halign="right", hx=0.6))
    r.add_widget(top)
    r.add_widget(ProgressTrack(ratio=max(0, min(ratio, 1)), fill_color=color,
                               size_hint_y=None, height=dp(8)))
    return r


class ArabicInput(TextInput):
    """TextInput that uses the Arabic font only while the text contains Arabic.
    Empty field (hint) and Latin text use Roboto, so no square symbols appear."""

    def __init__(self, **kw):
        kw["font_name"] = UI_FONT
        super().__init__(**kw)
        self.bind(text=self._sync_font)

    def _sync_font(self, inst, text):
        f = ARABIC_FONT_NAME if has_arabic(text) else UI_FONT
        if self.font_name != f:
            self.font_name = f


def tinput(text="", hint="", numeric=False, arabic=False):
    cls = ArabicInput if arabic else TextInput
    kw = dict(text=text, hint_text=hint,
              input_filter="float" if numeric else None,
              multiline=False, write_tab=False)
    if not arabic:
        kw["font_name"] = UI_FONT
    return cls(**kw)


def form_row(label, widget, h=44):
    r = BoxLayout(spacing=dp(8), size_hint_y=None, height=dp(h))
    r.add_widget(L(label, 13, COL_MUTED, hx=0.38))
    r.add_widget(widget)
    return r


def make_spinner(text, values):
    return Spinner(text=text, values=list(values), font_name=UI_FONT)


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
                  title_font=UI_FONT, separator_color=COL_GOLD)
    popup.msg = msg
    for i in range(0, len(buttons), 2):
        bar = BoxLayout(spacing=dp(8), size_hint_y=None, height=dp(44))
        for text, color, cb in buttons[i:i + 2]:
            b = Button(text=text, font_name=UI_FONT, background_normal="",
                       background_color=color, color=COL_WHITE)
            b.bind(on_release=lambda inst, cb=cb: cb(popup))
            bar.add_widget(b)
        content.add_widget(bar)
    popup.open()
    return popup


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
        letter_txt = nom[:1] if nom else "?"
        letter = Label(text=display_name(letter_txt), font_name=name_font(letter_txt),
                       bold=True, color=COL_WHITE, font_size=dp(18))
        avatar.bind(pos=lambda *a: setattr(letter, "center", avatar.center),
                    size=lambda *a: setattr(letter, "center", avatar.center))
        avatar.add_widget(letter)
        top.add_widget(avatar)
        top.add_widget(N(nom, 17, COL_TEXT, True))
        top.add_widget(L("DA " + fmt(restant), 17, main_color, True, "right", hx=0.42))
        self.add_widget(top)

        self.add_widget(ProgressTrack(ratio=ratio, fill_color=main_color,
                                      size_hint_y=None, height=dp(8)))

        mid = BoxLayout(size_hint_y=None, height=dp(20))
        mid.add_widget(L("Due: DA " + fmt(du), 13, COL_MUTED))
        mid.add_widget(L("Paid: DA " + fmt(paye), 13, COL_MUTED, halign="right"))
        self.add_widget(mid)

        bot = BoxLayout(size_hint_y=None, height=dp(20))
        kind = "Owed to you" if type_ == "creditor" else "You owe"
        bot.add_widget(L("{}  -  {}".format(kind, created or ""), 12, COL_MUTED))
        if type_ == "debtor" and restant > 0:
            bot.add_widget(L("Priority: " + PRIORITIES.get(prio, "Medium"), 12,
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
        title = note or cat or KIND_LABEL.get(kind, kind)

        left = BoxLayout(orientation="vertical")
        left.add_widget(N(title, 15, COL_TEXT, True))
        sub = "{}  -  {}".format(d, KIND_LABEL.get(kind, kind))
        if kind == "expense" and cat:
            sub = "{}  -  {}".format(d, cat)
        left.add_widget(L(sub, 12, COL_MUTED))
        self.add_widget(left)
        self.add_widget(L("{}DA {}".format(KIND_SIGN.get(kind, ""), fmt(amount)),
                          16, color, True, "right", hx=0.45))
        self.bind(on_release=lambda *a: open_txn_popup(self.app, self.row))


# ---------- Period navigator ----------
class PeriodNav(RoundedCard):
    """Pay-period navigator + 'Specific period' (custom date range) button."""

    def __init__(self, app, **kwargs):
        super().__init__(orientation="vertical", size_hint_y=None, height=dp(96),
                         padding=dp(6), spacing=dp(4), bg_color=COL_CARD, **kwargs)
        custom = app.custom_range is not None
        start, end = app.get_range()

        row = BoxLayout(spacing=dp(6), size_hint_y=None, height=dp(48))
        prev_b = Button(text="<", font_name=UI_FONT, bold=True, size_hint_x=None,
                        width=dp(48), background_normal="", disabled=custom,
                        background_color=COL_MUTED if custom else COL_HEADER,
                        color=COL_WHITE)
        next_b = Button(text=">", font_name=UI_FONT, bold=True, size_hint_x=None,
                        width=dp(48), background_normal="", disabled=custom,
                        background_color=COL_MUTED if custom else COL_HEADER,
                        color=COL_WHITE)
        prev_b.bind(on_release=lambda *a: app.shift_period(-1))
        next_b.bind(on_release=lambda *a: app.shift_period(1))
        label = ("{} - {}".format(start.strftime("%d %b %Y"), end.strftime("%d %b %Y"))
                 if custom else period_label(start))
        row.add_widget(prev_b)
        row.add_widget(L(label, 15, COL_ORANGE if custom else COL_HEADER, True, "center"))
        row.add_widget(next_b)
        self.add_widget(row)

        btns = BoxLayout(spacing=dp(6), size_hint_y=None, height=dp(34))
        pick = Button(text="Specific period", font_name=UI_FONT, bold=True,
                      font_size=dp(13), background_normal="",
                      background_color=COL_GOLD, color=COL_HEADER)
        pick.bind(on_release=lambda *a: open_range_popup(app))
        btns.add_widget(pick)
        if custom:
            back = Button(text="Back to pay periods", font_name=UI_FONT, bold=True,
                          font_size=dp(13), background_normal="",
                          background_color=COL_MUTED, color=COL_WHITE)
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

    def build(self):
        pass


class HomePage(BasePage):
    filter_mode = "All"

    def build(self):
        app, db = self.app, self.app.db
        c_du, c_paye, d_du, d_paye = db.summary()
        c_rest, d_rest = c_du - c_paye, d_du - d_paye
        net = c_rest - d_rest

        # ---- debts summary ----
        s = card(150)
        s.add_widget(L("Debt Position", 14, COL_MUTED, h=22))
        s.add_widget(L("DA " + fmt(net), 30, COL_GREEN if net >= 0 else COL_RED,
                       True, h=46))
        s.add_widget(Divider())
        cols = BoxLayout(size_hint_y=None, height=dp(48), padding=(0, dp(6), 0, 0))
        for title, val, col in (("Owed to you", c_rest, COL_GREEN),
                                ("You owe", d_rest, COL_RED)):
            c = BoxLayout(orientation="vertical")
            c.add_widget(L(title, 12, COL_MUTED, halign="center"))
            c.add_widget(L("DA " + fmt(val), 17, col, True, "center"))
            cols.add_widget(c)
        s.add_widget(cols)
        self.box.add_widget(s)

        # ---- salary banner ----
        cur = app.current_period_start()
        t = db.totals(cur, period_end(cur))
        if t["salary"] <= 0:
            saved = parse_float(db.get_setting("salary_amount", "0")) or 0
            msg = ("Salary not recorded for this period - tap to record"
                   if saved > 0 else "Set your monthly salary - tap here")
            b = TapCard(orientation="vertical", size_hint_y=None, height=dp(56),
                        padding=dp(14), bg_color=COL_GOLD)
            b.add_widget(L(msg, 14, COL_HEADER, True, "center"))
            b.bind(on_release=lambda *a: open_salary_popup(app))
            self.box.add_widget(b)

        # ---- current period ----
        spent = t["expense"] + t["debt_paid"]
        p = card(112)
        p.add_widget(L("This pay period  ({})".format(period_label(cur)), 13,
                       COL_MUTED, h=22))
        row = BoxLayout(size_hint_y=None, height=dp(56))
        for title, val, col in (("Salary", t["salary"], COL_GREEN),
                                ("Spent", spent, COL_RED),
                                ("Left", t["net"], COL_GREEN if t["net"] >= 0 else COL_RED)):
            c = BoxLayout(orientation="vertical")
            c.add_widget(L(title, 12, COL_MUTED, halign="center"))
            c.add_widget(L("DA " + fmt(val), 15, col, True, "center"))
            row.add_widget(c)
        p.add_widget(row)
        self.box.add_widget(p)

        # ---- filter ----
        fr = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(8))
        fr.add_widget(section_title("Debts"))
        sp = make_spinner(HomePage.filter_mode, ("All", "Owed to you", "You owe"))
        sp.size_hint_x = 0.5
        sp.bind(text=self._on_filter)
        fr.add_widget(sp)
        self.box.add_widget(fr)

        rows = db.get_debts()
        mode = HomePage.filter_mode
        if mode == "Owed to you":
            rows = [r for r in rows if r[2] == "creditor"]
        elif mode == "You owe":
            rows = [r for r in rows if r[2] == "debtor"]
        rows.sort(key=lambda r: (r[3] - r[4] <= 0, r[6], -r[0]))
        if not rows:
            self.box.add_widget(L("No debts recorded. Tap + to add", 14, COL_MUTED,
                                  halign="center", h=60))
        for r in rows:
            self.box.add_widget(PersonCard(r, app))

    def _on_filter(self, inst, text):
        HomePage.filter_mode = text
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
        for title, val, col in (("In", inflow, COL_GREEN), ("Out", outflow, COL_RED),
                                ("Net", t["net"], COL_GREEN if t["net"] >= 0 else COL_RED)):
            c = BoxLayout(orientation="vertical")
            c.add_widget(L(title, 12, COL_MUTED, halign="center"))
            c.add_widget(L("DA " + fmt(val), 16, col, True, "center"))
            row.add_widget(c)
        s.add_widget(row)
        self.box.add_widget(s)

        rows = db.txns_between(start, end)
        if not rows:
            self.box.add_widget(L("No operations in this period", 14, COL_MUTED,
                                  halign="center", h=60))
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
        c.add_widget(section_title("Overview"))
        c.add_widget(kv_row("Salary", "DA " + fmt(t["salary"]), COL_GREEN))
        c.add_widget(kv_row("Payments received", "DA " + fmt(t["debt_received"]), COL_GREEN))
        c.add_widget(kv_row("Expenses", "DA " + fmt(t["expense"]), COL_RED))
        c.add_widget(kv_row("Debts paid", "DA " + fmt(t["debt_paid"]), COL_RED))
        c.add_widget(kv_row("New debts (you owe)", "DA " + fmt(t["debt_borrowed"]), COL_ORANGE))
        c.add_widget(kv_row("Lent (owed to you)", "DA " + fmt(t["debt_lent"]), COL_ORANGE))
        c.add_widget(Divider())
        c.add_widget(kv_row("Net", "DA " + fmt(t["net"]),
                            COL_GREEN if t["net"] >= 0 else COL_RED))
        self.box.add_widget(c)

        # ---- usage of salary ----
        sal = t["salary"]
        out = t["expense"] + t["debt_paid"]
        u = card(130)
        u.add_widget(section_title("Salary usage"))
        base = sal if sal > 0 else max(out, 1)
        u.add_widget(bar_row("Expenses", "{}  ({:.0f}%)".format(
            fmt(t["expense"]), 100 * t["expense"] / base), t["expense"] / base, COL_RED))
        u.add_widget(bar_row("Debts paid", "{}  ({:.0f}%)".format(
            fmt(t["debt_paid"]), 100 * t["debt_paid"] / base), t["debt_paid"] / base, COL_ORANGE))
        self.box.add_widget(u)

        # ---- categories ----
        cats = db.expense_categories(start, end)
        if cats:
            total = sum(v for _, v in cats) or 1
            cc = card(46 + 44 * len(cats))
            cc.add_widget(section_title("Expenses by category"))
            for cat, val in cats:
                cc.add_widget(bar_row(cat, "DA {}  ({:.0f}%)".format(fmt(val), 100 * val / total),
                                      val / total, COL_BLUE))
            self.box.add_widget(cc)

        # ---- history ----
        hist = []
        for i in range(5, -1, -1):
            s0 = shift_month(app.period_start, -i)
            tt = db.totals(s0, period_end(s0))
            hist.append((s0, tt["salary"], tt["expense"] + tt["debt_paid"]))
        peak = max([max(h[1], h[2]) for h in hist] + [1])
        hh = card(46 + 44 * len(hist))
        hh.add_widget(section_title("Last 6 pay periods"))
        for s0, sal_, out_ in hist:
            hh.add_widget(bar_row(s0.strftime("%d %b %Y"),
                                  "Out {} / Salary {}".format(fmt(out_), fmt(sal_)),
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
        c.add_widget(section_title("Repayment plan"))
        self.ti_budget = tinput(fmt_plain(budget) if budget > 0 else "",
                                hint="Amount per pay period", numeric=True)
        c.add_widget(form_row("Budget / period", self.ti_budget))
        sp = make_spinner(strategy, STRATEGIES)
        sp.bind(text=self._on_strategy)
        c.add_widget(form_row("Order", sp))
        c.add_widget(L("Suggested: DA {}  (salary - expenses so far)".format(fmt(suggested)),
                       12, COL_MUTED, h=22))
        if suggested > 0:
            use = Button(text="Use suggestion", font_name=UI_FONT, size_hint_y=None,
                         height=dp(38), background_normal="",
                         background_color=COL_MUTED, color=COL_WHITE)
            use.bind(on_release=lambda *a: self._calc(suggested))
        else:
            use = Widget(size_hint_y=None, height=dp(1))
        calc = Button(text="Calculate plan", font_name=UI_FONT, size_hint_y=None,
                      height=dp(42), background_normal="", background_color=COL_GREEN,
                      color=COL_WHITE)
        calc.bind(on_release=lambda *a: self._calc(parse_float(self.ti_budget.text) or 0))
        c.add_widget(calc)
        c.add_widget(use)
        c.height = dp(250) if suggested > 0 else dp(210)
        self.box.add_widget(c)

        debts = [r for r in db.get_debts() if r[2] == "debtor" and r[3] - r[4] > 0.005]
        if not debts:
            self.box.add_widget(L("You have no debts to repay.", 14, COL_MUTED,
                                  halign="center", h=60))
            return

        # ---- priorities ----
        pc = card(50 + 50 * len(debts))
        pc.add_widget(section_title("Set priority per debt"))
        for r in sorted(debts, key=lambda r: (r[6], r[3] - r[4])):
            row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
            col = BoxLayout(orientation="vertical")
            col.add_widget(N(r[1], 14, COL_TEXT, True))
            col.add_widget(L("DA " + fmt(r[3] - r[4]), 12, COL_MUTED))
            row.add_widget(col)
            ps = make_spinner(PRIORITIES.get(r[6], "Medium"), PRIORITIES.values())
            ps.size_hint_x = 0.45
            ps.bind(text=lambda inst, text, id_=r[0]: self._on_priority(id_, text))
            row.add_widget(ps)
            pc.add_widget(row)
        self.box.add_widget(pc)

        # ---- result ----
        if budget <= 0:
            self.box.add_widget(L("Enter a budget and tap Calculate to see your plan.",
                                  14, COL_MUTED, halign="center", h=50))
            return
        plan = build_plan(db.get_debts(), budget, strategy, cur)

        fc = card(76 + 36 * len(plan["first"]))
        fc.add_widget(section_title("Pay this period  ({})".format(period_label(cur))))
        for nom, pay in plan["first"]:
            r = BoxLayout(size_hint_y=None, height=dp(30))
            r.add_widget(N(nom, 14))
            r.add_widget(L("DA " + fmt(pay), 15, COL_RED, True, "right", hx=0.5))
            fc.add_widget(r)
        fc.add_widget(Divider())
        fc.add_widget(kv_row("Total", "DA " + fmt(sum(p for _, p in plan["first"])),
                             COL_HEADER))
        self.box.add_widget(fc)

        tc = card(86 + 40 * len(plan["timeline"]))
        tc.add_widget(section_title("Payoff timeline"))
        for nom, months, end in plan["timeline"]:
            r = BoxLayout(size_hint_y=None, height=dp(36))
            r.add_widget(N(nom, 14))
            if months:
                txt = "{}  ({} mo.)".format(end.strftime("%b %Y"), months)
                r.add_widget(L(txt, 13, COL_GREEN, True, "right", hx=0.6))
            else:
                r.add_widget(L("Not within 20 years", 13, COL_RED, True, "right", hx=0.6))
            tc.add_widget(r)
        tc.add_widget(Divider())
        if plan["months"] > 0:
            tc.add_widget(L("Debt-free in {} pay periods (about {:.1f} years)".format(
                plan["months"], plan["months"] / 12.0), 13, COL_HEADER, True, h=26))
        else:
            tc.add_widget(L("Increase the budget to finish sooner.", 13, COL_RED,
                            True, h=26))
        self.box.add_widget(tc)

    def _calc(self, amount):
        self.app.db.set_setting("plan_budget", fmt_plain(amount))
        self.refresh()

    def _on_strategy(self, inst, text):
        self.app.db.set_setting("plan_strategy", text)
        Clock.schedule_once(lambda dt: self.refresh(), 0)

    def _on_priority(self, id_, text):
        self.app.db.set_priority(id_, PRIORITY_BY_NAME.get(text, 2))
        Clock.schedule_once(lambda dt: self.app.refresh(), 0)


# =====================================================================
#                             POPUPS
# =====================================================================
def open_add_menu(app):
    make_popup("Add", [], [
        ("New debt", COL_HEADER, lambda p: (p.dismiss(), open_add_debt_popup(app))),
        ("Expense", COL_RED, lambda p: (p.dismiss(), open_expense_popup(app))),
        ("Salary", COL_GREEN, lambda p: (p.dismiss(), open_salary_popup(app))),
        ("Cancel", COL_MUTED, lambda p: p.dismiss()),
    ])


def open_add_debt_popup(app):
    ti_nom = tinput(hint="Name (Arabic or Latin)", arabic=True)
    sp_type = make_spinner("Debtor (you owe)", ("Debtor (you owe)", "Creditor (owed to you)"))
    ti_du = tinput(hint="Amount", numeric=True)
    ti_paye = tinput(hint="Already paid (optional)", numeric=True)
    sp_pri = make_spinner("Medium", PRIORITIES.values())
    ti_date = tinput(today_str())
    rows = [form_row("Name", ti_nom), form_row("Type", sp_type),
            form_row("Amount due", ti_du), form_row("Paid", ti_paye),
            form_row("Priority", sp_pri), form_row("Date", ti_date)]

    def save(p):
        nom = ti_nom.text.strip()
        du = parse_float(ti_du.text)
        paye = parse_float(ti_paye.text) or 0
        d = parse_date(ti_date.text)
        if not nom:
            p.msg.text = "Enter a name"
        elif not du or du <= 0:
            p.msg.text = "Enter a valid amount"
        elif d is None:
            p.msg.text = "Date format: YYYY-MM-DD"
        else:
            type_ = "debtor" if sp_type.text.startswith("Debtor") else "creditor"
            app.db.add_debt(nom, type_, du, min(paye, du), d.isoformat(),
                            PRIORITY_BY_NAME.get(sp_pri.text, 2))
            p.dismiss()
            app.refresh()

    make_popup("Add New Debt", rows, [("Save", COL_GREEN, save),
                                      ("Cancel", COL_MUTED, lambda p: p.dismiss())])


def open_debt_popup(app, row):
    id_, nom, type_, du, paye, created, prio = row
    rem = max(du - paye, 0)
    is_owe = type_ == "debtor"
    ti_du = tinput(fmt_plain(du), numeric=True)
    sp_pri = make_spinner(PRIORITIES.get(prio, "Medium"), PRIORITIES.values())
    ti_amt = tinput(hint="Amount", numeric=True)
    ti_date = tinput(today_str())

    head = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(48))
    head.add_widget(N(nom, 17, COL_TEXT, True, h=26))
    head.add_widget(L("{}  -  Remaining DA {}  -  Added {}".format(
        "You owe" if is_owe else "Owed to you", fmt(rem), created or ""), 12, COL_MUTED, h=20))
    rows = [head, form_row("Amount due", ti_du)]
    if is_owe:
        rows.append(form_row("Priority", sp_pri))
    rows += [form_row("Payment" if is_owe else "Received", ti_amt), form_row("Date", ti_date)]

    def pay(p):
        amt = parse_float(ti_amt.text)
        d = parse_date(ti_date.text)
        if not amt or amt <= 0:
            p.msg.text = "Enter the amount"
        elif d is None:
            p.msg.text = "Date format: YYYY-MM-DD"
        elif app.db.pay_debt(id_, amt, d.isoformat()) <= 0:
            p.msg.text = "Nothing left to pay"
        else:
            p.dismiss()
            app.refresh()

    def save(p):
        v = parse_float(ti_du.text)
        if not v or v <= 0:
            p.msg.text = "Enter a valid amount"
            return
        app.db.update_debt(id_, v, PRIORITY_BY_NAME.get(sp_pri.text, prio))
        p.dismiss()
        app.refresh()

    def delete(p):
        app.db.delete_debt(id_)
        p.dismiss()
        app.refresh()

    make_popup("Debt Details", rows, [
        ("Record payment" if is_owe else "Record receipt", COL_GREEN, pay),
        ("Save changes", COL_HEADER, save),
        ("Delete", COL_RED, delete),
        ("Cancel", COL_MUTED, lambda p: p.dismiss()),
    ])


def open_expense_popup(app):
    ti_amt = tinput(hint="Amount", numeric=True)
    sp_cat = make_spinner("Food", CATEGORIES)
    ti_note = tinput(hint="Note (optional)", arabic=True)
    ti_date = tinput(today_str())
    rows = [form_row("Amount", ti_amt), form_row("Category", sp_cat),
            form_row("Note", ti_note), form_row("Date", ti_date)]

    def save(p):
        amt = parse_float(ti_amt.text)
        d = parse_date(ti_date.text)
        if not amt or amt <= 0:
            p.msg.text = "Enter a valid amount"
        elif d is None:
            p.msg.text = "Date format: YYYY-MM-DD"
        else:
            app.db.add_txn("expense", amt, ti_note.text.strip(), d.isoformat(), sp_cat.text)
            p.dismiss()
            app.refresh()

    make_popup("Add Expense", rows, [("Save", COL_GREEN, save),
                                     ("Cancel", COL_MUTED, lambda p: p.dismiss())])


def open_salary_popup(app):
    saved = parse_float(app.db.get_setting("salary_amount", "0")) or 0
    ti_amt = tinput(fmt_plain(saved) if saved > 0 else "", hint="Monthly salary", numeric=True)
    ti_day = tinput(str(app.pay_day), numeric=True)
    ti_date = tinput(today_str())
    rows = [form_row("Salary", ti_amt), form_row("Pay day (1-28)", ti_day),
            form_row("Received on", ti_date)]

    def save(p):
        amt = parse_float(ti_amt.text)
        day = parse_float(ti_day.text)
        d = parse_date(ti_date.text)
        if not amt or amt <= 0:
            p.msg.text = "Enter the salary"
        elif not day or not (1 <= int(day) <= 28):
            p.msg.text = "Pay day must be between 1 and 28"
        elif d is None:
            p.msg.text = "Date format: YYYY-MM-DD"
        else:
            app.db.set_setting("salary_amount", fmt_plain(amt))
            app.db.set_setting("pay_day", int(day))
            app.pay_day = int(day)
            app.db.add_txn("salary", amt, "Salary", d.isoformat())
            app.period_start = period_start_for(date.today(), app.pay_day)
            p.dismiss()
            app.refresh()

    make_popup("Record Salary", rows, [("Save", COL_GREEN, save),
                                       ("Cancel", COL_MUTED, lambda p: p.dismiss())])


def open_txn_popup(app, row):
    id_, debt_id, kind, amount, note, d, cat = row
    head = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(76))
    head.add_widget(N(note or cat or KIND_LABEL.get(kind, kind), 17, COL_TEXT, True, h=26))
    head.add_widget(L("{}DA {}".format(KIND_SIGN.get(kind, ""), fmt(amount)), 16,
                      KIND_COLOR.get(kind, COL_TEXT), True, h=24))
    head.add_widget(L("{}  -  {}".format(d, KIND_LABEL.get(kind, kind)), 12, COL_MUTED, h=20))
    buttons = []
    if kind in ("salary", "expense"):
        def delete(p):
            app.db.delete_txn(id_)
            p.dismiss()
            app.refresh()
        buttons.append(("Delete", COL_RED, delete))
    buttons.append(("Close", COL_MUTED, lambda p: p.dismiss()))
    make_popup("Operation", [head], buttons)


def open_range_popup(app):
    start, end = app.get_range()
    ti_from = tinput(start.isoformat())
    ti_to = tinput(end.isoformat())
    rows = [form_row("From", ti_from), form_row("To", ti_to),
            L("Format: YYYY-MM-DD. Applies to Ledger and Stats.", 12, COL_MUTED, h=20)]

    def apply(p):
        a, b = parse_date(ti_from.text), parse_date(ti_to.text)
        if a is None or b is None:
            p.msg.text = "Date format: YYYY-MM-DD"
        elif a > b:
            p.msg.text = "'From' must be before 'To'"
        else:
            app.set_range(a, b)
            p.dismiss()

    def reset(p):
        app.clear_range()
        p.dismiss()

    make_popup("Specific Period", rows, [
        ("Apply", COL_GREEN, apply),
        ("Pay periods", COL_HEADER, reset),
        ("Cancel", COL_MUTED, lambda p: p.dismiss()),
    ])


# =====================================================================
#                           MAIN APP
# =====================================================================
class DebtApp(App):
    def build(self):
        self.title = "Debt Manager"
        # On Android the app folder is replaced on every update, so keep the
        # database in the persistent user data directory instead.
        if platform == "android":
            self.db = Database(os.path.join(self.user_data_dir, "dettes.db"))
        else:
            self.db = Database()
        self.pay_day = int(self.db.get_setting("pay_day", PAY_DAY))
        self.period_start = period_start_for(date.today(), self.pay_day)
        self.custom_range = None  # (start, end) when a specific period is chosen

        outer = FloatLayout()
        outer.add_widget(FlatBg(bg_color=COL_BG, size_hint=(1, 1),
                                pos_hint={"x": 0, "y": 0}))
        root = BoxLayout(orientation="vertical")

        # ---- header ----
        header = FlatBg(bg_color=COL_HEADER, size_hint_y=None, height=dp(56),
                        padding=(dp(14), 0))
        self.header_lbl = L("Debt Manager", 20, COL_GOLD, True, "center")
        header.add_widget(self.header_lbl)
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
        self.titles = {"home": "Debts", "ledger": "Operations",
                       "stats": "Statistics", "plan": "Repayment Plan"}
        nav = FlatBg(bg_color=COL_HEADER, size_hint_y=None, height=dp(56))
        self.nav_btns = {}
        for name, text in (("home", "Debts"), ("ledger", "Ledger"),
                           ("stats", "Stats"), ("plan", "Plan")):
            b = Button(text=text, font_name=UI_FONT, bold=True, font_size=dp(14),
                       background_normal="", background_color=(0, 0, 0, 0))
            b.bind(on_release=lambda inst, n=name: self.switch(n))
            nav.add_widget(b)
            self.nav_btns[name] = b
        root.add_widget(nav)
        outer.add_widget(root)

        fab = FabButton(bg_color=COL_GOLD, size_hint=(None, None),
                        size=(dp(58), dp(58)), pos_hint={"right": 0.96, "y": 0.11})
        fab.bind(on_release=lambda *a: open_add_menu(self))
        outer.add_widget(fab)

        self.switch("home")
        return outer

    # ---- navigation ----
    def switch(self, name):
        self.sm.current = name
        self.header_lbl.text = self.titles[name]
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
