import cv2
import zmq
import json
import time
from ultralytics import YOLO
from pyfirmata2 import Arduino
from tkinter import Tk, Button

# ==== CONFIG ====
PORT = 'COM5'
PIN_SERVO = {
    "leftright": 9,
    "updown": 11,
    "grip1": 7,
    "grip2": 6
}
positions = [180, 141, 44]
CONFIDENCE_THRESHOLD = 0.8

# ==== YOLO Model ====
model = YOLO("best.pt")
print("🧠 YOLO Classes:", model.names)

# ==== ZeroMQ PUB ====
context = zmq.Context()
socket = context.socket(zmq.PUB)
socket.bind("tcp://*:5555")
print("📡 PUB พร้อมส่ง label")

# ==== CAMERA ====
cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

# ==== Arduino ====
board = Arduino(PORT)
board.samplingOn()
servo_lr = board.get_pin('d:9:s')    # ซ้าย-ขวา
servo_ud = board.get_pin('d:11:s')   # ขึ้น-ลง
grip1 = board.get_pin('d:7:s')       # gripper
grip2 = board.get_pin('d:6:s')       # gripper

# ==== เตรียมแขนและอ้า gripper ====
servo_ud.write(180)
servo_lr.write(95)
grip1.write(178)
grip2.write(1)
print("🔧 เตรียมพร้อม: ยกแขน (11=180), อ้า gripper (7=178, 6=1)")

# ==== Function ทำงานหลัก ====
def run_detection():
    for pos in positions:
        print(f"\n➡️ ขยับ pin9 (leftright) ไปที่ {pos}")
        servo_lr.write(pos)
        servo_ud.write(180)
        grip1.write(178)
        grip2.write(1)
        time.sleep(1.0)

        best_label = None
        best_conf = 0.0
        max_attempts = 20

        for _ in range(max_attempts):
            ret, frame = cap.read()
            if not ret or frame is None:
                print("❌ ไม่สามารถอ่านภาพจากกล้องได้")
                continue

            results = model(frame)[0]
            boxes = results.boxes

            for box in boxes:
                conf = float(box.conf)
                if conf < CONFIDENCE_THRESHOLD:
                    continue

                cls_id = int(box.cls[0])
                label = model.names[cls_id].lower()
                if conf > best_conf:
                    best_label = label
                    best_conf = conf
                    print(f"🎯 เจอวัตถุ: {label} (conf={conf:.2f})")

            if best_conf > 0.95:
                print("✅ หยุดการวน: มั่นใจสูง")
                break

            time.sleep(0.1)

        # ==== ส่ง stage ตาม label ====
        stage = None
        if best_label == "blue":
            stage = "stage1"
        elif best_label == "green":
            stage = "stage2"
        elif best_label == "red":
            stage = "stage3"

        if stage:
            socket.send_string(json.dumps([stage]))
            print(f"📤 ส่ง stage: {stage} (จาก label: {best_label})")
        else:
            print("⚠️ ไม่พบวัตถุที่เข้าเกณฑ์")

    cap.release()
    cv2.destroyAllWindows()

# ==== GUI Start Button ====
root = Tk()
root.title("Start Detection")
Button(root, text="▶ Start", command=run_detection).pack(padx=50, pady=30)
root.mainloop()