import cv2
import torch
import numpy as np
import os
import time
import threading
import requests
from PIL import Image
import torchvision.models as models
import torchvision.transforms as transforms
from sklearn.metrics.pairwise import cosine_similarity

# ============================
# 1. ตั้งค่า (แก้ IP ให้ตรงกับบอร์ด)
# ============================ฐ
STREAM_URL = f"http://{ESP32_IP}/stream"  # ตรงกับโค้ด ESP32 ใหม่

SIGNATURE_FILE       = "my_cat_signature.npy"
SIMILARITY_THRESHOLD = 0.65
FEED_INTERVAL        = 10  # วินาที

# ============================
# 2. โหลดโมเดล
# ============================
print("=" * 50)
print("  🐾 ESP32-CAM Animal Detection System")
print("=" * 50)

if not os.path.exists(SIGNATURE_FILE):
    print(f"\n❌ ไม่พบไฟล์ '{SIGNATURE_FILE}'")
    print("   กรุณารัน train_cat.py ก่อน!")
    exit()

print("\nกำลังโหลด signature แมวเรา...")
MY_CAT_SIGNATURE = np.load(SIGNATURE_FILE)
print("✅ โหลด signature สำเร็จ!")

print("กำลังโหลด ResNet50...")
feature_model = models.resnet50(weights='DEFAULT')
feature_model = torch.nn.Sequential(*list(feature_model.children())[:-1])
feature_model.eval()
transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406],
                         [0.229, 0.224, 0.225])
])
print("✅ โหลด ResNet50 สำเร็จ!")

print("กำลังโหลด YOLOv5...")
yolo = torch.hub.load('ultralytics/yolov5', 'yolov5s', pretrained=True)
yolo.conf = 0.5
yolo.classes = [14, 15, 16]  # 14=bird, 15=cat, 16=dog
print("✅ โหลด YOLOv5 สำเร็จ!\n")

# ============================
# 3. สีกรอบแต่ละสัตว์
# ============================
COLOR_MY_CAT    = (0, 255, 0)    # เขียว
COLOR_OTHER_CAT = (0, 0, 255)    # แดง
COLOR_DOG       = (0, 165, 255)  # ส้ม
COLOR_BIRD      = (255, 200, 0)  # ฟ้า
COLOR_TEXT_BG   = (0, 0, 0)      # พื้นหลังข้อความ

# ============================
# 4. ตัวแปร Global
# ============================
latest_frame   = None
latest_display = None
lock           = threading.Lock()
LAST_FED       = 0
detection_log  = []

# ============================
# 5. ฟังก์ชัน AI + UI
# ============================
def extract_feature(img_array):
    img    = Image.fromarray(cv2.cvtColor(img_array, cv2.COLOR_BGR2RGB))
    tensor = transform(img).unsqueeze(0)
    with torch.no_grad():
        feat = feature_model(tensor)
    return feat.squeeze().numpy()

def is_my_cat(cat_crop):
    feat = extract_feature(cat_crop)
    sim  = cosine_similarity([feat], [MY_CAT_SIGNATURE])[0][0]
    return sim, sim >= SIMILARITY_THRESHOLD

def draw_label_with_bg(frame, text, pos, color, font_scale=0.6, thickness=2):
    x, y = pos
    font = cv2.FONT_HERSHEY_SIMPLEX
    (w, h), baseline = cv2.getTextSize(text, font, font_scale, thickness)
    cv2.rectangle(frame, (x, y - h - 8), (x + w + 4, y + baseline), COLOR_TEXT_BG, -1)
    cv2.putText(frame, text, (x + 2, y - 4), font, font_scale, color, thickness)

def draw_info_panel(frame, logs):
    max_logs  = min(len(logs), 5)
    panel_h   = 30 + (max_logs * 22) + 10
    overlay   = frame.copy()
    cv2.rectangle(overlay, (0, 0), (280, panel_h), (30, 30, 30), -1)
    cv2.addWeighted(overlay, 0.65, frame, 0.35, 0, frame)
    cv2.putText(frame, "Detection Log", (8, 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1)
    for i, (text, color) in enumerate(logs[-5:]):
        cv2.putText(frame, text, (8, 42 + i * 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.48, color, 1)

def draw_legend(frame):
    h, w  = frame.shape[:2]
    items = [
        ("MY CAT -> Feed!", COLOR_MY_CAT),
        ("Other Cat",       COLOR_OTHER_CAT),
        ("Dog",             COLOR_DOG),
        ("Bird",            COLOR_BIRD),
    ]
    box_x = w - 190
    box_y = h - (len(items) * 22 + 15)
    overlay = frame.copy()
    cv2.rectangle(overlay, (box_x - 5, box_y - 18),
                  (w - 5, h - 5), (30, 30, 30), -1)
    cv2.addWeighted(overlay, 0.65, frame, 0.35, 0, frame)
    for i, (text, color) in enumerate(items):
        y = box_y + i * 22
        cv2.rectangle(frame, (box_x, y - 10), (box_x + 14, y + 4), color, -1)
        cv2.putText(frame, text, (box_x + 20, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)

def draw_timestamp(frame):
    h, w = frame.shape[:2]
    ts   = time.strftime("%Y-%m-%d  %H:%M:%S")
    cv2.putText(frame, ts, (w - 210, h - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1)

# ============================
# 6. Thread: ดึง MJPEG Stream จาก ESP32
# ============================
def stream_reader():
    global latest_frame
    print(f"🔄 กำลังเชื่อมต่อ {STREAM_URL}")

    while True:
        try:
            resp       = requests.get(STREAM_URL, stream=True, timeout=10)
            print(f"✅ เชื่อมต่อสำเร็จ! (status: {resp.status_code})")
            bytes_data = b""

            for chunk in resp.iter_content(chunk_size=4096):
                bytes_data += chunk

                # หาขอบเขต JPEG แต่ละเฟรม
                while True:
                    start = bytes_data.find(b'\xff\xd8')  # JPEG SOI
                    end   = bytes_data.find(b'\xff\xd9')  # JPEG EOI

                    if start == -1 or end == -1 or end <= start:
                        break  # รอข้อมูลเพิ่ม

                    jpg        = bytes_data[start:end + 2]
                    bytes_data = bytes_data[end + 2:]

                    img = cv2.imdecode(
                        np.frombuffer(jpg, dtype=np.uint8),
                        cv2.IMREAD_COLOR
                    )
                    if img is not None:
                        with lock:
                            latest_frame = img

        except Exception as e:
            print(f"❌ ขาดการเชื่อมต่อ: {e}")
            print("🔄 ลองใหม่ใน 3 วินาที...")
            time.sleep(3)

# ============================
# 7. Thread: AI Detection
# ============================
def detection_thread():
    global latest_display, LAST_FED, detection_log

    while True:
        with lock:
            frame = latest_frame.copy() if latest_frame is not None else None

        if frame is None:
            time.sleep(0.05)
            continue

        results       = yolo(frame, size=320)
        detections    = results.pandas().xyxy[0]
        display_frame = frame.copy()

        for _, row in detections.iterrows():
            x1     = int(row.xmin)
            y1     = int(row.ymin)
            x2     = int(row.xmax)
            y2     = int(row.ymax)
            animal = row['name']
            conf   = row['confidence']

            # แมว → เช็คว่าเป็นแมวเราไหม
            if animal == 'cat':
                cat_crop = frame[y1:y2, x1:x2]
                if cat_crop.size == 0:
                    continue
                similarity, mine = is_my_cat(cat_crop)
                if mine:
                    color = COLOR_MY_CAT
                    label = f"MY CAT {similarity:.0%}"
                    now   = time.time()
                    if now - LAST_FED > FEED_INTERVAL:
                        msg = f"[{time.strftime('%H:%M:%S')}] MY CAT {similarity:.0%}"
                        print(f"🐱 แมวเรา! ({similarity:.0%}) >>> ให้อาหาร! <<<")
                        detection_log.append((msg, COLOR_MY_CAT))
                        LAST_FED = now
                else:
                    color = COLOR_OTHER_CAT
                    label = f"Other Cat {similarity:.0%}"
                    msg   = f"[{time.strftime('%H:%M:%S')}] Other Cat"
                    print(f"🐱 แมวอื่น ({similarity:.0%})")
                    detection_log.append((msg, COLOR_OTHER_CAT))

            # หมา
            elif animal == 'dog':
                color = COLOR_DOG
                label = f"Dog {conf:.0%}"
                msg   = f"[{time.strftime('%H:%M:%S')}] Dog {conf:.0%}"
                print(f"🐶 พบหมา! ({conf:.0%})")
                detection_log.append((msg, COLOR_DOG))

            # นก
            elif animal == 'bird':
                color = COLOR_BIRD
                label = f"Bird {conf:.0%}"
                msg   = f"[{time.strftime('%H:%M:%S')}] Bird {conf:.0%}"
                print(f"🐦 พบนก! ({conf:.0%})")
                detection_log.append((msg, COLOR_BIRD))

            else:
                continue

            cv2.rectangle(display_frame, (x1, y1), (x2, y2), color, 2)
            draw_label_with_bg(display_frame, label, (x1, y1), color)

        # วาด UI ทับภาพ
        draw_info_panel(display_frame, detection_log)
        draw_legend(display_frame)
        draw_timestamp(display_frame)

        with lock:
            latest_display = display_frame

# ============================
# 8. เริ่มระบบ
# ============================
threading.Thread(target=stream_reader,    daemon=True).start()
threading.Thread(target=detection_thread, daemon=True).start()

print("📷 ระบบกำลังทำงาน...")
print("🟢 กรอบเขียว = MY CAT  → ให้อาหาร")
print("🔴 กรอบแดง  = Other Cat")
print("🟠 กรอบส้ม  = หมา")
print("🔵 กรอบฟ้า  = นก")
print("กด Q เพื่อออก | กด R เพื่อโหลด signature ใหม่")
print("=" * 50)

# ============================
# 9. Main Loop แสดงผล
# ============================
while True:
    with lock:
        view = latest_display if latest_display is not None else latest_frame

    if view is not None:
        cv2.imshow("ESP32-CAM Animal Detection", view)
    else:
        # หน้าจอรอเชื่อมต่อ
        waiting = np.zeros((300, 420, 3), dtype=np.uint8)
        cv2.putText(waiting, "Connecting to ESP32...",
                    (40, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        cv2.putText(waiting, STREAM_URL,
                    (40, 165), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1)
        cv2.putText(waiting, "Press Q to quit",
                    (130, 220), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (100, 100, 100), 1)
        cv2.imshow("ESP32-CAM Animal Detection", waiting)

    key = cv2.waitKey(1) & 0xFF

    if key == ord('q'):
        print("ปิดโปรแกรม...")
        break

    if key == ord('r'):
        if os.path.exists(SIGNATURE_FILE):
            MY_CAT_SIGNATURE = np.load(SIGNATURE_FILE)
            print("🔄 โหลด signature ใหม่สำเร็จ!")
        else:
            print("❌ ไม่พบไฟล์ signature")

cv2.destroyAllWindows()
print("✅ ปิดระบบเรียบร้อย")
