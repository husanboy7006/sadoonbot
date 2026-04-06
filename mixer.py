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
    """SaveFrom (ssyoutube) orqali YouTube scraping qilish"""
    print(f"[*] YouTube Scraping (ssyoutube): {url[:30]}...")
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
            page = await context.new_page()
            # ssyoutube.com orqali (SaveFrom)
            await page.goto(f"https://ssyoutube.com/en105/youtube-video-downloader", timeout=60000)
            await page.fill("input#id_url", url)
            await page.click("button#btn_submit")
            try:
                await page.wait_for_selector("div.result-box", timeout=30000)
                download_btn = await page.query_selector("a.download-icon")
                if download_btn:
                    video_url = await download_btn.get_attribute("href")
                    if video_url and video_url.startswith("http"):
                        print("[+] Scraper (SaveFrom) orqali video URL topildi.")
                        return video_url
            except:
                print("[-] Scraper (SaveFrom) timeout yoki link topilmadi.")
            await browser.close()
        except Exception as e:
            print(f"[-] YouTube Scraper error: {e}")
    return None

async def get_invidious_url(url: str):
    """Invidious API orqali YouTube stream olish"""
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
    
    # Instagram -> Scraper
    if "instagram.com" in url:
        v_url = await scrape_instagram(url)
        if v_url and await download_directly(v_url, output_path + ".temp.mp4"):
            AudioSegment.from_file(output_path + ".temp.mp4").export(output_path, format="mp3", bitrate="192k")
            os.remove(output_path + ".temp.mp4")
            return True

    # YouTube -> Invidious -> Scraper -> Cobalt -> yt-dlp
    if "youtube.com" in url or "youtu.be" in url:
        # Invidious
        v_url = await get_invidious_url(url)
        if v_url and await download_directly(v_url, output_path + ".temp.mp4"):
            AudioSegment.from_file(output_path + ".temp.mp4").export(output_path, format="mp3", bitrate="192k")
            os.remove(output_path + ".temp.mp4")
            return True
        # Scraper (SaveFrom)
        v_url = await scrape_youtube(url)
        if v_url and await download_directly(v_url, output_path + ".temp.mp4"):
            AudioSegment.from_file(output_path + ".temp.mp4").export(output_path, format="mp3", bitrate="192k")
            os.remove(output_path + ".temp.mp4")
            return True

    # Cobalt mirrors
    for mirror in ["https://api.cobalt.tools/api/json", "https://cobalt-api.kwiateusz.xyz/api/json", "https://co.wuk.sh/api/json"]:
        a_url = await get_cobalt_url_custom(url, mirror, "audio")
        if a_url and await download_directly(a_url, output_path): return True

    # yt-dlp
    return await yt_dlp_download(url, output_path, is_audio=True)

async def download_video(url: str, output_path: str):
    print(f"[*] Video yuklanmoqda: {url[:30]}...")
    
    # Instagram Scraper
    if "instagram.com" in url:
        v_url = await scrape_instagram(url)
        if v_url and await download_directly(v_url, output_path): return True

    # YouTube (Invidious -> Scraper -> Cobalt)
    if "youtube.com" in url or "youtu.be" in url:
        v_url = await get_invidious_url(url)
        if v_url and await download_directly(v_url, output_path): return True
        
        v_url = await scrape_youtube(url)
        if v_url and await download_directly(v_url, output_path): return True

    # Cobalt
    for mirror in ["https://api.cobalt.tools/api/json", "https://cobalt-api.kwiateusz.xyz/api/json", "https://co.wuk.sh/api/json"]:
        v_url = await get_cobalt_url_custom(url, mirror, "video")
        if v_url and await download_directly(v_url, output_path): return True

    # yt-dlp
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
    except Exception as e:
        print(f"[-] yt-dlp error: {e}")
        return False

async def download_directly(url, path):
    try:
        r = requests.get(url, stream=True, timeout=60, verify=False)
        with open(path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192): f.write(chunk)
        return True
    except: return False

async def get_cobalt_url_custom(url, api_url, mode):
    headers = {"Accept": "application/json", "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
    data = {"url": url, "videoQuality": "720", "downloadMode": mode, "audioFormat": "mp3"}
    try:
        print(f"[*] Cobalt Mirror: {api_url}")
        r = requests.post(api_url, json=data, headers=headers, timeout=10)
        if r.status_code == 200:
            res = r.json()
            if "url" in res: return res["url"]
    except Exception as e: print(f"[-] Cobalt error ({api_url}): {e}")
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
