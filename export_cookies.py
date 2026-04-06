import browser_cookie3
import http.cookiejar
import os

print("Brauzerlardan Instagram va YouTube cookie larini izlash boshlandi...")

cj = http.cookiejar.MozillaCookieJar('cookies.txt')

def add_cookies(browser_fn, name, domains):
    try:
        print(f"[*] {name} tekshirilmoqda...")
        for domain in domains:
            try:
                cookies = browser_fn(domain_name=domain)
                count = 0
                for cookie in cookies:
                    cj.set_cookie(cookie)
                    count += 1
                if count > 0:
                    print(f"   [+] {name} dan {count} ta {domain} cookie topildi!")
            except:
                continue
    except Exception as e:
        print(f"   [-] {name} dan topilmadi ({e}).")

# chrome, edge, brave, firefox, opera qidiriladi
checkers = [
    (browser_cookie3.chrome, "Chrome"),
    (browser_cookie3.edge, "Edge"),
    (browser_cookie3.brave, "Brave"),
    (browser_cookie3.firefox, "Firefox"),
    (browser_cookie3.opera, "Opera")
]

target_domains = ['instagram.com', 'youtube.com', 'google.com']

for func, bname in checkers:
    add_cookies(func, bname, target_domains)

if len(cj) > 0:
    cj.save(ignore_discard=True, ignore_expires=True)
    print("\n[MUVAFFAQIYAT!] Barcha topilgan cookies.txt fayliga saqlandi!")
    print(f"    Sizda {len(cj)} ta cookie mavjud. Endi bu faylni loyiha papkasida qoldiring.")
else:
    print("\n[XATOLIK] Hech qanday brauzerdan cookie topilmadi!")
    print("    Iltimos avval brauzerda instagram.com yoki youtube.com ga kiring.")
