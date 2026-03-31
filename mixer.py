import yt_dlp
import ffmpeg
import os
import requests
from shazamio import Shazam
from pydub import AudioSegment

# FFmpeg ni har qanday muhitda (Windows yoki Linux) to'g'ri ishlashi uchun:
if os.path.exists("ffmpeg.exe"):
    # Windows: loyal papkadagi ffmpeg.exe ishlatilsin
    os.environ["PATH"] += os.pathsep + os.path.abspath(".")
    AudioSegment.converter = os.path.abspath("ffmpeg.exe")
    ffmpeg_binary = os.path.abspath("ffmpeg.exe")
else:
    # Linux (Server): tizimning tubidagi ffmpeg ishlatilsin
    AudioSegment.converter = "ffmpeg"
    ffmpeg_binary = "ffmpeg"

def get_instagram_stream(url: str):
    """Instagram uchun RapidAPI orqali media ssilkasini oladi"""
    try:
        print(f"[*] Instagram uchun Social Downloader ishlatilmoqda: {url}")
        api_url = "https://social-downloader.p.rapidapi.com/api/instagram/video"
        headers = {
            "x-rapidapi-key": "af24a50843msh3494516d7830dcep165fd0jsn5bc86418db95",
            "x-rapidapi-host": "social-downloader.p.rapidapi.com"
        }
        res = requests.get(api_url, headers=headers, params={"url": url})
        data = res.json()
        # API dan kelgan video/media linkini olamiz
        return data.get("data", {}).get("video_url") or data.get("data", {}).get("media_url")
    except Exception as e:
        print(f"[-] RapidAPI Error: {e}")
        return None

def download_audio(url: str, output_path: str):
    """
    Ssilkadan audioni mp3 formatida tortib oladi.
    """
    if "instagram.com" in url:
        media_url = get_instagram_stream(url)
        if media_url:
            try:
                # Videoni vaqtincha yuklab, audiosini ajratamiz
                temp_v = f"{output_path}_temp.mp4"
                r = requests.get(media_url, stream=True)
                with open(temp_v, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192): f.write(chunk)
                
                ffmpeg.input(temp_v).output(output_path, acodec='libmp3lame', ab='192k').overwrite_output().run(quiet=True)
                if os.path.exists(temp_v): os.remove(temp_v)
                print(f"[+] Audio RapidAPI orqali olindi: {output_path}")
                return
            except Exception as e:
                print(f"[-] RapidAPI download error: {e}")

    # yt-dlp fallback
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': output_path.replace('.mp3', ''),
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': True,
        'noplaylist': True,
        'ffmpeg_location': '.', 
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        print(f"[*] Audioni tortish boshlandi (yt-dlp): {url}")
        ydl.download([url])
    print("[+] Audio muvaffaqiyatli tortildi!")

def download_video(url: str, output_path: str):
    """
    Ssilkadagi videoni o'zini yuklab oladi.
    """
    if "instagram.com" in url:
        media_url = get_instagram_stream(url)
        if media_url:
            try:
                r = requests.get(media_url, stream=True)
                with open(output_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192): f.write(chunk)
                print(f"[+] Video RapidAPI orqali yuklab olindi: {output_path}")
                return
            except Exception as e:
                print(f"[-] RapidAPI video download error: {e}")

    # yt-dlp fallback
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': output_path,
        'quiet': True,
        'noplaylist': True,
        'ffmpeg_location': '.', 
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        print(f"[*] Video yuklash boshlandi (yt-dlp): {url}")
        ydl.download([url])
    print(f"[+] Video yuklab olindi: {output_path}")

def mix_image_audio(image_path: str, audio_path: str, output_path: str):
    """
    Rasm va Audioni birlashtiradi.
    """
    print("[*] Rasm va audioni birlashtirish boshlandi...")
    input_image = ffmpeg.input(image_path, loop=1).filter('scale', 'trunc(iw/2)*2', 'trunc(ih/2)*2')
    input_audio = ffmpeg.input(audio_path)
    
    (
        ffmpeg
        .output(input_image, input_audio, output_path, vcodec='libx264', acodec='aac', shortest=None, pix_fmt='yuv420p', r=30)
        .overwrite_output()
        .run(quiet=True)
    )
    print(f"[+] Video tayyor: {output_path}")

async def identify_music(file_path: str):
    """
    Shazam orqali musiqani aniqlaydi.
    """
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
