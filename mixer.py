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

def find_best_media_in_json(obj, type_required):
    """JSON ichidan rekurziya orqali eng mos linkni topadi"""
    candidates = []
    exts = [".mp3", ".m4a", "audio", "mp3"] if type_required == "audio" else [".mp4", "video", "mp4"]
    
    def recurse(d):
        if isinstance(d, dict):
            for k, v in d.items():
                if isinstance(v, (dict, list)): recurse(v)
                elif isinstance(v, str) and v.startswith("http"):
                    if any(x in v.lower() for x in exts): candidates.append(v)
        elif isinstance(d, list):
            for i in d: recurse(i)
            
    recurse(obj)
    return candidates[0] if candidates else None

def get_instagram_stream(url: str, type_required: str = "video"):
    """Instagram uchun 15 bosqichli mega-barqarorlashtirish tizimi"""
    
    # 0. Ssilkani tozalash
    if "?" in url: url = url.split("?")[0]
    if not url.endswith("/"): url += "/"
        
    headers = {"x-rapidapi-key": "af24a50843msh3494516d7830dcep165fd0jsn5bc86418db95"}
    errors = []
    
    # 1. COBALT INSTANCES (v10 payload)
    instances = [
        "https://api.cobalt.tools/api/json", "https://cobalt-api.kwiateusz.xyz/api/json",
        "https://cobalt.sh/api/json", "https://imput.net/api/json",
        "https://api.geronimo.top/api/json", "https://cobalt-api.v0lume.xyz/api/json"
    ]
    for i, base in enumerate(instances, 1):
        try:
            res = requests.post(base, headers={"Accept": "application/json", "Content-Type": "application/json"}, 
                                json={"url": url, "downloadMode": "audio" if type_required == "audio" else "video", "videoQuality": "720"}, timeout=6)
            if res.status_code == 200:
                d = res.json()
                if d.get("url"): return d["url"]
        except: pass

    # 2. RAPIDAPI (Power search bilan)
    rapid_hosts = [
        "instagram-reels-downloader-api.p.rapidapi.com",
        "instagram-downloader-v2.p.rapidapi.com",
        "instagram-downloader-download-instagram-videos-stories.p.rapidapi.com",
        "instagram-media-downloader.p.rapidapi.com",
        "social-downloader.p.rapidapi.com",
        "instagram-bulk-scraper-latest.p.rapidapi.com",
        "instagram-data12.p.rapidapi.com"
    ]
    
    for i, host in enumerate(rapid_hosts, 1):
        try:
            params = {"url": url}
            endpoint = "/download" if "reels" in host else ("/index" if "downloader" in host else "/media/info")
            if "bulk" in host: endpoint = "/media_download_url"
            
            res = requests.get(f"https://{host}{endpoint}", headers={**headers, "x-rapidapi-host": host}, params=params, timeout=10)
            if res.status_code == 200:
                data = res.json()
                # 2.1 Ma'lum bir kalitlarni tekshirish
                link = data.get("media") or data.get("url") or data.get("download_url") or data.get("video_url")
                if not link: # 2.2 Deep recursion search
                    link = find_best_media_in_json(data, type_required)
                
                if link and isinstance(link, str) and link.startswith("http"): return link
            errors.append(f"R{i}:{res.status_code}")
        except:
            errors.append(f"R{i}:Err")

    # 3. YT-DLP FALLBACK (Oxirgi chora)
    try:
        # Eng oxirgi linkni olishga harakat qilamiz
        ydl_opts = {
            'quiet': True, 'no_warnings': True,
            'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None,
            'format': 'best', 'get_url': True
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info.get('url'): return info['url']
            if info.get('entries'): return info['entries'][0].get('url')
    except Exception as e:
        errors.append(f"ytd:{str(e)[:15]}")

    return " | ".join(errors)

def download_audio(url: str, output_path: str):
    """Audioni tortib oladi (API + yt-dlp fallback)"""
    if "instagram.com" in url:
        media_url = get_instagram_stream(url, type_required="audio")
        if not media_url or not isinstance(media_url, str) or not media_url.startswith("http"):
            err = media_url if isinstance(media_url, str) else "Noma'lum"
            raise Exception(f"Yuklab bo'lmadi. Sababi: {err}")
        
        temp_v = f"{output_path}_temp.mp4"
        r = requests.get(media_url, stream=True, timeout=30)
        with open(temp_v, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192): f.write(chunk)
        
        ffmpeg.input(temp_v).output(output_path, acodec='libmp3lame', ab='192k').overwrite_output().run(quiet=True, cmd=ffmpeg_binary)
        if os.path.exists(temp_v): os.remove(temp_v)
        print(f"[+] Audio tayyor: {output_path}")
        return

    # Instagram bo'lmagan saytlar uchun yt-dlp
    ydl_opts = {'format': 'bestaudio/best', 'outtmpl': output_path.replace('.mp3', ''), 'quiet': True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl: ydl.download([url])

def download_video(url: str, output_path: str):
    """Videoni yuklab oladi (Instagram uchun faqat API)"""
    if "instagram.com" in url:
        media_url = get_instagram_stream(url, type_required="video")
        if not media_url or not isinstance(media_url, str) or not media_url.startswith("http"):
            err = media_url if isinstance(media_url, str) else "Noma'lum"
            raise Exception(f"Instagram video o'qilmadi. Sababi: {err}")
        
        r = requests.get(media_url, stream=True, timeout=60)
        with open(output_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192): f.write(chunk)
        print(f"[+] Video tayyor: {output_path}")
        return

    # Boshqa saytlar
    ydl_opts = {'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best', 'outtmpl': output_path, 'quiet': True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl: ydl.download([url])

def mix_image_audio(image_path: str, audio_path: str, output_path: str):
    """
    Rasm va Audioni birlashtiradi.
    """
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
