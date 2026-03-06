import cv2
import torch
import numpy as np
import os
from PIL import Image
import torchvision.models as models
import torchvision.transforms as transforms

# ============================
# ตั้งค่า
# ============================
PHOTO_FOLDER = "my_cat_photos"       # โฟลเดอร์รูปแมวเรา
SIGNATURE_FILE = "my_cat_signature.npy"  # ไฟล์ที่จะบันทึก

# ============================
# โหลด Feature Extractor
# ============================
print("=" * 40)
print("  🐱 Cat Signature Trainer")
print("=" * 40)
print("\nกำลังโหลด model...")

feature_model = models.resnet50(pretrained=True)
feature_model = torch.nn.Sequential(*list(feature_model.children())[:-1])
feature_model.eval()

transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406],
                         [0.229, 0.224, 0.225])
])

print("✅ โหลด model สำเร็จ!\n")

# ============================
# ฟังก์ชันดึง Feature
# ============================
def extract_feature(img_array):
    img = Image.fromarray(cv2.cvtColor(img_array, cv2.COLOR_BGR2RGB))
    tensor = transform(img).unsqueeze(0)
    with torch.no_grad():
        feat = feature_model(tensor)
    return feat.squeeze().numpy()

# ============================
# ตรวจสอบโฟลเดอร์
# ============================
if not os.path.exists(PHOTO_FOLDER):
    print(f"❌ ไม่พบโฟลเดอร์ '{PHOTO_FOLDER}'")
    print(f"   กรุณาสร้างโฟลเดอร์ '{PHOTO_FOLDER}' แล้วใส่รูปแมวลงไป")
    exit()

files = [f for f in os.listdir(PHOTO_FOLDER)
         if f.lower().endswith(('.jpg', '.jpeg', '.png'))]

if len(files) == 0:
    print(f"❌ ไม่พบรูปภาพในโฟลเดอร์ '{PHOTO_FOLDER}'")
    print("   รองรับไฟล์ .jpg .jpeg .png")
    exit()

print(f"📁 พบรูปทั้งหมด {len(files)} รูป\n")

# ============================
# สร้าง Signature
# ============================
features = []
failed = []

for i, fname in enumerate(files):
    path = os.path.join(PHOTO_FOLDER, fname)
    img = cv2.imread(path)
    
    if img is None:
        print(f"  ⚠️  อ่านไม่ได้ → {fname}")
        failed.append(fname)
        continue
    
    feat = extract_feature(img)
    features.append(feat)
    print(f"  ✅ [{i+1}/{len(files)}] {fname}")

print(f"\n📊 ผลสรุป:")
print(f"   สำเร็จ  : {len(features)} รูป")
print(f"   ล้มเหลว : {len(failed)} รูป")

if len(features) < 3:
    print("\n⚠️  รูปน้อยเกินไป แนะนำใช้อย่างน้อย 10 รูป เพื่อความแม่นยำ")

# ============================
# บันทึก Signature
# ============================
signature = np.mean(features, axis=0)
np.save(SIGNATURE_FILE, signature)

print(f"\n💾 บันทึก signature สำเร็จ → '{SIGNATURE_FILE}'")
print("\n✅ เทรนเสร็จแล้ว! รัน detect_cat.py เพื่อเริ่มตรวจจับได้เลย")

print("=" * 40)
