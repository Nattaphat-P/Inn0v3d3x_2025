from tkinter import Tk, Scale, HORIZONTAL, Label, Button, Entry
from pyfirmata2 import Arduino

# Connect to the board
board = Arduino('COM5')
board.samplingOn()

servo_pins = [11, 10, 9, 7, 6]  # ขาของเซอร์โว
servos = {}
sliders = {}
entries = {}

# Attach servo objects
for pin in servo_pins:
    servos[pin] = board.get_pin(f'd:{pin}:s')

root = Tk()
root.title("Servo Control GUI")


def update_servo(angle, pin):
    """อัปเดตการหมุนของเซอร์โว"""
    try:
        angle = float(angle)
    except ValueError:
        return

    # จำกัดค่าไม่ให้เกิน 180
    angle = max(0, min(angle, 180))
    servos[pin].write(angle)

    # อัปเดตช่องกรอกตัวเลขให้ตรงกับสไลเดอร์
    entries[pin].delete(0, 'end')
    entries[pin].insert(0, str(int(angle)))


def on_entry_change(event, pin):
    """เมื่อพิมพ์ค่าในช่องแล้วกด Enter"""
    try:
        val = float(entries[pin].get())
        sliders[pin].set(val)
        update_servo(val, pin)
    except ValueError:
        pass


def reset_servos():
    """รีเซ็ตเซอร์โวทั้งหมดให้กลับค่ามาตรฐาน"""
    default_positions = [100, 180, 90, 170, 10]
    for i, pin in enumerate(servo_pins):
        pos = default_positions[i]
        servos[pin].write(pos)
        sliders[pin].set(pos)
        entries[pin].delete(0, 'end')
        entries[pin].insert(0, str(pos))


# Create sliders and entry boxes
for idx, pin in enumerate(servo_pins):
    Label(root, text=f"Servo on Pin {pin}").grid(row=idx, column=0, padx=10, pady=5)

    slider = Scale(
        root,
        from_=0,
        to=180,
        orient=HORIZONTAL,
        length=200,
        command=lambda value, p=pin: update_servo(value, p)
    )
    slider.grid(row=idx, column=1, padx=10, pady=5)
    sliders[pin] = slider

    entry = Entry(root, width=5)
    entry.grid(row=idx, column=2)
    entry.insert(0, "0")
    entry.bind("<Return>", lambda event, p=pin: on_entry_change(event, p))
    entries[pin] = entry

# Reset button
reset_button = Button(root, text="Reset All to Default", command=reset_servos)
reset_button.grid(row=len(servo_pins), column=0, columnspan=3, pady=10)

root.mainloop()