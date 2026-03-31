import browser_cookie3
import http.cookiejar
import os

print("Brauzerlardan Instagram cookie larini izlash boshlandi...")

cj = http.cookiejar.MozillaCookieJar('cookies.txt')

def add_cookies(browser_fn, name):
    try:
        print(f"[*] {name} tekshirilmoqda...")
        cookies = browser_fn(domain_name='instagram.com')
        count = 0
        for cookie in cookies:
            cj.set_cookie(cookie)
            count += 1
        if count > 0:
            print(f"   [+] {name} dan {count} ta Instagram cookie topildi!")
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

for func, bname in checkers:
    add_cookies(func, bname)

if len(cj) > 0:
    cj.save(ignore_discard=True, ignore_expires=True)
    print("\n[MUVAFFAQIYAT!] Barcha topilgan cookies.txt fayliga saqlandi!")
    print(f"    Sizda {len(cj)} ta cookie mavjud. Endi bu faylni serverga yuborishingiz mumkin.")
else:
    print("\n[XATOLIK] Hech qanday brauzerdan Instagram cookie topilmadi!")
    print("    Iltimos avval brauzerda instagram.com ga kirib, profilingizga (login/parol) kiring va shundan so'ng qayta ishga tushiring.")
