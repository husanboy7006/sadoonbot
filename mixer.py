import os
import re
import requests
import sys
import subprocess
import shutil
import asyncio
import json
from pydub import AudioSegment
from shazamio import Shazam
from playwright.async_api import async_playwright

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

def _extract_shortcode(url: str) -> str:
    url = url.rstrip("/")
    match = re.search(r'/(reel|p|tv)/([A-Za-z0-9_-]+)', url)
    return match.group(2) if match else url.split("/")[-1]

async def scrape_instagram(url: str):
    """SnapInsta orqali Instagram videosini scraping qilish"""
    print(f"[*] Instagram Scraping boshlandi: {url[:30]}...")
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
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

async def download_directly(video_url, output_path):
    """Berilgan URLdan faylni yuklab olish"""
    try:
        r = requests.get(video_url, stream=True, timeout=60, verify=False)
        with open(output_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192): f.write(chunk)
        return True
    except: return False

async def get_invidious_url(url: str):
    """Invidious API orqali YouTube stream olish"""
    v_id = None
    if "youtu.be" in url: v_id = url.split("/")[-1].split("?")[0]
    else:
        match = re.search(r"v=([A-Za-z0-9_-]+)", url)
        if match: v_id = match.group(1)
        else:
            match_short = re.search(r"/shorts/([A-Za-z0-9_-]+)", url)
            if match_short: v_id = match_short.group(1)
            else: v_id = url.split("/")[-1].split("?")[0]
            
    if not v_id: return None
    
    # Ko'proq va barqaror Invidious instance'lari
    instances = [
        "https://yewtu.be",
        "https://invidious.projectsegfau.lt",
        "https://iv.ggtyler.dev",
        "https://invidious.flokinet.to",
        "https://inv.riverside.rocks"
    ]
    for inst in instances:
        try:
            print(f"[*] YouTube (Invidious): {inst}/api/v1/videos/{v_id}")
            r = requests.get(f"{inst}/api/v1/videos/{v_id}", timeout=10)
            if r.status_code == 200:
                data = r.json()
                if "formatStreams" in data and len(data["formatStreams"]) > 0:
                    return data["formatStreams"][-1]["url"]
        except: pass
    return None

async def download_audio(url: str, output_path: str):
    """Audio yuklab olish logikasi"""
    print(f"[*] Audio yuklanmoqda: {url[:30]}...")
    
    # 1. Instagram scrap
    if "instagram.com" in url:
        v_url = await scrape_instagram(url)
        if v_url:
            if await download_directly(v_url, output_path + ".temp.mp4"):
                audio = AudioSegment.from_file(output_path + ".temp.mp4")
                audio.export(output_path, format="mp3", bitrate="192k")
                os.remove(output_path + ".temp.mp4")
                return True

    # 2. YouTube Invidious
    if "youtube.com" in url or "youtu.be" in url:
        v_url = await get_invidious_url(url)
        if v_url:
            if await download_directly(v_url, output_path + ".temp.mp4"):
                audio = AudioSegment.from_file(output_path + ".temp.mp4")
                audio.export(output_path, format="mp3", bitrate="192k")
                os.remove(output_path + ".temp.mp4")
                return True

    # 3. Cobalt API (Mirrors)
    cobalt_mirrors = [
        "https://api.cobalt.tools/api/json",
        "https://cobalt-api.kwiateusz.xyz/api/json",
        "https://co.wuk.sh/api/json"
    ]
    for mirror in cobalt_mirrors:
        audio_url = await get_cobalt_url_custom(url, mirror, mode="audio")
        if audio_url:
            if await download_directly(audio_url, output_path): return True

    # 4. yt-dlp (Last Resort)
    try:
        import yt_dlp
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': output_path.replace('.mp3', ''),
            'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
            'ffmpeg_location': ffmpeg_binary, 'quiet': True,
            'extractor_args': {'youtube': {'player_clients': ['ios', 'android', 'web_embedded']}}
        }
        if os.path.exists("cookies.txt"): ydl_opts['cookiefile'] = 'cookies.txt'
        with yt_dlp.YoutubeDL(ydl_opts) as ydl: ydl.download([url])
        if os.path.exists(output_path + ".mp3"): os.rename(output_path + ".mp3", output_path)
        return True
    except: raise Exception("Audio yuklab bo'lmadi.")

async def download_video(url: str, output_path: str):
    """Video yuklab olish"""
    print(f"[*] Video yuklanmoqda: {url[:30]}...")

    # 1. Instagram scrap
    if "instagram.com" in url:
        v_url = await scrape_instagram(url)
        if v_url:
            if await download_directly(v_url, output_path): return True

    # 2. YouTube Invidious
    if "youtube.com" in url or "youtu.be" in url:
        v_url = await get_invidious_url(url)
        if v_url:
            if await download_directly(v_url, output_path): return True

    # 3. Cobalt API Mirrors
    cobalt_mirrors = [
        "https://api.cobalt.tools/api/json",
        "https://cobalt-api.kwiateusz.xyz/api/json",
        "https://co.wuk.sh/api/json"
    ]
    for mirror in cobalt_mirrors:
        v_url = await get_cobalt_url_custom(url, mirror, mode="video")
        if v_url:
            if await download_directly(v_url, output_path): return True

    # 4. yt-dlp
    try:
        import yt_dlp
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best',
            'outtmpl': output_path, 'ffmpeg_location': ffmpeg_binary, 'quiet': True,
            'extractor_args': {'youtube': {'player_clients': ['ios', 'android', 'web_embedded']}}
        }
        if os.path.exists("cookies.txt"): ydl_opts['cookiefile'] = 'cookies.txt'
        with yt_dlp.YoutubeDL(ydl_opts) as ydl: ydl.download([url])
        return True
    except: raise Exception("Video yuklab bo'lmadi.")

async def get_cobalt_url_custom(url: str, api_url: str, mode: str) -> str:
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
