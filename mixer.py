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

def _extract_shortcode(url: str) -> str:
    """URL dan shortcode ajratib olish"""
    url = url.rstrip("/")
    # /reel/ABC123/ yoki /p/ABC123/ formatdan
    match = re.search(r'/(reel|p|tv)/([A-Za-z0-9_-]+)', url)
    return match.group(2) if match else url.split("/")[-1]

async def get_instagram_video_url_cobalt(url: str) -> str:
    """Cobalt API orqali video URL olish (tez va barqaror)"""
    # Bir nechta Cobalt API instansiyalarini sinab ko'rish
    api_urls = [
        "https://api.cobalt.tools/api/json",
        "https://cobalt-api.kwiateusz.xyz/api/json"
    ]
    
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
    }
    
    data = {
        "url": url,
        "videoQuality": "720",
        "downloadMode": "video"
    }
    
    for api_url in api_urls:
        try:
            print(f"[*] Cobalt API sinab ko'rilmoqda: {api_url}")
            response = requests.post(api_url, json=data, headers=headers, timeout=10)
            if response.status_code == 200:
                res_data = response.json()
                if "url" in res_data:
                    print(f"[+] Cobalt orqali topildi: {api_url}")
                    return res_data["url"]
                elif "status" in res_data and res_data["status"] == "redirect":
                    return res_data["url"]
            print(f"[-] Cobalt API xatosi ({api_url}): {response.status_code}")
        except Exception as e:
            print(f"[-] Cobalt API xatosi ({api_url}): {e}")
            
    return None

async def get_instagram_video_url(url: str) -> str:
    """Instagram video URL olish (Cobalt -> Playwright fallback)"""
    # 1-usul: Cobalt API (Tavsiya etiladi - tez va eng barqaror)
    video_url = await get_instagram_video_url_cobalt(url)
    if video_url:
        return video_url
        
    # 2-usul: Playwright (Zaxira - agar Cobalt ishlamasa)
    print("[*] Cobalt ishlamadi, Playwright (Embed) sinab ko'rilmoqda...")
    shortcode = _extract_shortcode(url)
    embed_url = f"https://www.instagram.com/p/{shortcode}/embed/"
    
    async with async_playwright() as p:
        # Brauzer parametrlarini optimallashtiramiz
        browser = await p.chromium.launch(
            headless=True, 
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 540, "height": 960}
        )
        page = await context.new_page()
        
        try:
            # Embed sahifani ochish
            await page.goto(embed_url, timeout=30000, wait_until="domcontentloaded")
            
            for attempt in range(3):
                await page.wait_for_timeout(3000)
                
                # Video tagini qidirish
                videos = await page.evaluate("""
                    () => {
                        const videos = document.querySelectorAll('video');
                        return Array.from(videos).map(v => v.src || v.currentSrc).filter(s => s && s.startsWith('http'));
                    }
                """)
                if videos:
                    print(f"[+] Playwright (Embed) video topildi: {videos[0][:60]}...")
                    await browser.close()
                    return videos[0]
                
                # Agar video bo'lmasa, 'play' tugmasini bosib ko'rish
                try:
                    play_btn = page.locator('button, [role="button"], .EmbedVideo').first
                    if await play_btn.is_visible(timeout=500):
                        await play_btn.click()
                except:
                    pass
            
            # Agar hali ham topilmasa, to'g'ridan-to'g'ri reel sahifasiga o'tamiz
            print("[*] Embed ishlamadi, direct page sinab ko'rilmoqda...")
            direct_url = f"https://www.instagram.com/reel/{shortcode}/"
            await page.goto(direct_url, timeout=30000, wait_until="domcontentloaded")
            
            for attempt in range(2):
                await page.wait_for_timeout(5000)
                videos = await page.evaluate("""
                    () => {
                        const videos = document.querySelectorAll('video');
                        return Array.from(videos).map(v => v.src || v.currentSrc).filter(s => s && s.startsWith('http'));
                    }
                """)
                if videos:
                    print(f"[+] Playwright (Direct) video topildi: {videos[0][:60]}...")
                    await browser.close()
                    return videos[0]
                
        except Exception as e:
            print(f"[-] Playwright xatosi: {e}")
        
        await browser.close()
    
    raise Exception("Video topilmadi. Linkni tekshiring yoki keyinroq urinib ko'ring.")

async def download_audio(url: str, output_path: str):
    """Instagram video dan audio ajratib olish"""
    if "instagram.com" in url:
        video_url = await get_instagram_video_url(url)
        
        temp_v = f"{output_path}_temp.mp4"
        r = requests.get(video_url, stream=True, timeout=60)
        with open(temp_v, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192): 
                f.write(chunk)
        
        ffmpeg.input(temp_v).output(output_path, acodec='libmp3lame', ab='192k').overwrite_output().run(quiet=True, cmd=ffmpeg_binary)
        if os.path.exists(temp_v): os.remove(temp_v)
        print(f"[+] Audio tayyor: {output_path}")
        return
    
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
