from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import sqlite3
import os
import json
from datetime import datetime
import uvicorn
from apscheduler.schedulers.background import BackgroundScheduler
from scraper import fetch_reviews_for_product
from analyzer import analyze_reviews

app = FastAPI(
    title="ReviewPulse",
    description="Competitor review monitoring with sentiment analysis — track what customers say about your competitors",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = os.getenv("DB_PATH", "review_pulse.db")
CHECK_INTERVAL_HOURS = int(os.getenv("CHECK_INTERVAL_HOURS", "24"))


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            description TEXT,
            g2_slug TEXT,
            trustpilot_slug TEXT,
            capterra_slug TEXT,
            alert_keywords TEXT DEFAULT '[]',
            alert_email TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            source TEXT NOT NULL,
            review_id TEXT,
            rating REAL,
            title TEXT,
            body TEXT,
            author TEXT,
            published_at TEXT,
            sentiment TEXT,
            sentiment_score REAL,
            keyword_matches TEXT DEFAULT '[]',
            fetched_at TEXT DEFAULT (datetime('now')),
            UNIQUE(source, review_id),
            FOREIGN KEY (product_id) REFERENCES products(id)
        );

        CREATE TABLE IF NOT EXISTS digest_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER,
            reviews_found INTEGER,
            new_reviews INTEGER,
            avg_sentiment REAL,
            ran_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (product_id) REFERENCES products(id)
        );
    """)
    conn.commit()
    conn.close()


class ProductCreate(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None
    g2_slug: Optional[str] = None
    trustpilot_slug: Optional[str] = None
    capterra_slug: Optional[str] = None
    alert_keywords: Optional[List[str]] = []
    alert_email: Optional[str] = None


class ProductUpdate(BaseModel):
    alert_keywords: Optional[List[str]] = None
    alert_email: Optional[str] = None
    g2_slug: Optional[str] = None
    trustpilot_slug: Optional[str] = None
    capterra_slug: Optional[str] = None


@app.get("/")
def root():
    return {"service": "ReviewPulse", "status": "running", "docs": "/docs"}


@app.post("/products")
def create_product(product: ProductCreate):
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("""
            INSERT INTO products (name, slug, description, g2_slug, trustpilot_slug, capterra_slug, alert_keywords, alert_email)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            product.name, product.slug, product.description,
            product.g2_slug, product.trustpilot_slug, product.capterra_slug,
            json.dumps(product.alert_keywords), product.alert_email,
        ))
        conn.commit()
        return {"message": "Product added", "slug": product.slug}
    except sqlite3.IntegrityError:
        raise HTTPException(409, f"Product with slug '{product.slug}' already exists")
    finally:
        conn.close()


@app.get("/products")
def list_products():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM products ORDER BY created_at DESC")
    rows = []
    for r in cur.fetchall():
        row = dict(r)
        row["alert_keywords"] = json.loads(row["alert_keywords"] or "[]")
        rows.append(row)
    conn.close()
    return rows


@app.patch("/products/{slug}")
def update_product(slug: str, update: ProductUpdate):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id FROM products WHERE slug = ?", (slug,))
    if not cur.fetchone():
        raise HTTPException(404, "Product not found")

    fields = {}
    if update.alert_keywords is not None:
        fields["alert_keywords"] = json.dumps(update.alert_keywords)
    if update.alert_email is not None:
        fields["alert_email"] = update.alert_email
    if update.g2_slug is not None:
        fields["g2_slug"] = update.g2_slug
    if update.trustpilot_slug is not None:
        fields["trustpilot_slug"] = update.trustpilot_slug
    if update.capterra_slug is not None:
        fields["capterra_slug"] = update.capterra_slug

    if fields:
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        conn.execute(f"UPDATE products SET {set_clause} WHERE slug = ?", [*fields.values(), slug])
        conn.commit()

    conn.close()
    return {"message": "Updated"}


@app.post("/products/{slug}/fetch")
def fetch_reviews(slug: str, background_tasks: BackgroundTasks):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM products WHERE slug = ?", (slug,))
    product = cur.fetchone()
    conn.close()
    if not product:
        raise HTTPException(404, "Product not found")

    background_tasks.add_task(_run_fetch, dict(product))
    return {"message": f"Review fetch started for {product['name']}"}


def _run_fetch(product: dict):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    keywords = json.loads(product["alert_keywords"] or "[]")
    all_reviews = []

    for source, slug_key in [("g2", "g2_slug"), ("trustpilot", "trustpilot_slug"), ("capterra", "capterra_slug")]:
        slug = product.get(slug_key)
        if not slug:
            continue
        reviews = fetch_reviews_for_product(source, slug)
        for r in reviews:
            sentiment, score = analyze_reviews(r.get("body", ""))
            kw_matches = [kw for kw in keywords if kw.lower() in (r.get("body", "") + r.get("title", "")).lower()]
            try:
                cur.execute("""
                    INSERT OR IGNORE INTO reviews
                    (product_id, source, review_id, rating, title, body, author, published_at, sentiment, sentiment_score, keyword_matches)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    product["id"], source, r.get("review_id"),
                    r.get("rating"), r.get("title"), r.get("body"),
                    r.get("author"), r.get("published_at"),
                    sentiment, score, json.dumps(kw_matches),
                ))
                all_reviews.append(r)
            except Exception as e:
                print(f"Insert error: {e}")

    conn.commit()

    cur.execute("""
        SELECT AVG(sentiment_score) as avg_score, COUNT(*) as total
        FROM reviews WHERE product_id = ? AND fetched_at >= datetime('now', '-1 day')
    """, (product["id"],))
    row = cur.fetchone()
    avg_sentiment = row[0] if row and row[0] else 0.0

    cur.execute("""
        INSERT INTO digest_runs (product_id, reviews_found, new_reviews, avg_sentiment)
        VALUES (?, ?, ?, ?)
    """, (product["id"], len(all_reviews), len(all_reviews), avg_sentiment))
    conn.commit()
    conn.close()
    print(f"Fetched {len(all_reviews)} reviews for {product['name']}")


@app.get("/products/{slug}/reviews")
def get_reviews(
    slug: str,
    source: Optional[str] = None,
    sentiment: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT id FROM products WHERE slug = ?", (slug,))
    p = cur.fetchone()
    if not p:
        raise HTTPException(404, "Product not found")

    query = "SELECT * FROM reviews WHERE product_id = ?"
    params = [p["id"]]
    if source:
        query += " AND source = ?"
        params.append(source)
    if sentiment:
        query += " AND sentiment = ?"
        params.append(sentiment)
    query += " ORDER BY fetched_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    cur.execute(query, params)
    rows = []
    for r in cur.fetchall():
        row = dict(r)
        row["keyword_matches"] = json.loads(row["keyword_matches"] or "[]")
        rows.append(row)
    conn.close()
    return rows


@app.get("/products/{slug}/insights")
def get_insights(slug: str):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM products WHERE slug = ?", (slug,))
    product = cur.fetchone()
    if not product:
        raise HTTPException(404, "Product not found")

    cur.execute("""
        SELECT
            source,
            COUNT(*) as review_count,
            AVG(rating) as avg_rating,
            AVG(sentiment_score) as avg_sentiment,
            SUM(CASE WHEN sentiment = 'positive' THEN 1 ELSE 0 END) as positive_count,
            SUM(CASE WHEN sentiment = 'negative' THEN 1 ELSE 0 END) as negative_count,
            SUM(CASE WHEN sentiment = 'neutral' THEN 1 ELSE 0 END) as neutral_count
        FROM reviews WHERE product_id = ?
        GROUP BY source
    """, (product["id"],))
    by_source = [dict(r) for r in cur.fetchall()]

    cur.execute("""
        SELECT * FROM reviews
        WHERE product_id = ? AND keyword_matches != '[]' AND keyword_matches IS NOT NULL
        ORDER BY fetched_at DESC LIMIT 10
    """, (product["id"],))
    keyword_hits = []
    for r in cur.fetchall():
        row = dict(r)
        row["keyword_matches"] = json.loads(row["keyword_matches"] or "[]")
        keyword_hits.append(row)

    cur.execute("""
        SELECT * FROM reviews
        WHERE product_id = ? AND sentiment = 'negative' AND rating <= 2
        ORDER BY sentiment_score ASC LIMIT 5
    """, (product["id"],))
    worst = [dict(r) for r in cur.fetchall()]

    cur.execute("""
        SELECT * FROM reviews
        WHERE product_id = ? AND sentiment = 'positive' AND rating >= 4
        ORDER BY sentiment_score DESC LIMIT 5
    """, (product["id"],))
    best = [dict(r) for r in cur.fetchall()]

    conn.close()
    return {
        "product": dict(product),
        "by_source": by_source,
        "keyword_hits": keyword_hits,
        "top_negative_reviews": worst,
        "top_positive_reviews": best,
    }


@app.get("/products/{slug}/digest")
def get_digest_history(slug: str):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT id FROM products WHERE slug = ?", (slug,))
    p = cur.fetchone()
    if not p:
        raise HTTPException(404, "Product not found")
    cur.execute(
        "SELECT * FROM digest_runs WHERE product_id = ? ORDER BY ran_at DESC LIMIT 30",
        (p["id"],)
    )
    return [dict(r) for r in cur.fetchall()]


def scheduled_fetch_all():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM products")
    products = [dict(r) for r in cur.fetchall()]
    conn.close()
    for product in products:
        try:
            _run_fetch(product)
        except Exception as e:
            print(f"Scheduled fetch error for {product['name']}: {e}")


if __name__ == "__main__":
    init_db()
    scheduler = BackgroundScheduler()
    scheduler.add_job(scheduled_fetch_all, "interval", hours=CHECK_INTERVAL_HOURS, id="review_fetch")
    scheduler.start()
    print(f"ReviewPulse running — fetching reviews every {CHECK_INTERVAL_HOURS}h")
    uvicorn.run(app, host="0.0.0.0", port=8000)
