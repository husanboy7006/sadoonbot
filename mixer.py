import yt_dlp
import ffmpeg
import os
import requests

def download_audio(url: str, output_path: str):
    """
    Instagram g'ldan (yoki istalgan boshqa platformadan) videoning 
    audiosini mp3 formatida tortib oladi.
    """
    print(f"[*] Audioni ajratib olish boshlandi: {url}")
    
    # Instagram bo'lsa RapidAPI'ni sinab ko'ramiz
    if "instagram.com" in url:
        try:
            print("[*] Instagram uchun RapidAPI ishlatilmoqda...")
            api_url = "https://instagram-reels-downloader-api.p.rapidapi.com/download"
            querystring = {"url": url}
            headers = {
                "x-rapidapi-key": "af24a50843msh3494516d7830dcep165fd0jsn5bc86418db95",
                "x-rapidapi-host": "instagram-reels-downloader-api.p.rapidapi.com"
            }
            response = requests.get(api_url, headers=headers, params=querystring)
            data = response.json()
            
            # API dan olingan videodan audioni ajratib olish (yoki audio url bo'lsa o'shani olish)
            media_url = data.get("url") or data.get("download_url")
            
            if media_url:
                print(f"[+] Media link topildi, yuklash boshlandi...")
                temp_video = output_path.replace(".mp3", "_temp.mp4")
                r = requests.get(media_url, stream=True)
                with open(temp_video, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                # Videodan audioni ajratish (FFmpeg orqali)
                ffmpeg.input(temp_video).output(output_path, q=0).overwrite_output().run(quiet=True)
                os.remove(temp_video)
                print("[+] Audio muvaffaqiyatli tortildi!")
                return
            else:
                print("[-] API dan link olinmadi, yt-dlp ga o'tyapmiz...")
        except Exception as e:
            print(f"[-] RapidAPI xatosi: {e}, yt-dlp ga o'tyapmiz...")

    # yt-dlp fallback (yoki Instagram bo'lmasa)
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': output_path.replace('.mp3', '') + '.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': False,
        'noplaylist': True,
        # Oson usul (Faqat kompyuteringiz uchun)
        'cookiesfrombrowser': ('chrome',), 
    }
    
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    cookie_path = os.path.join(BASE_DIR, 'cookies.txt')
    
    if os.path.exists(cookie_path):
        ydl_opts['cookiefile'] = cookie_path
        ydl_opts.pop('cookiesfrombrowser', None)

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
        
    print("[+] Audio muvaffaqiyatli tortildi!")

def mix_image_audio(image_path: str, audio_path: str, output_path: str):
    """
    Rasm va Audioni birlashtiradi. 
    Video o'lchami rasmning asl o'lchami bilan bir xil bo'ladi (qora yo'laklarsiz yoki xira fonsiz).
    """
    print("[*] Rasm va audioni birlashtirib video ishlash boshlandi...")
    
    # FFmpeg orqali rasm va audioni qo'shish jarayoni:
    # rasm o'lchamlarini x264 kodeki uchun juft songa aylantiramiz: trunc(iw/2)*2
    input_image = (
        ffmpeg
        .input(image_path, loop=1)
        .filter('scale', 'trunc(iw/2)*2', 'trunc(ih/2)*2')
    )
    input_audio = ffmpeg.input(audio_path)
    
    (
        ffmpeg
        .output(
            input_image, 
            input_audio, 
            output_path, 
            vcodec='libx264', # Videoni eng mashhur siqish standarti
            acodec='aac',     # Audio kodeki
            shortest=None,    # Eng qisqa fayl (ya'ni audio) tugaganda videoni kesib tashlaydi
            pix_fmt='yuv420p',
            r=30              # Kadr tezligi (FPS)
        )
        .overwrite_output()   # Agar shunday fayl bo'lsa ustidan yoz
        .run()
    )
    
    print(f"[+] Video tayyor: {output_path}")
