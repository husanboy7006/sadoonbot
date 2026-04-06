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

# FFmpeg yo'lini aniqlash (Linux va Windows uchun)
ffmpeg_binary = "ffmpeg"
if os.path.exists("ffmpeg.exe"):
    ffmpeg_binary = os.path.abspath("ffmpeg.exe")
elif shutil.which("ffmpeg"):
    ffmpeg_binary = shutil.which("ffmpeg")

# Pydub uchun sozlash
AudioSegment.converter = ffmpeg_binary
print(f"DEBUG: Tizimda ishlatilaidgan FFmpeg: {ffmpeg_binary}")

def _extract_shortcode(url: str) -> str:
    """URL dan shortcode ajratib olish (Instagram uchun)"""
    url = url.rstrip("/")
    match = re.search(r'/(reel|p|tv)/([A-Za-z0-9_-]+)', url)
    return match.group(2) if match else url.split("/")[-1]

async def scrape_instagram(url: str):
    """SnapInsta orqali Instagram videosini scraping qilish"""
    print(f"[*] Instagram Scraping boshlandi: {url[:30]}...")
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            await page.goto("https://snapinsta.app/", timeout=60000)
            await page.fill("input#url", url)
            await page.click("button.btn-get")
            try:
                await page.wait_for_selector("div.download-items", timeout=20000)
                download_btn = await page.query_selector("a.download-media")
                if download_btn:
                    video_url = await download_btn.get_attribute("href")
                    if video_url and video_url.startswith("http"):
                        return video_url
            except:
                pass
            await browser.close()
        except Exception as e:
            print(f"[-] Instagram Scraper error: {e}")
    return None

async def scrape_youtube(url: str):
    """y2mate.is (va boshqalar) orqali YouTube videosini scraping qilish"""
    print(f"[*] YouTube Scraping boshlandi: {url[:30]}...")
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            # y2mate.nu yoki boshqalar orqali (SSL xatosini chetlab o'tish uchun bir nechta sinab ko'ramiz)
            try:
                await page.goto("https://y2mate.nu/en117/", timeout=60000)
                await page.fill("input#url", url)
                await page.keyboard.press("Enter")
                await page.wait_for_selector("a#download-btn", timeout=20000)
                video_url = await (await page.query_selector("a#download-btn")).get_attribute("href")
                if video_url and video_url.startswith("http"):
                    return video_url
            except:
                pass
                
            await browser.close()
        except Exception as e:
            print(f"[-] YouTube Scraper error: {e}")
    return None

async def get_invidious_url(url: str):
    """Invidious API orqali YouTube stream olish (Alternativ yo'l)"""
    v_id = None
    if "youtu.be" in url:
        v_id = url.split("/")[-1].split("?")[0]
    else:
        match = re.search(r"v=([A-Za-z0-9_-]+)", url)
        if match: v_id = match.group(1)
        else: v_id = url.split("/")[-1].split("?")[0]
        
    if not v_id: return None
    
    instances = ["https://yewtu.be", "https://invidious.snopyta.org", "https://inv.riverside.rocks"]
    for inst in instances:
        try:
            r = requests.get(f"{inst}/api/v1/videos/{v_id}", timeout=10)
            if r.status_code == 200:
                data = r.json()
                if "formatStreams" in data:
                    # Eng sifatli streamni olamiz
                    return data["formatStreams"][-1]["url"]
        except: pass
    return None

async def download_audio(url: str, output_path: str):
    """Har qanday video dan audio ajratib olish"""
    print(f"[*] Audio yuklanmoqda: {url[:30]}...")
    
    # 1. Scraping fallbacks
    video_url = None
    if "instagram.com" in url:
        video_url = await scrape_instagram(url)
    elif "youtube.com" in url or "youtu.be" in url:
        # Avval Invidious sinab ko'ramiz (Tezroq)
        video_url = await get_invidious_url(url)
        if not video_url:
            video_url = await scrape_youtube(url)
        
    if video_url:
        try:
            r = requests.get(video_url, stream=True, timeout=60, verify=False) # Boshqa SSL xatolar uchun verify=False
            temp_vid = output_path + ".temp.mp4"
            with open(temp_vid, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192): f.write(chunk)
            audio = AudioSegment.from_file(temp_vid)
            audio.export(output_path, format="mp3", bitrate="192k")
            os.remove(temp_vid)
            print("[+] Audio Scraper via Invidious/y2mate orqali yuklandi.")
            return True
        except:
            pass

    # 2. Cobalt API
    audio_url = await get_cobalt_url(url, mode="audio")
    if audio_url:
        try:
            r = requests.get(audio_url, stream=True, timeout=60)
            with open(output_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192): f.write(chunk)
            print("[+] Audio Cobalt orqali yuklandi.")
            return True
        except:
            pass

    # 3. yt-dlp fallback (Eng oxirgi yo'l)
    try:
        import yt_dlp
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': output_path.replace('.mp3', ''),
            'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
            'ffmpeg_location': ffmpeg_binary,
            'quiet': True,
            'extractor_args': {'youtube': {'player_clients': ['ios', 'android', 'web_embedded']}}
        }
        if os.path.exists("cookies.txt"):
            ydl_opts['cookiefile'] = 'cookies.txt'
            
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        if os.path.exists(output_path + ".mp3"):
            os.rename(output_path + ".mp3", output_path)
        return True
    except Exception as e:
        print(f"[-] yt-dlp error: {e}")
        raise Exception(f"Audio yuklab bo'lmadi.")

async def download_video(url: str, output_path: str):
    """Har qanday video yuklab olish"""
    print(f"[*] Video yuklanmoqda: {url[:30]}...")
    
    # 1. Scraping fallbacks
    video_url = None
    if "instagram.com" in url:
        video_url = await scrape_instagram(url)
    elif "youtube.com" in url or "youtu.be" in url:
        video_url = await get_invidious_url(url)
        if not video_url:
            video_url = await scrape_youtube(url)
        
    if video_url:
        try:
            r = requests.get(video_url, stream=True, timeout=60, verify=False)
            with open(output_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192): f.write(chunk)
            print("[+] Video Scraper/Invidious orqali yuklandi.")
            return True
        except:
            pass

    # 2. Cobalt API
    video_url = await get_cobalt_url(url, mode="video")
    if video_url:
        try:
            r = requests.get(video_url, stream=True, timeout=60)
            with open(output_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192): f.write(chunk)
            print("[+] Video Cobalt orqali yuklandi.")
            return True
        except:
            pass

    # 3. yt-dlp fallback
    try:
        import yt_dlp
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best',
            'outtmpl': output_path,
            'ffmpeg_location': ffmpeg_binary,
            'quiet': True,
            'extractor_args': {'youtube': {'player_clients': ['ios', 'android', 'web_embedded']}}
        }
        if os.path.exists("cookies.txt"):
            ydl_opts['cookiefile'] = 'cookies.txt'
            
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return True
    except Exception as e:
        print(f"[-] yt-dlp video error: {e}")
        raise Exception(f"Video yuklab bo'lmadi.")

async def get_cobalt_url(url: str, mode: str = "video") -> str:
    """Cobalt API orqali media URL olish"""
    api_urls = [
        "https://api.cobalt.tools/api/json",
        "https://cobalt-api.kwiateusz.xyz/api/json",
        "https://cobalt.lonely-dev.xyz/api/json"
    ]
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
    }
    data = {"url": url, "videoQuality": "720", "downloadMode": mode, "audioFormat": "mp3"}
    for api_url in api_urls:
        try:
            response = requests.post(api_url, json=data, headers=headers, timeout=15)
            if response.status_code == 200:
                res_data = response.json()
                if "url" in res_data: return res_data["url"]
        except: pass
    return None

def mix_image_audio(image_path: str, audio_path: str, output_path: str):
    """Rasm va Audioni birlashtiradi"""
    try:
        cmd = [ffmpeg_binary, "-y", "-loop", "1", "-i", image_path, "-i", audio_path,
               "-c:v", "libx264", "-tune", "stillimage", "-c:a", "aac", "-b:a", "192k",
               "-pix_fmt", "yuv420p", "-shortest", output_path]
        subprocess.run(cmd, check=True, capture_output=True)
        return True
    except Exception as e:
        raise Exception("Video yasashda xatolik yuz berdi.")

async def identify_music(file_path: str):
    """Shazam orqali musiqani aniqlaydi"""
    try:
        shazam = Shazam()
        out = await shazam.recognize(file_path)
        if not out.get('track'): return None
        track = out['track']
        return {
            "title": track.get('title'),
            "subtitle": track.get('subtitle'),
            "url": track.get('url'),
            "image": track.get('images', {}).get('coverarthq'),
            "shazam_url": track.get('share', {}).get('href')
        }
    except:
        return None
