import os
import sqlite3
from datetime import datetime
from supabase import create_client, Client

# --- SOZLAMALAR ---
# Agar Supabase ma'lumotlari bo'lsa, u bilan ishlaydi, aks holda SQLite (loyiha rivoji uchun)
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
DB_PATH = "database.db"

# Supabase mijozini sozlash
supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("✅ Supabase-ga ulanish muvaffaqiyatli yakunlandi!")
    except Exception as e:
        print(f"❌ Supabase xatoligi: {e}")

def init_db():
    if not supabase:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Foydalanuvchilar jadvali (SQLITE)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                join_date TEXT
            )
        ''')
        
        # Xizmatlardan foydalanish jadvali (SQLITE)
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
    else:
        # Supabase-da jadvallar dashboard orqali yoki SQL orqali oldindan ochilgan bo'lishi kerak.
        # Lekin biz jadval borligiga ishonch qilishimiz mumkin.
        print("💡 Supabase-dan foydalanilmoqda. Jadvallarni Supabase Dashboard-da yaratishni unutmang!")

def add_user(user_id, username):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if supabase:
        try:
            # INSERT OR IGNORE ning Supabase-dagi analogi: upsert
            supabase.table("users").upsert({
                "user_id": user_id,
                "username": username,
                "join_date": now
            }, on_conflict="user_id").execute()
        except: pass
    else:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO users (user_id, username, join_date) VALUES (?, ?, ?)", (user_id, username, now))
        conn.commit()
        conn.close()

def log_stats(user_id, service_type):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if supabase:
        try:
            supabase.table("stats").insert({
                "user_id": user_id,
                "service_type": service_type,
                "timestamp": now
            }).execute()
        except: pass
    else:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO stats (user_id, service_type, timestamp) VALUES (?, ?, ?)", (user_id, service_type, now))
        conn.commit()
        conn.close()

def get_stats_report():
    today = datetime.now().strftime("%Y-%m-%d")
    
    if supabase:
        try:
            # Jami foydalanuvchilar
            users_res = supabase.table("users").select("user_id", count="exact").execute()
            total_users = users_res.count if users_res.count is not None else 0
            
            # Bugungi yangi odamlar
            new_res = supabase.table("users").select("user_id", count="exact").filter("join_date", "gte", f"{today} 00:00:00").execute()
            new_users_today = new_res.count if new_res.count is not None else 0
            
            # Xizmatlar statistikasi
            stats_res = supabase.table("stats").select("service_type").execute()
            service_usage = {}
            for item in stats_res.data:
                stype = item["service_type"]
                service_usage[stype] = service_usage.get(stype, 0) + 1
        except Exception as e:
            print(f"Stats Error: {e}")
            return "❌ Statistikani olishda xatolik yuz berdi."
    else:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM users WHERE join_date LIKE ?", (f"{today}%",))
        new_users_today = cursor.fetchone()[0]
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
