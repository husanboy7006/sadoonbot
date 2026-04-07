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
import time
from pydub import AudioSegment
from shazamio import Shazam

# [UNIVERSAL DNS PATCH] - Hugging Face dagi DNS muammolarini hal qilish
ctx = ssl._create_unverified_context()
old_getaddrinfo = socket.getaddrinfo
dns_cache = {}
in_dns_lookup = False

def is_ip(host):
    return re.match(r"^\d{1,3}(\.\d{1,3}){3}$", host) is not None

def new_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    global in_dns_lookup
    if in_dns_lookup or is_ip(host) or host in ["localhost", "127.0.0.1", "0.0.0.0"]:
        return old_getaddrinfo(host, port, family, type, proto, flags)
    if host == "api.telegram.org":
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', ('149.154.167.220', port))]
    if host in dns_cache:
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', (dns_cache[host], port))]
    try:
        in_dns_lookup = True
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
    except: pass
    finally: in_dns_lookup = False
    return old_getaddrinfo(host, port, family, type, proto, flags)

socket.getaddrinfo = new_getaddrinfo

# FFmpeg yo'lini aniqlash
ffmpeg_binary = "ffmpeg"
if os.path.exists("ffmpeg.exe"): ffmpeg_binary = os.path.abspath("ffmpeg.exe")
elif shutil.which("ffmpeg"): ffmpeg_binary = shutil.which("ffmpeg")
AudioSegment.converter = ffmpeg_binary

# [STRATEGY 1] - RapidAPI va boshqa uchinchi tomon API-lari (Ehtiyoj bo'lsa)
# Hozircha Cobalt va yt-dlp ni kuchaytiramiz

async def download_tiktok_tikwm(url: str):
    print(f"[*] TikTok (TikWM): {url[:30]}...")
    try:
        r = requests.post("https://www.tikwm.com/api/", data={'url': url}, timeout=15).json()
        if r.get('code') == 0: return "https://www.tikwm.com" + r['data']['play']
    except Exception as e:
        print(f"[!] TikWM Error: {e}")
    return None

async def download_audio(url: str, output_path: str):
    print(f"[*] Audio yuklash: {url[:30]}...")
    
    # 1. TikTok uchun maxsus TikWM
    if "tiktok.com" in url:
        v_url = await download_tiktok_tikwm(url)
        if v_url and await download_directly(v_url, output_path + ".temp.mp4"):
            try:
                AudioSegment.from_file(output_path + ".temp.mp4").export(output_path, format="mp3", bitrate="192k")
                if os.path.exists(output_path + ".temp.mp4"): os.remove(output_path + ".temp.mp4")
                return True
            except: pass
            
    # 2. Cobalt API Fallbacks
    cobalt_mirrors = [
        "https://api.cobalt.tools/api/json",
        "https://cobalt-api.kwiateusz.xyz/api/json",
        "https://co.wuk.sh/api/json",
        "https://cobalt.pervage.xyz/api/json"
    ]
    for mirror in cobalt_mirrors:
        print(f"[*] Try Cobalt Mirror: {mirror}")
        a_url = await get_cobalt_url_custom(url, mirror, "audio")
        if a_url and await download_directly(a_url, output_path): 
            print("[+] Cobalt success!")
            return True
            
    # 3. Yt-dlp (Instagram va barlar uchun oxirgi umid)
    print("[*] Try yt-dlp fallback...")
    return await yt_dlp_download(url, output_path, is_audio=True)

async def download_video(url: str, output_path: str):
    print(f"[*] Video yuklash: {url[:30]}...")

    # 1. TikTok uchun maxsus TikWM
    if "tiktok.com" in url:
        v_url = await download_tiktok_tikwm(url)
        if v_url and await download_directly(v_url, output_path): return True
        
    # 2. Cobalt API Fallbacks
    cobalt_mirrors = [
        "https://api.cobalt.tools/api/json",
        "https://cobalt-api.kwiateusz.xyz/api/json",
        "https://co.wuk.sh/api/json",
        "https://cobalt.pervage.xyz/api/json"
    ]
    for mirror in cobalt_mirrors:
        print(f"[*] Try Cobalt Mirror: {mirror}")
        v_url = await get_cobalt_url_custom(url, mirror, "video")
        if v_url and await download_directly(v_url, output_path): 
            print("[+] Cobalt success!")
            return True

    # 3. Yt-dlp Fallback (Cookie bilan)
    print("[*] Try yt-dlp fallback with cookies...")
    return await yt_dlp_download(url, output_path, is_audio=False)

async def search_and_download_music(query: str, output_path: str):
    print(f"[*] Musiqa qidirilmoqda: {query}")
    
    # 1 va 2 - Vreden va Invidious (Avvalgi loyihada bor edi)
    try:
        r = requests.get(f"https://api.vreden.me/api/yt-search", params={"query": query}, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data.get('status') and data.get('data'):
                v_url = data['data'][0]['url']
                if await download_audio(v_url, output_path): return True
    except: pass

    # Invidious Search
    instances = ["https://yewtu.be", "https://invidious.projectsegfau.lt", "https://iv.ggtyler.dev"]
    for inst in instances:
        try:
            r = requests.get(f"{inst}/api/v1/search", params={"q": query, "type": "video"}, timeout=10)
            if r.status_code == 200:
                data = r.json()
                if data and len(data) > 0:
                    v_url = f"https://www.youtube.com/watch?v={data[0]['videoId']}"
                    if await download_audio(v_url, output_path): return True
        except: pass
    
    return await yt_dlp_download(f"ytsearch1:{query}", output_path, is_audio=True)

async def yt_dlp_download(url, output_path, is_audio=False):
    print(f"[*] yt-dlp: {url[:30]} (Audio={is_audio})")
    try:
        import yt_dlp
        ydl_opts = {
            'format': 'bestaudio/best' if is_audio else 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best',
            'outtmpl': output_path.replace('.mp3', '') if is_audio else output_path,
            'ffmpeg_location': ffmpeg_binary,
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': True,
            'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1',
            'extractor_args': {'youtube': {'player_clients': ['web', 'android']}}
        }
        
        # [IMPORTANT] - Cookies fayli bo'lsa uni ulaymiz
        if os.path.exists("cookies.txt"):
            print("[+] Using cookies.txt for authentication")
            ydl_opts['cookiefile'] = "cookies.txt"
            
        if is_audio: 
            ydl_opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}]
            
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            
        # Natijani tekshirish
        if is_audio:
            if os.path.exists(output_path + ".mp3"):
                if os.path.exists(output_path): os.remove(output_path)
                os.rename(output_path + ".mp3", output_path)
                return True
            return os.path.exists(output_path)
        return os.path.exists(output_path)
    except Exception as e:
        print(f"[!] yt-dlp error: {e}")
        return False

async def download_directly(url, path):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (iphone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"}
        r = requests.get(url, stream=True, timeout=60, verify=False, headers=headers)
        if r.status_code != 200: return False
        with open(path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192): f.write(chunk)
        return True
    except Exception as e:
        print(f"[!] Download directly error: {e}")
        return False

async def get_cobalt_url_custom(url, api_url, mode):
    headers = {"Accept": "application/json", "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
    data = {"url": url, "videoQuality": "720", "downloadMode": mode, "audioFormat": "mp3"}
    try:
        r = requests.post(api_url, json=data, headers=headers, timeout=15)
        if r.status_code == 200:
            res = r.json()
            if "url" in res: return res["url"]
    except: pass
    return None

def mix_image_audio(image_path: str, audio_path: str, output_path: str):
    print(f"[*] Mixing image + audio -> {output_path}")
    try:
        cmd = [ffmpeg_binary, "-y", "-loop", "1", "-i", image_path, "-i", audio_path,
               "-c:v", "libx264", "-tune", "stillimage", "-c:a", "aac", "-b:a", "192k",
               "-pix_fmt", "yuv420p", "-shortest", output_path]
        subprocess.run(cmd, check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"[!] FFmpeg error: {e.stderr.decode()}")
        raise Exception("Video yasashda xatolik yuz berdi (FFmpeg error).")

async def identify_music(file_path: str):
    print(f"[*] Shazam identifying: {file_path}")
    try:
        shazam = Shazam()
        out = await shazam.recognize(file_path)
        if not out.get('track'): return None
        track = out['track']
        return {"title": track.get('title'), "subtitle": track.get('subtitle'), "url": track.get('url'),
                "image": track.get('images', {}).get('coverarthq'), "shazam_url": track.get('share', {}).get('href')}
    except Exception as e:
        print(f"[!] Shazam error: {e}")
        return None
