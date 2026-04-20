import os
from datetime import datetime
from supabase import create_client, Client

# --- SOZLAMALAR ---
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

class Database:
    def __init__(self):
        self.supabase = None
        if not SUPABASE_URL or not SUPABASE_KEY:
            print("WARNING: SUPABASE_URL or SUPABASE_KEY not found! Database logging is disabled.")
        else:
            try:
                self.supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
            except Exception as e:
                print(f"❌ Supabase ulanish xatosi: {e}")

    def init_db(self):
        pass

    def get_balance(self, user_id):
        if not self.supabase: return 0
        try:
            res = self.supabase.table("users").select("balance").eq("user_id", user_id).execute()
            if res.data:
                data = res.data[0]
                return data.get("balance", 0)
        except Exception as e:
            print(f"Error getting balance: {e}")
        return 0

    def update_balance(self, user_id, amount):
        if not self.supabase: return False
        try:
            current = self.get_balance(user_id)
            new_balance = current + amount
            if new_balance < 0: return False
            
            self.supabase.table("users").update({"balance": new_balance}).eq("user_id", user_id).execute()
            return True
        except Exception as e:
            print(f"Error updating balance: {e}")
            return False

    def set_balance(self, user_id, amount):
        if not self.supabase: return False
        try:
            self.supabase.table("users").update({"balance": amount}).eq("user_id", user_id).execute()
            return True
        except Exception as e:
            print(f"Error setting balance: {e}")
            return False

    def add_user(self, user_id, username):
        if not self.supabase: return
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            self.supabase.table("users").upsert({
                "user_id": user_id,
                "username": username,
                "join_date": now,
                "balance": 1  # Yangi foydalanuvchiga 1 ta bepul sovg'a
            }, on_conflict="user_id").execute()
        except: pass

    def get_all_users(self):
        if not self.supabase: return []
        try:
            res = self.supabase.table("users").select("user_id").execute()
            return [row['user_id'] for row in res.data]
        except Exception as e:
            print(f"Error fetching users: {e}")
            return []

    def log_stats(self, user_id, service_type):
        if not self.supabase: return
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            self.supabase.table("stats").insert({
                "user_id": user_id,
                "service_type": service_type,
                "timestamp": now
            }).execute()
        except: pass

    def get_stats_report(self):
        if not self.supabase:
            return "⚠️ Ma'lumotlar bazasi (Supabase) ulanmagan yoki kalitlar xato. Statistika mavjud emas."
            
        today = datetime.now().strftime("%Y-%m-%d")
        try:
            # 1. Jami foydalanuvchilar
            total_users = 0
            try:
                users_res = self.supabase.table("users").select("user_id", count="exact").execute()
                total_users = users_res.count if users_res.count is not None else 0
            except: pass
            
            # 2. Bugungi yangi odamlar
            new_users_today = 0
            try:
                new_res = self.supabase.table("users").select("user_id", count="exact").filter("join_date", "gte", f"{today} 00:00:00").execute()
                new_users_today = new_res.count if new_res.count is not None else 0
            except: pass
            
            # 3. Stats ma'lumotlarini olish
            data = []
            try:
                stats_res = self.supabase.table("stats").select("user_id, service_type, timestamp").execute() 
                data = stats_res.data or []
            except: pass
            
            # Hisoblash uchun lug'atlar
            total_bd = {"mix": 0, "shazam": 0, "download": 0, "cgi": 0}
            today_bd = {"mix": 0, "shazam": 0, "download": 0, "cgi": 0}
            
            today_str = str(today)
            for item in data:
                if not isinstance(item, dict): continue
                stype = item.get("service_type")
                if not stype or stype not in total_bd: stype = "download"
                
                total_bd[stype] += 1
                ts = item.get("timestamp", "")
                if today_str in ts:
                    today_bd[stype] += 1
                
            report = f"📊 <b>Sadoon AI Admin Paneli</b>\n"
            report += f"━━━━━━━━━━━━━━━\n\n"
            report += f"👥 <b>Foydalanuvchilar</b>\n"
            report += f"├─ Jami: {total_users} kishi\n"
            report += f"└─ Bugun: +{new_users_today} yangi\n\n"
            report += f"📅 <b>BUGUNGI AKTIVLIK:</b>\n"
            report += f"├─ 🎬 Klip yasash: {today_bd['mix']}\n"
            report += f"├─ 🔍 Musiqa topish: {today_bd['shazam']}\n"
            report += f"├─ 🚀 CGI Artist: {today_bd['cgi']}\n"
            report += f"└─ 📥 Instagram: {today_bd['download']}\n\n"
            report += f"🚀 <b>UMUMIY AKTIVLIK:</b>\n"
            report += f"├─ 🎬 Klip yasash: {total_bd['mix']}\n"
            report += f"├─ 🔍 Musiqa topish: {total_bd['shazam']}\n"
            report += f"├─ 🚀 CGI Artist: {total_bd['cgi']}\n"
            report += f"└─ 📥 Instagram: {total_bd['download']}\n\n"
            report += f"📈 <b>JAMI AMALLAR:</b> {len(data)} marta\n"
            report += f"━━━━━━━━━━━━━━━"
            return report
        except Exception as e:
            return f"❌ Hisobot tayyorlashda xatolik yuz berdi: {e}"
