import os
import subprocess
import shutil
import asyncio
import aiohttp
from concurrent.futures import ThreadPoolExecutor
from pydub import AudioSegment

_executor = ThreadPoolExecutor(max_workers=os.cpu_count() or 4)

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
        async with aiohttp.ClientSession() as session:
            async with session.post("https://www.tikwm.com/api/", data={'url': url}, timeout=15) as response:
                r = await response.json()
                if r.get('code') == 0:
                    play = r['data']['play']
                    return play if play.startswith('http') else "https://www.tikwm.com" + play
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

async def download_instagram(url: str, output_path: str):
    print(f"[*] Instagram (instaloader): {url[:50]}")
    try:
        import instaloader, re, tempfile
        import shutil as _shutil

        m = re.search(r'/(reel|p|tv)/([A-Za-z0-9_-]+)', url)
        if not m:
            return False
        shortcode = m.group(2)

        def _run():
            L = instaloader.Instaloader(
                download_pictures=False, download_videos=True,
                download_video_thumbnails=False, download_geotags=False,
                download_comments=False, save_metadata=False,
                compress_json=False, quiet=True
            )
            with tempfile.TemporaryDirectory() as tmpdir:
                post = instaloader.Post.from_shortcode(L.context, shortcode)
                L.download_post(post, target=tmpdir)
                for root, _, files in os.walk(tmpdir):
                    for f in files:
                        if f.endswith(".mp4"):
                            _shutil.move(os.path.join(root, f), output_path)
                            return True
            return False

        loop = asyncio.get_event_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(_executor, _run), timeout=60
        )
    except Exception as e:
        print(f"[!] Instaloader error: {e}")
    return False

async def download_video(url: str, output_path: str):
    print(f"[*] Video yuklash: {url[:30]}...")

    # 1. TikTok uchun maxsus TikWM
    if "tiktok.com" in url:
        v_url = await download_tiktok_tikwm(url)
        if v_url and await download_directly(v_url, output_path): return True

    # 2. Instagram uchun instaloader
    if "instagram.com" in url:
        if await download_instagram(url, output_path): return True
        print("[!] Instaloader failed, trying cobalt...")

    # 3. Cobalt API Fallbacks
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

    # 4. Yt-dlp Fallback
    print("[*] Try yt-dlp fallback with cookies...")
    return await yt_dlp_download(url, output_path, is_audio=False)

async def search_and_download_music(query: str, output_path: str):
    print(f"[*] Musiqa qidirilmoqda: {query}")
    
    # 1 va 2 - Vreden va Invidious
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://api.vreden.me/api/yt-search", params={"query": query}, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('status') and data.get('data'):
                        v_url = data['data'][0]['url']
                        if await download_audio(v_url, output_path): return True
    except: pass

    # Invidious Search
    instances = ["https://yewtu.be", "https://invidious.projectsegfau.lt", "https://iv.ggtyler.dev"]
    for inst in instances:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{inst}/api/v1/search", params={"q": query, "type": "video"}, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
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
            
        def _run():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(_executor, _run)
            
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
    print(f"[*] Downloading directly: {url[:30]}...")
    try:
        headers = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=60) as response:
                if response.status != 200:
                    return False
                with open(path, 'wb') as f:
                    while True:
                        chunk = await response.content.read(1024*1024)  # 1MB chunks
                        if not chunk:
                            break
                        f.write(chunk)
                return True
    except Exception as e:
        print(f"[!] Download directly error: {e}")
        return False

async def get_cobalt_url_custom(url, api_url, mode):
    headers = {"Accept": "application/json", "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
    data = {"url": url, "videoQuality": "720", "downloadMode": mode, "audioFormat": "mp3"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(api_url, json=data, headers=headers, timeout=5) as response:
                if response.status == 200:
                    res = await response.json()
                    if "url" in res: return res["url"]
    except Exception as e:
        print(f"[!] Cobalt {api_url} error: {e}")
    return None

async def mix_image_audio(image_path: str, audio_path: str, output_path: str):
    print(f"[*] Mixing image + audio (async) -> {output_path}")
    try:
        # -preset ultrafast va -crf 28 tezlikni oshirish uchun
        cmd = [ffmpeg_binary, "-y", "-loop", "1", "-i", f'"{image_path}"', "-i", f'"{audio_path}"',
               "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28", "-b:v", "800k", 
               "-tune", "stillimage", "-c:a", "aac", "-b:a", "128k", "-pix_fmt", "yuv420p", 
               "-shortest", f'"{output_path}"']
        
        process = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            print(f"[!] FFmpeg error: {stderr.decode()}")
            raise Exception("Video yasashda xatolik yuz berdi (FFmpeg error).")
        return True
    except Exception as e:
        print(f"[!] Mix error: {e}")
        raise e

async def compress_video(input_path: str, output_path: str):
    """Katta videoni 720p ga tushirib, 1 ta yadroda tezkor siqish"""
    print(f"[*] Compressing video (optimized): {input_path}")
    try:
        # Threads 1 va scale 720p RAM ni kam sarflaydi va tezroq bitadi
        cmd = [ffmpeg_binary, "-y", "-i", input_path, "-vcodec", "libx264", "-preset", "ultrafast", 
               "-crf", "30", "-vf", "scale='min(720,iw)':-2", "-threads", "1",
               "-acodec", "aac", "-b:a", "128k", output_path]
        process = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            # 5 daqiqali timeout
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=300)
            if process.returncode != 0:
                print(f"[!] Compression failed: {stderr.decode()}")
                return False
            print(f"[+] Compression success -> {output_path}")
            return True
        except asyncio.TimeoutError:
            print("[!] Compression timeout!")
            process.kill()
            return False
    except Exception as e:
        print(f"[!] Compression error: {e}")
        return False

async def identify_music(file_path: str):
    print(f"[*] Shazam vaqtincha ishlamaydi: {file_path}")
    return None
    # print(f"[*] Shazam identifying: {file_path}")
    # try:
    #     shazam = Shazam()
    #     out = await shazam.recognize(file_path)
    #     if not out.get('track'): return None
    #     track = out['track']
    #     return {"title": track.get('title'), "subtitle": track.get('subtitle'), "url": track.get('url'),
    #             "image": track.get('images', {}).get('coverarthq'), "shazam_url": track.get('share', {}).get('href')}
    # except Exception as e:
    #     print(f"[!] Shazam error: {e}")
    #     return None
