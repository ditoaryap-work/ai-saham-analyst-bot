# IDX AI TRADING ASSISTANT — MASTER BUILD PROMPT
> Untuk: Antigravity IDE dengan Claude Opus 4.6  
> Tujuan: Build seluruh sistem dari nol, incremental  
> Dibuat: Maret 2026

---

## KONTEKS KAMU

Kamu adalah senior Python engineer sekaligus quant analyst yang diminta build sistem AI Trading Assistant lengkap untuk pasar saham Indonesia (IDX/BEI). User adalah trader dengan modal Rp 10-15 juta, familiar Python dan terminal, VPS Ubuntu sudah jalan dengan n8n terinstall.

Bangun sistem ini secara **INCREMENTAL** — satu file/modul per langkah, selalu tanya konfirmasi sebelum lanjut ke modul berikutnya. Jangan build semua sekaligus.

---

## BAGIAN 1: TECH STACK & PROJECT STRUCTURE

### Infrastruktur
- VPS Tencent Cloud 2GB RAM, Ubuntu 22.04, Jakarta region
- n8n sudah terinstall (untuk scheduling otomatis)
- Python 3.11+
- SQLite sebagai database utama
- Telegram Bot (token sudah ada)
- OpenRouter API (DeepSeek V3.2, model: `deepseek/deepseek-v3.2`)

### Project Structure
```
/home/user/trading-assistant/
├── config/
│   ├── .env                    # API keys, tokens
│   └── settings.py             # Konfigurasi sistem
├── data/
│   ├── fetcher/
│   │   ├── stock_fetcher.py      # Ambil OHLCV via yfinance
│   │   ├── news_fetcher.py       # RSS scraper berita
│   │   ├── macro_fetcher.py      # Indeks Asia, kurs, komoditas (yfinance)
│   │   └── fundamental_fetcher.py # Data Lapkeu API via yfinance
│   └── database.py             # SQLite operations
├── analysis/
│   ├── screening.py            # Layer 0-3 screening logic
│   ├── scoring.py              # Step 4 composite scoring
│   ├── technical.py            # Semua indikator teknikal
│   ├── fundamental.py          # F-Score, Z-Score
│   └── calendar.py             # Kalender ekonomi IDX
├── ai/
│   ├── agents.py               # 5 agent system
│   ├── prompts.py              # Semua prompt templates
│   └── sentiment.py            # Sentimen berita via AI
├── portfolio/
│   ├── tracker.py              # Track posisi & dana
│   └── reporting.py            # Laporan portfolio
├── bot/
│   ├── telegram_bot.py         # Telegram interface
│   ├── commands.py             # Command handlers
│   └── formatter.py            # Format pesan Telegram
├── scheduler/
│   └── jobs.py                 # Cron jobs
├── utils/
│   ├── logger.py               # Logging sistem
│   └── helpers.py              # Utility functions
├── database.sqlite             # SQLite database
├── requirements.txt
└── main.py                     # Entry point
```

### Python Libraries
```bash
pip install pandas numpy pandas-ta requests beautifulsoup4
pip install feedparser python-dotenv loguru
pip install python-telegram-bot apscheduler openai
pip install scipy statsmodels aiohttp sqlalchemy yfinance curl_cffi
```

---

## BAGIAN 2: DATABASE SCHEMA

Buat file `data/database.py` dengan SQLite dan tabel berikut:

### Tabel 1: harga_historis
```sql
kode TEXT, tanggal DATE, open REAL, high REAL,
low REAL, close REAL, volume INTEGER, value REAL,
PRIMARY KEY (kode, tanggal)
```

### Tabel 2: daftar_emiten
```sql
kode TEXT PRIMARY KEY, nama TEXT, sektor TEXT,
subsektor TEXT, papan TEXT, listed_date DATE,
market_cap REAL, is_suspended INTEGER DEFAULT 0, last_update DATE
```

### Tabel 3: fundamental
```sql
kode TEXT, periode TEXT,
revenue REAL, net_income REAL, total_assets REAL,
total_equity REAL, total_debt REAL, current_assets REAL,
current_liabilities REAL, operating_cashflow REAL,
gross_profit REAL, ebit REAL, roa REAL, roe REAL,
der REAL, per REAL, pbv REAL, eps REAL,
retained_earnings REAL, working_capital REAL,
f_score INTEGER, z_score REAL, last_update DATE
```

### Tabel 6: berita
```sql
id INTEGER PRIMARY KEY AUTOINCREMENT,
judul TEXT, url TEXT, sumber TEXT,
tanggal DATETIME, isi_ringkas TEXT,
emiten_terkait TEXT, sentimen TEXT,
confidence REAL, processed INTEGER DEFAULT 0
```

### Tabel 7: makro_data
```sql
tanggal DATE, ihsg_change REAL, nikkei_change REAL,
hsi_change REAL, sti_change REAL, usd_idr REAL,
cpo_change REAL, coal_change REAL, nikel_change REAL,
market_label TEXT, narasi TEXT
```

### Tabel 8: sinyal_history
```sql
id INTEGER PRIMARY KEY AUTOINCREMENT,
kode TEXT, tanggal DATE, waktu TEXT,
skor_total REAL, label TEXT,
entry_low REAL, entry_high REAL,
target REAL, stoploss REAL,
rr_ratio REAL, confidence REAL,
alasan TEXT, risk_warning TEXT,
status TEXT DEFAULT 'ACTIVE'
```

### Tabel 9: portfolio_config
```sql
user_id TEXT DEFAULT 'default',
modal_awal REAL, risk_profile TEXT,
max_posisi INTEGER DEFAULT 5,
max_per_saham_pct REAL DEFAULT 0.30
```

### Tabel 8: posisi_aktif
```sql
id INTEGER PRIMARY KEY AUTOINCREMENT,
kode TEXT, lot INTEGER, harga_beli REAL,
harga_terkini REAL, unrealized_pnl REAL,
tanggal_beli DATE, stoploss_set REAL,
target_set REAL, label_sinyal TEXT
```

### Tabel 11: historis_trade
```sql
id INTEGER PRIMARY KEY AUTOINCREMENT,
kode TEXT, lot INTEGER, harga_beli REAL,
harga_jual REAL, tanggal_beli DATE,
tanggal_jual DATE, pnl REAL, pnl_pct REAL,
label_sinyal TEXT, hit INTEGER
```

### Tabel 12: dana_snapshot
```sql
tanggal DATE, total_portfolio REAL,
cash REAL, invested REAL, return_pct REAL
```

### Tabel 13: kalender_ekonomi
```sql
tanggal DATE, event_type TEXT, kode TEXT,
deskripsi TEXT, impact TEXT
```

---

## BAGIAN 3: DATA FETCHER

### 3A. Stock Fetcher (`data/fetcher/stock_fetcher.py` & `fundamental_fetcher.py`)

Sumber data utama: **`yfinance`** (Yahoo Finance API). Gratis, tanpa API key.
Format ticker JSX: tambahkan suffix `.JK` (contoh: `BBCA.JK`).

```python
# OHLCV historis per saham (stock_fetcher.py):
import yfinance as yf
# yf.Ticker("BBCA.JK").history(period="1y")

# Laporan Keuangan Fundamental (fundamental_fetcher.py):
# yf.Ticker("BBCA.JK").income_stmt
# yf.Ticker("BBCA.JK").balance_sheet
# yf.Ticker("BBCA.JK").cashflow
# yf.Ticker("BBCA.JK").info  (untuk PER, PBV, ROE, Market Cap)
```

**Implementasi wajib:**
- Delay 0.5 detik antar request (hindari rate limit)
- Retry logic: max 3x 
- Fetch secara batch: 50 saham per batch
- Simpan ke SQLite via `database.py` (hapus `.JK` saat simpan ke DB)
- Log setiap operasi via `loguru`
- Jadwal `stock_fetcher.py`: jam 16.30 WIB setiap hari kerja (OHLCV)
- Jadwal `fundamental_fetcher.py`: tiap malam (lapkeu triwulanan)

### 3B. News Fetcher (`data/fetcher/news_fetcher.py`)

RSS Feeds:
```
https://rss.kontan.co.id/news/keuangan
https://www.bisnis.com/finansial/rss
https://www.idnfinancials.com/rss/news
https://www.idx.co.id/rss
```

**Implementasi:**
- Gunakan `feedparser`
- Untuk setiap artikel: fetch URL, extract 3 paragraf pertama via BeautifulSoup
- Simpan ke tabel `berita` dengan `processed=0`
- Jalankan setiap 2 jam
- Batch belum diproses → kirim ke `ai/sentiment.py`

### 3C. Macro Fetcher (`data/fetcher/macro_fetcher.py`)

```python
# Indeks Asia (via yfinance):
yfinance: ^JKSE (IHSG), ^N225, ^HSI, ^STI

# USD/IDR:
Bank Indonesia RSS atau open.er-api.com (free)

# Komoditas (via yfinance):
yfinance: GC=F (Gold), CL=F (Crude Oil)
```

---

## BAGIAN 4: SCREENING LOGIC (`analysis/screening.py`)

### Layer 0: Market Context Classifier
```
BULLISH  : IHSG change > 0%
MIXED    : -1.5% <= IHSG change <= 0%
BEARISH  : -3% <= IHSG change < -1.5%
EXTREME  : IHSG change < -3%
```
> ⚠️ PENTING: Layer 0 adalah CLASSIFIER bukan FILTER.  
> Sistem **TIDAK PERNAH berhenti analisa** apapun kondisi pasar.  
> Label ini dibawa sebagai KONTEKS ke semua layer berikutnya.

### Layer 1: Filter Dasar Likuiditas (Binary — gugur jika tidak lolos)
```python
avg_value_5d > 3_000_000_000   # Nilai transaksi rata2 5 hari > Rp 3M
avg_volume_5d > 1_000_000       # Rata-rata volume 5 hari
close > 50                      # Harga > Rp 50
data_length >= 200              # Minimal 200 hari data historis
change_1d > -0.15               # ARB rule (Flat -15%)
change_1d < ARA_LIMIT           # ARA berjenjang (35% < Rp200, 25% < Rp5000, 20% > Rp5000)
```

### Layer 2: Scoring Teknikal
Gunakan `pandas-ta` untuk semua kalkulasi.  
**PENTING: Format semua hasil sebagai tabel terstruktur, bukan angka mentah, sebelum dikirim ke AI.**

**Indikator yang dihitung:**
- EMA: 20, 50, 200
- RSI: periode 14
- StochRSI: periode 14
- MACD: fast 12, slow 26, signal 9
- Bollinger Bands: periode 20, std 2
  - BB%B = (close - lower) / (upper - lower)
  - BB Squeeze: bandwidth < threshold (Keltner Channel)
- ATR: periode 14 → ATR% = ATR/close×100 (wajib > 2%)
- OBV: On-Balance Volume
- Volume ratio: volume hari ini / EMA20 volume
- Fibonacci: dari swing high/low 20 hari
- Pivot Points: PP=(H+L+C)/3, R1=(2×PP)-Low, S1=(2×PP)-High
- Gap Analysis: close hari ini vs close kemarin
- Candlestick: hammer, engulfing, doji, marubozu via pandas-ta
- Elliott Wave: simplified detection (impulsive vs corrective)

**Scoring Layer 2 (kembalikan dict skor):**

| Indikator | Kondisi | Skor |
|-----------|---------|------|
| EMA Alignment | EMA20>EMA50>EMA200 | +8 |
| EMA Alignment | EMA20>EMA50 saja | +5 |
| EMA Alignment | EMA20<EMA50 | +2 |
| RSI | 40-55 (sweet spot) | +3 |
| RSI | 55-65 (kuat) | +2 |
| RSI | 65-70 (hati-hati) | +1 |
| RSI | <40 atau >70 | 0 |
| StochRSI | Cross UP dari <20 | +4 |
| StochRSI | 20-50 dan naik | +3 |
| StochRSI | 50-80 | +1 |
| StochRSI | >80 | 0 |
| RSI Divergence Bullish | Ada | +3 bonus |
| MACD | Golden cross <3 hari | +4 |
| MACD | Histogram positif & naik | +3 |
| MACD | Histogram positif mendatar | +1 |
| MACD | Histogram negatif | 0 |
| BB | Squeeze aktif | +4 |
| BB%B | 0.4-0.7 | +3 |
| BB%B | 0.7-0.85 | +2 |
| BB%B | <0.4 + RSI oversold | +3 |
| BB%B | >0.85 | 0 |
| Fibonacci | Bounce dari 61.8% | +5 |
| Fibonacci | Di zona 38.2-61.8% | +4 |
| Pivot | Break above R1 | +4 |
| Pivot | Bounce dari PP/S1 | +3 |
| Volume | >3x EMA20 + harga naik | +4 |
| Volume | 1.5-3x + harga naik | +2 |
| Volume | >3x + harga turun | -3 |
| Gap | Gap up + volume besar | +3 |
| Gap | Gap down | -3 |
| Elliott | Wave 3 (impulsive) | +4 |
| Elliott | Wave 5 (akhir impulsive) | +2 |
| Elliott | Wave 4 / Wave B | -2 |

**Threshold Layer 2: Minimal skor 15 untuk lanjut ke Layer 3**

### Layer 3: OBV + Volume Profile + Candlestick

| Komponen | Kondisi | Skor |
|----------|---------|------|
| OBV | Naik saat harga sideways (akumulasi!) | +10 |
| OBV | Bullish divergence | +9 |
| OBV | Naik konfirmasi harga | +7 |
| OBV | Turun (distribusi) | -5 |
| Area Nilai | Harga mantul di demand zone historis | +5 |
| Area Nilai | Menembus supply zone dengan volume | +4 |
| Volume Profile | Volume spike >3x + harga naik | +7 |
| Volume Profile | Volume spike >3x + candle doji atas | -8 |
| Candlestick | Bullish Engulfing | +6 |
| Candlestick | Hammer/Pin Bar | +5 |
| Candlestick | Marubozu hijau | +4 |
| Candlestick | Doji di resistance | -1 |

**Output Layer 3: 15-30 saham dengan raw scores siap ke Step 4**

---

## BAGIAN 5: SCORING SYSTEM (`analysis/scoring.py`)

### 4 Dimensi Equal Weight — Total 100 Poin

Setiap dimensi dikonversi secara matematis menjadi 0-25 poin menggunakan normalisasi `max(0, min(25, (raw_score_layer - MIN_RAW) / (MAX_RAW - MIN_RAW) * 25))`.

#### Dimensi 1: Teknikal (25 poin)
Normalize raw score Layer 2 ke skala 0-25. (Min raw -8, Max raw 49)

#### Dimensi 2: Volume/Price Action (25 poin)
Normalize raw score Layer 3 ke skala 0-25.

#### Dimensi 3: Fundamental (25 poin)

Sumber data fundamental: `yfinance` balance sheet, income statement, dan cash flow.

**A. Piotroski F-Score (max 15 poin)**

Profitabilitas (masing-masing +1 jika terpenuhi):
1. ROA > 0 tahun ini
2. Operating Cash Flow > 0
3. ROA tahun ini > ROA tahun lalu
4. Cash Flow > Net Income (kualitas laba)

Leverage & Likuiditas (masing-masing +1):
5. Long-term debt turun (Total Debt turun)
6. Current ratio naik (jika data available, else skip)
7. Tidak ada penerbitan saham baru (Shares Outstanding tetap/turun)

Efisiensi Operasional (masing-masing +1):
8. Gross margin naik
9. Asset turnover naik

> ⚠️ MODIFIKASI BANK: Skip kriteria 5, 6, 7 untuk saham perbankan  
> (BBCA, BBRI, BMRI, BNI, BRIS, NISP, dll)

Konversi ke poin:
- F-Score 8-9 → 15 poin (Bank 6 → 15)
- F-Score 6-7 → 10 poin (Bank 4-5 → 10)
- F-Score 4-5 → 6 poin  (Bank 3 → 6)
- F-Score 0-3 → 2 poin  (Bank <3 → 2)

**B. Altman Z-Score (max 10 poin)**
```
Z = 1.2A + 1.4B + 3.3C + 0.6D + 1.0E
A = Working Capital / Total Assets
B = Retained Earnings / Total Assets
C = EBIT / Total Assets
D = Market Cap / Total Liabilities
E = Revenue / Total Assets

Z > 2.99   → 10 poin (zona aman)
Z 1.81-2.99 → 5 poin (zona abu-abu)
Z < 1.81   → 0 poin (zona bahaya)
```

**C. Momentum Score** (pelengkap jika laporan > 90 hari)
- Dibutuhkan jika data fundamental kosong di yfinance.
- Price momentum 1 bulan vs 3 bulan. Konversi ke 0-25 range.

#### Dimensi 4: Sentimen (25 poin) — 7 Hari Rolling

**A. Firm-Specific Sentiment (max 15 poin)**
- Sangat positif (conf > 0.85) = 15
- Positif (conf 0.65-0.85) = 10
- Netral = 5
- Negatif = 0
- Sangat negatif = -5

**B. Industry/Sektor Sentiment (max 10 poin)**
- Positif = 10, Netral = 5, Negatif = 0

### Label Final
- **🔵 AMAN** : Skor 75-100
- **🟠 MOMENTUM** : Skor 60-74
- **🟡 SPEKULATIF** : Skor 45-59
- **❌ SKIP** : Skor < 45

### Kalender Ekonomi Check
Sebelum finalize sinyal, cek array hard-coded dividend dates, dll.
- Ex-dividend besok → tambahkan WARNING
- Rilis laporan keuangan besok → tambahkan OPPORTUNITY note
- Ada RUPS → tambahkan INFO

---

## BAGIAN 6: AI DECISION LAYER (`ai/agents.py`)

### Setup
```
Platform  : OpenRouter
Base URL  : https://openrouter.ai/api/v1
Model     : deepseek/deepseek-v3.2
```

> ⚠️ PENTING: Selalu format data sebagai tabel terstruktur sebelum kirim ke AI.  
> Jika confidence < 60% → label SKIP otomatis.

### System Prompt (Cache-Friendly — Simpan sebagai Konstanta)
```
KAMU ADALAH tim analis saham profesional IDX Indonesia dengan 
keahlian mendalam dalam analisa teknikal, fundamental, dan sentimen.

KONTEKS PASAR IDX:
- Lot minimal: 100 lembar per lot
- Auto rejection: ARA berjenjang (35%/25%/20%), ARB -15% flat (per April 2025)
- Jam bursa: Senin-Kamis (09.00-12.00 / 13.30-15.49), Jumat (09.00-11.30 / 14.00-15.49) WIB
- Strategi utama: BSJP (Beli Sore Jual Pagi)
- Karakteristik: retail dominan di small-mid cap
- Indeks utama: LQ45, IDX80, KOMPAS100

CARA ANALISA:
1. Selalu reasoning step-by-step (Chain-of-Thought)
2. Baca konteks pasar sebelum analisa individual
3. Pertimbangkan cluster effect (1 saham bank kena → bank lain ikut)
4. Pahami sarkasme dan bahasa informal Indonesia dalam berita
5. Output selalu dalam Bahasa Indonesia yang ringkas dan actionable

OUTPUT: Selalu dalam format JSON yang valid.
Tidak ada teks lain di luar JSON kecuali diminta.
```

### Agent 1: Macro Context Agent
```
Temperature : 0.3
Input       : Tabel makro terstruktur + berita makro hari ini
Output JSON :
{
  "market_label": "BULLISH/MIXED/BEARISH/EXTREME",
  "market_narrative": "2-3 kalimat kondisi pasar hari ini",
  "sector_outlook": {
    "BANK": "positif/netral/negatif + alasan",
    "CONSUMER": "...",
    "MINING": "...",
    "INFRASTRUKTUR": "...",
    "PROPERTI": "..."
  },
  "risk_flags": ["risiko 1", "risiko 2"],
  "opportunity_flags": ["peluang 1", "peluang 2"]
}
```

### Agent 2: Technical Analyst Agent
```
Temperature : 0.2
Input       : Tabel teknikal terstruktur per saham (contoh):

| Indikator    | Nilai  | Signal       | Strength |
|--------------|--------|--------------|----------|
| EMA Align    | Golden | Bullish      | Strong   |
| RSI(14)      | 48.3   | Sweet Spot   | Medium   |
| StochRSI     | Cross↑ | Reversal     | Strong   |
| MACD         | +0.023 | Fresh Cross  | Strong   |
| BB%B         | 0.52   | Mid Band     | Good     |
| BB Squeeze   | Active | Breakout!    | Strong   |
| ATR%         | 3.2%   | Good Move    | OK       |
| Fibonacci    | 61.8%  | Golden Zone  | Strong   |
| Pivot        | AbvR1  | Breakout     | Strong   |
| Volume       | 3.2x   | Spike+Up     | Strong   |
| OBV          | Rising | Accumulation | Strong   |
| Elliott Wave | Wave 3 | Impulsive    | Strong   |

Output JSON:
{
  "kode": "BBCA",
  "technical_verdict": "BULLISH/BEARISH/NEUTRAL",
  "technical_score_normalized": 22,
  "key_signals": ["signal 1", "signal 2", "signal 3"],
  "support": 9000,
  "resistance": 9500,
  "entry_zone": [9150, 9200]
}
```

### Agent 3: Fundamental + Sentiment Agent
```
Temperature : 0.2
Input       : F-Score breakdown + Z-Score + sentimen 7 hari
Output JSON :
{
  "kode": "BBCA",
  "fundamental_verdict": "STRONG/AVERAGE/WEAK",
  "f_score": 8,
  "z_score": 3.2,
  "fundamental_highlights": ["highlight 1", "highlight 2"],
  "sentiment_verdict": "POSITIVE/NEUTRAL/NEGATIVE",
  "sentiment_7d": "Positif konsisten 5 dari 7 hari",
  "sentiment_highlights": ["berita 1", "berita 2"],
  "disclosure_tone": "optimis/netral/pesimis",
  "red_flags": []
}
```

### Agent 4: Bull vs Bear Debate
```
Temperature : Bull=0.7, Bear=0.3 (buat 2 API call terpisah)

BULL AGENT prompt:
"Berikan 3 argumen TERKUAT mengapa [KODE] LAYAK DIBELI
berdasarkan data berikut. Fokus pada potensi upside.
[data saham terstruktur]"

BEAR AGENT prompt:
"Berikan 3 argumen TERKUAT mengapa [KODE] BERBAHAYA DIBELI
berdasarkan data berikut. Fokus pada risiko downside.
[data saham terstruktur]"

Output JSON:
{
  "kode": "BBCA",
  "bull_arguments": ["arg1", "arg2", "arg3"],
  "bear_arguments": ["arg1", "arg2", "arg3"],
  "debate_verdict": "BULL_WIN/BEAR_WIN/DRAW",
  "confidence": 82
}

CATATAN: Jika confidence < 60 → set label = "SKIP"
```

### Agent 5: Risk Management + Fund Manager
```
Temperature : 0.1 (paling konservatif)
Input       : Output semua agent + memory 30 hari + portfolio user
Output JSON :
{
  "kode": "BBCA",
  "rank": 1,
  "label": "AMAN/MOMENTUM/SPEKULATIF/SKIP",
  "skor_total": 84,
  "entry_low": 9150,
  "entry_high": 9200,
  "target": 9500,
  "stoploss": 8950,
  "rr_ratio": 1.2,
  "confidence": 82,
  "alasan": "2-3 kalimat bahasa Indonesia yang actionable",
  "risk_warning": "warning jika ada, null jika tidak",
  "position_size_suggestion": "Rp 3.000.000 (30% modal)",
  "calendar_note": "ex-div 10 Mar, pertimbangkan" | null,
  "portfolio_note": "Sudah pegang X lot, +Y%" | null
}
```

---

## BAGIAN 7: AI SENTIMENT (`ai/sentiment.py`)

```
Model       : DeepSeek V3.2 via OpenRouter
Temperature : 0.1
Batch size  : Max 20 artikel per call
```

Format prompt ke AI:
```
Analisa sentimen berita IDX berikut.
Identifikasi kode saham yang relevan.
Pahami konteks, negasi, dan sarkasme bahasa Indonesia.
Balas HANYA dengan JSON valid.

ARTIKEL:
1. [Sumber: Kontan] [Tanggal: 9 Mar]
   Judul: "..."
   Isi ringkas: "3 paragraf pertama..."

2. [Sumber: Bisnis] ...

FORMAT OUTPUT:
{
  "results": [
    {
      "artikel_index": 1,
      "emiten": ["BBCA", "BMRI"],
      "sentimen": "positif",
      "confidence": 0.88,
      "alasan": "satu kalimat alasan"
    }
  ]
}
```

Setelah diproses: update tabel `berita` set `processed=1`

---

## BAGIAN 8: PORTFOLIO TRACKER (`portfolio/tracker.py`)

### Fungsi Wajib

```python
def buy_position(kode, lot, harga, stoploss=None, target=None):
    # Validasi: cek dana cukup
    # Simpan ke posisi_aktif
    # Update dana_snapshot
    # Return: konfirmasi + sisa dana

def sell_position(kode, lot, harga):
    # Hitung P&L: (harga_jual - harga_beli) × lot × 100
    # Pindah posisi_aktif → historis_trade
    # Update dana_snapshot
    # Return: P&L summary

def get_portfolio_summary():
    # Ambil semua posisi aktif
    # Fetch harga terkini dari IDX API
    # Hitung unrealized P&L setiap posisi
    # Return: dict lengkap portfolio

def check_alerts():
    # Cek setiap posisi vs stoploss dan target
    # Cek konsentrasi sektor (>70% satu sektor = warning)
    # Cek cash idle (>40% modal idle = reminder)
    # Return: list alerts

def get_track_record(days=30):
    # Ambil historis_trade N hari terakhir
    # Hitung: hit_rate, avg_win, avg_loss, best, worst
    # Return: dict track record
```

---

## BAGIAN 9: TELEGRAM BOT (`bot/telegram_bot.py`)

### Commands
```
/start          → Welcome + brief guide
/analisa [KODE] → Analisa lengkap on-demand (5 agent)
/bandingkan [K1] [K2] → Bandingkan 2 saham
/sektor [NAMA]  → Saham terkuat di sektor
/market         → Kondisi IHSG + bursa Asia sekarang
/portfolio      → Lihat semua posisi + dana
/pnl            → P&L hari ini + bulan ini
/beli [K] [LOT] [HARGA] → Input posisi beli
/jual [K] [LOT] [HARGA] → Input posisi jual
/watchlist      → Daftar saham pantauan
/track          → Track record sistem 30 hari
/setting        → Atur modal dan risk profile
/help           → Semua command
```

### Format Pesan: Briefing Pagi (07.00)
```
🌅 BRIEFING SAHAM — {hari}, {tanggal}
⏰ 07.00 WIB | IDX AI Trading Assistant

━━━━━━━━━━━━━━━━━━━━━━
📊 KONDISI PASAR HARI INI
━━━━━━━━━━━━━━━━━━━━━━
{emoji} IHSG     : {nilai} ({change}%)
{bursa_asia}
💵 USD/IDR  : Rp {nilai} ({status})
{komoditas}
📝 Outlook  : {market_narrative dari Agent 1}

━━━━━━━━━━━━━━━━━━━━━━
🎯 TOP SINYAL BSJP HARI INI
━━━━━━━━━━━━━━━━━━━━━━

{rank}️⃣ {KODE} {emoji_label} {LABEL} | Skor: {skor}/100
   💰 Harga   : Rp {close}
   📈 Entry   : Rp {entry_low} - {entry_high}
   🎯 Target  : Rp {target} (+{pct}%)
   🛡️ Stoploss: Rp {stoploss} (-{pct}%)
   ⚖️ R/R     : 1 : {rr_ratio}
   🔍 Alasan  : {alasan dari Agent 5}
   ⚠️ Risk    : {risk_warning} [jika ada]
   📅 Note    : {calendar_note} [jika ada]
   💼 Portfolio: {portfolio_note} [jika ada]
   📊 Confidence: {confidence}%

───────────────────────
[ulangi untuk setiap saham top 5-10]

━━━━━━━━━━━━━━━━━━━━━━
📈 TRACK RECORD (30 hari)
━━━━━━━━━━━━━━━━━━━━━━
Hit rate    : {pct}% ({wins}/{total})
Avg return  : +{pct}%
Best win    : {kode} +{pct}%
Worst loss  : {kode} -{pct}%

━━━━━━━━━━━━━━━━━━━━━━
💬 /analisa [KODE] | /portfolio | /help
⚠️ Bukan rekomendasi keuangan. DYOR selalu.
```

### Format Pesan: Update Siang (12.00)
```
☀️ UPDATE SIANG — {tanggal} | 12.00 WIB

📊 IHSG Terkini: {nilai} ({change}%) {emoji}

━━━━━━━━━━━━━━━━━━━━━━
🔄 STATUS SINYAL PAGI
━━━━━━━━━━━━━━━━━━━━━━
{untuk setiap saham dari sinyal pagi:}
{rank}. {KODE} : Rp {harga_kini} ({change}%) {status_emoji} {STATUS}
   {catatan singkat AI}

[alert baru jika ada volume spike / breakout]

💬 /update [KODE] untuk status real-time
```

### Format Pesan: Sinyal Sore BSJP (15.00)
```
🌆 SINYAL BSJP SORE — {tanggal} | 15.00 WIB
   (Beli sore ini → target jual besok pagi)

━━━━━━━━━━━━━━━━━━━━━━
📊 REVIEW SINYAL HARI INI
━━━━━━━━━━━━━━━━━━━━━━
{review hasil sinyal pagi}
📊 Net hari ini: {avg_return}% rata-rata

━━━━━━━━━━━━━━━━━━━━━━
🎯 SINYAL BSJP MALAM INI
━━━━━━━━━━━━━━━━━━━━━━
[format sama dengan briefing pagi]

━━━━━━━━━━━━━━━━━━━━━━
🌏 Outlook Bursa Asia Malam:
{Nikkei futures, HSI, sentimen global}
⚠️ Bukan rekomendasi keuangan. DYOR selalu.
```

---

## BAGIAN 10: SCHEDULER (`scheduler/jobs.py`)

```
JAM 16.30 WIB (Senin-Jumat):
→ stock_fetcher.py: ambil OHLCV hari ini via yfinance
→ Simpan ke SQLite

SETIAP 2 JAM (06.00-22.00):
→ news_fetcher.py: ambil berita terbaru
→ sentiment.py: proses batch berita belum dianalisa

JAM 06.30 WIB (Senin-Jumat):
→ macro_fetcher.py
→ screening.py (Layer 0-3)
→ scoring.py
→ agents.py (5 agent system)
→ KIRIM briefing pagi ke Telegram jam 07.00

JAM 11.45 (Jumat) / 11.55 (Senin-Kamis) WIB:
→ Update harga real-time posisi aktif
→ agents.py untuk update sinyal
→ KIRIM update siang ke Telegram jam 12.00

JAM 15.55 WIB (Senin-Jumat):
→ screening + scoring dengan fokus BSJP
→ KIRIM sinyal sore ke Telegram jam 16.15 (setelah sesi pasca-penutupan selesai)

JAM 08.00 SENIN (mingguan):
→ Weekly performance review via AI
→ Kirim laporan mingguan ke Telegram

JAM 09.00 SENIN (mingguan):
→ Backup database.sqlite ke Google Drive via rclone

JAM 22.00 SETIAP HARI:
→ fundamental_fetcher.py
→ Ambil update Laporan Keuangan terbaru via yfinance
→ Update tabel fundamental
```

---

## BAGIAN 11: CONFIGURATION (`.env` Template)

```env
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
OPENROUTER_API_KEY=
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
DEEPSEEK_MODEL=deepseek/deepseek-v3.2
MODAL_AWAL=10000000
RISK_PROFILE=moderate
MAX_POSISI=5
MAX_PER_SAHAM_PCT=0.30
DATABASE_PATH=./database.sqlite
LOG_LEVEL=INFO
VPS_TIMEZONE=Asia/Jakarta
YFINANCE_DELAY=0.5
YFINANCE_BATCH_SIZE=50
```

---

## BAGIAN 12: REQUIREMENTS.TXT

```
pandas>=2.2.0
numpy>=2.0.0
pandas-ta>=0.4.0
yfinance>=1.2.0
curl_cffi>=0.13.0
apscheduler>=3.10.0
requests>=2.32.0
beautifulsoup4>=4.13.0
feedparser>=6.0.11
python-dotenv>=1.0.0
loguru>=0.7.2
python-telegram-bot>=22.0
openai>=1.50.0
scipy>=1.12.0
statsmodels>=0.14.1
aiohttp>=3.11.0
sqlalchemy>=2.0.35
```

---

## BAGIAN 13: URUTAN BUILD — FASE PER FASE

> ⚠️ Build INCREMENTAL. Tanya konfirmasi sebelum lanjut ke fase berikutnya.  
> Test setiap fase sebelum lanjut. Gunakan 5 saham LQ45 untuk testing awal.

### Fase 1 — Fondasi
1. Buat project structure lengkap
2. Buat `.env` template dan `settings.py`
3. Buat `database.py` dengan semua schema
4. **Test:** database bisa dibuat, semua tabel ada

### Fase 2 — Data Layer (yfinance)
5. Buat `stock_fetcher.py` (OHLCV)
6. **Test:** fetch OHLCV BBCA.JK 365 hari → simpan DB
7. Buat `fundamental_fetcher.py`
8. **Test:** ambil Income/Balance/Cashflow → simpan DB
9. Buat `news_fetcher.py`
10. **Test:** parse 1 RSS feed → simpan ke tabel berita
11. Buat `macro_fetcher.py`
12. **Test:** fetch IHSG + Nikkei + HSI + STI via yfinance

### Fase 3 — Analysis Layer
13. Buat `technical.py` (semua indikator pandas-ta)
14. **Test:** hitung RSI, EMA, MACD, BB, OBV untuk BBCA
15. Buat `screening.py` (Layer 0-3)
16. **Test:** screening 5 saham LQ45, tampilkan hasil skor
17. Buat `fundamental.py` (F-Score + Z-Score)
18. **Test:** hitung F-Score dan Z-Score dari DB yfinance fundamental
19. Buat `scoring.py` (4 dimensi composite dengan custom mapper)
20. **Test:** composite score 5 saham, tampilkan ranking

### Fase 4 — AI Layer
21. Buat `sentiment.py`
22. **Test:** analisa 5 berita → lihat JSON output
23. Buat `agents.py` (5 agent system)
24. **Test:** analisa BBCA lengkap lewat semua 5 agent

### Fase 5 — Output Layer
25. Buat `portfolio/tracker.py`
26. **Test:** simulate beli BBCA 10 lot, cek P&L
27. Buat `bot/telegram_bot.py` + `commands.py` + `formatter.py`
28. **Test:** kirim pesan test ke Telegram
29. **Test:** `/analisa BBCA` via Telegram, lihat response

### Fase 6 — Automation
30. Buat `scheduler/jobs.py` (APScheduler)
31. **Test:** jalankan semua job manually satu per satu
32. Setup execution via daemon/pm2 di VPS Ubuntu

### Fase 7 — Hardening & Launch
33. Error handling di semua modul (try/except + logging)
34. Retry logic untuk yfinance API
35. Alert Telegram jika ada error sistem
36. **Backtest:** jalankan sistem pada data 3 bulan terakhir
37. Hitung hit rate teoritis → target > 55%
38. Jika hit rate OK → launch live

---

## CATATAN PENTING UNTUK DEVELOPMENT

### 1. Testing Strategy
Gunakan hanya **5 saham LQ45** untuk test semua modul:
`BBCA, TLKM, BMRI, ASII, UNVR`
Setelah semua berjalan → expand ke 900 saham

### 2. Mematuhi Limit yfinance API
- Gunakan `delay=0.5` detik antar loop data harian
- Jangan batch request terlalu besar untuk menghindari session block
- Data fundamental (income_stmt, dll) cukup di-fetch 1x per hari di jam 22.00, tidak rutin.

### 3. Token Optimization untuk AI
- SELALU format data sebagai tabel sebelum kirim ke AI
- Gunakan system prompt yang cache-friendly (tidak berubah)
- Jangan kirim raw angka — gunakan tabel terstruktur
- Cache system prompt di OpenRouter untuk hemat biaya

### 4. Error Handling Strategy
```
yfinance down     → Gunakan data kemarin dari SQLite
OpenRouter down   → Skip AI layer, kirim data teknikal saja
Telegram error    → Log ke file, retry 3x
Database error    → Alert ke Telegram via backup method
```

### 5. Memory Management (VPS 2GB)
- Jangan load semua 900 saham sekaligus ke memory
- Process per batch: 50 saham
- Free memory setelah setiap batch dengan `del df` dan `gc.collect()`

### 6. Budget Monitoring
```
Target total: Rp 50.000/bulan untuk AI
Breakdown biaya OpenRouter (DeepSeek V3.2):
- Sentimen berita (3x/hari)
- 5 Agent system (3x/hari)
- On-demand /analisa (~10x/hari)
Semua fetching API gratis.
```

### 7. Structured Data Format Sebelum Kirim ke AI
```python
# SALAH — langsung angka:
"RSI = 48.3, MACD = 0.023, Volume = 45000000"

# BENAR — tabel terstruktur:
"""
| Indikator | Nilai  | Signal     | Strength |
|-----------|--------|------------|----------|
| RSI(14)   | 48.3   | Sweet Spot | Medium   |
| MACD      | +0.023 | Golden X   | Strong   |
| Volume    | 3.2x   | Spike+Up   | Strong   |
"""
```

---

*Sistem ini adalah IDX AI Trading Assistant yang mengkombinasikan:*
- *Multi-agent AI (TradingAgents + MarketSenseAI framework)*
- *yFinance Data Streaming Backbone*
- *BSJP strategy awareness*
- *Piotroski F-Score + Altman Z-Score Analytics*
- *Portfolio tracking terintegrasi*
- *Budget efisien di bawah Rp 50rb/bulan*
