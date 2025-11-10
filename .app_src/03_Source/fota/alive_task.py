import RPi.GPIO as GPIO
import time

# Cấu hình GPIO
INPUT_PIN = 10    # Chân đọc tín hiệu
OUTPUT_PIN = 24   # Chân xuất tín hiệu

# Dùng sơ đồ chân Broadcom
GPIO.setmode(GPIO.BCM)

# Thiết lập chân vào/ra
GPIO.setup(INPUT_PIN, GPIO.IN)
GPIO.setup(OUTPUT_PIN, GPIO.OUT)

try:
    print("Bắt đầu theo dõi GPIO 10. Nhấn Ctrl+C để dừng.")
    while True:
        state = GPIO.input(INPUT_PIN)  # Đọc trạng thái chân 10
        GPIO.output(OUTPUT_PIN, state) # Gửi trạng thái đó ra chân 24
        time.sleep(0.01)               # Delay nhẹ để tránh CPU load cao
except KeyboardInterrupt:
    print("\nDừng chương trình.")
finally:
    GPIO.cleanup()  # Reset các chân GPIO khi kết thúc
