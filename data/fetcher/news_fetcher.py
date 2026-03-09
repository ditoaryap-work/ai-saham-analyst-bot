"""
news_fetcher.py — RSS scraper berita keuangan Indonesia.

Mengambil berita dari:
- Kontan (keuangan)
- Bisnis Indonesia (finansial)
- IDN Financials

Simpan ke tabel berita dengan processed=0 (belum dianalisa sentimen).
"""

import sys
from pathlib import Path
from datetime import datetime

import feedparser
from bs4 import BeautifulSoup
import requests
from loguru import logger

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import RSS_FEEDS
from data.database import db
from utils.helpers import delay


def parse_rss_feed(feed_url: str, max_items: int = 20) -> list:
    """
    Parse satu RSS feed dan return list artikel.
    
    Returns:
        List of dict: [{'judul', 'url', 'sumber', 'tanggal', 'isi_ringkas'}, ...]
    """
    articles = []
    
    try:
        feed = feedparser.parse(feed_url)
        
        if not feed.entries:
            logger.warning(f"RSS feed kosong: {feed_url}")
            return []
        
        # Identifikasi sumber dari URL
        if 'kontan' in feed_url:
            sumber = 'Kontan'
        elif 'bisnis' in feed_url:
            sumber = 'Bisnis Indonesia'
        elif 'cnbcindonesia' in feed_url:
            sumber = 'CNBC Indonesia'
        elif 'detik' in feed_url:
            sumber = 'Detik Finance'
        elif 'idnfinancials' in feed_url:
            sumber = 'IDN Financials'
        else:
            sumber = feed.feed.get('title', 'Unknown')
        
        for entry in feed.entries[:max_items]:
            judul = entry.get('title', '').strip()
            url = entry.get('link', '').strip()
            
            # Parse tanggal
            tanggal = None
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                tanggal = datetime(*entry.published_parsed[:6]).isoformat()
            elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                tanggal = datetime(*entry.updated_parsed[:6]).isoformat()
            else:
                tanggal = datetime.now().isoformat()
            
            # Ambil ringkasan dari feed (tanpa fetch halaman penuh)
            isi_ringkas = ''
            if hasattr(entry, 'summary'):
                # Bersihkan HTML tags
                soup = BeautifulSoup(entry.summary, 'html.parser')
                isi_ringkas = soup.get_text(strip=True)[:500]
            
            if judul and url:
                articles.append({
                    'judul': judul,
                    'url': url,
                    'sumber': sumber,
                    'tanggal': tanggal,
                    'isi_ringkas': isi_ringkas,
                })
        
        logger.info(f"[{sumber}] {len(articles)} artikel ditemukan.")
        return articles
        
    except Exception as e:
        logger.error(f"Gagal parse RSS {feed_url}: {e}")
        return []


def save_articles_to_db(articles: list) -> int:
    """
    Simpan artikel ke tabel berita (skip duplikat berdasarkan URL).
    Returns jumlah artikel baru yang disimpan.
    """
    saved = 0
    
    for art in articles:
        # Cek apakah URL sudah ada di DB
        existing = db.execute(
            "SELECT id FROM berita WHERE url = ?", (art['url'],)
        )
        
        if existing:
            continue  # Skip duplikat
        
        db.execute(
            """INSERT INTO berita 
               (judul, url, sumber, tanggal, isi_ringkas, 
                emiten_terkait, sentimen, confidence, processed)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                art['judul'], art['url'], art['sumber'],
                art['tanggal'], art['isi_ringkas'],
                None, None, None, 0,
            ),
        )
        saved += 1
    
    if saved > 0:
        logger.info(f"{saved} artikel baru disimpan ke DB.")
    
    return saved


def fetch_all_news() -> int:
    """
    Fetch berita dari semua RSS feeds.
    Returns total artikel baru.
    """
    total_new = 0
    
    for feed_url in RSS_FEEDS:
        articles = parse_rss_feed(feed_url)
        new_count = save_articles_to_db(articles)
        total_new += new_count
        delay(1)  # Delay antar feed
    
    logger.info(f"Total berita baru: {total_new}")
    return total_new


# ── Entry point ──────────────────────────────────────
if __name__ == "__main__":
    print("\n📰 News Fetcher — Test RSS Feeds\n")
    
    db.create_all_tables()
    total = fetch_all_news()
    
    # Verifikasi
    print("\n📊 Berita di Database:")
    print("-" * 60)
    
    # Per sumber
    for sumber in ['Kontan', 'Bisnis Indonesia', 'IDN Financials']:
        rows = db.execute(
            "SELECT COUNT(*) as cnt FROM berita WHERE sumber = ?",
            (sumber,),
        )
        cnt = rows[0]['cnt'] if rows else 0
        print(f"  {'✅' if cnt > 0 else '⚠️'} {sumber}: {cnt} artikel")
    
    # 3 berita terbaru
    latest = db.execute(
        "SELECT judul, sumber, tanggal FROM berita ORDER BY tanggal DESC LIMIT 3"
    )
    if latest:
        print(f"\n📌 3 Berita Terbaru:")
        for b in latest:
            b = dict(b)
            print(f"  • [{b['sumber']}] {b['judul'][:60]}...")
    
    print(f"\n🎉 Total {total} berita baru di-fetch.")
