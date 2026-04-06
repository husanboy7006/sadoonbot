import os

import re

import requests

import sys

import subprocess

import shutil

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

print(f"DEBUG: Tizimda ishlatiladigan FFmpeg: {ffmpeg_binary}")



def _extract_shortcode(url: str) -> str:

    """URL dan shortcode ajratib olish (Instagram uchun)"""

    url = url.rstrip("/")

    match = re.search(r'/(reel|p|tv)/([A-Za-z0-9_-]+)', url)

    return match.group(2) if match else url.split("/")[-1]



async def get_cobalt_url(url: str, mode: str = "video") -> str:

    """Cobalt API orqali media URL olish (mode: 'video' yoki 'audio')"""

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

    

    data = {

        "url": url,

        "videoQuality": "720",

        "downloadMode": mode,

        "audioFormat": "mp3"

    }

    

    for api_url in api_urls:

        try:

            print(f"[*] Cobalt API ({mode}): {api_url}")

            response = requests.post(api_url, json=data, headers=headers, timeout=15)

            if response.status_code == 200:

                res_data = response.json()

                if "url" in res_data:

                    return res_data["url"]

                elif "status" in res_data and res_data["status"] == "redirect":

                    return res_data["url"]

        except Exception as e:

            print(f"[-] API error ({api_url}): {e}")

            

    return None



async def download_audio(url: str, output_path: str):

    """Har qanday video dan audio ajratib olish"""

    print(f"[*] Audio yuklanmoqda: {url[:30]}...")

    

    # 1-yo'l: Cobalt API (MP3 mode)

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



    # 2-yo'l: yt-dlp fallback

    try:

        import yt_dlp

        ydl_opts = {

            'format': 'bestaudio/best',

            'outtmpl': output_path.replace('.mp3', ''),

            'postprocessors': [{

                'key': 'FFmpegExtractAudio',

                'preferredcodec': 'mp3',

                'preferredquality': '192',

            }],

            'ffmpeg_location': ffmpeg_binary,

            'quiet': True

        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:

            ydl.download([url])

        

        if os.path.exists(output_path + ".mp3"):

            os.rename(output_path + ".mp3", output_path)

        return True

    except Exception as e:

        print(f"[-] yt-dlp error: {e}")

        raise Exception(f"Audio yuklab bo'lmadi: {e}")



async def download_video(url: str, output_path: str):

    """Har qanday video yuklab olish"""

    print(f"[*] Video yuklanmoqda: {url[:30]}...")

    

    # 1-yo'l: Cobalt API

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



    # 2-yo'l: yt-dlp

    try:

        import yt_dlp

        ydl_opts = {

            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best',

            'outtmpl': output_path,

            'ffmpeg_location': ffmpeg_binary,

            'quiet': True

        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:

            ydl.download([url])

        return True

    except Exception as e:

        print(f"[-] yt-dlp video error: {e}")

        raise Exception(f"Video yuklab bo'lmadi: {e}")



def mix_image_audio(image_path: str, audio_path: str, output_path: str):

    """Rasm va Audioni birlashtiradi (Subprocess orqali barqarorroq)"""

    try:

        cmd = [

            ffmpeg_binary, "-y",

            "-loop", "1", "-i", image_path,

            "-i", audio_path,

            "-c:v", "libx264", "-tune", "stillimage",

            "-c:a", "aac", "-b:a", "192k",

            "-pix_fmt", "yuv420p", "-shortest",

            output_path

        ]

        subprocess.run(cmd, check=True, capture_output=True)

        return True

    except subprocess.CalledProcessError as e:

        print(f"ERROR: ffmpeg failed: {e.stderr.decode()}")

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

