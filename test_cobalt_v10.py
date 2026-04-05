import requests
import json

url = "https://cobalt-api.kwiateusz.xyz/api/json"
data = {
    "url": "https://www.instagram.com/reel/DV6N5afjPCu/",
    "downloadMode": "video",
    "videoQuality": "720"
}
headers = {
    "Accept": "application/json",
    "Content-Type": "application/json"
}

try:
    response = requests.post(url, json=data, headers=headers)
    print(response.status_code, response.text)
except Exception as e:
    print(e)
