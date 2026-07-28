# push_base_only_gui_release_with_delay.py
# งาน: กด START → ดันฐานไปจุดสิ้นสุด → หน่วงเวลา → ปล่อยที่คีบ
# ก่อนแสดง GUI: เซ็ตมุมเริ่มต้น 11=180, 10=180, 9=0, 7=120, 6=20

import time
import threading
from tkinter import Tk, Button, Label
from pyfirmata2 import Arduino

# ===== CONFIG =====
PORT = 'COM5'

# Servo mapping order: [updown(11), forward(10), base(9), grip1(7), grip2(6)]
SERVO_PINS = [11, 10, 9, 7, 6]

# --- ท่าเริ่มก่อนแสดง GUI (ตามที่สั่ง) ---
PRE_GUI_POSE = [180, 180, 0, 120, 20]   # 11,10,9,7,6

# --- ท่าที่ใช้เมื่อกด START (ตัวอย่าง flow ดันฐาน) ---
START_POS = [150, 90, 180, 90, 90]     # ตั้งท่าก่อนดัน
PUSH_POS  = [150, 90,   0, 90, 90]     # ดันฐานด้วยการหมุน base ไป 0

# --- ท่าปล่อยที่คีบ (เปลี่ยนเลของศาตรงนี้ได้) ---
RELEASE_GRIP = [None, None, None, 160, 10]  # pin7=160, pin6=10; None = ไม่ขยับเซอร์โวนั้น

# --- เวลาหน่วงก่อนปล่อยที่คีบ (ปรับได้) ---
RELEASE_DELAY_SEC = 0.5  # <<== เวลาที่จะหน่วงก่อนปล่อยที่คีบ

SLOW_STEP = 1
SLOW_FRAME_DELAY = 0.010
INTER_JOINT_DELAY = 0.080

# ===== Low-level =====
board = None
servos = {}
current = {}

def connect():
    global board, servos
    if board is None:
        board = Arduino(PORT)
        board.samplingOn()
        servos = {pin: board.get_pin(f'd:{pin}:s') for pin in SERVO_PINS}
        for p in SERVO_PINS:
            current[p] = 90

def write_servo(pin, angle, delay=0.01):
    servos[pin].write(int(angle))
    current[pin] = int(angle)
    time.sleep(delay)

def move_all(angles):
    # ขยับ 11,10,9,7,6 ตามลำดับ; ถ้าเป็น None จะข้าม
    for pin, angle in zip(SERVO_PINS, angles):
        if angle is not None:
            write_servo(pin, angle)
    time.sleep(0.2)

def cleanup():
    global board
    try:
        if board:
            board.exit()
            board = None
    except:
        pass

# ===== Task on START =====
def push_base(status_cb=lambda s: None):
    try:
        connect()

        status_cb("Setting start position")
        move_all(START_POS)
        time.sleep(0.5)

        status_cb("Pushing base...")
        move_all(PUSH_POS)

        # หน่วงเวลาก่อนปล่อยที่คีบ
        status_cb(f"Holding before release ({RELEASE_DELAY_SEC:.2f}s)")
        time.sleep(RELEASE_DELAY_SEC)  # <<== เพิ่ม delay ตรงนี้

        # === ปล่อยที่คีบ ===
        status_cb("Releasing gripper...")
        move_all(RELEASE_GRIP)  # ปล่อยที่คีบ (pin7, pin6) ← แก้เลของศาตรงนี้ได้

        status_cb("Done ✅")
    except Exception as e:
        status_cb(f"Error: {e}")

# ===== GUI =====
def main():
    connect()
    print("Setting pre-GUI pose: 11=180, 10=180, 9=0, 7=120, 6=20")
    move_all(PRE_GUI_POSE)

    root = Tk()
    root.title("Push Base Only – with Release Delay")

    status = Label(root, text="Ready", font=("Arial", 12))
    status.pack(padx=16, pady=(16,8))

    def set_status(s):
        status.config(text=s)
        status.update_idletasks()

    running = {"flag": False}

    def on_start():
        if running["flag"]:
            return
        running["flag"] = True
        set_status("Starting...")
        def worker():
            try:
                push_base(set_status)
            finally:
                running["flag"] = False
        threading.Thread(target=worker, daemon=True).start()

    def on_exit():
        set_status("Exiting...")
        cleanup()
        root.after(200, root.destroy)

    Button(root, text="▶ START", font=("Arial", 16), command=on_start).pack(padx=16, pady=8, fill="x")
    Button(root, text="✖ EXIT",  font=("Arial", 12), command=on_exit).pack(padx=16, pady=(0,16), fill="x")

    root.protocol("WM_DELETE_WINDOW", on_exit)
    root.mainloop()

if __name__ == "__main__":
    main()