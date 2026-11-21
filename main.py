
# -*- coding: utf-8 -*-
"""服装记工本 V1.0 - Kivy + SQLite 单机记工与工资周期管理"""

import os
import sqlite3
import json
import shutil
import calendar

from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from kivy.app import App
from kivy.metrics import dp
from kivy.lang import Builder
from kivy.core.text import LabelBase
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.popup import Popup
from kivy.uix.spinner import Spinner
from kivy.uix.scrollview import ScrollView


APP_NAME = "服装记工本"
BLUE = (0.08, 0.32, 0.68, 1)
LIGHT = (0.94, 0.96, 0.99, 1)


# ============================================================
# 中文字体设置
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

FONT_PATH = os.path.join(
    BASE_DIR,
    "fonts",
    "NotoSansSC-Regular.otf"
)


def register_chinese_font():
    """
    注册 Noto Sans SC 中文字体。

    将 Kivy 默认使用的 Roboto 字体名称注册为中文字体，
    让原有 Label、Button、TextInput 等控件能够显示中文。
    """

    if not os.path.isfile(FONT_PATH):
        raise FileNotFoundError(
            "找不到中文字体文件：\n"
            + FONT_PATH
            + "\n请确认 fonts 文件夹和字体文件已经放入项目。"
        )

    # 注册默认字体名称
    LabelBase.register(
        name="Roboto",
        fn_regular=FONT_PATH
    )

    # 同时注册独立中文字体名称
    LabelBase.register(
        name="Chinese",
        fn_regular=FONT_PATH
    )


# ============================================================
# 金额与日期处理
# ============================================================

def cents(value):
    return int(
        (
            Decimal(str(value or "0")) * 100
        ).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP
        )
    )


def money(c):
    return f"¥{int(c) / 100:.2f}"


def parse_date(s):
    return date.fromisoformat(s)


def period_for(work_date, pay_day):
    """
    工资周期：
    上一个发薪日的次日至本次发薪日。

    如果当月不存在指定发薪日，
    自动使用当月最后一天。
    """

    d = parse_date(work_date) if isinstance(work_date, str) else work_date

    def payday(y, m):
        last = calendar.monthrange(y, m)[1]
        return date(y, m, min(int(pay_day), last))

    this_pay = payday(d.year, d.month)

    if d <= this_pay:
        end = this_pay

        if d.month == 1:
            py, pm = d.year - 1, 12
        else:
            py, pm = d.year, d.month - 1

        start = payday(py, pm) + timedelta(days=1)

    else:
        if d.month == 12:
            ny, nm = d.year + 1, 1
        else:
            ny, nm = d.year, d.month + 1

        end = payday(ny, nm)
        start = this_pay + timedelta(days=1)

    return start.isoformat(), end.isoformat()


# ============================================================
# SQLite 数据库
# ============================================================

class DB:

    def __init__(self, path):
        self.path = path

        os.makedirs(
            os.path.dirname(path),
            exist_ok=True
        )

        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row

        self.conn.execute("PRAGMA foreign_keys=ON")

        self.init()

    def init(self):

        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        INSERT OR IGNORE INTO settings(key,value)
        VALUES('pay_day','15');

        CREATE TABLE IF NOT EXISTS bills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            work_date TEXT NOT NULL,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS bill_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bill_id INTEGER NOT NULL
                REFERENCES bills(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            quantity INTEGER NOT NULL CHECK(quantity>=0),
            unit_price_cents INTEGER NOT NULL
                CHECK(unit_price_cents>=0)
        );

        CREATE TABLE IF NOT EXISTS wage_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            period_start TEXT NOT NULL,
            period_end TEXT NOT NULL,
            paid_date TEXT NOT NULL,
            amount_cents INTEGER NOT NULL
                CHECK(amount_cents>0),
            note TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS operation_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            detail TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS price_memory (
            name TEXT PRIMARY KEY,
            unit_price_cents INTEGER NOT NULL
        );
        """)

        self.conn.commit()

    def setting(self, key, default=""):

        row = self.conn.execute(
            "SELECT value FROM settings WHERE key=?",
            (key,)
        ).fetchone()

        return row["value"] if row else default

    def set_setting(self, key, value):

        self.conn.execute(
            "INSERT OR REPLACE INTO settings VALUES(?,?)",
            (key, str(value))
        )

        self.conn.commit()

    def bill_total(self, bill_id):

        row = self.conn.execute(
            """
            SELECT COALESCE(
                SUM(quantity*unit_price_cents),0
            ) v
            FROM bill_items
            WHERE bill_id=?
            """,
            (bill_id,)
        ).fetchone()

        return row["v"]

    def bills(self):

        return self.conn.execute("""
        SELECT
            b.*,
            COUNT(i.id) item_count,
            COALESCE(
                SUM(i.quantity*i.unit_price_cents),0
            ) total
        FROM bills b
        LEFT JOIN bill_items i ON i.bill_id=b.id
        GROUP BY b.id
        ORDER BY b.work_date DESC,b.id DESC
        """).fetchall()

    def save_bill(self, bill_id, work_date, name, items):

        if not name.strip() or not items:
            raise ValueError(
                "请填写账单名称并至少添加一条明细"
            )

        for item in items:

            if (
                not item["name"].strip()
                or int(item["quantity"]) < 0
                or int(cents(item["price"])) < 0
            ):
                raise ValueError(
                    "明细名称、数量或工价不正确"
                )

        with self.conn:

            if bill_id:

                self.conn.execute(
                    """
                    UPDATE bills
                    SET work_date=?,name=?
                    WHERE id=?
                    """,
                    (work_date, name.strip(), bill_id)
                )

                self.conn.execute(
                    "DELETE FROM bill_items WHERE bill_id=?",
                    (bill_id,)
                )

                action = "修改账单"

            else:

                cur = self.conn.execute(
                    """
                    INSERT INTO bills(
                        work_date,name,created_at
                    )
                    VALUES(?,?,?)
                    """,
                    (
                        work_date,
                        name.strip(),
                        datetime.now().isoformat(
                            timespec="seconds"
                        )
                    )
                )

                bill_id = cur.lastrowid
                action = "新增账单"

            for it in items:

                pc = cents(it["price"])

                self.conn.execute(
                    """
                    INSERT INTO bill_items(
                        bill_id,name,quantity,unit_price_cents
                    )
                    VALUES(?,?,?,?)
                    """,
                    (
                        bill_id,
                        it["name"].strip(),
                        int(it["quantity"]),
                        pc
                    )
                )

                self.conn.execute(
                    """
                    INSERT OR REPLACE INTO price_memory(
                        name,unit_price_cents
                    )
                    VALUES(?,?)
                    """,
                    (it["name"].strip(), pc)
                )

            self.conn.execute(
                """
                INSERT INTO operation_log(
                    action,detail,created_at
                )
                VALUES(?,?,?)
                """,
                (
                    action,
                    f"账单编号:{bill_id}",
                    datetime.now().isoformat(
                        timespec="seconds"
                    )
                )
            )

        return bill_id

    def delete_bill(self, bill_id):

        with self.conn:

            self.conn.execute(
                "DELETE FROM bills WHERE id=?",
                (bill_id,)
            )

            self.conn.execute(
                """
                INSERT INTO operation_log(
                    action,detail,created_at
                )
                VALUES(?,?,?)
                """,
                (
                    "删除账单",
                    f"账单编号:{bill_id}",
                    datetime.now().isoformat(
                        timespec="seconds"
                    )
                )
            )

    def bill_items(self, bill_id):

        return self.conn.execute(
            """
            SELECT *
            FROM bill_items
            WHERE bill_id=?
            ORDER BY id
            """,
            (bill_id,)
        ).fetchall()

    def period_summary(self, start, end):

        row = self.conn.execute(
            """
            SELECT COALESCE(
                SUM(i.quantity*i.unit_price_cents),0
            ) total
            FROM bills b
            JOIN bill_items i ON i.bill_id=b.id
            WHERE b.work_date BETWEEN ? AND ?
            """,
            (start, end)
        ).fetchone()

        paid = self.conn.execute(
            """
            SELECT COALESCE(SUM(amount_cents),0) v
            FROM wage_payments
            WHERE period_start=? AND period_end=?
            """,
            (start, end)
        ).fetchone()["v"]

        return row["total"], paid

    def payments(self, start, end):

        return self.conn.execute(
            """
            SELECT *
            FROM wage_payments
            WHERE period_start=? AND period_end=?
            ORDER BY paid_date DESC,id DESC
            """,
            (start, end)
        ).fetchall()

    def add_payment(
        self,
        start,
        end,
        paid_date,
        amount_cents,
        note=""
    ):

        due, paid = self.period_summary(start, end)

        if amount_cents <= 0:
            raise ValueError("发放金额必须大于0")

        if amount_cents > due - paid:
            raise ValueError(
                "发放金额超过未发工资，当前最多可记录 "
                + money(due - paid)
            )

        with self.conn:

            self.conn.execute(
                """
                INSERT INTO wage_payments(
                    period_start,
                    period_end,
                    paid_date,
                    amount_cents,
                    note
                )
                VALUES(?,?,?,?,?)
                """,
                (
                    start,
                    end,
                    paid_date,
                    amount_cents,
                    note
                )
            )

            self.conn.execute(
                """
                INSERT INTO operation_log(
                    action,detail,created_at
                )
                VALUES(?,?,?)
                """,
                (
                    "记录工资发放",
                    f"{start}至{end}，{money(amount_cents)}",
                    datetime.now().isoformat(
                        timespec="seconds"
                    )
                )
            )

    def delete_payment(self, payment_id):

        with self.conn:

            self.conn.execute(
                "DELETE FROM wage_payments WHERE id=?",
                (payment_id,)
            )

            self.conn.execute(
                """
                INSERT INTO operation_log(
                    action,detail,created_at
                )
                VALUES(?,?,?)
                """,
                (
                    "删除发放记录",
                    f"记录编号:{payment_id}",
                    datetime.now().isoformat(
                        timespec="seconds"
                    )
                )
            )


# ============================================================
# 首页
# ============================================================

class MainScreen(Screen):

    def on_pre_enter(self, *args):
        self.refresh()

    def refresh(self):

        root = self.ids.content
        root.clear_widgets()

        db = App.get_running_app().db

        today = date.today()

        pd = int(db.setting("pay_day", "15"))

        start, end = period_for(today, pd)

        due, paid = db.period_summary(start, end)

        all_total = db.conn.execute(
            """
            SELECT COALESCE(
                SUM(i.quantity*i.unit_price_cents),0
            ) v
            FROM bill_items i
            """
        ).fetchone()["v"]

        root.add_widget(
            Label(
                text=(
                    f"[b]服装记工本[/b]\n"
                    f"累计总钱数  {money(all_total)}\n"
                    f"本期应发  {money(due)}\n"
                    f"已发  {money(paid)}    "
                    f"未发  {money(due-paid)}"
                ),
                markup=True,
                size_hint_y=None,
                height=dp(130),
                color=(0.05, 0.16, 0.32, 1)
            )
        )

        root.add_widget(
            Button(
                text="＋ 新增记工账单",
                size_hint_y=None,
                height=dp(48),
                background_color=BLUE,
                on_release=lambda *_: setattr(
                    self.manager,
                    "current",
                    "edit"
                )
            )
        )

        root.add_widget(
            Label(
                text="账单列表（点击查看详情）",
                size_hint_y=None,
                height=dp(38),
                color=(0.1, 0.1, 0.1, 1)
            )
        )

        for b in db.bills():

            btn = Button(
                text=(
                    f"{b['work_date']}   "
                    f"{b['name']}   "
                    f"{b['item_count']}项   "
                    f"{money(b['total'])}"
                ),
                size_hint_y=None,
                height=dp(52),
                color=(0.08, 0.12, 0.2, 1),
                background_color=LIGHT
            )

            btn.bind(
                on_release=lambda _, bid=b["id"]:
                self.open_detail(bid)
            )

            root.add_widget(btn)

    def open_detail(self, bill_id):

        self.manager.get_screen(
            "detail"
        ).bill_id = bill_id

        self.manager.current = "detail"


# ============================================================
# 新增记工账单
# ============================================================

class EditScreen(Screen):

    bill_id = None
    items = []

    def on_pre_enter(self, *args):

        self.bill_id = None
        self.items = []

        self.ids.bill_date.text = date.today().isoformat()
        self.ids.bill_name.text = "服装加工"

        self.ids.item_rows.clear_widgets()

        self.add_item()

    def add_item(self):

        row = GridLayout(
            cols=4,
            size_hint_y=None,
            height=dp(48),
            spacing=dp(4)
        )

        name = TextInput(
            hint_text="名称",
            multiline=False
        )

        qty = TextInput(
            hint_text="数量",
            multiline=False,
            input_filter="int"
        )

        price = TextInput(
            hint_text="工价",
            multiline=False,
            input_filter="float"
        )

        row.add_widget(name)
        row.add_widget(qty)
        row.add_widget(price)

        delbtn = Button(
            text="删除",
            size_hint_x=None,
            width=dp(56)
        )

        row.add_widget(delbtn)

        entry = {
            "row": row,
            "name": name,
            "qty": qty,
            "price": price
        }

        self.items.append(entry)

        delbtn.bind(
            on_release=lambda *_: self.remove_item(entry)
        )

        name.bind(
            text=lambda _, v, e=entry: self.autofill(e)
        )

        self.ids.item_rows.add_widget(row)

    def autofill(self, entry):

        if entry["price"].text:
            return

        r = App.get_running_app().db.conn.execute(
            """
            SELECT unit_price_cents
            FROM price_memory
            WHERE name=?
            """,
            (entry["name"].text.strip(),)
        ).fetchone()

        if r:

            entry["price"].text = (
                f"{r['unit_price_cents'] / 100:.2f}"
            )

    def remove_item(self, entry):

        if len(self.items) <= 1:
            return

        self.items.remove(entry)

        self.ids.item_rows.remove_widget(
            entry["row"]
        )

    def save(self):

        try:

            items = []

            for e in self.items:

                items.append({
                    "name": e["name"].text,
                    "quantity": int(
                        e["qty"].text or "0"
                    ),
                    "price": e["price"].text or "0"
                })

            App.get_running_app().db.save_bill(
                None,
                self.ids.bill_date.text,
                self.ids.bill_name.text,
                items
            )

            self.manager.current = "main"

        except Exception as ex:

            show_msg("保存失败", str(ex))


# ============================================================
# 账单详情
# ============================================================

class DetailScreen(Screen):

    bill_id = None

    def on_pre_enter(self, *args):
        self.refresh()

    def refresh(self):

        db = App.get_running_app().db

        b = db.conn.execute(
            "SELECT * FROM bills WHERE id=?",
            (self.bill_id,)
        ).fetchone()

        if not b:
            self.manager.current = "main"
            return

        self.ids.detail_title.text = (
            f"{b['work_date']}  {b['name']}"
        )

        box = self.ids.detail_rows

        box.clear_widgets()

        total = 0

        for it in db.bill_items(self.bill_id):

            amount = (
                it["quantity"] * it["unit_price_cents"]
            )

            total += amount

            box.add_widget(
                Label(
                    text=(
                        f"{it['name']}    "
                        f"{it['quantity']}    "
                        f"{money(it['unit_price_cents'])}    "
                        f"{money(amount)}"
                    ),
                    size_hint_y=None,
                    height=dp(42),
                    color=(0.08, 0.12, 0.2, 1)
                )
            )

        self.ids.detail_total.text = (
            "本张账单总工钱：" + money(total)
        )

    def delete(self):

        confirm = Popup(
            title="确认删除",
            content=Label(
                text="确定删除这张账单及其全部明细吗？"
            ),
            size_hint=(.85, .35)
        )

        btn = Button(
            text="确认删除",
            size_hint_y=None,
            height=dp(46)
        )

        btn.bind(
            on_release=lambda *_: (
                App.get_running_app().db.delete_bill(
                    self.bill_id
                ),
                confirm.dismiss(),
                setattr(self.manager, "current", "main")
            )
        )

        content = BoxLayout(
            orientation="vertical"
        )

        content.add_widget(
            Label(
                text="删除后会重新计算所属工资周期。"
            )
        )

        content.add_widget(btn)

        confirm.content = content

        confirm.open()


# ============================================================
# 工资统计与发放
# ============================================================

class WageScreen(Screen):

    def on_pre_enter(self, *args):
        self.refresh()

    def refresh(self):

        db = App.get_running_app().db

        pd = int(db.setting("pay_day", "15"))

        start, end = period_for(date.today(), pd)

        due, paid = db.period_summary(start, end)

        self.ids.wage_summary.text = (
            f"工资周期：{start} 至 {end}\n"
            f"应发：{money(due)}\n"
            f"已发：{money(paid)}\n"
            f"未发：{money(due-paid)}"
        )

        rows = self.ids.payment_rows

        rows.clear_widgets()

        for p in db.payments(start, end):

            rows.add_widget(
                Label(
                    text=(
                        f"{p['paid_date']}   "
                        f"{money(p['amount_cents'])}   "
                        f"{p['note']}"
                    ),
                    size_hint_y=None,
                    height=dp(40),
                    color=(0.08, 0.12, 0.2, 1)
                )
            )

    def add_payment(self):

        db = App.get_running_app().db

        pd = int(db.setting("pay_day", "15"))

        start, end = period_for(date.today(), pd)

        amount = TextInput(
            hint_text="发放金额，例如 1000.00",
            multiline=False,
            input_filter="float"
        )

        paid_date = TextInput(
            text=date.today().isoformat(),
            multiline=False
        )

        note = TextInput(
            hint_text="备注（可不填）",
            multiline=False
        )

        content = BoxLayout(
            orientation="vertical",
            spacing=dp(8),
            padding=dp(10)
        )

        content.add_widget(paid_date)
        content.add_widget(amount)
        content.add_widget(note)

        pop = Popup(
            title="记录工资发放",
            content=content,
            size_hint=(.9, .55)
        )

        save = Button(
            text="保存发放记录",
            size_hint_y=None,
            height=dp(46)
        )

        content.add_widget(save)

        def do_save(*_):

            try:

                db.add_payment(
                    start,
                    end,
                    paid_date.text,
                    cents(amount.text),
                    note.text
                )

                pop.dismiss()

                self.refresh()

            except Exception as ex:

                show_msg("无法保存", str(ex))

        save.bind(on_release=do_save)

        pop.open()


# ============================================================
# 软件设置
# ============================================================

class SettingsScreen(Screen):

    def on_pre_enter(self, *args):

        self.ids.pay_day.text = (
            App.get_running_app().db.setting(
                "pay_day",
                "15"
            )
        )

    def save(self):

        try:

            n = int(self.ids.pay_day.text)

            if n < 1 or n > 31:
                raise ValueError(
                    "发薪日必须为1至31"
                )

            App.get_running_app().db.set_setting(
                "pay_day",
                n
            )

            show_msg(
                "保存成功",
                "工资发放日已更新。特殊月份自动按当月最后一天处理。"
            )

        except Exception as ex:

            show_msg("设置失败", str(ex))

    def backup(self):

        db = App.get_running_app().db

        target = os.path.join(
            App.get_running_app().user_data_dir,
            "服装记工本备份_"
            + datetime.now().strftime("%Y%m%d_%H%M%S")
            + ".db"
        )

        db.conn.commit()

        shutil.copy2(db.path, target)

        show_msg(
            "备份完成",
            "备份文件已保存到应用私有目录：\n" + target
        )


# ============================================================
# 消息提示
# ============================================================

def show_msg(title, message):

    Popup(
        title=title,
        content=Label(text=message),
        size_hint=(.88, .38)
    ).open()


# ============================================================
# Kivy 界面布局
# ============================================================

KV = r"""

#:import dp kivy.metrics.dp

<MainScreen>:

    BoxLayout:
        orientation: "vertical"
        padding: dp(10)
        spacing: dp(8)

        ScrollView:

            GridLayout:
                id: content
                cols: 1
                spacing: dp(6)
                size_hint_y: None
                height: self.minimum_height


<EditScreen>:

    BoxLayout:
        orientation: "vertical"
        padding: dp(10)
        spacing: dp(8)

        Label:
            text: "新增记工账单"
            size_hint_y: None
            height: dp(42)
            color: 0.05,0.16,0.32,1

        TextInput:
            id: bill_date
            hint_text: "工作日期 YYYY-MM-DD"
            multiline: False
            size_hint_y: None
            height: dp(48)

        TextInput:
            id: bill_name
            hint_text: "账单名称"
            multiline: False
            size_hint_y: None
            height: dp(48)

        Label:
            text: "名称 / 数量 / 工价 / 删除"
            size_hint_y: None
            height: dp(32)
            color: 0.1,0.1,0.1,1

        ScrollView:

            GridLayout:
                id: item_rows
                cols: 1
                spacing: dp(5)
                size_hint_y: None
                height: self.minimum_height

        Button:
            text: "＋ 添加明细"
            size_hint_y: None
            height: dp(46)
            on_release: root.add_item()

        Button:
            text: "保存账单"
            size_hint_y: None
            height: dp(50)
            background_color: 0.08,0.32,0.68,1
            on_release: root.save()

        Button:
            text: "返回"
            size_hint_y: None
            height: dp(42)
            on_release: app.root.current = "main"


<DetailScreen>:

    BoxLayout:
        orientation: "vertical"
        padding: dp(10)
        spacing: dp(8)

        Label:
            id: detail_title
            text: "账单详情"
            size_hint_y: None
            height: dp(45)
            color: 0.05,0.16,0.32,1

        Label:
            text: "名称       数量       工价       钱数"
            size_hint_y: None
            height: dp(34)
            color: 0.1,0.1,0.1,1

        ScrollView:

            GridLayout:
                id: detail_rows
                cols: 1
                size_hint_y: None
                height: self.minimum_height

        Label:
            id: detail_total
            text: "本张账单总工钱：¥0.00"
            size_hint_y: None
            height: dp(48)
            color: 0.05,0.45,0.2,1

        Button:
            text: "删除账单"
            size_hint_y: None
            height: dp(46)
            on_release: root.delete()

        Button:
            text: "返回首页"
            size_hint_y: None
            height: dp(44)
            on_release: app.root.current = "main"


<WageScreen>:

    BoxLayout:
        orientation: "vertical"
        padding: dp(12)
        spacing: dp(8)

        Label:
            text: "工资统计与发放"
            size_hint_y: None
            height: dp(44)
            color: 0.05,0.16,0.32,1

        Label:
            id: wage_summary
            text: ""
            size_hint_y: None
            height: dp(130)
            color: 0.05,0.16,0.32,1

        Button:
            text: "＋ 记录工资发放"
            size_hint_y: None
            height: dp(48)
            on_release: root.add_payment()

        Label:
            text: "本期发放记录"
            size_hint_y: None
            height: dp(36)
            color: 0.1,0.1,0.1,1

        ScrollView:

            GridLayout:
                id: payment_rows
                cols: 1
                size_hint_y: None
                height: self.minimum_height

        Button:
            text: "返回首页"
            size_hint_y: None
            height: dp(44)
            on_release: app.root.current = "main"


<SettingsScreen>:

    BoxLayout:
        orientation: "vertical"
        padding: dp(14)
        spacing: dp(10)

        Label:
            text: "软件设置"
            size_hint_y: None
            height: dp(44)
            color: 0.05,0.16,0.32,1

        Label:
            text: "每月发工资日（1至31日）"
            size_hint_y: None
            height: dp(36)
            color: 0.1,0.1,0.1,1

        TextInput:
            id: pay_day
            hint_text: "例如 15"
            input_filter: "int"
            multiline: False
            size_hint_y: None
            height: dp(48)

        Button:
            text: "保存工资设置"
            size_hint_y: None
            height: dp(48)
            on_release: root.save()

        Button:
            text: "立即备份数据库"
            size_hint_y: None
            height: dp(48)
            on_release: root.backup()

        Label:
            text: "数据保存在本机应用私有目录。卸载软件可能导致数据被系统删除，请定期备份。"
            color: 0.35,0.35,0.35,1

        Button:
            text: "返回首页"
            size_hint_y: None
            height: dp(44)
            on_release: app.root.current = "main"

"""


# ============================================================
# 软件主程序
# ============================================================

class GarmentLedgerApp(App):

    title = APP_NAME

    def build(self):

        # 第一步：注册中文字体
        # 必须在加载 KV 和创建界面控件之前执行
        register_chinese_font()

        # 第二步：初始化数据库
        self.db = DB(
            os.path.join(
                self.user_data_dir,
                "garment_ledger.sqlite3"
            )
        )

        # 第三步：加载界面
        Builder.load_string(KV)

        # 第四步：创建页面管理器
        sm = ScreenManager()

        sm.add_widget(
            MainScreen(name="main")
        )

        sm.add_widget(
            EditScreen(name="edit")
        )

        sm.add_widget(
            DetailScreen(name="detail")
        )

        sm.add_widget(
            WageScreen(name="wage")
        )

        sm.add_widget(
            SettingsScreen(name="settings")
        )

        # 第五步：底部导航
        shell = BoxLayout(
            orientation="vertical"
        )

        nav = GridLayout(
            cols=3,
            size_hint_y=None,
            height=dp(48),
            spacing=dp(3)
        )

        for label, target in [
            ("记工首页", "main"),
            ("工资管理", "wage"),
            ("设置", "settings")
        ]:

            nav.add_widget(
                Button(
                    text=label,
                    on_release=lambda _, t=target:
                    setattr(sm, "current", t)
                )
            )

        shell.add_widget(nav)
        shell.add_widget(sm)

        return shell

    def on_stop(self):

        if hasattr(self, "db"):

            self.db.conn.commit()
            self.db.conn.close()


if __name__ == "__main__":

    GarmentLedgerApp().run()

