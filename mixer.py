import yt_dlp
import ffmpeg
import os

def download_audio(url: str, output_path: str):
    """
    Instagram g'ldan (yoki istalgan boshqa platformadan) videoning 
    audiosini mp3 formatida tortib oladi.
    """
    print(f"[*] Audioni ajratib olish boshlandi: {url}")
    
    # Agar fayl ext bo'lmasa qõshamiz (yt-dlp ni nastroykasi)
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
    }
    
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
