import os
from datetime import datetime
from supabase import create_client

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

    def add_user(self, user_id, username):
        if not self.supabase: return
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            res = self.supabase.table("users").select("user_id").eq("user_id", str(user_id)).execute()
            if not res.data:
                self.supabase.table("users").insert({
                    "user_id": str(user_id),
                    "username": username,
                    "join_date": now,
                    "balance": 0,
                    "metadata": {}
                }).execute()
        except Exception as e:
            print(f"Error adding user: {e}")

    def get_user_metadata(self, user_id):
        if not self.supabase: return {}
        try:
            res = self.supabase.table("users").select("metadata").eq("user_id", str(user_id)).execute()
            if res.data:
                return res.data[0].get("metadata") or {}
        except Exception as e:
            print(f"Error getting metadata: {e}")
        return {}

    def update_user_metadata(self, user_id, metadata):
        if not self.supabase: return False
        try:
            current = self.get_user_metadata(user_id)
            current.update(metadata)
            self.supabase.table("users").update({"metadata": current}).eq("user_id", str(user_id)).execute()
            return True
        except Exception as e:
            print(f"Error updating metadata: {e}")
            return False

    def set_user_metadata(self, user_id, metadata):
        if not self.supabase: return False
        try:
            self.supabase.table("users").update({"metadata": metadata}).eq("user_id", str(user_id)).execute()
            return True
        except Exception as e:
            print(f"Error setting metadata: {e}")
            return False

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

    def is_premium(self, user_id):
        try:
            from datetime import date
            meta = self.get_user_metadata(user_id)
            until = meta.get("premium_until", "")
            result = bool(until) and until >= str(date.today())
            print(f"[DB] is_premium: user_id={user_id}, until={until!r}, result={result}")
            return result
        except Exception as e:
            print(f"[DB] is_premium error: {e}")
            return False

    def activate_premium(self, user_id, days):
        from datetime import date, timedelta
        until = str(date.today() + timedelta(days=days))
        print(f"[DB] activate_premium: user_id={user_id}, until={until}")
        ok = self.update_user_metadata(user_id, {"premium_until": until})
        meta_after = self.get_user_metadata(user_id)
        print(f"[DB] activate_premium result={ok}, meta_after={meta_after}")
        return until

    def get_daily_smm(self, user_id):
        from datetime import date
        today = str(date.today())
        meta = self.get_user_metadata(user_id)
        if meta.get("smm_date") != today:
            return 0
        return meta.get("smm_count", 0)

    def increment_daily_smm(self, user_id):
        from datetime import date
        today = str(date.today())
        meta = self.get_user_metadata(user_id)
        if meta.get("smm_date") != today:
            meta["smm_date"] = today
            meta["smm_count"] = 0
        meta["smm_count"] = meta.get("smm_count", 0) + 1
        self.update_user_metadata(user_id, meta)
        return meta["smm_count"]

    def get_state(self, user_id):
        if not self.supabase:
            return (None, "")
        try:
            res = self.supabase.table("states").select("state, data").eq("user_id", str(user_id)).execute()
            if res.data:
                return (res.data[0].get("state"), res.data[0].get("data") or "")
        except Exception as e:
            print(f"Error getting state: {e}")
        return (None, "")

    def set_state(self, user_id, state, data=""):
        if not self.supabase:
            return
        try:
            self.supabase.table("states").upsert({
                "user_id": str(user_id),
                "state": state,
                "data": data or ""
            }).execute()
        except Exception as e:
            print(f"Error setting state: {e}")

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
            total_bd = {"mix": 0, "shazam": 0, "download": 0, "translate": 0,
                        "smm_post": 0, "smm_reels": 0, "smm_plan": 0,
                        "smm_hashtag": 0, "smm_caption": 0, "smm_strategy": 0}
            today_bd = {"mix": 0, "shazam": 0, "download": 0, "translate": 0,
                        "smm_post": 0, "smm_reels": 0, "smm_plan": 0,
                        "smm_hashtag": 0, "smm_caption": 0, "smm_strategy": 0}
            
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
            smm_today = sum(today_bd[k] for k in ("smm_post", "smm_reels", "smm_plan", "smm_hashtag", "smm_caption", "smm_strategy"))
            smm_total = sum(total_bd[k] for k in ("smm_post", "smm_reels", "smm_plan", "smm_hashtag", "smm_caption", "smm_strategy"))
            report += f"📅 <b>BUGUNGI AKTIVLIK:</b>\n"
            report += f"├─ 🎬 Klip yasash: {today_bd['mix']}\n"
            report += f"├─ 🔍 Shazam: {today_bd['shazam']}\n"
            report += f"├─ 📥 Yuklab olish: {today_bd['download']}\n"
            report += f"├─ 🌐 Tarjima: {today_bd['translate']}\n"
            report += f"└─ ✍️ SMM Studio: {smm_today}\n"
            report += f"   ├─ 📝 Post: {today_bd['smm_post']}\n"
            report += f"   ├─ 🎬 Reels: {today_bd['smm_reels']}\n"
            report += f"   ├─ 📅 Plan: {today_bd['smm_plan']}\n"
            report += f"   ├─ #️⃣ Hashtag: {today_bd['smm_hashtag']}\n"
            report += f"   ├─ 💬 Caption: {today_bd['smm_caption']}\n"
            report += f"   └─ 📊 Strategiya: {today_bd['smm_strategy']}\n\n"
            report += f"🚀 <b>UMUMIY AKTIVLIK:</b>\n"
            report += f"├─ 🎬 Klip yasash: {total_bd['mix']}\n"
            report += f"├─ 🔍 Shazam: {total_bd['shazam']}\n"
            report += f"├─ 📥 Yuklab olish: {total_bd['download']}\n"
            report += f"├─ 🌐 Tarjima: {total_bd['translate']}\n"
            report += f"└─ ✍️ SMM Studio: {smm_total}\n"
            report += f"   ├─ 📝 Post: {total_bd['smm_post']}\n"
            report += f"   ├─ 🎬 Reels: {total_bd['smm_reels']}\n"
            report += f"   ├─ 📅 Plan: {total_bd['smm_plan']}\n"
            report += f"   ├─ #️⃣ Hashtag: {total_bd['smm_hashtag']}\n"
            report += f"   ├─ 💬 Caption: {total_bd['smm_caption']}\n"
            report += f"   └─ 📊 Strategiya: {total_bd['smm_strategy']}\n\n"
            report += f"📈 <b>JAMI AMALLAR:</b> {len(data)} marta\n"
            report += f"━━━━━━━━━━━━━━━"
            return report
        except Exception as e:
            return f"❌ Hisobot tayyorlashda xatolik yuz berdi: {e}"
