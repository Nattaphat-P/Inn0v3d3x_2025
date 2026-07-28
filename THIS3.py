# THIS.py — สแกนครบ 3 สี → คีบ/วางตาม flow ใหม่
# - ก่อน GUI: ramp ช้าๆ → ยก (11=180), ยื่น (10=174), อ้า (7=178,6=1), หมุนฐานไปซ้ายสุด 180
# - ช่วงสแกน: ขยับเฉพาะ pin9 (ฐาน) เท่านั้น (11=180, 10=174, gripper เปิด)
# - หลังสแกน: คีบ/วางแบบค่อยๆ (ขยับทีละข้อต่อ) ตามลำดับที่สั่ง

import cv2
import time
from tkinter import Tk, Button
from ultralytics import YOLO
from pyfirmata2 import Arduino

# ======================== CONFIG ========================
PORT = 'COM5'
SERVO_PINS = [11, 10, 9, 7, 6]   # [updown, fwd/back, rotate, grip1, grip2]
POSITIONS = [180, 141, 44]       # ซ้าย -> ขวา
CONFIDENCE_THRESHOLD = 0.8
RESCAN_THRESHOLD = 0.7
LABELS_NEEDED = {'blue', 'green', 'red'}

# ช่วงสแกน (ใช้เฉพาะตอนสแกน)
SCAN_UPDOWN = 110    # pin11
SCAN_FWDBACK = 141   # pin10
SCAN_GRIP1 = 178     # pin7
SCAN_GRIP2 = 1       # pin6

MAX_ROUNDS = 2
MAX_ATTEMPTS = 3
EARLY_STOP_CONF = 0.96

# ====== ช้า/นิ่ม ======
SLOW_STEP = 1
SLOW_FRAME_DELAY = 0.010
INTER_JOINT_DELAY = 0.080
HOLD_REPEAT = 3
HOLD_DELAY = 0.030

# ===================== ACTION SEQUENCES ==================
# ค่าตามที่สั่งรอบล่าสุด
ACTION_MAP = {
    'blue': {   # position1 = 180
        'pos': 180,
        'prep':       [60, 130, 180, 178, 1],   # เปิดพร้อมกัน
        'grab':       [30, 130, 180, 113, 56],  # ปิดพร้อมกัน
        'lift':       [150,130, 180, 113, 56],
        'place_prep': [150,130, 180, 113, 56],
        'place':      [60, 130, 180, 178, 1]
    },
    'green': {  # position2 = 141
        'pos': 141,
        'prep':       [60, 130, 141, 178, 1],
        'grab':       [30, 130, 141, 113, 56],
        'lift':       [150,130, 141, 113, 56],
        'place_prep': [150,130, 141, 113, 56],
        'place':      [60, 130, 141, 178, 1]
    },
    'red': {    # position3 = 44
        'pos': 44,
        'prep':       [60, 130, 29, 178, 1],
        'grab':       [30, 130, 29, 113, 56],
        'lift':       [150,130, 29, 113, 56],
        'place_prep': [150,130, 29, 113, 56],
        'place':      [60, 130, 29, 178, 1]
    },
    'base': {
        'prep':        [180, 130,   0, 113, 56],  # ฐาน=1
        'place':       [60,  130,   0, 113, 56],
        'center_push': [60,  0,   86, 113, 56]   # ตรงกลาง=100
    }
}

# ==================== LOAD YOLO & CAMERA =================
model = YOLO("best1.pt")
print("✅ YOLO Loaded:", model.names)

cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

# =================== ARDUINO & SERVOS ====================
board = Arduino(PORT)
board.samplingOn()
servos = {pin: board.get_pin(f'd:{pin}:s') for pin in SERVO_PINS}
_current_angles = {11: 90, 10: 90, 9: 90, 7: 90, 6: 90}

DETECTED_POS = {}  # {'blue':pos, 'green':pos, 'red':pos}

# ----------------- Gripper helpers -----------------
def move_gripper(angle7, angle6, repeats=HOLD_REPEAT, delay=HOLD_DELAY):
    for _ in range(repeats):
        servos[7].write(int(angle7))
        servos[6].write(int(angle6))
        time.sleep(delay)
    _current_angles[7] = int(angle7)
    _current_angles[6] = int(angle6)

def close_gripper(): move_gripper(112, 53)
def open_gripper():  move_gripper(178, 1)

# ------------- smooth move helpers -------------
def ramp_move_one(board_pin, start, target, step=SLOW_STEP, frame_delay=SLOW_FRAME_DELAY):
    if start == target:
        board_pin.write(target); return
    direction = 1 if target > start else -1
    for ang in range(int(start), int(target), direction * step):
        board_pin.write(ang); time.sleep(frame_delay)
    board_pin.write(target)

def move_all_smooth(targets, inter_joint_delay=INTER_JOINT_DELAY,
                    step=SLOW_STEP, frame_delay=SLOW_FRAME_DELAY):
    # ขยับ 11,10,9 ทีละข้อต่อ -> แล้วค่อยขยับ gripper พร้อมกัน
    for pin, target in zip(SERVO_PINS[:3], targets[:3]):
        start = _current_angles.get(pin, 90)
        ramp_move_one(servos[pin], start, int(target), step=step, frame_delay=frame_delay)
        _current_angles[pin] = int(target)
        time.sleep(inter_joint_delay)
    move_gripper(targets[3], targets[4])

def write_servo_safe(pin, angle, repeats=HOLD_REPEAT, delay=HOLD_DELAY):
    for _ in range(repeats):
        servos[pin].write(int(angle)); time.sleep(delay)
    _current_angles[pin] = int(angle)

# ---------- initial ramp BEFORE GUI (กันดีด) ----------
def apply_initial_scan_pose():
    write_servo_safe(11, SCAN_UPDOWN)   # ยก
    write_servo_safe(10, SCAN_FWDBACK)  # ยื่น
    open_gripper()                      # อ้า
    write_servo_safe(9, POSITIONS[0])   # หมุนไปซ้ายสุด 180
    time.sleep(0.4)

# ----------------- SCAN: move only pin9 -----------------
def scan_position_once(pos, threshold):
    write_servo_safe(11, SCAN_UPDOWN)
    write_servo_safe(10, SCAN_FWDBACK)
    open_gripper()

    ramp_move_one(servos[9], _current_angles[9], int(pos))
    _current_angles[9] = int(pos)
    time.sleep(0.7)

    best_label, best_conf = None, 0.0
    for _ in range(MAX_ATTEMPTS):
        ret, frame = cap.read()
        if not ret: continue
        results = model(frame)[0]
        for box in results.boxes:
            conf = float(box.conf)
            if conf < threshold: continue
            label = model.names[int(box.cls[0])].lower()
            if label in LABELS_NEEDED and conf > best_conf:
                best_label, best_conf = label, conf
        if best_conf > EARLY_STOP_CONF: break
        time.sleep(0.09)
    return best_label, best_conf

def detect_labels():
    detected = {}
    for round_idx in range(1, MAX_ROUNDS + 1):
        need = LABELS_NEEDED - set(detected.keys())
        if not need: break
        thr = CONFIDENCE_THRESHOLD if round_idx == 1 else RESCAN_THRESHOLD
        print(f"\n🔄 Scan Round {round_idx} (thr={thr}) — need: {sorted(list(need))}")

        for pos in POSITIONS:
            if len(detected) == 3: break
            label, conf = scan_position_once(pos, thr)
            if label and label not in detected:
                detected[label] = int(pos)
                print(f"✅ Captured {label} @ {pos} (conf={conf:.2f})")
            else:
                print(f"⚠️ Nothing new @ {pos} (best={label}, conf={conf:.2f})")
        if len(detected) == 3: break

    if set(detected.keys()) != LABELS_NEEDED:
        missing = LABELS_NEEDED - set(detected.keys())
        print(f"❌ ยังขาด: {sorted(list(missing))} — จะไม่เข้าสเต็ปคีบ/วาง")
    return detected

# -------- inject real base pos into sequence --------
def inject_pos(seq5, pos_value):
    if seq5 is None: return None
    out = list(seq5); out[2] = int(pos_value); return out

# ---------------- Flow ตามที่สั่ง ----------------
def stack_flow_exact(detected):
    # ต้องมีครบ 3 สี
    if set(detected.keys()) != {'blue', 'green', 'red'}:
        print("⛔ ยังครบไม่ 3 สี — ข้ามขั้นตอนคีบ/วาง")
        return

    blue_pos  = detected['blue']
    green_pos = detected['green']
    red_pos   = detected['red']

    # 1) ไปตำแหน่งน้ำเงิน → ลด 11 เพื่อหนีบ → ยกขึ้น
    move_all_smooth(inject_pos(ACTION_MAP['blue']['prep'], blue_pos))   # ลด 11 + เปิดคีบ
    move_all_smooth(inject_pos(ACTION_MAP['blue']['grab'], blue_pos))   # คีบ
    move_all_smooth(inject_pos(ACTION_MAP['blue']['lift'], blue_pos))   # ยก

    # 2) หมุนไปตำแหน่งเขียว → วาง → ลด 11 เพื่อคีบกอง → ยกขึ้น
    move_all_smooth(inject_pos(ACTION_MAP['green']['place_prep'], green_pos))
    move_all_smooth(inject_pos(ACTION_MAP['green']['place'], green_pos))    # วาง (ปล่อย)
    move_all_smooth(inject_pos(ACTION_MAP['green']['prep'], green_pos))     # ลด 11 + เปิดคีบ
    move_all_smooth(inject_pos(ACTION_MAP['green']['grab'], green_pos))     # คีบกอง (blue+green)
    move_all_smooth(inject_pos(ACTION_MAP['green']['lift'], green_pos))     # ยก

    # 3) หมุนไปตำแหน่งแดง → ลด 11 เพื่อปล่อย → ลด 11 อีกเพื่อหนีบขึ้น → ยก
    move_all_smooth(inject_pos(ACTION_MAP['red']['place_prep'], red_pos))
    move_all_smooth(inject_pos(ACTION_MAP['red']['place'], red_pos))        # วาง (ปล่อยลงบนแดง)
    move_all_smooth(inject_pos(ACTION_MAP['red']['prep'], red_pos))         # ลด 11 + เปิดคีบ
    move_all_smooth(inject_pos(ACTION_MAP['red']['grab'], red_pos))         # หนีบทั้งสาม
    move_all_smooth(inject_pos(ACTION_MAP['red']['lift'], red_pos))         # ยก

    # 4) ไปฐาน → วาง → ปัดเข้ากลาง
    move_all_smooth(ACTION_MAP['base']['prep'])
    move_all_smooth(ACTION_MAP['base']['place'])
    move_all_smooth(ACTION_MAP['base']['center_push'])

    # 5) ดัน pin10 ไปข้างหน้าแบบนิ่ม แล้วอ้า gripper ออก จบ
    ramp_move_one(servos[10], _current_angles[10], 0)   # ไปหน้า (0)
    _current_angles[10] = 0
    open_gripper()

# ======================== GUI FLOW =======================
def start():
    print("\n🚀 Start: สแกน (pin9 เฉพาะช่วงสแกน) → เก็บครบ 3 สี แล้วค่อยคีบ/วาง")
    detected = detect_labels()
    print("\n📋 Detected:", detected)

    if set(detected.keys()) != LABELS_NEEDED:
        cap.release(); cv2.destroyAllWindows()
        print("⛔ ยังไม่ครบ 3 สี — ยุติ")
        return

    DETECTED_POS.clear(); DETECTED_POS.update(detected)
    cap.release(); cv2.destroyAllWindows()
    stack_flow_exact(detected)
    print("✅ Done")

# ---------- ก่อน GUI: ตั้งท่าสแกนแบบ ramp ช้า ----------
apply_initial_scan_pose()

root = Tk()
root.title("🍩 Donut Sorter (dynamic + exact flow)")
Button(root, text="▶ START", font=("Arial", 20), command=start).pack(padx=50, pady=50)
root.mainloop()