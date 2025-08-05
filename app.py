from flask import Flask,render_template, request, jsonify, redirect
from bs4 import BeautifulSoup
import requests,sqlite3
from datetime import datetime


app = Flask(__name__)

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
        bookmarked.append({'title':row['title'],'url':row['url'],'id':row['id']})
    con.close()
    return bookmarked


def price_history_table(page=1,per_page=10,product_id=None):
    con = sql_conn()
    cur = con.cursor()
    offset = (page - 1) * per_page
    if product_id:
        cur.execute("""SELECT COUNT(*) AS total FROM price_history WHERE product_id = ? """,(product_id,))
        total_count = cur.fetchone()['total']
        cur.execute("""
                    SELECT price_history.recorded_at,products.title,price_history.price,price_history.product_id 
                    FROM price_history JOIN products 
                    ON price_history.product_id = products.id 
                    WHERE price_history.product_id = ? ORDER BY price_history.recorded_at DESC
                    LIMIT ? OFFSET ?
        """, (product_id,per_page, offset))
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
        all_items.append({'date':details['recorded_at'],'title':details['title'],'price':details['price'],'product_id': details['product_id']})
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
        }}

def flip_search(product_url):
    headers = {
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
    'accept-language':'en-US,en;q=0.9',
    'accept-encoding':'gzip, deflate, br, zstd',
    'accept':'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',

}
    res = requests.get(product_url, headers=headers)
    soup = BeautifulSoup(res.text, 'lxml')
    # with open("ref_page.html","w",encoding='utf-8') as f:
    #     f.write(res.text)
    product = []
    try:
        title = soup.find("span", class_="VU-ZEz").text.strip()
        price = soup.find("div", class_="Nx9bqj CxhGGd").text.strip()
        price = price[1:]
        # rating_tag = soup.find("div", class_="XQDdHH")
        # rating = rating_tag.text.strip() if rating_tag else "No rating"
        image_tag = soup.find("img", class_="DByuf4")
        image = image_tag['src'] if image_tag else ""

        if title and price and product_url:
            product.append({
                "name": title,
                "price": price,
                "link": product_url,
                "image": image
            })
            print(title)
        return product
    except Exception as e:
        print(f"Error scraping product: {str(e)}")
        return None

def amazon_search(product_url):
    headers = {
    'user-agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36'
}
    res = requests.get(product_url, headers=headers)
    soup = BeautifulSoup(res.text, 'lxml')
    product = []
    try:
        title = soup.find('span',id="productTitle").text.strip()
        price = soup.find('span',class_="a-price-whole").text.strip()
        price = price[:-1]
        # rating_tag = soup.find("div", class_="XQDdHH")
        # rating = rating_tag.text.strip() if rating_tag else "No rating"
        image = soup.find('img',id="landingImage")["src"]

        if title and price and product_url:
            product.append({
                "name": title,
                "price": price,
                "link": product_url,
                "image": image
            })
            print(title)
        return product
    except Exception as e:
        print(f"Error scraping product: {str(e)}")
        return None

@app.route("/")
def index():
    page = request.args.get('page', 1, type=int)
    product_id = request.args.get('id', type=int)
    per_page = 10  # Items per page

    if product_id:
        price_data = price_history_table(page,per_page,product_id)
    else:
        price_data = price_history_table(page, per_page)
    # print("product_id",product_id)

    return render_template("index.html",bookmarked = get_bookmarked_products(),all_items = price_data['items'],pagination=price_data['pagination'],selected_product_id=product_id)

# @app.route("/search")
# def search_flipkart():
#     query = request.args.get("query")
#     url = f"https://www.flipkart.com/search?q={query}"
#     res = requests.get(url,headers=headers)
#     soup = BeautifulSoup(res.text,'lxml')

#     products = []
#     containers = soup.find_all("div", class_="tUxRFH")

#     for item in containers:
#         title = item.find("div",class_="KzDlHZ")
#         price = item.find("div", class_="Nx9bqj _4b5DiR")
#         link = item.find("a", class_="CGtC98")


#         if title and price and link:
#             products.append({
#                 "name": title.text.strip(),
#                 "price": price.text.strip(),
#                 "link": "https://www.flipkart.com" + link["href"]
#             })

#     return render_template("index.html",products=products)

@app.route('/product/<int:product_id>')
def open_product_details(product_id):
    con = sql_conn()
    cur = con.cursor()
    cur.execute("SELECT * FROM products WHERE id = ?", (product_id,))
    product = cur.fetchone()
    cur.execute("SELECT price,recorded_at FROM price_history WHERE product_id = ? ORDER BY recorded_at", (product_id,))
    history = cur.fetchall()
    con.close()
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
    if product:
        return render_template("product.html", product=product, time=time, prices=prices,stats=price_stats)
    else:
        return "Product not found", 404

@app.route('/product-search', methods=['GET'])
def get_product_details():
    product_url = request.args.get("url")
    if not product_url:
        return jsonify({"error": "URL is required"}), 400
    try:
        if "amazon" in product_url:
            product = amazon_search(product_url=product_url)
        elif "flipkart" in product_url:
            product = flip_search(product_url=product_url)
        
        price_data = price_history_table()
        return render_template("index.html", bookmarked=get_bookmarked_products(), all_items=price_data['items'], pagination=price_data['pagination'], products=product)
    except Exception as e:
        print(f"Error scraping product: {str(e)}")
        return redirect('/')

@app.route("/track", methods=['POST'])
def track():
    con = sql_conn()
    cur = con.cursor()
    
    name = request.form.get("name")
    price = request.form.get("price")
    link = request.form.get("link")
    image = request.form.get("image")
    price = int(price.replace(',', '')) # \u20b974,900 , \u20b9 is the rupee char

    cur.execute("""SELECT id FROM products WHERE url =?""",(link,))
    row = cur.fetchone()
    if row:
        product_id = row['id']
    else:
        cur.execute("""INSERT INTO products(title,url,image) VALUES (?,?,?)""",(name,link,image))
        cur.execute("""SELECT id FROM products WHERE url =?""",(link,))
        row = cur.fetchone()
        product_id = row['id']

    cur.execute("""INSERT INTO price_history(product_id,price) VALUES (?,?)""",(product_id,price))

    con.commit()
    con.close()

    return redirect('/')

@app.route("/refresh")
def refresh():
    con = sql_conn()
    cur = con.cursor()
    
    cur.execute("""SELECT id,url FROM products""")
    rows = cur.fetchall()
    
    #urls = [row['url'] for row in rows]
    
    for row in rows:
        product_id = row['id']
        product_url = row['url']
        product_data = None

        print("checking: ", product_id)
        
        if "amazon" in product_url:
            product_data = amazon_search(product_url)
        elif "flipkart" in product_url:
            product_data = flip_search(product_url)
        
        # Check if scraping was successful before processing
        if product_data:
            try:
                price_str = product_data[0]['price']
                price = int(price_str.replace(',', ''))
                
                print(f"Scraped '{product_data[0]['name']}', Price: {price}")
                cur.execute("""INSERT INTO price_history(product_id,price) VALUES (?,?)""", (product_id, price))
            except (ValueError, KeyError, IndexError) as e:
                print(f"Could not process data for {product_url}: {e}")
        else:
            print(f"Failed to scrape {product_id}. Skipping.")
    con.commit()
    con.close()
    return redirect('/')

@app.route("/filter/<int:product_id>")
def filter_by_product(product_id):
    page = request.args.get('page', 1, type=int)
    price_data = price_history_table(page, 10, product_id)
    
    return jsonify({
        'items': [dict(item) for item in price_data['items']],
        'pagination': price_data['pagination']
    })



if __name__ == "__main__":
    app.run(debug=True)