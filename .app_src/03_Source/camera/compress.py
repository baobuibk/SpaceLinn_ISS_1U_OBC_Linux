import numpy as np
import cv2

width, height = 3840, 5120
raw_file = "output.raw"

# Đọc file .raw
with open(raw_file, "rb") as f:
    data = f.read()
file_size = len(data)

num_pixels = width * height

if abs(file_size - num_pixels * 2) < 100:  
    # Unpacked 16-bit
    print("Detected: Unpacked RAW10 (16-bit per pixel)")
    raw = np.frombuffer(data, dtype=np.uint16).reshape((height, width))
    raw10 = raw & 0x3FF   # giữ 10-bit
elif abs(file_size - num_pixels * 5 // 4) < 100:
    # Packed RAW10
    print("Detected: Packed RAW10")
    packed = np.frombuffer(data, dtype=np.uint8)
    raw10 = np.zeros(num_pixels, dtype=np.uint16)

    in_index = 0
    out_index = 0
    while in_index < len(packed):
        b0 = packed[in_index + 0]
        b1 = packed[in_index + 1]
        b2 = packed[in_index + 2]
        b3 = packed[in_index + 3]
        b4 = packed[in_index + 4]

        raw10[out_index + 0] = (b0 << 2) | ((b4 >> 0) & 0x3)
        raw10[out_index + 1] = (b1 << 2) | ((b4 >> 2) & 0x3)
        raw10[out_index + 2] = (b2 << 2) | ((b4 >> 4) & 0x3)
        raw10[out_index + 3] = (b3 << 2) | ((b4 >> 6) & 0x3)

        in_index += 5
        out_index += 4

    raw10 = raw10.reshape((height, width))
else:
    raise ValueError("Không khớp định dạng RAW10")

# Chuyển sang 8-bit
raw8 = (raw10 >> 2).astype(np.uint8)

# Demosaic Bayer -> BGR (chú ý pattern AR2020 có thể BG/GB/RG/GR)
bgr = cv2.cvtColor(raw8, cv2.COLOR_BAYER_BG2BGR)

# BGR -> YUV420 planar (I420)
yuv420 = cv2.cvtColor(bgr, cv2.COLOR_BGR2YUV_I420)

# Ghi ra file .yuv
with open("output.yuv", "wb") as f:
    f.write(yuv420.tobytes())

print("Đã lưu ảnh YUV420 → output.yuv")
