# 📁 custom_model_detection.py
# ตรวจจับวัตถุด้วยโมเดล YOLOv8 และแสดงกรอบ + label + confidence score

import cv2                      # ใช้สำหรับเปิดกล้องและแสดงภาพ
from ultralytics import YOLO    # ไลบรารีสำหรับโหลดและใช้ YOLOv8

# ─────────── PARAMETER CONFIG ───────────

MODEL_PATH = "best.pt"          # ที่อยู่ของโมเดลที่ฝึกเอง (custom model จาก Roboflow หรือ train เอง)
CONFIDENCE_THRESHOLD = 0.5      # ค่าความมั่นใจขั้นต่ำที่ยอมรับให้แสดงผล
CAMERA_INDEX = 0                # หมายเลขกล้อง (0 = กล้องหลักในระบบ)

# ─────────── โหลดโมเดล YOLOv8 ───────────

model = YOLO(MODEL_PATH)        # โหลดโมเดล YOLO ที่ฝึกมาแล้ว

# ─────────── เปิดกล้อง Webcam ───────────

cap = cv2.VideoCapture(CAMERA_INDEX)            # เปิดกล้อง
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)          # ตั้งความกว้างภาพ 640px
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)         # ตั้งความสูงภาพ 480px

# ตรวจสอบว่ากล้องเปิดติดไหม
if not cap.isOpened():
    print("❌ ไม่พบกล้องหรือเปิดไม่สำเร็จ")
    exit()

print("🎥 เริ่มการตรวจจับ... กด 'q' เพื่อออก")

# ─────────── วนลูปรับภาพจากกล้องและทำ Object Detection ───────────
while True:
    ret, frame = cap.read()     # อ่านภาพจากกล้อง
    if not ret:
        print("⚠️ ไม่สามารถอ่านภาพจากกล้องได้")
        continue

    results = model(frame)[0]   # ส่งภาพเข้าโมเดล → คืนผลลัพธ์กล่องทั้งหมด

    for box in results.boxes:
        conf = float(box.conf)  # ดึงค่าความมั่นใจ (confidence)

        # ข้ามวัตถุที่ไม่มั่นใจพอ
        if conf < CONFIDENCE_THRESHOLD:
            continue

        # ดึงพิกัดกรอบ Bounding Box
        x1, y1, x2, y2 = map(int, box.xyxy[0])       # มุมบนซ้าย → ล่างขวา
        cls_id = int(box.cls[0])                     # หมายเลขคลาส
        label = model.names[cls_id]                  # แปลงเป็นชื่อ label
        color = (0, 255, 0)                          # สีของกรอบ (เขียว)

        # วาดกรอบรอบวัตถุที่ตรวจพบ
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

        # สร้างข้อความ label เช่น "APPLE (0.87)"
        text = f"{label.upper()} ({conf:.2f})"

        # วัดขนาดของข้อความเพื่อวาดกล่องพื้นหลัง label
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)

        # วาดพื้นหลัง label (กรอบทึบ) ด้านบนของวัตถุ
        cv2.rectangle(frame, (x1, y1 - th - 10), (x1 + tw, y1), color, -1)

        # วางข้อความ label ด้านบนกรอบ
        cv2.putText(frame, text, (x1, y1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)

    # แสดงผลภาพพร้อมกรอบตรวจจับ
    cv2.imshow("Custom YOLOv8 Detection", frame)

    # ออกจากลูปเมื่อกดปุ่ม 'q'
    if cv2.waitKey(1) & 0xFF == ord('q'):
        print("👋 จบการตรวจจับ")
        break

# ─────────── ปิดกล้องและหน้าต่างแสดงผล ───────────
cap.release()
cv2.destroyAllWindows()