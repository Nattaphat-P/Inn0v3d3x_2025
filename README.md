# Innovedex 2025 รางวัล 🏅 ระดับเหรียญทอง 🏅

## วิธีการติดตั้งและใช้งาน YOLOv8, PyZMQ, Arduino Firmata ขั้นตอนการตั้งค่าระบบการตรวจจับวัตถุด้วย YOLOv8, การสื่อสารข้อมูลผ่าน PyZMQ และการเชื่อมต่อควบคุมบอร์ด Arduino ด้วย PyFirmata2

---

## 📋 สารบัญ (Table of Contents)
1. [การเตรียม Virtual Environment บน Windows](#1-การเตรียม-virtual-environment-บน-windows)
2. [การเตรียม Dataset และเทรนโมเดล YOLOv8 บน Google Colab](#2-การเตรียม-dataset-และเทรนโมเดล-yolov8-บน-google-colab)
3. [การรัน Object Detection บนเครื่อง Local](#3-การรัน-object-detection-บนเครื่อง-local)
4. [การรับ-ส่งข้อมูลด้วย PyZMQ (Publish-Subscribe Pattern)](#4-การรับ-ส่งข้อมูลด้วย-pyzmq-publish-subscribe-pattern)
5. [การตั้งค่า Arduino สำหรับควบคุมด้วย PyFirmata2](#5-การตั้งค่า-arduino-สำหรับควบคุมด้วย-pyfirmata2)

---

## 1. การเตรียม Virtual Environment บน Windows

### 1.1 สร้างโฟลเดอร์โปรเจกต์
เปิด **PowerShell** แล้วไปยังไดรฟ์หรือไดเรกทอรีที่ต้องการ จากนั้นสร้างโฟลเดอร์สำหรับทำงาน:
```powershell
# ไปยังไดรฟ์ C: (หรือพาธที่ต้องการ)
cd C:\

# สร้างโฟลเดอร์ใหม่และเข้าไปยังโฟลเดอร์นั้น
mkdir MyYoloProject
cd MyYoloProject
```
*(คำแนะนำ: สามารถคัดลอก Path ของโฟลเดอร์จาก File Explorer มาใช้สั่ง `cd "path"` ใน PowerShell ได้)*

### 1.2 สร้างและเรียกใช้งาน Virtual Environment (venv)
```powershell
# สร้าง virtual environment ชื่อ venv
python -m venv venv

# เปิดใช้งาน (Activate) venv
.\venv\Scripts\activate
```
> **หมายเหตุ:** เมื่อเปิดใช้งานสำเร็จ จะมีข้อความ `(venv)` ปรากฏอยู่ด้านหน้าพรอมต์ของ PowerShell

### 1.3 ติดตั้ง Python Libraries ที่จำเป็น
```powershell
# ติดตั้ง OpenCV และ Ultralytics (YOLOv8)
pip install opencv-python ultralytics

# ติดตั้ง PyZMQ สำหรับสื่อสารข้อมูลผ่าน Socket
pip install pyzmq

# ติดตั้ง PyFirmata2 สำหรับเชื่อมต่อและควบคุม Arduino
pip install pyfirmata2

# ตรวจสอบรายการแพ็กเกจที่ติดตั้งเรียบร้อย
pip list
```

---

## 2. การเตรียม Dataset และเทรนโมเดล YOLOv8 บน Google Colab

### 2.1 เตรียมข้อมูลบน Roboflow
1. สมัคร/ล็อกอินเข้าใช้งาน [Roboflow](https://roboflow.com/)
2. สร้างโปรเจกต์ประเภท **Object Detection**
3. นำเข้าภาพและทำ Annotation (วาดกรอบระบุวัตถุ)
4. ทำการ **Generate Dataset** และเลือก Export ในรูปแบบ **YOLOv8**
5. คัดลอก Snippet Code / API Key สำหรับดึง Dataset

### 2.2 กระบวนการเทรนบน Google Colab
1. เปิด [Google Colab](https://colab.research.google.com/) แล้วกด **Connect** (แนะนำให้เปลี่ยน Runtime เป็น GPU เช่น T4 GPU)
2. ติดตั้ง Library และสร้างโฟลเดอร์รองรับ Dataset:
   ```bash
   !pip install ultralytics
   !mkdir -p dataset
   ```
   *(การใช้สวิตช์ `-p` จะช่วยสร้าง parent folder ให้อัตโนมัติหากยังไม่มีอยู่)*
3. วาง Code ที่คัดลอกมาจาก Roboflow เพื่อดาวน์โหลด Dataset เข้ามาใน Colab
4. เริ่มทำการ Train โมเดล:
   ```python
   from ultralytics import YOLO

   # เลือกขนาดโมเดลตั้งต้น (yolov8n, yolov8s, yolov8m, yolov8l, yolov8x)
   model = YOLO('yolov8s.pt')

   # สั่งรันการเทรน พร้อมกำหนดไฟล์สเปก dataset และจำนวนรอบ (epochs)
   model.train(data='dataset/data.yaml', epochs=50, imgsz=640)
   ```
5. เมื่อเทรนเสร็จสิ้น ไฟล์ Weights จะถูกบันทึกไว้ที่ `runs/detect/train/weights/`:
   * `last.pt` : น้ำหนักโมเดล ณ Epoch สุดท้าย
   * `best.pt` : น้ำหนักโมเดลที่ให้ค่าประสิทธิภาพดีที่สุดในการทดสอบ
6. ดาวน์โหลดไฟล์ `best.pt` ลงมายังเครื่อง Local

---

## 3. การรัน Object Detection บนเครื่อง Local

### 3.1 การเตรียมไฟล์และโค้ด
1. นำไฟล์ `best.pt` มาวางไว้ในโฟลเดอร์โปรเจกต์ Local
2. คัดลอกโค้ดสคริปต์ตรวจจับวัตถุจากตัวอย่าง: [custom_model_detection.py]([https://github.com/chacharin/learn_python_yolo/blob/main/custom_model_detection.py](https://github.com/Nattaphat-P/Inn0v3d3x_2025/blob/main/Train_Custom_YoloV8.ipynb))
3. เปิด VS Code จาก PowerShell (โดยที่ venv ยัง active อยู่):
   ```powershell
   code .
   ```

### 3.2 การปรับแก้สคริปต์ `custom_model_detection.py`
* **บรรทัดโหลดโมเดล (ประมาณบรรทัดที่ 8):** มั่นใจว่าเรียกใช้ไฟล์ `best.pt`
  ```python
  model = YOLO('best.pt')
  ```
* **บรรทัดตั้งค่ากล้อง (ประมาณบรรทัดที่ 10):** ปรับดัชนีกล้อง
  ```python
  cap = cv2.VideoCapture(0)  # หากใช้กล้องเว็บแคมเสริม อาจเปลี่ยนเป็น 1, 2 หรือ 3
  ```

### 3.3 การรันสคริปต์ตรวจจับ
สั่งรันผ่าน PowerShell:
```powershell
python .\custom_model_detection.py
```
* **ผลลัพธ์:** จะปรากฏหน้าต่างวิดีโอพร้อมวาดกรอบ Bounding Box และระบุ Class/Confidence แบบ Real-time
* **การออกจากโปรแกรม:** กดปุ่ม `q` ที่คีย์บอร์ดขณะโฟกัสอยู่ที่หน้าต่างวิดีโอ

---

## 4. การรับ-ส่งข้อมูลด้วย PyZMQ (Publish-Subscribe Pattern)

ใช้ PyZMQ ในการส่งข้อมูลผลลัพธ์จากการตรวจจับวัตถุไปยังกระบวนการอื่น

1. เตรียมสคริปต์ 2 ไฟล์: `pub.py` (Publisher - ผู้ส่ง) และ `sub.py` (Subscriber - ผู้รับ)
2. กำหนด Protocol และ Port สื่อสารในสคริปต์ เช่น `tcp://127.0.0.1:5555`
3. **วิธีการทดสอบรัน:**
   * เปิด PowerShell หน้าต่างที่ 1 (Activate venv) แล้วรัน Subscriber เพื่อรอรับข้อมูล:
     ```powershell
     python sub.py
     ```
   * เปิด PowerShell หน้าต่างที่ 2 (Activate venv) แล้วรัน Publisher เพื่อส่งข้อมูล:
     ```powershell
     python pub.py
     ```
4. สามารถหยุดการทำงานของสคริปต์ได้โดยกด `Ctrl + C`

---

## 5. การตั้งค่า Arduino สำหรับควบคุมด้วย PyFirmata2

การเตรียมบอร์ด Arduino ให้สามารถรับคำสั่งควบคุมจาก Python ผ่านโปรโตคอล Firmata:

1. เปิดโปรแกรม **Arduino IDE**
2. ไปที่ **Tools** -> **Manage Libraries...** แล้วค้นหาและติดตั้ง **Firmata** (แนะนำเวอร์ชัน `2.5.9`)
3. ไปที่เมนู **File** -> **Examples** -> **Firmata** -> **StandardFirmata**
4. เสียบสายเชื่อมต่อบอร์ด Arduino กับคอมพิวเตอร์ เลือก **Board** และ **Serial Port** ให้ถูกต้อง
5. กดปุ่ม **Upload** เพื่ออัปโหลดโค้ด `StandardFirmata` ลงบอร์ด
6. เมื่ออัปโหลดเรียบร้อย สคริปต์ Python ในเครื่อง Local ที่ใช้ `pyfirmata2` จะสามารถส่งคำสั่งควบคุม Pin ต่างๆ บน Arduino ได้โดยตรง
