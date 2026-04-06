import os
import re
import requests
import sys
import subprocess
import shutil
import asyncio
import json
import socket
import urllib.request
import ssl
from pydub import AudioSegment
from shazamio import Shazam
from playwright.async_api import async_playwright

# [UNIVERSAL DNS PATCH] - Recursion-safe version
ctx = ssl._create_unverified_context()
old_getaddrinfo = socket.getaddrinfo
dns_cache = {}
in_dns_lookup = False

def is_ip(host):
    return re.match(r"^\d{1,3}(\.\d{1,3}){3}$", host) is not None

def new_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    global in_dns_lookup
    
    # 1. IP manzil bo'lsa yoki maxsus manzillar bo'lsa originalni qaytaramiz (Recursion oldini olish)
    if in_dns_lookup or is_ip(host) or host in ["localhost", "127.0.0.1", "0.0.0.0"]:
        return old_getaddrinfo(host, port, family, type, proto, flags)
    
    # 2. Telegram API uchun qat'iy IP (DNS ga bormasdan)
    if host == "api.telegram.org":
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', ('149.154.167.220', port))]
    
    # 3. Keshdan tekshirish
    if host in dns_cache:
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', (dns_cache[host], port))]
    
    # 4. Cloudflare DNS-over-HTTPS orqali IP ni aniqlash
    try:
        in_dns_lookup = True
        # DoH so'rovi (IP 1.1.1.1 ga to'g'ridan to'g'ri boradi, cheksiz siklni oldini oladi)
        url = f"https://1.1.1.1/dns-query?name={host}&type=A"
        req = urllib.request.Request(url, headers={'accept': 'application/dns-json'})
        with urllib.request.urlopen(req, timeout=5, context=ctx) as response:
            data = json.loads(response.read().decode())
            if "Answer" in data:
                for ans in data["Answer"]:
                    if ans["type"] == 1: # A record
                        ip = ans["data"]
                        dns_cache[host] = ip
                        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', (ip, port))]
    except:
        pass
    finally:
        in_dns_lookup = False
    
    return old_getaddrinfo(host, port, family, type, proto, flags)

socket.getaddrinfo = new_getaddrinfo
# -------------------------------------------------------------

# Unicode (emoji) xatolarni oldini olish
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

# FFmpeg yo'lini aniqlash
ffmpeg_binary = "ffmpeg"
if os.path.exists("ffmpeg.exe"):
    ffmpeg_binary = os.path.abspath("ffmpeg.exe")
elif shutil.which("ffmpeg"):
    ffmpeg_binary = shutil.which("ffmpeg")

AudioSegment.converter = ffmpeg_binary

async def scrape_instagram(url: str):
    """SnapInsta orqali Instagram videosini scraping qilish"""
    print(f"[*] Instagram Scraping: {url[:30]}...")
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
            page = await context.new_page()
            await page.goto("https://snapinsta.app/", timeout=60000)
            await page.fill("input#url", url)
            await page.click("button.btn-get")
            try:
                await page.wait_for_selector("div.download-items", timeout=20000)
                download_btn = await page.query_selector("a.download-media")
                if download_btn: return await download_btn.get_attribute("href")
            except: pass
            await browser.close()
        except Exception as e: print(f"[-] Instagram Scraper error: {e}")
    return None

async def scrape_youtube(url: str):
    """YouTube scraping qilish (ssyoutube / yt1s)"""
    print(f"[*] YouTube Scraping: {url[:30]}...")
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
            context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
            page = await context.new_page()
            sites = ["https://en.savefrom.net/1-youtube-video-downloader-524.html", "https://yt1s.com.co/en1/"]
            for site in sites:
                try:
                    await page.goto(site, timeout=40000)
                    if "savefrom" in site:
                        await page.fill("input#sf_url", url)
                        await page.click("button#sf_submit")
                        await page.wait_for_selector("div.link-box", timeout=15000)
                        btn = await page.query_selector("a.download-icon")
                        if btn: 
                            link = await btn.get_attribute("href")
                            if link and link.startswith("http"): return link
                    else:
                        await page.fill("input#s_input", url)
                        await page.click("button.btn-red")
                        await page.wait_for_selector("div#search-result", timeout=15000)
                        btn = await page.query_selector("a.btn-success")
                        if btn: 
                            link = await btn.get_attribute("href")
                            if link and link.startswith("http"): return link
                except:
                    continue
            await browser.close()
        except Exception as e:
            print(f"[-] YouTube Scraper error: {e}")
    return None

async def get_invidious_url(url: str):
    v_id = None
    if "youtu.be" in url: v_id = url.split("/")[-1].split("?")[0]
    else:
        m = re.search(r"v=([A-Za-z0-9_-]+)", url)
        if m: v_id = m.group(1)
        else:
            ms = re.search(r"/shorts/([A-Za-z0-9_-]+)", url)
            if ms: v_id = ms.group(1)
            else: v_id = url.split("/")[-1].split("?")[0]
    if not v_id: return None
    
    instances = ["https://yewtu.be", "https://invidious.projectsegfau.lt", "https://iv.ggtyler.dev", "https://invidious.flokinet.to"]
    for inst in instances:
        try:
            r = requests.get(f"{inst}/api/v1/videos/{v_id}", timeout=10)
            if r.status_code == 200:
                data = r.json()
                if "formatStreams" in data and data["formatStreams"]:
                    return data["formatStreams"][-1]["url"]
        except: pass
    return None

async def download_audio(url: str, output_path: str):
    print(f"[*] Audio yuklanmoqda: {url[:30]}...")
    if "instagram.com" in url:
        v_url = await scrape_instagram(url)
        if v_url and await download_directly(v_url, output_path + ".temp.mp4"):
            AudioSegment.from_file(output_path + ".temp.mp4").export(output_path, format="mp3", bitrate="192k")
            os.remove(output_path + ".temp.mp4")
            return True

    if "youtube.com" in url or "youtu.be" in url:
        v_url = await get_invidious_url(url)
        if v_url and await download_directly(v_url, output_path + ".temp.mp4"):
            AudioSegment.from_file(output_path + ".temp.mp4").export(output_path, format="mp3", bitrate="192k")
            os.remove(output_path + ".temp.mp4")
            return True
        v_url = await scrape_youtube(url)
        if v_url and await download_directly(v_url, output_path + ".temp.mp4"):
            AudioSegment.from_file(output_path + ".temp.mp4").export(output_path, format="mp3", bitrate="192k")
            os.remove(output_path + ".temp.mp4")
            return True

    for mirror in ["https://api.cobalt.tools/api/json", "https://cobalt-api.kwiateusz.xyz/api/json", "https://co.wuk.sh/api/json"]:
        a_url = await get_cobalt_url_custom(url, mirror, "audio")
        if a_url and await download_directly(a_url, output_path): return True

    return await yt_dlp_download(url, output_path, is_audio=True)

async def download_video(url: str, output_path: str):
    print(f"[*] Video yuklanmoqda: {url[:30]}...")
    if "instagram.com" in url:
        v_url = await scrape_instagram(url)
        if v_url and await download_directly(v_url, output_path): return True

    if "youtube.com" in url or "youtu.be" in url:
        v_url = await get_invidious_url(url)
        if v_url and await download_directly(v_url, output_path): return True
        v_url = await scrape_youtube(url)
        if v_url and await download_directly(v_url, output_path): return True

    for mirror in ["https://api.cobalt.tools/api/json", "https://cobalt-api.kwiateusz.xyz/api/json", "https://co.wuk.sh/api/json"]:
        v_url = await get_cobalt_url_custom(url, mirror, "video")
        if v_url and await download_directly(v_url, output_path): return True

    return await yt_dlp_download(url, output_path, is_audio=False)

async def yt_dlp_download(url, output_path, is_audio=False):
    try:
        import yt_dlp
        ydl_opts = {
            'format': 'bestaudio/best' if is_audio else 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best',
            'outtmpl': output_path.replace('.mp3', '') if is_audio else output_path,
            'ffmpeg_location': ffmpeg_binary, 'quiet': True,
            'extractor_args': {'youtube': {'player_clients': ['ios', 'android', 'web_embedded']}}
        }
        if is_audio: ydl_opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}]
        if os.path.exists("cookies.txt"): ydl_opts['cookiefile'] = 'cookies.txt'
        with yt_dlp.YoutubeDL(ydl_opts) as ydl: ydl.download([url])
        if is_audio and os.path.exists(output_path + ".mp3"): os.rename(output_path + ".mp3", output_path)
        return True
    except: return False

async def download_directly(url, path):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"}
        r = requests.get(url, stream=True, timeout=60, verify=False, headers=headers)
        with open(path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192): f.write(chunk)
        return True
    except: return False

async def get_cobalt_url_custom(url, api_url, mode):
    headers = {"Accept": "application/json", "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
    data = {"url": url, "videoQuality": "720", "downloadMode": mode, "audioFormat": "mp3"}
    try:
        r = requests.post(api_url, json=data, headers=headers, timeout=10)
        if r.status_code == 200:
            res = r.json()
            if "url" in res: return res["url"]
    except: pass
    return None

def mix_image_audio(image_path: str, audio_path: str, output_path: str):
    try:
        cmd = [ffmpeg_binary, "-y", "-loop", "1", "-i", image_path, "-i", audio_path,
               "-c:v", "libx264", "-tune", "stillimage", "-c:a", "aac", "-b:a", "192k",
               "-pix_fmt", "yuv420p", "-shortest", output_path]
        subprocess.run(cmd, check=True, capture_output=True)
        return True
    except: raise Exception("Video yasashda xatolik yuz berdi.")

async def identify_music(file_path: str):
    try:
        shazam = Shazam()
        out = await shazam.recognize(file_path)
        if not out.get('track'): return None
        track = out['track']
        return {"title": track.get('title'), "subtitle": track.get('subtitle'), "url": track.get('url'),
                "image": track.get('images', {}).get('coverarthq'), "shazam_url": track.get('share', {}).get('href')}
    except: return None
