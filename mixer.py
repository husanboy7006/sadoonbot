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

def get_instagram_stream(url: str, type_required: str = "video"):
    """Instagram uchun 4 bosqichli barqarorlashtirish tizimi"""
    
    # 0. Ssilkani tozalash
    if "?" in url:
        url = url.split("?")[0]
    if not url.endswith("/"): url += "/"
        
    headers = {"x-rapidapi-key": "af24a50843msh3494516d7830dcep165fd0jsn5bc86418db95"}
    errors = []
    
    # 1. Cobalt (unscrobbler)
    try:
        cobalt_1 = "https://cobalt.api.unscrobbler.com/api/json"
        res = requests.post(cobalt_1, headers={"Accept": "application/json", "Content-Type": "application/json"}, 
                            json={"url": url, "isAudioOnly": True if type_required == "audio" else False}, timeout=8)
        data = res.json()
        if data.get("url"): return data["url"]
        errors.append(f"Cobalt-1: {data.get('message', 'Nomalum')}")
    except Exception as e:
        errors.append(f"Cobalt-1: {str(e)}")

    # 2. Cobalt (rest instance)
    try:
        cobalt_2 = "https://api.cobalt.tools/api/json"
        res = requests.post(cobalt_2, headers={"Accept": "application/json", "Content-Type": "application/json"}, 
                            json={"url": url, "isAudioOnly": True if type_required == "audio" else False}, timeout=8)
        data = res.json()
        if data.get("url"): return data["url"]
        errors.append(f"Cobalt-2: {data.get('message', 'Nomalum')}")
    except Exception as e:
        errors.append(f"Cobalt-2: {str(e)}")

    # 3. API 1 (social-downloader)
    try:
        host1 = "social-downloader.p.rapidapi.com"
        res = requests.get(f"https://{host1}/api/instagram/video", headers={**headers, "x-rapidapi-host": host1}, params={"url": url}, timeout=10)
        data = res.json()
        link = data.get("data", {}).get("video_url") or data.get("data", {}).get("media_url")
        if link: return link
        errors.append(f"Rapid-1: {data.get('message', 'Maalumot yoq')}")
    except Exception as e:
        errors.append(f"Rapid-1: {str(e)}")

    # 4. API 2 (instagram-reels-downloader-api)
    try:
        host2 = "instagram-reels-downloader-api.p.rapidapi.com"
        res = requests.get(f"https://{host2}/download", headers={**headers, "x-rapidapi-host": host2}, params={"url": url}, timeout=10)
        data = res.json()
        medias = data.get("data", {}).get("medias", [])
        for m in medias:
            if type_required == "video" and m.get("type") == "video": return m.get("url")
            if type_required == "audio" and (m.get("type") == "audio" or m.get("is_audio")): return m.get("url")
        errors.append(f"Rapid-2: {data.get('message', 'Topilmadi')}")
    except Exception as e:
        errors.append(f"Rapid-2: {str(e)}")

    return " | ".join(errors)

def download_audio(url: str, output_path: str):
    """Audioni tortib oladi (Instagram uchun faqat API)"""
    if "instagram.com" in url:
        media_url = get_instagram_stream(url, type_required="audio")
        if not media_url or not isinstance(media_url, str) or not media_url.startswith("http"):
            err = media_url if isinstance(media_url, str) else "Noma'lum"
            raise Exception(f"Instagram ssilkasi o'qilmadi. Sababi: {err}")
        
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
