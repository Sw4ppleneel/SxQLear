"""
seed_test_db.py — Creates a realistic ecommerce SQLite database for testing SxQLear.

Usage:
    python scripts/seed_test_db.py

Creates: ~/.sxqlear/test_ecommerce.db

Tables:
    customers, addresses, products, categories, orders, order_items,
    reviews, discount_codes, shipments
"""
from __future__ import annotations

import random
import sqlite3
import string
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path.home() / ".sxqlear" / "test_ecommerce.db"

DDL = """
CREATE TABLE IF NOT EXISTS categories (
    category_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL UNIQUE,
    parent_id     INTEGER REFERENCES categories(category_id),
    description   TEXT,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
    product_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    sku           TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL,
    description   TEXT,
    category_id   INTEGER REFERENCES categories(category_id),
    price_cents   INTEGER NOT NULL,
    cost_cents    INTEGER,
    stock_qty     INTEGER NOT NULL DEFAULT 0,
    is_active     INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS customers (
    customer_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT NOT NULL UNIQUE,
    first_name    TEXT NOT NULL,
    last_name     TEXT NOT NULL,
    phone         TEXT,
    is_verified   INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL,
    last_login_at TEXT
);

CREATE TABLE IF NOT EXISTS addresses (
    address_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id   INTEGER NOT NULL REFERENCES customers(customer_id),
    line1         TEXT NOT NULL,
    line2         TEXT,
    city          TEXT NOT NULL,
    state         TEXT,
    postal_code   TEXT NOT NULL,
    country_code  TEXT NOT NULL DEFAULT 'US',
    is_default    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS discount_codes (
    code_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    code          TEXT NOT NULL UNIQUE,
    discount_pct  REAL NOT NULL,
    max_uses      INTEGER,
    uses_count    INTEGER NOT NULL DEFAULT 0,
    expires_at    TEXT,
    is_active     INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS orders (
    order_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id       INTEGER NOT NULL REFERENCES customers(customer_id),
    shipping_address_id INTEGER REFERENCES addresses(address_id),
    discount_code_id  INTEGER REFERENCES discount_codes(code_id),
    status            TEXT NOT NULL DEFAULT 'pending',
    subtotal_cents    INTEGER NOT NULL,
    discount_cents    INTEGER NOT NULL DEFAULT 0,
    shipping_cents    INTEGER NOT NULL DEFAULT 0,
    total_cents       INTEGER NOT NULL,
    currency          TEXT NOT NULL DEFAULT 'USD',
    placed_at         TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS order_items (
    item_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id      INTEGER NOT NULL REFERENCES orders(order_id),
    product_id    INTEGER NOT NULL REFERENCES products(product_id),
    quantity      INTEGER NOT NULL,
    unit_price_cents INTEGER NOT NULL,
    total_cents   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS shipments (
    shipment_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id      INTEGER NOT NULL REFERENCES orders(order_id),
    carrier       TEXT,
    tracking_number TEXT,
    status        TEXT NOT NULL DEFAULT 'pending',
    shipped_at    TEXT,
    delivered_at  TEXT,
    estimated_delivery TEXT
);

CREATE TABLE IF NOT EXISTS reviews (
    review_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id    INTEGER NOT NULL REFERENCES products(product_id),
    customer_id   INTEGER NOT NULL REFERENCES customers(customer_id),
    rating        INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
    title         TEXT,
    body          TEXT,
    is_verified_purchase INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL
);
"""

# ── Data generators ────────────────────────────────────────────────────────────

def rnd_date(days_ago_max=730) -> str:
    """Positive = past, negative = future."""
    if days_ago_max >= 0:
        delta = random.randint(0, max(1, days_ago_max))
        dt = datetime.now() - timedelta(days=delta)
    else:
        delta = random.randint(1, max(1, abs(days_ago_max)))
        dt = datetime.now() + timedelta(days=delta)
    return dt.strftime("%Y-%m-%d %H:%M:%S")

def rnd_email(first: str, last: str, i: int) -> str:
    domains = ["gmail.com", "yahoo.com", "outlook.com", "proton.me", "icloud.com"]
    return f"{first.lower()}.{last.lower()}{i}@{random.choice(domains)}"

FIRST_NAMES = ["Alice","Bob","Carol","David","Emma","Frank","Grace","Henry","Isla","Jack",
               "Karen","Liam","Mia","Noah","Olivia","Paul","Quinn","Rachel","Sam","Tina",
               "Uma","Victor","Wendy","Xander","Yara","Zoe","Ava","Ben","Chloe","Dylan"]
LAST_NAMES  = ["Smith","Johnson","Williams","Brown","Jones","Garcia","Miller","Davis",
               "Wilson","Moore","Taylor","Anderson","Thomas","Jackson","White","Harris",
               "Martin","Thompson","Lee","Walker","Hall","Allen","Young","King","Scott"]
CITIES = [("New York","NY","10001"),("Los Angeles","CA","90001"),("Chicago","IL","60601"),
          ("Houston","TX","77001"),("Phoenix","AZ","85001"),("Portland","OR","97201"),
          ("Seattle","WA","98101"),("Denver","CO","80201"),("Atlanta","GA","30301"),
          ("Boston","MA","02101")]
CARRIERS = ["FedEx","UPS","USPS","DHL","OnTrac"]
ORDER_STATUSES = ["pending","processing","shipped","delivered","cancelled","refunded"]

def seed(conn: sqlite3.Connection):
    cur = conn.cursor()

    # Categories
    cats = [
        (1, "Electronics", None, "Consumer electronics and gadgets"),
        (2, "Clothing", None, "Apparel and fashion"),
        (3, "Home & Garden", None, "Home improvement and garden"),
        (4, "Sports", None, "Sports and outdoor equipment"),
        (5, "Laptops", 1, "Laptops and ultrabooks"),
        (6, "Smartphones", 1, "Mobile phones and accessories"),
        (7, "Men's Clothing", 2, "Men's apparel"),
        (8, "Women's Clothing", 2, "Women's apparel"),
        (9, "Furniture", 3, "Indoor furniture"),
        (10, "Fitness", 4, "Gym and fitness equipment"),
    ]
    cur.executemany(
        "INSERT OR IGNORE INTO categories(category_id,name,parent_id,description,created_at) VALUES(?,?,?,?,?)",
        [(c[0], c[1], c[2], c[3], rnd_date(1000)) for c in cats]
    )

    # Products
    product_data = [
        ("LAP-001","ThinkPad X1 Carbon",5,149999,80000,42),
        ("LAP-002","MacBook Air M3",5,129999,70000,88),
        ("LAP-003","Dell XPS 15",5,174999,95000,31),
        ("PHN-001","iPhone 16 Pro",6,99999,55000,210),
        ("PHN-002","Samsung Galaxy S25",6,89999,48000,175),
        ("PHN-003","Google Pixel 9",6,69999,38000,95),
        ("CLM-001","Merino Wool Sweater",7,8999,3200,340),
        ("CLM-002","Oxford Dress Shirt",7,5499,1800,520),
        ("CLF-001","Floral Sundress",8,6999,2400,290),
        ("CLF-002","Cashmere Cardigan",8,12999,5500,140),
        ("FRN-001","Ergonomic Office Chair",9,39999,18000,67),
        ("FRN-002","Standing Desk",9,59999,28000,43),
        ("FIT-001","Adjustable Dumbbells",10,18999,9000,128),
        ("FIT-002","Yoga Mat Pro",10,4999,1800,305),
        ("FIT-003","Resistance Bands Set",10,2999,900,420),
    ]
    for sku, name, cat_id, price, cost, stock in product_data:
        cur.execute(
            "INSERT OR IGNORE INTO products(sku,name,category_id,price_cents,cost_cents,stock_qty,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
            (sku, name, cat_id, price, cost, stock, rnd_date(500), rnd_date(30))
        )

    # Customers
    customer_ids = []
    for i in range(1, 51):
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        email = rnd_email(first, last, i)
        created = rnd_date(600)
        cur.execute(
            "INSERT OR IGNORE INTO customers(email,first_name,last_name,is_verified,created_at,last_login_at) VALUES(?,?,?,?,?,?)",
            (email, first, last, random.randint(0,1), created, rnd_date(7))
        )
        customer_ids.append(cur.lastrowid)

    # Re-fetch real customer IDs
    customer_ids = [r[0] for r in cur.execute("SELECT customer_id FROM customers").fetchall()]

    # Addresses
    address_map: dict[int, int] = {}  # customer_id -> address_id
    for cid in customer_ids:
        city, state, postal = random.choice(CITIES)
        cur.execute(
            "INSERT INTO addresses(customer_id,line1,city,state,postal_code,is_default) VALUES(?,?,?,?,?,1)",
            (cid, f"{random.randint(100,9999)} {random.choice(['Main','Oak','Pine','Maple','Cedar'])} St", city, state, postal)
        )
        address_map[cid] = cur.lastrowid

    # Discount codes
    for code in ["WELCOME10","SUMMER20","LOYAL15","FLASH25","NEWYR30"]:
        discount = float(code[-2:]) / 100
        cur.execute(
            "INSERT OR IGNORE INTO discount_codes(code,discount_pct,max_uses,expires_at,is_active) VALUES(?,?,?,?,1)",
            (code, discount, random.randint(50,500), rnd_date(-90))  # some in future
        )
    discount_ids = [r[0] for r in cur.execute("SELECT code_id FROM discount_codes").fetchall()]
    product_ids  = [r[0] for r in cur.execute("SELECT product_id FROM products").fetchall()]
    product_prices = {r[0]: r[1] for r in cur.execute("SELECT product_id,price_cents FROM products").fetchall()}

    # Orders + order_items + shipments
    for _ in range(200):
        cid = random.choice(customer_ids)
        addr_id = address_map.get(cid)
        disc_id = random.choice([None, None, None] + discount_ids)
        placed_at = rnd_date(400)
        status = random.choice(ORDER_STATUSES)
        disc_pct = 0.0

        if disc_id:
            row = cur.execute("SELECT discount_pct FROM discount_codes WHERE code_id=?", (disc_id,)).fetchone()
            disc_pct = row[0] if row else 0.0

        # Pick 1-4 items
        items = []
        num_items = random.randint(1, 4)
        chosen_products = random.sample(product_ids, min(num_items, len(product_ids)))
        subtotal = 0
        for pid in chosen_products:
            qty = random.randint(1, 3)
            unit_price = product_prices[pid]
            total = qty * unit_price
            subtotal += total
            items.append((pid, qty, unit_price, total))

        discount_cents = int(subtotal * disc_pct)
        shipping_cents = 0 if subtotal > 5000 else 999
        total_cents = subtotal - discount_cents + shipping_cents

        cur.execute(
            """INSERT INTO orders(customer_id,shipping_address_id,discount_code_id,status,
               subtotal_cents,discount_cents,shipping_cents,total_cents,placed_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (cid, addr_id, disc_id, status, subtotal, discount_cents, shipping_cents, total_cents, placed_at, placed_at)
        )
        order_id = cur.lastrowid

        for pid, qty, unit_price, total in items:
            cur.execute(
                "INSERT INTO order_items(order_id,product_id,quantity,unit_price_cents,total_cents) VALUES(?,?,?,?,?)",
                (order_id, pid, qty, unit_price, total)
            )

        # Shipment for non-pending/cancelled orders
        if status in ("shipped","delivered"):
            carrier = random.choice(CARRIERS)
            tracking = "".join(random.choices(string.ascii_uppercase + string.digits, k=14))
            shipped_at = rnd_date(30)
            delivered_at = None
            if status == "delivered":
                delivered_at = (datetime.strptime(shipped_at, "%Y-%m-%d %H:%M:%S") + timedelta(days=random.randint(1,7))).strftime("%Y-%m-%d %H:%M:%S")
            cur.execute(
                "INSERT INTO shipments(order_id,carrier,tracking_number,status,shipped_at,delivered_at) VALUES(?,?,?,?,?,?)",
                (order_id, carrier, tracking, status, shipped_at, delivered_at)
            )

    # Reviews
    for _ in range(120):
        pid  = random.choice(product_ids)
        cid  = random.choice(customer_ids)
        rating = random.choices([1,2,3,4,5], weights=[2,3,10,25,35])[0]
        titles = ["Great product!","Not what I expected","Solid quality","Would recommend","Disappointing",
                  "Exceeded expectations","Good value","Fast shipping","Average","Love it!"]
        cur.execute(
            "INSERT OR IGNORE INTO reviews(product_id,customer_id,rating,title,is_verified_purchase,created_at) VALUES(?,?,?,?,?,?)",
            (pid, cid, rating, random.choice(titles), random.randint(0,1), rnd_date(200))
        )

    conn.commit()
    print(f"✓ Seeded test_ecommerce.db")
    for row in cur.execute("SELECT name, COUNT(*) as cnt FROM sqlite_master WHERE type='table' GROUP BY name ORDER BY name").fetchall():
        count = cur.execute(f"SELECT COUNT(*) FROM [{row[0]}]").fetchone()[0]
        print(f"  {row[0]:<25} {count:>5} rows")


if __name__ == "__main__":
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()
        print(f"Removed existing {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(DDL)
    seed(conn)
    conn.close()
    print(f"\nDatabase path: {DB_PATH}")
    print("\nTo connect in SxQLear:")
    print(f"  Dialect: SQLite")
    print(f"  Database: {DB_PATH}")
