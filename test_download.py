from mixer import get_instagram_stream
import sys

url = "https://www.instagram.com/reel/DWYNRitDI4i/"

print("--- Testing VIDEO ---")
res_video = get_instagram_stream(url, type_required="video")
print(f"VIDEO Result: {res_video}")

print("\n--- Testing AUDIO ---")
res_audio = get_instagram_stream(url, type_required="audio")
print(f"AUDIO Result: {res_audio}")
