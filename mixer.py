import os
import re
import requests
import ffmpeg
from shazamio import Shazam
from pydub import AudioSegment
from playwright.async_api import async_playwright

# FFmpeg sozlamasi
if os.path.exists("ffmpeg.exe"):
    os.environ["PATH"] += os.pathsep + os.path.abspath(".")
    AudioSegment.converter = os.path.abspath("ffmpeg.exe")
    ffmpeg_binary = os.path.abspath("ffmpeg.exe")
else:
    AudioSegment.converter = "ffmpeg"
    ffmpeg_binary = "ffmpeg"

# Instagram cookies (env dan yoki hardcoded fallback)
IG_COOKIES = [
    {"name": "csrftoken", "value": os.getenv("IG_CSRF", "iATgLAVLxRKdeHf5enEcuk"), "domain": ".instagram.com", "path": "/"},
    {"name": "ds_user_id", "value": os.getenv("IG_USER_ID", "72619245503"), "domain": ".instagram.com", "path": "/"},
    {"name": "sessionid", "value": os.getenv("IG_SESSION", "72619245503%3AcfIWsEkZUkKfD7%3A8%3AAYiPRzsiHNaP_6vNmM2Yt1zPunP3woaU3GFHdCaYcw"), "domain": ".instagram.com", "path": "/"},
    {"name": "mid", "value": os.getenv("IG_MID", "acgo0gALAAFlmmFzqVZpXOq5hZq0"), "domain": ".instagram.com", "path": "/"},
    {"name": "ig_did", "value": os.getenv("IG_DID", "57703F0B-BC11-40A9-B5BA-4EBC7499B23D"), "domain": ".instagram.com", "path": "/"},
    {"name": "datr", "value": os.getenv("IG_DATR", "0ijIaRLe-VW6YpeFwX2ugW6W"), "domain": ".instagram.com", "path": "/"},
]

async def get_instagram_video_url(url: str) -> str:
    """Playwright brauzer emulatori orqali Instagram video URL ni olish"""
    print(f"[*] Playwright: {url}")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )
        await context.add_cookies(IG_COOKIES)
        page = await context.new_page()
        
        try:
            await page.goto(url, timeout=30000)
            await page.wait_for_timeout(8000)
            
            # Video elementlardan src olish
            videos = await page.evaluate("""
                () => {
                    const videos = document.querySelectorAll('video');
                    return Array.from(videos).map(v => v.src || v.currentSrc).filter(s => s && s.startsWith('http'));
                }
            """)
            
            if videos:
                print(f"[+] Video topildi: {videos[0][:80]}...")
                await browser.close()
                return videos[0]
                
        except Exception as e:
            print(f"[-] Playwright xato: {e}")
        
        await browser.close()
    
    raise Exception("Instagram video topilmadi. Link noto'g'ri yoki post o'chirilgan bo'lishi mumkin.")

async def download_audio(url: str, output_path: str):
    """Instagram video dan audio ajratib olish"""
    if "instagram.com" in url:
        video_url = await get_instagram_video_url(url)
        
        # Videoni vaqtincha yuklab olish
        temp_v = f"{output_path}_temp.mp4"
        r = requests.get(video_url, stream=True, timeout=60)
        with open(temp_v, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192): 
                f.write(chunk)
        
        # Audio ajratish
        ffmpeg.input(temp_v).output(output_path, acodec='libmp3lame', ab='192k').overwrite_output().run(quiet=True, cmd=ffmpeg_binary)
        if os.path.exists(temp_v): os.remove(temp_v)
        print(f"[+] Audio tayyor: {output_path}")
        return
    
    # Instagram bo'lmagan saytlar uchun yt-dlp
    import yt_dlp
    ydl_opts = {'format': 'bestaudio/best', 'outtmpl': output_path.replace('.mp3', ''), 'quiet': True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl: 
        ydl.download([url])

async def download_video(url: str, output_path: str):
    """Instagram video ni yuklab olish"""
    if "instagram.com" in url:
        video_url = await get_instagram_video_url(url)
        
        r = requests.get(video_url, stream=True, timeout=60)
        with open(output_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192): 
                f.write(chunk)
        print(f"[+] Video tayyor: {output_path}")
        return
    
    # Boshqa saytlar uchun yt-dlp
    import yt_dlp
    ydl_opts = {'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best', 'outtmpl': output_path, 'quiet': True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl: 
        ydl.download([url])

def mix_image_audio(image_path: str, audio_path: str, output_path: str):
    """Rasm va Audioni birlashtiradi"""
    print("[*] Rasm va audioni birlashtirish boshlandi...")
    input_image = ffmpeg.input(image_path, loop=1).filter('scale', 'trunc(iw/2)*2', 'trunc(ih/2)*2')
    input_audio = ffmpeg.input(audio_path)
    
    (
        ffmpeg
        .output(input_image, input_audio, output_path, vcodec='libx264', acodec='aac', shortest=None, pix_fmt='yuv420p', r=30, preset='ultrafast')
        .overwrite_output()
        .run(quiet=True, cmd=ffmpeg_binary)
    )
    print(f"[+] Video tayyor: {output_path}")

async def identify_music(file_path: str):
    """Shazam orqali musiqani aniqlaydi"""
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
