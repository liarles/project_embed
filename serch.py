import requests

IP = "172.20.10.3"
urls = [
    f"http://{IP}/stream",
    f"http://{IP}:81/stream",
    f"http://{IP}/mjpeg/1",
    f"http://{IP}:81/mjpeg/1",
    f"http://{IP}/video",
    f"http://{IP}/capture",
    f"http://{IP}/jpg",
    f"http://{IP}/cam.mjpeg",
]

print("กำลังหา URL...")
for url in urls:
    try:
        r = requests.get(url, timeout=3, stream=True)
        ct = r.headers.get('Content-Type', '')
        print(f"✅ {url}")
        print(f"   Content-Type: {ct}")
    except Exception as e:
        print(f"❌ {url}")