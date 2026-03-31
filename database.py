import sqlite3
from datetime import datetime
import os

# Bazani saqlash joyi (HuggingFace da /data/ o'rniga hozircha ./db/ ishlatamiz)
DB_PATH = "database.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Foydalanuvchilar jadvali
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            join_date TEXT
        )
    ''')
    
    # Xizmatlardan foydalanish jadvali
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            service_type TEXT,
            timestamp TEXT
        )
    ''')
    
    conn.commit()
    conn.close()

def add_user(user_id, username):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    join_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username, join_date) VALUES (?, ?, ?)", (user_id, username, join_date))
    conn.commit()
    conn.close()

def log_stats(user_id, service_type):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("INSERT INTO stats (user_id, service_type, timestamp) VALUES (?, ?, ?)", (user_id, service_type, now))
    conn.commit()
    conn.close()

def get_stats_report():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Jami foydalanuvchilar
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    
    # Bugungi yangi odamlar
    today = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("SELECT COUNT(*) FROM users WHERE join_date LIKE ?", (f"{today}%",))
    new_users_today = cursor.fetchone()[0]
    
    # Xizmatlar statistikasi
    cursor.execute("SELECT service_type, COUNT(*) FROM stats GROUP BY service_type")
    service_usage = dict(cursor.fetchall())
    
    conn.close()
    
    report = f"📊 **Bot Statistikasi**\n\n"
    report += f"👥 Jami foydalanuvchilar: {total_users}\n"
    report += f"🆕 Bugun qo'shilganlar: {new_users_today}\n\n"
    report += f"⚙️ **Xizmatlar aktivligi:**\n"
    report += f"🎬 Video Mix: {service_usage.get('mix', 0)}\n"
    report += f"🔍 Shazam: {service_usage.get('shazam', 0)}\n"
    report += f"📥 Downloader: {service_usage.get('download', 0)}\n"
    
    return report
