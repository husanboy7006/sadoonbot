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
        
        # Barcha amallarni olish
        stats_res = supabase.table("stats").select("user_id, service_type").execute()
        data = stats_res.data
        
        # Alohida hisoblash uchun lug'at
        # Format: { 'mix': {'bot': 0, 'web': 0}, ... }
        breakdown = {
            "mix": {"bot": 0, "web": 0},
            "shazam": {"bot": 0, "web": 0},
            "download": {"bot": 0, "web": 0}
        }
        
        for item in data:
            stype = item["service_type"]
            if stype in breakdown:
                if item["user_id"] == 0:
                    breakdown[stype]["web"] += 1
                else:
                    breakdown[stype]["bot"] += 1
            
        report = f"📊 **Bot Statistikasi (Cloud)**\n\n"
        report += f"👥 Jami foydalanuvchilar: {total_users}\n"
        report += f"🆕 Bugun qo'shilganlar: {new_users_today}\n\n"
        
        report += f"⚙️ **Xizmatlar aktivligi:**\n"
        
        for key, name in [("mix", "🎬 Video Mix"), ("shazam", "🔍 Shazam"), ("download", "📥 Downloader")]:
            b = breakdown[key]
            total = b['bot'] + b['web']
            report += f"{name}: {total} (🤖 Bot: {b['bot']} | 🌐 Sayt: {b['web']})\n"
            
        return report
    except Exception as e:
        return f"❌ Xato: {str(e)[:50]}"
