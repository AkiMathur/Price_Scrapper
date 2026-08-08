import sqlite3

con = sqlite3.connect("price_tracker.db")

cur = con.cursor()

# cur.execute("DELETE FROM products WHERE id=6")
# cur.execute("DELETE FROM price_history WHERE product_id=6")

cur.execute("""CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    url TEXT UNIQUE,
    image TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"""
            )

cur.execute("""CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER,
    price INTEGER,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(product_id) REFERENCES products(id))
            """)

con.commit()
con.close()