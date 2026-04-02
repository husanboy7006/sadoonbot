import os
from datetime import datetime
from supabase import create_client, Client

# --- SOZLAMALAR ---
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise Exception("❌ SUPABASE_URL yoki SUPABASE_KEY topilmadi!")

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    raise e

def init_db():
    pass

def add_user(user_id, username):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        supabase.table("users").upsert({
            "user_id": user_id,
            "username": username,
            "join_date": now
        }, on_conflict="user_id").execute()
    except: pass

def get_all_users():
    """Barcha foydalanuvchilar ID ro'yxatini qaytaradi (reklama yuborish uchun)"""
    try:
        res = supabase.table("users").select("user_id").execute()
        return [row['user_id'] for row in res.data]
    except Exception as e:
        print(f"Error fetching users: {e}")
        return []

def log_stats(user_id, service_type):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        supabase.table("stats").insert({
            "user_id": user_id,
            "service_type": service_type,
            "timestamp": now
        }).execute()
    except: pass

def get_stats_report():
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        # Jami foydalanuvchilar
        users_res = supabase.table("users").select("user_id", count="exact").execute()
        total_users = users_res.count if users_res.count is not None else 0
        
        # Bugungi yangi odamlar
        new_res = supabase.table("users").select("user_id", count="exact").filter("join_date", "gte", f"{today} 00:00:00").execute()
        new_users_today = new_res.count if new_res.count is not None else 0
        
        # Barcha amallarni olish (Lifetime)
        stats_res = supabase.table("stats").select("user_id, service_type, created_at").execute() # created_at ni ham olamiz
        data = stats_res.data or []
        
        # Hisoblash uchun lug'atlar
        total_bd = {"mix": 0, "shazam": 0, "download": 0}
        today_bd = {"mix": 0, "shazam": 0, "download": 0}
        
        today_str = str(today) # YYYY-MM-DD
        
        for item in data:
            stype = item.get("service_type")
            if not stype or stype not in total_bd: continue
            
            # Lifetime stats
            total_bd[stype] += 1
            
            # Today's stats (Kutilmagan xatoliklarni oldini olish uchun local check)
            created_at = item.get("created_at", "")
            if today_str in created_at:
                today_bd[stype] += 1
            
        report = f"📊 <b>InstaMixer Admin Paneli</b>\n"
        report += f"━━━━━━━━━━━━━━━\n\n"
        
        report += f"👥 <b>Foydalanuvchilar</b>\n"
        report += f"├─ Jami: {total_users} kishi\n"
        report += f"└─ Bugun: +{new_users_today} yangi\n\n"
        
        report += f"📅 <b>BUGUNGI AKTIVLIK:</b>\n"
        report += f"├─ 🎬 Mix: {today_bd['mix']}\n"
        report += f"├─ 🔍 Shazam: {today_bd['shazam']}\n"
        report += f"└─ 📥 Download: {today_bd['download']}\n\n"
        
        report += f"🚀 <b>UMUMIY AKTIVLIK:</b>\n"
        report += f"├─ 🎬 Mix: {total_bd['mix']}\n"
        report += f"├─ 🔍 Shazam: {total_bd['shazam']}\n"
        report += f"└─ 📥 Download: {total_bd['download']}\n\n"
        
        total_actions = len(data)
        report += f"📈 <b>JAMI AMALLAR:</b> {total_actions} marta\n"
        report += f"━━━━━━━━━━━━━━━"
        
        return report
    except Exception as e:
        return f"❌ Xato: {str(e)[:50]}"
