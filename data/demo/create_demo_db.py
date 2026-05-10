"""
Скрипт создания демо-базы данных для Ru2SQL.

Запуск из корня проекта:
    python data/demo/create_demo_db.py
"""

import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "sales.sqlite"


def create_db():
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.executescript("""
        CREATE TABLE customers (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT    NOT NULL,
            city       TEXT,
            phone      TEXT,
            email      TEXT,
            created_at TEXT    DEFAULT (date('now'))
        );

        CREATE TABLE managers (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL,
            department TEXT
        );

        CREATE TABLE products (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            name      TEXT    NOT NULL,
            category  TEXT,
            price     REAL    NOT NULL,
            is_active INTEGER DEFAULT 1
        );

        -- amount — итоговая сумма заказа в рублях (не путать с order_items.price)
        CREATE TABLE orders (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER REFERENCES customers(id),
            manager_id  INTEGER REFERENCES managers(id),
            amount      REAL    NOT NULL,
            status      TEXT    DEFAULT 'paid',
            order_date  TEXT    NOT NULL
        );

        -- price — цена за единицу товара; quantity — количество штук
        CREATE TABLE order_items (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id   INTEGER REFERENCES orders(id),
            product_id INTEGER REFERENCES products(id),
            quantity   INTEGER NOT NULL,
            price      REAL    NOT NULL
        );
    """)

    customers = [
        ("ООО Ромашка",          "Москва",          "+7 495 111-22-33", "romashka@example.com"),
        ("ИП Петров",            "Санкт-Петербург", "+7 812 333-44-55", "petrov@example.com"),
        ("Сеть магазинов Радуга","Казань",           "+7 843 555-66-77", "raduga@example.com"),
        ("АО Стройснаб",         "Екатеринбург",    "+7 343 777-88-99", "stroysnab@example.com"),
        ("ООО Технолайн",        "Новосибирск",     "+7 383 999-00-11", "technoline@example.com"),
        ("ИП Сидорова",          "Москва",          "+7 495 222-33-44", "sidorova@example.com"),
        ("ООО Прогресс",         "Краснодар",       "+7 861 444-55-66", "progress@example.com"),
        ("ЗАО Мегатрейд",        "Самара",          "+7 846 666-77-88", "megatrade@example.com"),
    ]
    cur.executemany(
        "INSERT INTO customers (name, city, phone, email) VALUES (?,?,?,?)",
        customers,
    )

    managers = [
        ("Иванов Алексей",  "Продажи"),
        ("Смирнова Мария",  "Продажи"),
        ("Козлов Дмитрий",  "Корпоративные клиенты"),
        ("Новикова Анна",   "Корпоративные клиенты"),
    ]
    cur.executemany("INSERT INTO managers (name, department) VALUES (?,?)", managers)

    products_data = [
        ("Ноутбук Dell XPS 15",      "Электроника",         89990.0, 1),
        ("Монитор LG 27inch",         "Электроника",         24990.0, 1),
        ("Клавиатура Logitech MX",    "Периферия",            8990.0, 1),
        ("Мышь Logitech G502",        "Периферия",            5490.0, 1),
        ("Наушники Sony WH-1000XM5",  "Аудио",               29990.0, 1),
        ("Веб-камера Logitech C920",  "Периферия",            7990.0, 1),
        ("SSD Samsung 1TB",           "Комплектующие",        6990.0, 1),
        ("Принтер HP LaserJet",       "Оргтехника",          18990.0, 0),
        ("Роутер TP-Link AX3000",     "Сетевое оборудование", 4990.0, 1),
        ("ИБП APC 1500VA",            "Сетевое оборудование",14990.0, 1),
    ]
    cur.executemany(
        "INSERT INTO products (name, category, price, is_active) VALUES (?,?,?,?)",
        products_data,
    )

    random.seed(42)
    start = date(2025, 1, 1)
    end   = date(2026, 4, 30)
    delta = (end - start).days
    statuses = ["paid", "paid", "paid", "pending", "cancelled"]

    order_id = 1
    items_rows = []
    for _ in range(120):
        d           = start + timedelta(days=random.randint(0, delta))
        customer_id = random.randint(1, 8)
        manager_id  = random.randint(1, 4)
        status      = random.choice(statuses)
        n_items     = random.randint(1, 4)
        picked      = random.sample(range(1, 11), n_items)
        total = 0.0
        for prod_id in picked:
            qty   = random.randint(1, 5)
            price = products_data[prod_id - 1][2]
            total += qty * price
            items_rows.append((order_id, prod_id, qty, price))
        cur.execute(
            "INSERT INTO orders (customer_id, manager_id, amount, status, order_date) "
            "VALUES (?,?,?,?,?)",
            (customer_id, manager_id, round(total, 2), status, d.isoformat()),
        )
        order_id += 1

    cur.executemany(
        "INSERT INTO order_items (order_id, product_id, quantity, price) VALUES (?,?,?,?)",
        items_rows,
    )

    conn.commit()
    conn.close()

    print(f"База создана: {DB_PATH}")
    conn2 = sqlite3.connect(DB_PATH)
    for tbl in ["customers", "managers", "products", "orders", "order_items"]:
        cnt = conn2.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        print(f"  {tbl}: {cnt} строк")
    conn2.close()


if __name__ == "__main__":
    create_db()
