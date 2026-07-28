# sub_print_yolo_label.py
import zmq
import json

context = zmq.Context()
socket = context.socket(zmq.SUB)
socket.connect("tcp://localhost:5555")
socket.setsockopt_string(zmq.SUBSCRIBE, "")

print("📡 SUB รอรับ label จาก PUB...")

while True:
    msg = socket.recv_string()
    labels = json.loads(msg)
    if labels:
        print(f"📥 ได้ label: {labels[0]}")