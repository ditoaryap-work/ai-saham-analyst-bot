# 🚀 Panduan Deploy ke VPS

## Prasyarat
- VPS Ubuntu (Tencent Cloud 2C/2G)
- Akses SSH (`ssh root@IP_VPS`)

---

## Step 1 — Install Python & Dependencies

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python 3.12 + pip + venv
sudo apt install -y python3 python3-pip python3-venv git

# Set timezone WIB
sudo timedatectl set-timezone Asia/Jakarta
```

## Step 2 — Install PM2

```bash
# Install Node.js (untuk PM2)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# Install PM2
sudo npm install -g pm2
```

## Step 3 — Clone & Setup Project

```bash
# Clone dari GitHub
cd /root
git clone https://github.com/ditoaryap-work/ai-saham-analyst-bot.git
cd ai-saham-analyst-bot

# Buat virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Buat folder logs
mkdir -p logs
```

## Step 4 — Copy .env

```bash
# Buat file .env (copy dari laptop atau ketik manual)
nano config/.env
```

Isi dengan:
```
TELEGRAM_BOT_TOKEN=xxxx
TELEGRAM_CHAT_ID=xxxx
OPENROUTER_API_KEY=xxxx
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

## Step 5 — Test Dulu

```bash
# Test kirim pesan Telegram
source venv/bin/activate
python bot/telegram_bot.py --test

# Kalau OK → lanjut ke PM2
```

## Step 6 — Jalankan dengan PM2

```bash
# Start bot
pm2 start ecosystem.config.js

# Cek status
pm2 status

# Lihat log real-time
pm2 logs ai-saham

# Auto-start saat VPS reboot
pm2 save
pm2 startup
```

## Commands PM2 Berguna

```bash
pm2 status          # Lihat status bot
pm2 logs ai-saham   # Log real-time
pm2 restart ai-saham # Restart bot
pm2 stop ai-saham   # Stop bot
pm2 monit           # Monitor CPU/RAM
```

## Update Code (Kalau Ada Perubahan)

```bash
cd /root/ai-saham-analyst-bot
git pull
pm2 restart ai-saham
```
