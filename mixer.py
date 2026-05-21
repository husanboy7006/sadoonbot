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

        loop = asyncio.get_running_loop()
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
        is_youtube = "youtube.com" in url or "youtu.be" in url

        ydl_opts = {
            'format': 'bestaudio/best' if is_audio else 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[filesize<?50M]/best',
            'outtmpl': output_path.replace('.mp3', '') if is_audio else output_path,
            'ffmpeg_location': ffmpeg_binary,
            'quiet': False,
            'no_warnings': False,
            'ignoreerrors': False,
            'socket_timeout': 30,
        }

        if is_youtube:
            ydl_opts['extractor_args'] = {
                'youtube': {'player_clients': ['ios', 'web_creator', 'android']}
            }
            ydl_opts['http_headers'] = {
                'User-Agent': 'com.google.android.youtube/19.09.37 (Linux; U; Android 11) gzip'
            }
        else:
            ydl_opts['http_headers'] = {
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15'
            }

        if os.path.exists("cookies.txt"):
            print("[+] Using cookies.txt")
            ydl_opts['cookiefile'] = "cookies.txt"

        if is_audio:
            ydl_opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}]

        def _run():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(_executor, _run)

        if is_audio:
            if os.path.exists(output_path + ".mp3"):
                if os.path.exists(output_path): os.remove(output_path)
                os.rename(output_path + ".mp3", output_path)
                return True
            return os.path.exists(output_path)
        return os.path.exists(output_path) and os.path.getsize(output_path) > 1000
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
                        chunk = await response.content.read(1024*1024)
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

async def download_audio_raw(url: str, out_base: str) -> str | None:
    """URL dan bestaudio yuklab, orijinal formatda saqlash. Fayl yo'lini qaytaradi."""
    import glob
    tmp_base = out_base + ".ytdlp"
    try:
        import yt_dlp
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': tmp_base + '.%(ext)s',
            'ffmpeg_location': ffmpeg_binary,
            'quiet': True,
            'no_warnings': True,
        }
        def _run():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(_executor, _run)
        files = glob.glob(tmp_base + '.*')
        if not files or os.path.getsize(files[0]) < 500:
            for f in files:
                try: os.remove(f)
                except: pass
            return None
        src = files[0]
        ext = os.path.splitext(src)[1]   # .m4a, .webm, .opus ...
        actual = out_base + ext
        os.rename(src, actual)
        print(f"[+] Audio yuklandi: {actual} ({os.path.getsize(actual)} bytes)")
        return actual
    except Exception as e:
        print(f"[!] download_audio_raw error: {e}")
        for f in glob.glob(tmp_base + '.*'):
            try: os.remove(f)
            except: pass
        return None

async def mix_image_audio(image_path: str, audio_path: str, output_path: str):
    """Rasm + audio/video fayl → video klip"""
    print(f"[*] Mixing: {image_path} + {audio_path} -> {output_path}")
    cmd = [ffmpeg_binary, "-y",
           "-loop", "1", "-i", image_path,
           "-i", audio_path,
           "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
           "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
           "-tune", "stillimage",
           "-c:a", "aac", "-b:a", "128k",
           "-pix_fmt", "yuv420p",
           "-shortest", output_path]
    process = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        err = stderr.decode()[-400:]
        print(f"[!] FFmpeg mix error: {err}")
        raise Exception(f"Video yasashda xatolik (FFmpeg):\n{err[-150:]}")
    return True

async def ensure_mp3(path: str) -> bool:
    """Istalgan audio/video faylni mp3 ga o'tkazish"""
    if not os.path.exists(path) or os.path.getsize(path) < 500:
        return False
    tmp = path + ".tmp.mp3"
    cmd = [ffmpeg_binary, "-y", "-i", path, "-vn", "-acodec", "libmp3lame",
           "-ab", "192k", "-ar", "44100", tmp]
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    _, stderr = await proc.communicate()
    if proc.returncode == 0 and os.path.exists(tmp) and os.path.getsize(tmp) > 500:
        os.replace(tmp, path)
        return True
    if os.path.exists(tmp): os.remove(tmp)
    print(f"[!] ensure_mp3 failed: {stderr.decode()[-200:]}")
    return False

async def compress_video(input_path: str, output_path: str):
    """Katta videoni 720p ga tushirib, 1 ta yadroda tezkor siqish"""
    print(f"[*] Compressing video (optimized): {input_path}")
    try:
        cmd = [ffmpeg_binary, "-y", "-i", input_path, "-vcodec", "libx264", "-preset", "ultrafast",
               "-crf", "30", "-vf", "scale='min(720,iw)':-2", "-threads", "1",
               "-acodec", "aac", "-b:a", "128k", output_path]
        process = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
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
