from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from bs4 import BeautifulSoup
import sqlite3
from datetime import datetime
from typing import Optional
from curl_cffi import requests
import asyncio
import json
import re
#import requests

app = FastAPI(title="Price Scrapper")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def sql_conn():
    con = sqlite3.connect("price_tracker.db")
    con.row_factory = sqlite3.Row
    return con


def get_bookmarked_products():
    con = sql_conn()
    cur = con.cursor()
    bookmarked = []

    cur.execute("""SELECT id,title,url FROM products""")
    rows = cur.fetchall()
    for row in rows:
        bookmarked.append({'title': row['title'], 'url': row['url'], 'id': row['id']})
    con.close()
    return bookmarked


def price_history_table(page: int = 1, per_page: int = 10, product_id: Optional[int] = None):
    con = sql_conn()
    cur = con.cursor()
    offset = (page - 1) * per_page

    if product_id:
        cur.execute("""SELECT COUNT(*) AS total FROM price_history WHERE product_id = ? """, (product_id,))
        total_count = cur.fetchone()['total']
        cur.execute("""
                    SELECT price_history.recorded_at,products.title,price_history.price,price_history.product_id 
                    FROM price_history JOIN products 
                    ON price_history.product_id = products.id 
                    WHERE price_history.product_id = ? ORDER BY price_history.recorded_at DESC
                    LIMIT ? OFFSET ?
        """, (product_id, per_page, offset))
    else:
        cur.execute("""SELECT COUNT(*) AS total FROM price_history""")
        total_count = cur.fetchone()['total']
        cur.execute("""
                    SELECT price_history.recorded_at,products.title,price_history.price,price_history.product_id 
                    FROM price_history JOIN products 
                    ON price_history.product_id = products.id 
                    ORDER BY price_history.recorded_at DESC
                    LIMIT ? OFFSET ?
        """, (per_page, offset))

    all_items = []
    rows = cur.fetchall()
    for details in rows:
        all_items.append({
            'date': details['recorded_at'],
            'title': details['title'],
            'price': details['price'],
            'product_id': details['product_id']
        })
    con.close()

    print(total_count)

    total_pages = (total_count + per_page - 1) // per_page
    has_prev = page > 1
    has_next = page < total_pages

    return {
        'items': all_items,
        'pagination': {
            'page': page,
            'per_page': per_page,
            'total': total_count,
            'total_pages': total_pages,
            'has_prev': has_prev,
            'has_next': has_next
        }
    }


# ---------------------------------------------------------------------------
# Scraping helpers
# ---------------------------------------------------------------------------

async def flip_search(product_url: str):
    url = re.findall(r"\.com/(.*?)\?pid",product_url)[0]
    url = f"https://www.flipkart.com/{url}"
    print(url)
    session = requests.AsyncSession()
    res = await session.get(url,impersonate="chrome101")
    soup = BeautifulSoup(res.text,'html.parser')
    #print(soup.prettify()[:1000])

    # Grab the product details from the JSON-LD script tag
    product_details = soup.select_one("script#jsonLD").text.strip()
    product_details = json.loads(product_details)[0]
    #print(product_details["name"])

    data = [{
        "name": product_details["name"],
        "price": int(product_details["offers"]["price"]),
        "link": url,
        "image": product_details["image"][0]
    }]

    return data

async def amazon_search(product_url: str):

    id = re.findall("dp/(.*)/", product_url)[0]
    url = f"https://www.amazon.in/dp/{id}"
    #Creating a session, send a request and spoupify the HTML
    session = requests.AsyncSession()
    res = await session.get(url, impersonate="chrome101")
    soup = BeautifulSoup(res.text,'html.parser')
    #print(soup.prettify()[:1000])

    try:
        #the product title and price
        product_title = soup.select_one("span#productTitle").text.strip()
        product_price_whole = soup.select_one("div#corePriceDisplay_desktop_feature_div span.a-price-whole").text.strip()
        product_price = int(product_price_whole.replace(",", ""))
        product_img = soup.select_one("img#landingImage")["src"]
        print("price",product_price)
        data = [{
            "name": product_title,
            "price": product_price,
            "link": product_url,
            "image": product_img
        }]
        return data
    
    except Exception as e:
        print(f"Error scraping product: {str(e)}")
        return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, page: int = 1, id: Optional[int] = None):
    per_page = 10
    product_id = id

    if product_id:
        price_data = price_history_table(page, per_page, product_id)
    else:
        price_data = price_history_table(page, per_page)

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "bookmarked": get_bookmarked_products(),
            "all_items": price_data['items'],
            "pagination": price_data['pagination'],
            "selected_product_id": product_id,
        }
    )


@app.get("/product/{product_id}", response_class=HTMLResponse)
async def open_product_details(request: Request, product_id: int):
    con = sql_conn()
    cur = con.cursor()
    cur.execute("SELECT * FROM products WHERE id = ?", (product_id,))
    product = cur.fetchone()
    cur.execute("SELECT price,recorded_at FROM price_history WHERE product_id = ? ORDER BY recorded_at", (product_id,))
    history = cur.fetchall()
    con.close()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    time = [row['recorded_at'].split(' ')[0] for row in history]
    prices = [int(row["price"]) for row in history]
    price_stats = {
        'current': prices[-1] if prices else 0,
        'lowest': min(prices) if prices else 0,
        'highest': max(prices) if prices else 0,
        'average': sum(prices) // len(prices) if prices else 0,
        'count': len(prices) if prices else 0,
        'is_lowest': prices and len(prices) > 0 and prices[-1] == min(prices),
        'is_highest': prices and len(prices) > 0 and prices[-1] == max(prices),
        'variation_percent': ((max(prices) - min(prices)) / min(prices) * 100) if prices else 0,
        'variation_amount': max(prices) - min(prices) if prices else 0,
        'trend': 'Decreased' if len(prices) > 1 and prices[-1] < prices[-2] else 'Increased' if len(prices) > 1 and prices[-1] > prices[-2] else 'Unchanged' if len(prices) > 1 else 'Not enough data',
        'trend_description': f"Price dropped by ₹{'{:,}'.format(prices[-2] - prices[-1])} since last update." if len(prices) > 1 and prices[-1] < prices[-2] else f"Price increased by ₹{'{:,}'.format(prices[-1] - prices[-2])} since last update." if len(prices) > 1 and prices[-1] > prices[-2] else "Price remained the same since last update." if len(prices) > 1 else "We need more data points to show price trends."
    }

    return templates.TemplateResponse(
        request,
        "product.html",
        {
            "product": dict(product),
            "time": time,
            "prices": prices,
            "stats": price_stats,
        }
    )


@app.get("/product-search", response_class=HTMLResponse)
def get_product_details(request: Request, url: Optional[str] = None):
    if not url:
        return JSONResponse({"error": "URL is required"}, status_code=400)
    try:
        product = None
        if "amazon" in url:
            product = asyncio.run(amazon_search(product_url=url))
        elif "flipkart" in url:
            product = asyncio.run(flip_search(product_url=url))

        price_data = price_history_table()
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "bookmarked": get_bookmarked_products(),
                "all_items": price_data['items'],
                "pagination": price_data['pagination'],
                "products": product,
            }
        )
    except Exception as e:
        print(f"Error scraping product: {str(e)}")
        return RedirectResponse('/', status_code=303)


@app.post("/track")
async def track(
    name: str = Form(...),
    price: str = Form(...),
    link: str = Form(...),
    image: str = Form(...),
):
    con = sql_conn()
    cur = con.cursor()

    clean_price = int(price.replace(',', ''))  # ₹74,900 → 74900

    cur.execute("""SELECT id FROM products WHERE url =?""", (link,))
    row = cur.fetchone()
    if row:
        product_id = row['id']
    else:
        cur.execute("""INSERT INTO products(title,url,image) VALUES (?,?,?)""", (name, link, image))
        cur.execute("""SELECT id FROM products WHERE url =?""", (link,))
        row = cur.fetchone()
        product_id = row['id']

    cur.execute("""INSERT INTO price_history(product_id,price) VALUES (?,?)""", (product_id, clean_price))

    con.commit()
    con.close()

    return RedirectResponse('/', status_code=303)


@app.get("/refresh")
async def refresh():
    con = sql_conn()
    cur = con.cursor()

    cur.execute("""SELECT id,url FROM products""")
    rows = cur.fetchall()

    for row in rows:
        product_id = row['id']
        product_url = row['url']
        product_data = None

        print("checking: ", product_id)

        if "amazon" in product_url:
            product_data = await amazon_search(product_url=product_url)
        elif "flipkart" in product_url:
            product_data = await flip_search(product_url=product_url)

        if product_data:
            try:
                price_str = product_data[0]['price']
                price = int(price_str)

                print(f"Scraped '{product_data[0]['name']}', Price: {price}")
                cur.execute("""INSERT INTO price_history(product_id,price) VALUES (?,?)""", (product_id, price))
            except (ValueError, KeyError, IndexError) as e:
                print(f"Could not process data for {product_url}: {e}")
        else:
            print(f"Failed to scrape {product_id}. Skipping.")

    con.commit()
    con.close()
    return RedirectResponse('/', status_code=303)


@app.get("/filter/{product_id}")
async def filter_by_product(product_id: int, page: int = 1):
    price_data = price_history_table(page, 10, product_id)
    return {
        'items': price_data['items'],
        'pagination': price_data['pagination']
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)