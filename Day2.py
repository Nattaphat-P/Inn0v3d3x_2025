# -*- coding: utf-8 -*-
# onefile_centerline_donut.py
# -----------------------------------------------------------------------------
# โหมดทำงาน: ไฟล์เดียวจบ มี GUI ปุ่ม START
# 1) สแกนฐาน (pin9) จากซ้าย→ขวา (180→0) โดย "คงโพสแขน" ขณะสแกน:
#       pin11=180 (เงยสูง), pin10=178 (ถอยหลัง), gripper อ้า (pin7=174, pin6=1)
#    - กล้องติดนิ่ง (มองลง) แต่หมุนตาม pin9 → ค่า X ของโดนัทในภาพสัมพันธ์กับมุม pin9
#    - ใช้ YOLO (best.pt) ตรวจเฉพาะ 3 สีจริง: red/green/blue (skip yellow/purple)
#    - บันทึก "มุมฐาน" ตอนที่ศูนย์กลาง bbox ของสี "ตัดเส้นกึ่งกลางภาพ" (center-line)
#      เพื่อใช้เป็น "มุมไปหยิบ" ที่นิ่งและไม่ต้องคาลิเบรตพิกเซล→องศา
#
# 2) เมื่อได้มุมครบ 3 สี → ทำลำดับคีบ/วางตามสเปค:
#    - เข้าหา (pin11=150, pin10=178, pin9=มุมสี, gripper เปิดพอไม่ชน pin7=120, pin6=40)
#    - ลดลง (pin11=60) และดันเข้า (pin10=30) → ปิดกริป (pin7=111, pin6=50)
#    - ยกขึ้น (pin11=180)
#    - ไปฐานและวาง (pin9=0, pin11=180, pin10=178 → ลด pin11=30 → เปิดกริป)
#    - สีสุดท้าย (น้ำเงิน): ไม่ต้องยก pin11; ปัดฐานไปกลาง (pin9=95) + ดันไปหน้า (pin10=20) + เปิดกริป
#
# หมายเหตุ:
# - กด ESC ในหน้าต่าง Preview เพื่อยกเลิกการสแกนทันที
# - หากสแกนแล้วยังขาดบางสี: ใช้มุมที่ "conf สูงสุด" เป็น fallback เพื่อให้ไปต่อได้
# - ปรับความเนียน/ความเร็วด้วยพารามิเตอร์: STEP_DEG, SETTLE, CENTER_TOL, FRAMES_PER_ANGLE
# -----------------------------------------------------------------------------

import time
import json
import threading
from collections import defaultdict

import cv2
from ultralytics import YOLO
from pyfirmata2 import Arduino
import tkinter as tk
from tkinter import ttk

# ===================== CONFIG =====================
PORT = 'COM5'  # พอร์ตบอร์ด (Windows มักจะ COMx)
# แม็ปพินของเซอร์โวทั้งหมด: 11=ยกขึ้นลง, 10=หน้า/หลัง, 9=หมุนฐาน, 7-6=กรรไกรคีบ
PINS = dict(p11=11, p10=10, p9=9, p7=7, p6=6)

CONF_TH = 0.80       # ค่าความมั่นใจขั้นต่ำของ YOLO (0.0–1.0)
MODEL_PATH = 'best.pt'  # ชื่อไฟล์โมเดล YOLO (วางไว้โฟลเดอร์เดียวกับสคริปต์นี้)

# ---------------- กล้อง ----------------
CAM_INDEX = 0            # index กล้อง (0 = กล้องตัวแรก)
FRAME_W, FRAME_H = 640, 480
CENTER_X = FRAME_W // 2  # พิกัด X เส้นกึ่งกลางภาพ (ใช้เป็น trigger center-line)
CENTER_TOL = 6           # ยอมรับว่า "ตัดกลาง" ถ้า |cx - CENTER_X| <= 6 พิกเซล
# ปรับให้หลวมขึ้นถ้าโดนัทใหญ่/มี noise เช่น 8–10

# ----------- โพส "ขณะสแกน" (ต้องคงค่าเสมอ) -----------
SCAN_P11 = 180  # pin11 เงยสูงสุดเพื่อหลีกเลี่ยงการชน
SCAN_P10 = 178  # pin10 ถอยหลังจนใกล้สุด เพื่อให้ระยะเล็งคงที่
SCAN_P7  = 135  # gripper ด้านซ้าย อ้า
SCAN_P6  = 3    # gripper ด้านขวา อ้า

# ---------------- กวาดฐาน ----------------
START_ANGLE = 180   # ซ้ายสุด
END_ANGLE   = 0     # ขวาสุด
STEP_DEG    = 2     # ขยับทีละ 2 องศา (ละเอียด=1 ช้าแต่แม่นขึ้น)
SETTLE      = 0.10  # หน่วงให้ฐานนิ่งก่อนถ่ายภาพ (วิเดียว=0.10–0.20 ตามแรงเฉื่อย)
FRAMES_PER_ANGLE = 3        # จับภาพกี่เฟรมต่อมุม เพื่อลด noise
CENTER_HITS_NEEDED = 2      # ต้องเห็นตัดกลาง ≥2 ครั้งในมุมนั้น จึงถือว่า "เสถียร"

# ---------------- สีที่สนใจ / สีหลอก ----------------
REQUIRED = ('red', 'green', 'blue')  # สีจริงที่ต้องหยิบ
EXCLUDE  = {'yellow', 'purple'}      # สีหลอก (ถ้าโมเดลมี ก็จะถูกกรองทิ้ง)

# ----------- สเปค "เข้า–คีบ–ยก–วาง" (ทำตามโจทย์) -----------
APPROACH_P11 = 150                # เงยลงมาระดับเข้าหาวัตถุ
APPROACH_P10 = 178                # ยังถอยหลัง
APPROACH_OPEN_7 = 120             # เปิดกริปให้พอไม่ชน (ซ้าย)
APPROACH_OPEN_6 = 40              # เปิดกริปให้พอไม่ชน (ขวา)

PICK_LOWER_P11 = 60               # ลดลงจ่อโดนัทก่อนคีบ
PICK_PUSH_P10  = 30               # ดันไปข้างหน้าเข้าโดนัท
GRIP_CLOSE_7   = 111              # ปิดกริป (ซ้าย)
GRIP_CLOSE_6   = 50               # ปิดกริป (ขวา)

LIFT_P11 = 180                    # ยกโดนัทขึ้นให้พ้น

BASE_P9   = 0                     # หมุนฐานไปตำแหน่งฐานวาง
BASE_P10  = 178                   # ถอยหลัง
BASE_P11  = 180                   # เงยสูง
DROP_P11  = 30                    # ลดลงเพื่อวาง
RELEASE_OPEN_7 = 174              # เปิดกริปเพื่อวาง (ซ้าย)
RELEASE_OPEN_6 = 1                # เปิดกริปเพื่อวาง (ขวา)

FINAL_CENTER_P9 = 95              # หลังวางชิ้นสุดท้าย ปัดฐานมาที่กลาง
FINAL_PUSH_P10  = 20              # ดันไปด้านหน้า
# ---------------------------------------------------

OUT_JSON = 'detected_positions.json'  # บันทึกผลมุม center-line เพื่อดีบัก/อ้างอิง

# =================== Servo helpers ===================
class Servo:
    """ตัวช่วยควบคุมเซอร์โวแบบมีการจำค่าปัจจุบันและค่อยๆ ไล่ทีละสเต็ปเพื่อลดกระชาก"""
    def __init__(self, board, pin, init=90):
        self.pin = board.get_pin(f'd:{pin}:s')  # โหมด servo: 'd:<pin>:s'
        self.cur = None
        time.sleep(0.05)        # หน่วงเล็กน้อยให้บอร์ดพร้อม
        self.write(init)        # ตั้งค่าเริ่มต้น

    def write(self, ang):
        """เขียนมุมแบบตรงๆ (หน่วยองศา) พร้อม clamp 0..180"""
        ang = max(0, min(180, int(ang)))
        self.pin.write(ang)
        self.cur = ang

    def goto(self, target, step=2, delay=0.006):
        """เลื่อนไปยัง target แบบค่อยๆ ขยับ (smooth) ลดแรงกระชาก/สั่น"""
        target = max(0, min(180, int(target)))
        if self.cur is None:
            self.write(target); return
        sgn = 1 if target > self.cur else -1
        for a in range(self.cur, target, sgn*step):
            self.pin.write(a); time.sleep(delay)
        self.pin.write(target); self.cur = target

def open_grip(servos, a7, a6, step=2, delay=0.006):
    """เปิดกริปเปอร์สองข้างไปมุมที่กำหนด (พร้อมกัน)"""
    servos['p7'].goto(a7, step=step, delay=delay)
    servos['p6'].goto(a6, step=step, delay=delay)

def close_grip(servos, a7=GRIP_CLOSE_7, a6=GRIP_CLOSE_6, step=2, delay=0.006):
    """ปิดกริปเปอร์สองข้างไปมุมที่กำหนด (พร้อมกัน)"""
    servos['p7'].goto(a7, step=step, delay=delay)
    servos['p6'].goto(a6, step=step, delay=delay)

# =================== Vision helpers ===================
def norm_label(s: str) -> str:
    """แปลงฉลากคลาสให้เป็นตัวพิมพ์เล็ก (กันกรณี 'Blue'/'BLUE' ฯลฯ)"""
    return str(s).strip().lower()

def detect_once(model, frame):
    """
    รัน YOLO หนึ่งครั้งบนภาพ 'frame'
    คืน: รายการ dict เฉพาะคลาสที่ต้องการ (R/G/B) และ conf >= CONF_TH
         แต่ละ dict: {label, conf, cx, cy, bbox}
    """
    out = []
    res = model(frame, verbose=False)[0]
    names = {i: norm_label(n) for i, n in model.names.items()}
    for b in res.boxes:
        conf = float(b.conf.item() if hasattr(b.conf, "item") else b.conf)
        if conf < CONF_TH:
            continue
        cls_id = int(b.cls.item() if hasattr(b.cls, "item") else b.cls)
        lbl = norm_label(names.get(cls_id, str(cls_id)))
        # ตัดสีหลอก (ถ้าโมเดลมี) และตัดคลาสที่ไม่ใช่ R/G/B
        if lbl in EXCLUDE:
            continue
        if lbl not in REQUIRED:
            continue
        # แปลงพิกัด bbox และคำนวณ cx, cy (ศูนย์กลาง bbox)
        x1, y1, x2, y2 = map(float, b.xyxy[0].tolist())
        cx, cy = 0.5*(x1+x2), 0.5*(y1+y2)
        out.append(dict(label=lbl, conf=conf, cx=cx, cy=cy, bbox=(x1,y1,x2,y2)))
    return out

# =================== Scan (center-line) ===================
def scan_get_center_angles(set_status):
    """
    ขั้นตอนสแกนเพื่อหา "มุมฐาน pin9" สำหรับแต่ละสี ด้วยวิธี center-line:
    - คงโพสสแกน: p11=180, p10=178, p7=174, p6=1 (gripper อ้า, ยกสูง, ถอยหลัง)
    - กวาด p9 จาก 180 → 0 ตาม STEP_DEG; แต่ละมุม:
        * หน่วง SETTLE ให้แรงสั่นหยุด
        * จับภาพ FRAMES_PER_ANGLE เฟรมและตรวจ YOLO
        * นับว่ามี "hit" กี่ครั้งที่ |cx - CENTER_X| <= CENTER_TOL
        * ถ้า "hit" ถึง CENTER_HITS_NEEDED ในมุมนั้น → ยอมรับเป็นมุมของสีนั้น
    - หากบางสีไม่เจอ "center" จริง ๆ จะใช้ "มุมที่ conf สูงสุด" เป็น fallback (พอให้ไปต่อได้)
    - คืนค่า: (board, servos, angles) โดย angles เช่น {'red':142, 'green':87, 'blue':26}
    """
    # ----- เตรียมฮาร์ดแวร์ -----
    try:
        board = Arduino(PORT); board.samplingOn()
    except Exception as e:
        set_status(f"Arduino error: {e}")
        return None, None, None

    # แนบเซอร์โวก่อนสแกน + ตั้งโพสสแกน
    servos = {
        'p11': Servo(board, PINS['p11'], init=SCAN_P11),
        'p10': Servo(board, PINS['p10'], init=SCAN_P10),
        'p9' : Servo(board, PINS['p9'],  init=START_ANGLE),
        'p7' : Servo(board, PINS['p7'],  init=SCAN_P7),
        'p6' : Servo(board, PINS['p6'],  init=SCAN_P6),
    }

    # ----- เปิดกล้อง + โหลดโมเดล -----
    cap = cv2.VideoCapture(CAM_INDEX)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_H)
    try:
        model = YOLO(MODEL_PATH)
    except Exception as e:
        set_status(f"Model load error: {e}")
        cap.release()
        return None, None, None

    angles = {}  # มุม center-line ต่อสี (ผลหลัก)
    # เก็บ "มุมที่ conf สูงสุด" เป็นแผนสำรอง หากสีไหนไม่เคยตัดกลางภาพ
    best_conf_angle = defaultdict(lambda: (-1.0, None))  # label -> (best_conf, angle)

    set_status("Scanning…")
    for ang in range(START_ANGLE, END_ANGLE - 1, -STEP_DEG):
        # หมุนฐานไปที่มุม ang (ไล่ทีละ step เพื่อลดกระชาก)
        servos['p9'].goto(ang, step=2, delay=0.003)
        time.sleep(SETTLE)  # ปล่อยให้หยุดไหวก่อนถ่าย

        hits = defaultdict(int)  # นับจำนวนครั้งที่แตะเส้นกลางสำหรับมุมนี้ (ต่อสี)

        for _ in range(FRAMES_PER_ANGLE):
            ok, frame = cap.read()
            if not ok:
                continue
            dets = detect_once(model, frame)

            # ---------- แสดงผลช่วยดีบัก ----------
            vis = frame.copy()
            # วาดเส้นกึ่งกลางภาพ (แนวตั้ง) เพื่อเช็คด้วยตา
            cv2.line(vis, (CENTER_X, 0), (CENTER_X, FRAME_H), (255,255,255), 1)
            for d in dets:
                x1,y1,x2,y2 = map(int, d['bbox'])
                cv2.rectangle(vis, (x1,y1), (x2,y2), (255,255,255), 1)
                cv2.putText(vis, f"{d['label']} {d['conf']:.2f}",
                            (x1, max(0,y1-7)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1)
                cv2.circle(vis, (int(d['cx']), int(d['cy'])), 3, (0,0,255), -1)

                # บันทึกมุมที่ conf สูงสุด (fallback)
                if d['conf'] > best_conf_angle[d['label']][0]:
                    best_conf_angle[d['label']] = (d['conf'], ang)
                # ตรวจว่าตัดเส้นกลางหรือยัง
                if abs(d['cx'] - CENTER_X) <= CENTER_TOL:
                    hits[d['label']] += 1

            cv2.putText(vis, f"pin9={ang} deg", (8, 22),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0,255,0), 2)
            cv2.imshow("Preview", vis)
            # กด ESC เพื่อล้มเลิกการสแกน
            if cv2.waitKey(1) & 0xFF == 27:
                cap.release(); cv2.destroyAllWindows()
                set_status("Aborted.")
                return None, None, None

        # หากสีใดมี hits ถึงเกณฑ์ → lock-in มุมสำหรับสีนั้น (ครั้งแรกครั้งเดียว)
        for lbl, n in hits.items():
            if lbl in REQUIRED and lbl not in angles and n >= CENTER_HITS_NEEDED:
                angles[lbl] = ang

        set_status(f"Scanning… pin9={ang}°  found={len(angles)}/3")
        # ได้ครบสามสีแล้วออกจากลูปได้เลย
        if all(c in angles for c in REQUIRED):
            break

    # เติมมุม fallback สำหรับสีที่ยังไม่มีมุม center-line
    for c in REQUIRED:
        if c not in angles and best_conf_angle[c][1] is not None:
            angles[c] = int(best_conf_angle[c][1])

    # ปิดอุปกรณ์แสดงผลกล้อง
    cap.release(); cv2.destroyAllWindows()

    # บันทึกผลลงไฟล์ไว้ตรวจย้อนหลัง/ดีบัก
    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump({'angles_center': angles,
                   'meta': {'center_tol_px': CENTER_TOL, 'conf_th': CONF_TH,
                            'step_deg': STEP_DEG, 'frames_per_angle': FRAMES_PER_ANGLE}},
                  f, ensure_ascii=False, indent=2)

    if not angles:
        # ไม่มีสีใดเลย → แจ้งเตือน
        set_status("No colors found.")
        return board, servos, None

    set_status(f"Angles: {angles}")  # ตัวอย่าง: {'red': 142, 'green': 88, 'blue': 27}
    return board, servos, angles

# =================== Pick & Place (per spec) ===================
def pick_and_place(servos, color, angle_p9, last_is_blue=False, set_status=lambda s: None):
    """
    ทำลำดับการหยิบ-วางสำหรับสีหนึ่งสี ตามพารามิเตอร์ที่กำหนดไว้ด้านบน
    - angle_p9: มุมฐานที่ได้จากสแกนด้วย center-line (ของสีนั้น)
    - last_is_blue: ถ้า True (สีน้ำเงิน): จบด้วยปัดฐาน/ดันไปหน้า + เปิดกริป (ไม่ยก p11)
    """
    # ---------- เข้าเป้า ----------
    set_status(f"{color}: approach")
    servos['p11'].goto(APPROACH_P11)                         # เงยลงมาเตรียมเข้าหา
    servos['p10'].goto(APPROACH_P10)                         # ถอยไว้ก่อน
    servos['p9'].goto(angle_p9)                              # หมุนฐานไปมุมของสี
    open_grip(servos, APPROACH_OPEN_7, APPROACH_OPEN_6)      # เปิดกริปพอไม่ชน

    # ---------- ลดลง + ดันเข้า + คีบ ----------
    set_status(f"{color}: lower & grip")
    servos['p11'].goto(PICK_LOWER_P11)                       # ลดลง
    servos['p10'].goto(PICK_PUSH_P10)                        # ดันไปหน้า
    close_grip(servos, GRIP_CLOSE_7, GRIP_CLOSE_6)           # ปิดกริปคีบโดนัท
    time.sleep(0.12)                                         # หน่วงให้กริปล็อก

    # ---------- ยกโดนัทให้พ้น ----------
    servos['p11'].goto(LIFT_P11)

    # ---------- เคลื่อนไปฐาน + วาง ----------
    set_status(f"{color}: to base")
    servos['p9'].goto(BASE_P9)
    servos['p10'].goto(BASE_P10)
    servos['p11'].goto(DROP_P11)                             # ลดลงเตรียมวาง
    open_grip(servos, RELEASE_OPEN_7, RELEASE_OPEN_6)        # ปล่อย
    time.sleep(0.12)

    if last_is_blue:
        # สีสุดท้าย (น้ำเงิน): ไม่ยก p11; ปัดเข้า "กลาง" + ดันไปด้านหน้า + เผื่อเปิดกริปอีกครั้ง
        set_status(f"{color}: final center push")
        servos['p9'].goto(FINAL_CENTER_P9)
        servos['p10'].goto(FINAL_PUSH_P10)
        open_grip(servos, RELEASE_OPEN_7, RELEASE_OPEN_6)
    else:
        # สีอื่น: ยกออกเพื่อความปลอดภัย
        servos['p11'].goto(LIFT_P11)

# =================== GUI ===================
class App:
    """GUI เรียบง่าย: เลือกพอร์ต / ชื่อโมเดล → START เพื่อสแกน + คีบ/วางครบลูป"""
    def __init__(self, root):
        self.root = root
        root.title("🍩 Donut (Center-Line) - Single File")
        root.geometry("560x220")

        self.status = tk.StringVar(value="Idle")

        # พอร์ตบอร์ด
        ttk.Label(root, text="Port:").grid(row=0, column=0, sticky="e", padx=8, pady=8)
        self.port_entry = ttk.Entry(root, width=12); self.port_entry.insert(0, PORT)
        self.port_entry.grid(row=0, column=1, sticky="w")

        # ชื่อไฟล์โมเดล YOLO
        ttk.Label(root, text="Model:").grid(row=1, column=0, sticky="e", padx=8, pady=8)
        self.model_entry = ttk.Entry(root, width=30); self.model_entry.insert(0, MODEL_PATH)
        self.model_entry.grid(row=1, column=1, sticky="w")

        # ปุ่ม START / EXIT
        self.start_btn = ttk.Button(root, text="▶ START", command=self.on_start)
        self.start_btn.grid(row=2, column=0, padx=8, pady=10, sticky="ew")
        self.exit_btn = ttk.Button(root, text="✖ EXIT", command=self.on_exit)
        self.exit_btn.grid(row=2, column=1, padx=8, pady=10, sticky="ew")

        # สถานะการทำงาน
        self.status_label = ttk.Label(root, textvariable=self.status, font=("Segoe UI", 11))
        self.status_label.grid(row=3, column=0, columnspan=2, padx=8, sticky="w")

        # ขยายคอลัมน์ให้ยืดได้
        for i in range(2):
            root.grid_columnconfigure(i, weight=1)

        root.protocol("WM_DELETE_WINDOW", self.on_exit)

    def set_status(self, text):
        """อัปเดตข้อความสถานะจาก thread อื่นได้อย่างปลอดภัย"""
        self.root.after(0, self.status.set, text)

    def on_start(self):
        """เริ่ม pipeline บน thread แยก เพื่อไม่ให้ GUI ค้าง"""
        global PORT, MODEL_PATH
        PORT = self.port_entry.get().strip() or PORT
        MODEL_PATH = self.model_entry.get().strip() or MODEL_PATH
        self.start_btn.config(state="disabled")
        threading.Thread(target=self.run_pipeline, daemon=True).start()

    def on_exit(self):
        """ปิดหน้าต่าง + ปิดหน้าต่างกล้อง (ถ้ามี)"""
        try:
            cv2.destroyAllWindows()
        except:
            pass
        self.root.destroy()

    def run_pipeline(self):
        """ลูปหลัก: 1) สแกนหา angles  2) คีบ/วาง R→G→B ตามลำดับ"""
        # Phase 1: Scan & get angles
        board, servos, angles = scan_get_center_angles(self.set_status)
        if servos is None or angles is None:
            self.set_status("Scan failed.")
            self.start_btn.config(state="normal")
            return

        # Phase 2: Pick & Place in order R→G→B (ข้ามสีที่หาไม่เจอ)
        order = ['red', 'green', 'blue']
        for color in order:
            if color not in angles:
                continue
            last_is_blue = (color == 'blue')
            try:
                pick_and_place(servos, color, angles[color], last_is_blue, self.set_status)
                self.set_status(f"{color}: done")
            except Exception as e:
                # ถ้ามี error กลางคัน ให้ break และคืนปุ่ม START ให้กดใหม่
                self.set_status(f"{color}: error {e}")
                break

        self.set_status("Completed.")
        self.start_btn.config(state="normal")

def main():
    """บู๊ต GUI และเริ่มรอคำสั่งผู้ใช้"""
    root = tk.Tk()
    try:
        style = ttk.Style(root); style.theme_use("clam")  # ธีมอ่านง่าย
    except:
        pass
    App(root)
    root.mainloop()

if __name__ == "__main__":
    # entry point guard: รันไฟล์นี้ตรงๆ จึงเข้าฟังก์ชัน main()
    main()