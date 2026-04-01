import os
from datetime import datetime
from supabase import create_client, Client

# --- SOZLAMALAR ---
# HuggingFace-dagi "Secrets" bo'limidan o'qib olinadigan o'zgaruvchilar
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise Exception("❌ SUPABASE_URL yoki SUPABASE_KEY topilmadi! Iltimos, HuggingFace Secrets bo'limini tekshiring.")

# Supabase mijozini yaratish
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("✅ Supabase cloud bazasiga ulanish muvaffaqiyatli yakunlandi!")
except Exception as e:
    print(f"❌ Supabase-ga ulanishda xatolik: {e}")
    raise e

def init_db():
    """Supabase-da jadvallar dashboard orqali SQL-da yaratilgan bo'lishi kerak."""
    # Hech nima qilish shart emas, lekin funksiya bot.py-da chaqirilgani uchun qoldiramiz.
    print("💡 Supabase bazasi ishga tushirildi.")

def add_user(user_id, username):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        # INSERT OR IGNORE ning Supabase-dagi analogi: upsert
        supabase.table("users").upsert({
            "user_id": user_id,
            "username": username,
            "join_date": now
        }, on_conflict="user_id").execute()
    except Exception as e:
        print(f"[-] add_user error: {e}")

def log_stats(user_id, service_type):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        supabase.table("stats").insert({
            "user_id": user_id,
            "service_type": service_type,
            "timestamp": now
        }).execute()
    except Exception as e:
        print(f"[-] log_stats error: {e}")

def get_stats_report():
    today = datetime.now().strftime("%Y-%m-%d")
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
            
        report = f"📊 **Bot Statistikasi (Cloud)**\n\n"
        report += f"👥 Jami foydalanuvchilar: {total_users}\n"
        report += f"🆕 Bugun qo'shilganlar: {new_users_today}\n\n"
        report += f"⚙️ **Xizmatlar aktivligi:**\n"
        report += f"🎬 Video Mix: {service_usage.get('mix', 0)}\n"
        report += f"🔍 Shazam: {service_usage.get('shazam', 0)}\n"
        report += f"📥 Downloader: {service_usage.get('download', 0)}\n"
        return report
    except Exception as e:
        print(f"Stats Error: {e}")
        return f"❌ Statistikani olishda xatolik yuz berdi: {str(e)[:50]}"
