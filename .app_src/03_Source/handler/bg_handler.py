import sys
import serial
import time
import os
import threading
from queue import Queue
from datetime import datetime
from modfsp import MODFSP, MODFSPReturn, crc16_xmodem_update
import spidev
from pathlib import Path
import subprocess
from datetime import datetime
import logging
# import signal

# SCRIPT_DIR = Path.home() / "Data"
# SCRIPT_DIR.mkdir(parents=True, exist_ok=True)  # Tạo thư mục nếu chưa tồn tại
BASE_DATA_DIR = Path.home() / "Data/Raw"
BASE_DATA_DIR.mkdir(parents=True, exist_ok=True)  # Tạo thư mục Data nếu chưa tồn tại

CONFIG_DIR = Path.home() / ".app_src/02_ConfigSystem"

CAMERA_SWITCH_SCRIPT = Path.home() / ".app_src/03_Source/camera"
LOG_FILE = Path(__file__).parent / "handler.log"

# Global variable to track current timepoint folder
current_timepoint_folder = None

def get_daily_folder():
    today = datetime.now().strftime("%Y%m%d")
    daily_folder = BASE_DATA_DIR / today
    daily_folder.mkdir(parents=True, exist_ok=True)
    return daily_folder

def get_timepoint_folder():
    """Get current timepoint folder, create temp folder if none exists"""
    global current_timepoint_folder
    
    if current_timepoint_folder is None:
        # Create default temp folder if no timepoint has been set
        daily_folder = get_daily_folder()
        temp_folder = daily_folder / "temp"
        temp_folder.mkdir(parents=True, exist_ok=True)
        return temp_folder
    
    return current_timepoint_folder

def stop_existing_handlers():
    """Stop any existing handler.py processes"""
    script_name = os.path.basename(__file__)
    current_pid = os.getpid()
    
    print(f"[*] Checking for existing {script_name} processes...")
    
    try:
        # Find processes running this script
        result = subprocess.run(['pgrep', '-f', script_name], 
                              capture_output=True, text=True)
        
        if result.returncode == 0:
            pids = result.stdout.strip().split('\n')
            killed_count = 0
            
            for pid_str in pids:
                if pid_str.strip():
                    pid = int(pid_str.strip())
                    if pid != current_pid:  # Don't kill ourselves
                        try:
                            print(f"[!] Found existing handler process: PID {pid}")
                            # Try graceful termination first
                            os.kill(pid, 15)  # SIGTERM
                            time.sleep(1)
                            
                            # Check if process still exists
                            try:
                                os.kill(pid, 0)  # Just check if process exists
                                # If we get here, process still exists, force kill
                                print(f"[!] Forcefully killing PID {pid}")
                                os.kill(pid, 9)  # SIGKILL
                            except OSError:
                                # Process already terminated
                                pass
                                
                            print(f"[OK] Terminated PID {pid}")
                            killed_count += 1
                            
                        except OSError as e:
                            if e.errno != 3:  # Ignore "No such process" error
                                print(f"[!] Error killing PID {pid}: {e}")
            
            if killed_count == 0:
                print("[*] No other handler processes found")
            else:
                print(f"[*] Stopped {killed_count} existing handler process(es)")
                time.sleep(1)  # Give time for resources to be released
        else:
            print("[*] No existing handler processes found")
            
    except FileNotFoundError:
        # pgrep not available, try alternative method
        print("[*] pgrep not found, skipping process cleanup")
    except Exception as e:
        print(f"[!] Error during process cleanup: {e}")

# Stop existing handlers before starting
stop_existing_handlers()


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),               # console
        logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8")  # <-- "w" để clear mỗi lần start
    ]
)

logger = logging.getLogger("handler")

# Mã lệnh
CMD_REQUEST_MAKE_FOLDER_TIMEPOINT = 0x70

CMD_REQUEST_SCRIPT = 0x09
CMD_SEND_RTC_STM32 = 0x08

CMD_SET_CAM_POSITION = 0x50
CMD_TAKE_IMAGE = 0x51
CMD_CHUNK = 0x21
CMD_CURRENT = 0x22
CMD_LOG = 0x23

TEST_CONNECTION_CM4_CMD = 0x99
TEST_CONNECTION_CM4_ACK = 0x98

MODFSP_MASTER_ACK = 0x31
MODFSP_MASTER_NAK = 0x32

# SPI
SPI_BLOCK_SIZE = 32768
SPI_SUB_BLOCK_SIZE = 32768
NUM_SPI_BLOCKS = SPI_BLOCK_SIZE // SPI_SUB_BLOCK_SIZE
SPI_SPEED_HZ = 15000000
SPI_BUS = 1
SPI_DEVICE = 0

RUN_EXPERIMENT_CMD = 0x02
RUN_EXPERIMENT_ACK = 0x12

# Serial
SERIAL_PORT = "/dev/ttyAMA3"
SERIAL_BAUDRATE = 115200

current_cam_idx = None  

# Queue cho TX
tx_queue = Queue()

# Khởi tạo SPI
spi = spidev.SpiDev()
spi.open(SPI_BUS, SPI_DEVICE)
spi.max_speed_hz = SPI_SPEED_HZ
spi.mode = 0b10

# Serial
ser = None
while ser is None:
    try:
        ser = serial.Serial(SERIAL_PORT, SERIAL_BAUDRATE, timeout=0.01)
        print(f"[OK] Serial port {SERIAL_PORT} opened @ {SERIAL_BAUDRATE}")
        logger.info(f"[OK] Serial port {SERIAL_PORT} opened @ {SERIAL_BAUDRATE}")
    except serial.SerialException as e:
        print(f"[!] Cannot open serial port {SERIAL_PORT}: {e}")
        print("[.] Waiting for port to be released...")
        logger.info("[.] Waiting for port to be released...")
        time.sleep(5)

# MODFSP
modfsp = MODFSP(timeout_ms=2000, debug=False)

CRC_TABLE = [
    0x00000000, 0x04C11DB7, 0x09823B6E, 0x0D4326D9, 0x130476DC, 0x17C56B6B, 0x1A864DB2, 0x1E475005,
    0x2608EDB8, 0x22C9F00F, 0x2F8AD6D6, 0x2B4BCB61, 0x350C9B64, 0x31CD86D3, 0x3C8EA00A, 0x384FBDBD,
    0x4C11DB70, 0x48D0C6C7, 0x4593E01E, 0x4152FDA9, 0x5F15ADAC, 0x5BD4B01B, 0x569796C2, 0x52568B75,
    0x6A1936C8, 0x6ED82B7F, 0x639B0DA6, 0x675A1011, 0x791D4014, 0x7DDC5DA3, 0x709F7B7A, 0x745E66CD,
    0x9823B6E0, 0x9CE2AB57, 0x91A18D8E, 0x95609039, 0x8B27C03C, 0x8FE6DD8B, 0x82A5FB52, 0x8664E6E5,
    0xBE2B5B58, 0xBAEA46EF, 0xB7A96036, 0xB3687D81, 0xAD2F2D84, 0xA9EE3033, 0xA4AD16EA, 0xA06C0B5D,
    0xD4326D90, 0xD0F37027, 0xDDB056FE, 0xD9714B49, 0xC7361B4C, 0xC3F706FB, 0xCEB42022, 0xCA753D95,
    0xF23A8028, 0xF6FB9D9F, 0xFBB8BB46, 0xFF79A6F1, 0xE13EF6F4, 0xE5FFEB43, 0xE8BCCD9A, 0xEC7DD02D,
    0x34867077, 0x30476DC0, 0x3D044B19, 0x39C556AE, 0x278206AB, 0x23431B1C, 0x2E003DC5, 0x2AC12072,
    0x128E9DCF, 0x164F8078, 0x1B0CA6A1, 0x1FCDBB16, 0x018AEB13, 0x054BF6A4, 0x0808D07D, 0x0CC9CDCA,
    0x7897AB07, 0x7C56B6B0, 0x71159069, 0x75D48DDE, 0x6B93DDDB, 0x6F52C06C, 0x6211E6B5, 0x66D0FB02,
    0x5E9F46BF, 0x5A5E5B08, 0x571D7DD1, 0x53DC6066, 0x4D9B3063, 0x495A2DD4, 0x44190B0D, 0x40D816BA,
    0xACA5C697, 0xA864DB20, 0xA527FDF9, 0xA1E6E04E, 0xBFA1B04B, 0xBB60ADFC, 0xB6238B25, 0xB2E29692,
    0x8AAD2B2F, 0x8E6C3698, 0x832F1041, 0x87EE0DF6, 0x99A95DF3, 0x9D684044, 0x902B669D, 0x94EA7B2A,
    0xE0B41DE7, 0xE4750050, 0xE9362689, 0xEDF73B3E, 0xF3B06B3B, 0xF771768C, 0xFA325055, 0xFEF34DE2,
    0xC6BCF05F, 0xC27DEDE8, 0xCF3ECB31, 0xCBFFD686, 0xD5B88683, 0xD1799B34, 0xDC3ABDED, 0xD8FBA05A,
    0x690CE0EE, 0x6DCDFD59, 0x608EDB80, 0x644FC637, 0x7A089632, 0x7EC98B85, 0x738AAD5C, 0x774BB0EB,
    0x4F040D56, 0x4BC510E1, 0x46863638, 0x42472B8F, 0x5C007B8A, 0x58C1663D, 0x558240E4, 0x51435D53,
    0x251D3B9E, 0x21DC2629, 0x2C9F00F0, 0x285E1D47, 0x36194D42, 0x32D850F5, 0x3F9B762C, 0x3B5A6B9B,
    0x0315D626, 0x07D4CB91, 0x0A97ED48, 0x0E56F0FF, 0x1011A0FA, 0x14D0BD4D, 0x19939B94, 0x1D528623,
    0xF12F560E, 0xF5EE4BB9, 0xF8AD6D60, 0xFC6C70D7, 0xE22B20D2, 0xE6EA3D65, 0xEBA91BBC, 0xEF68060B,
    0xD727BBB6, 0xD3E6A601, 0xDEA580D8, 0xDA649D6F, 0xC423CD6A, 0xC0E2D0DD, 0xCDA1F604, 0xC960EBB3,
    0xBD3E8D7E, 0xB9FF90C9, 0xB4BCB610, 0xB07DABA7, 0xAE3AFBA2, 0xAAFBE615, 0xA7B8C0CC, 0xA379DD7B,
    0x9B3660C6, 0x9FF77D71, 0x92B45BA8, 0x9675461F, 0x8832161A, 0x8CF30BAD, 0x81B02D74, 0x857130C3,
    0x5D8A9099, 0x594B8D2E, 0x5408ABF7, 0x50C9B640, 0x4E8EE645, 0x4A4FFBF2, 0x470CDD2B, 0x43CDC09C,
    0x7B827D21, 0x7F436096, 0x7200464F, 0x76C15BF8, 0x68860BFD, 0x6C47164A, 0x61043093, 0x65C52D24,
    0x119B4BE9, 0x155A565E, 0x18197087, 0x1CD86D30, 0x029F3D35, 0x065E2082, 0x0B1D065B, 0x0FDC1BEC,
    0x3793A651, 0x3352BBE6, 0x3E119D3F, 0x3AD08088, 0x2497D08D, 0x2056CD3A, 0x2D15EBE3, 0x29D4F654,
    0xC5A92679, 0xC1683BCE, 0xCC2B1D17, 0xC8EA00A0, 0xD6AD50A5, 0xD26C4D12, 0xDF2F6BCB, 0xDBEE767C,
    0xE3A1CBC1, 0xE760D676, 0xEA23F0AF, 0xEEE2ED18, 0xF0A5BD1D, 0xF464A0AA, 0xF9278673, 0xFDE69BC4,
    0x89B8FD09, 0x8D79E0BE, 0x803AC667, 0x84FBDBD0, 0x9ABC8BD5, 0x9E7D9662, 0x933EB0BB, 0x97FFAD0C,
    0xAFB010B1, 0xAB710D06, 0xA6322BDF, 0xA2F33668, 0xBCB4666D, 0xB8757BDA, 0xB5365D03, 0xB1F740B4,
]

def create_timepoint_folder(year, month, day, hour, minute, second):
    """Create and set new timepoint folder"""
    global current_timepoint_folder
    
    # Create daily folder first
    daily_date = f"{2000+year:04d}{month:02d}{day:02d}"
    daily_folder = BASE_DATA_DIR / daily_date
    daily_folder.mkdir(parents=True, exist_ok=True)
    
    # Create timepoint folder inside daily folder
    timepoint_name = f"{2000+year:04d}{month:02d}{day:02d}-{hour:02d}{minute:02d}{second:02d}"
    timepoint_folder = daily_folder / timepoint_name
    timepoint_folder.mkdir(parents=True, exist_ok=True)
    
    # Update global current timepoint folder
    current_timepoint_folder = timepoint_folder
    
    print(f"[+] Created timepoint folder: {timepoint_folder}")
    logger.info(f"[+] Created timepoint folder: {timepoint_folder}")
    
    return timepoint_folder

def calculate_crc32(data):
    
    checksum = 0xFFFFFFFF
    crc_packet = bytearray()  

    for byte in data:
        crc_packet.extend([0x00, 0x00, 0x00, byte])

    for byte in crc_packet:
        top = (checksum >> 24) & 0xFF
        top ^= byte
        checksum = ((checksum << 8) & 0xFFFFFFFF) ^ CRC_TABLE[top]

    return checksum

def crc32_stm32_algo(data: bytes) -> int:
    polynomial = 0x04C11DB7
    crc = 0xFFFFFFFF

    for byte in data:
        crc ^= (byte << 24) 

        for _ in range(8):
            if (crc & 0x80000000):
                crc = (crc << 1) ^ polynomial
            else:
                crc <<= 1

            crc &= 0xFFFFFFFF  

    return crc

def read_byte_callback():
    if ser.in_waiting:
        byte = ser.read(1)
        return True, byte[0]
    return False, 0

def send_byte_callback(byte):
    ser.write(bytes([byte]))

def space_callback():
    return 2048

modfsp.set_read_callback(read_byte_callback)
modfsp.set_send_callback(send_byte_callback)
modfsp.set_space_callback(space_callback)

# CRC
def calculate_crc16(data):
    crc = 0x0000
    for b in data:
        crc = crc16_xmodem_update(crc, b)
    return crc

# Đọc SPI an toàn từng phần 4096 byte
def read_spi_block():
    data = bytearray()
    for _ in range(NUM_SPI_BLOCKS):
        dummy = [0x77] * SPI_SUB_BLOCK_SIZE
        data = spi.xfer2(dummy)
    return bytes(data)

def save_data_file(filename, content, append=False, use_timepoint=True):
    """Save data file to appropriate location"""
    if use_timepoint:
        # Save to timepoint folder for experiment data
        folder = get_timepoint_folder()
    else:
        # Save to daily folder for logs
        folder = get_daily_folder()
    
    filepath = folder / filename
    mode = "ab" if append else "wb"
    with open(filepath, mode) as f:
        f.write(content)
    if append == False:
        logger.info(f"[+] Saved to {filepath}")
    print(f"[+] Saved to {filepath} ({'append' if append else 'write'})")

def hex_dump_block(data, base_addr=0x00000000, width=16):
    for i in range(0, len(data), width):
        chunk = data[i:i+width]
        hex_bytes = " ".join(f"{b:02X}" for b in chunk)
        ascii_bytes = "".join(chr(b) if 32 <= b <= 126 else "." for b in chunk)
        print(f"0x{base_addr+i:08X}: {hex_bytes:<{width*3}} |{ascii_bytes}|")

# Handlers
def handle_request_make_folder_timepoint(payload):
    """Handle request to create timepoint folder"""
    try:
        print("[CMD] REQUEST MAKE FOLDER TIMEPOINT")
        
        if len(payload) != 6:
            print(f"[!] Invalid MAKE_FOLDER_TIMEPOINT payload size: {len(payload)} bytes (expected 6)")
            # modfsp.send(MODFSP_MASTER_NAK, b'')
            return
        
        year = payload[0]
        month = payload[1]
        day = payload[2]
        hour = payload[3]
        minute = payload[4]
        second = payload[5]
        
        print(f"-> Request timepoint: 20{year:02d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}")
        logger.info(f"-> Request timepoint: 20{year:02d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}")
        
        # Create the timepoint folder
        timepoint_folder = create_timepoint_folder(year, month, day, hour, minute, second)
        
        # Send ACK
        # modfsp.send(MODFSP_MASTER_ACK, b'')
        print("[OK] Timepoint folder created successfully")
        
    except Exception as e:
        print(f"[!] Exception in MAKE_FOLDER_TIMEPOINT handler: {e}")
        logger.exception(f"[!] Exception in MAKE_FOLDER_TIMEPOINT handler: {e}")
        # modfsp.send(MODFSP_MASTER_NAK, b'')

def handle_test_connection(payload):
    try:
        print("[CMD] TEST CONNECTION")
        
        if len(payload) != 4:
            print(f"[!] Invalid TEST_CONNECTION payload size: {len(payload)} bytes (expected 4)")
            modfsp.send(MODFSP_MASTER_NAK, b'')
            return
        
        data_32bit = (payload[0] << 24) | (payload[1] << 16) | (payload[2] << 8) | payload[3]
        print(f"Received 32-bit data: 0x{data_32bit:08X}")
        print(f"Payload bytes: {payload.hex().upper()}")
        
        echo_payload = payload 
        modfsp.send(TEST_CONNECTION_CM4_ACK, echo_payload)
        print(f"[OK] Echoed back: {echo_payload.hex().upper()}")
        
    except Exception as e:
        print(f"[!] Exception in TEST_CONNECTION handler: {e}")
        modfsp.send(MODFSP_MASTER_NAK, b'')

def handle_set_cam(payload):
    global current_cam_idx

    print("[CMD] Set Cam Position")
    print(f"Payload Size: {len(payload)}")
    print(f"Payload: {payload.hex()}")

    try:
        if len(payload) != 1:
            raise ValueError("Invalid payload size for set_cam")

        cam_val = payload[0]
        if cam_val not in [1, 2, 3, 4]:
            raise ValueError(f"Invalid cam value {cam_val}")

        # Mapping: 1→0, 2→1, 3→0, 4→1
        sensor_map = {1: 0, 2: 1, 3: 2, 4: 3}
        lane_map   = {1: 0, 2: 1, 3: 2, 4: 3}

        sensor_idx = sensor_map[cam_val]
        lane_idx   = lane_map[cam_val]
        current_cam_idx = cam_val  

        print(f"-> Switching to sensor {sensor_idx}, lane {lane_idx}")
        logger.info(f"-> Switching to sensor {sensor_idx}, lane {lane_idx}")
        # Run switch scripts
        subprocess.run([sys.executable, str(CAMERA_SWITCH_SCRIPT / "switch_sensor.py"), str(sensor_idx)], check=True)
        subprocess.run([sys.executable, str(CAMERA_SWITCH_SCRIPT / "switch_lane.py"), str(lane_idx)], check=True)

        # Set format
        subprocess.run([
            "v4l2-ctl", "--device=/dev/video0",
            "--set-fmt-video=width=5120,height=3840,pixelformat=pBAA"
        ], check=True, timeout=2.5)

        print("[OK] Camera position set")

    except Exception as e:
        logger.exception(f"[!] Error in handle_set_cam: {e}")

def handle_take_image(payload):
    global current_cam_idx

    print("[CMD] Take Image")
    print(f"Payload Size: {len(payload)}")
    print(f"Payload: {payload.hex()}")

    try:
        if len(payload) != 0:
            raise ValueError("Payload for take_image must be empty")

        if current_cam_idx is None:
            raise RuntimeError("No camera selected before take_image")

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_file = f"bg_Camera{current_cam_idx}_{ts}.raw"
        
        timepoint_folder = get_timepoint_folder()
        full_path = timepoint_folder / out_file

        print(f"-> Capturing image to {full_path}")
        logger.info(f"-> Capturing image to {full_path}")
        subprocess.run([
            "v4l2-ctl", "--device=/dev/video0",
            "--set-fmt-video=pixelformat=pBAA",
            "--stream-mmap", "--stream-count=1",
            f"--stream-to={full_path}"
        ], check=True, timeout=2.5)

        print("[OK] Image captured")

    except subprocess.TimeoutExpired:
        print("[!] Timeout while capturing image")
    except Exception as e:
        logger.exception(f"[!] Error in handle_take_image: {e}")
        print(f"[!] Error in handle_take_image: {e}")

def handle_chunk(payload):
    try:
        print("[CMD] CHUNK")
        if len(payload) != 13:
            print("[!] Invalid CHUNK payload")
            modfsp.send(MODFSP_MASTER_NAK, b'')
            return
        
        chunk_id = (payload[0] << 8) | payload[1]
        crc_received = (
            (payload[2] << 24) |
            (payload[3] << 16) |
            (payload[4] << 8) |
            payload[5]
        )
        year = payload[6]
        month = payload[7]
        day = payload[8]
        hour = payload[9]
        minute = payload[10]
        second = payload[11]
        index = payload[12]

        data = read_spi_block()
        crc = calculate_crc32(data)

        print(f"Chunk ID: {chunk_id}")
        print(f"Received CRC: {crc_received:08X}, Calculated CRC: {crc:08X}")
        print(f"Timestamp: 20{year:02d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}")

        if crc_received == crc:
            print("[OK]")
            modfsp.send(MODFSP_MASTER_ACK, b'')
        else:
            print("[FAIL] CRC mismatch")
            modfsp.send(MODFSP_MASTER_NAK, b'')

        # Save with timestamped filename, append mode
        filename = f"bg_dls_i{index:02d}_20{year:02d}{month:02d}{day:02d}_{hour:02d}{minute:02d}{second:02d}.bin"
        save_data_file(filename, data, append=True, use_timepoint=True)
        print(f"[v] Finish chunk: {chunk_id}")
        if chunk_id == 0: 
            logger.info("[CMD] CHUNK")
            logger.info(f"[v] New DLS Data Chunk accepted")

    except Exception as e:
        print(f"[!] Exception in CHUNK handler: {e}")
        modfsp.send(MODFSP_MASTER_NAK, b'')
        logger.exception(f"[!] Exception in CHUNK handler: {e}")

def handle_current(payload):
    try:
        print("[CMD] CURRENT")
        if len(payload) != 11:
            print("[!] Invalid CURRENT payload")
            modfsp.send(MODFSP_MASTER_NAK, b'')
            return
        logger.info("[CMD] CURRENT")
        crc_received = (
            (payload[0] << 24) |
            (payload[1] << 16) |
            (payload[2] << 8) |
            payload[3]
        )
        year = payload[4]
        month = payload[5]
        day = payload[6]
        hour = payload[7]
        minute = payload[8]
        second = payload[9]
        index = payload[10]

        data = read_spi_block()
        crc_calc = calculate_crc32(data)

        print(f"Received CRC: {crc_received:08X}, Calculated CRC: {crc_calc:08X}")
        print(f"Timestamp: 20{year:02d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}")

        if crc_received == crc_calc:
            print("[OK]")
            modfsp.send(MODFSP_MASTER_ACK, b'')
        else:
            print("[FAIL] CRC mismatch")
            modfsp.send(MODFSP_MASTER_NAK, b'')

        print("[.] Current Data got!")
        logger.info("[.] Current Data got!")
        filename = f"bg_current_i{index:02d}_20{year:02d}{month:02d}{day:02d}_{hour:02d}{minute:02d}{second:02d}.bin"
        save_data_file(filename, data, use_timepoint=True)

    except Exception as e:
        print(f"[!] Exception in CURRENT handler: {e}")
        modfsp.send(MODFSP_MASTER_NAK, b'')
        logger.exception(f"[!] Exception in CURRENT handler: {e}")

def handle_log(payload):
    try:
        print("[CMD] LOG")
        if len(payload) != 7:
            print("[!] Invalid LOG payload")
            modfsp.send(MODFSP_MASTER_NAK, b'')
            return
        logger.info("[CMD] LOG")
        log_type = payload[0]  # 0xFF for obc, else exp
        year = payload[1]
        month = payload[2]
        day = payload[3]
        hour = payload[4]
        minute = payload[5]
        second = payload[6]

        label = "obc_log" if log_type == 0xFF else "exp_log"
        filename = f"{label}_20{year:02d}{month:02d}{day:02d}_{hour:02d}{minute:02d}{second:02d}.bin"

        print(f"[.] -> Got: {label}!")
        data = read_spi_block()
        save_data_file(filename, data, use_timepoint=False)
        logger.info(f"[.] -> Got: {label}!")
        # Send ACK after successful processing
        modfsp.send(MODFSP_MASTER_ACK, b'')

    except Exception as e:
        print(f"[!] Exception in LOG handler: {e}")
        modfsp.send(MODFSP_MASTER_NAK, b'')
        logger.exception(f"[!] Exception in LOG handler: {e}")

def handle_run_exp_ack(payload):
    print("[CMD] Run Experiment ACK!")

def handle_request_script(payload):
    """Handle request to send experiment_run.bin"""
    try:
        print("[CMD] REQUEST SCRIPT")
        file_path = CONFIG_DIR / "experiment_run.bin"

        if not file_path.exists():
            print(f"[!] File not found: {file_path}")
            modfsp.send(MODFSP_MASTER_NAK, b'')
            return

        with open(file_path, "rb") as f:
            data = f.read()

        print(f"Sending file: {file_path.name} ({len(data)} bytes)")
        logger.info(f"Sending file: {file_path.name} ({len(data)} bytes)")

        # Gửi trực tiếp qua serial
        ser.write(data)

        # Gửi ACK sau khi gửi xong
        # modfsp.send(CMD_REQUEST_SCRIPT_ACK, b'')
        print("[OK] experiment_run.bin sent")
        time.sleep(5)
        run_experiment()
    except Exception as e:
        print(f"[!] Exception in handle_request_script: {e}")
        logger.exception(f"[!] Exception in handle_request_script: {e}")
        # modfsp.send(MODFSP_MASTER_NAK, b'')
        
def handle_send_rtc_stm32(payload):
    try:
        print("[CMD] SEND RTC STM32")
        if len(payload) != 6:
            print(f"[!] Invalid RTC payload size: {len(payload)}")
            modfsp.send(MODFSP_MASTER_NAK, b'')
            return

        hour   = payload[0]
        minute = payload[1]
        second = payload[2]
        day    = payload[3]
        month  = payload[4]
        year   = payload[5] + 2000  # STM32 gửi YY, mình đổi thành 20YY

        dt_str = f"{year}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}"
        print(f"-> Setting CM4 RTC to: {dt_str}")
        logger.info(f"-> Setting CM4 RTC to: {dt_str}")

        # Dùng lệnh date để set hệ thống
        os.system(f"sudo date -s '{dt_str}'")

        # Gửi ACK
        # modfsp.send(MODFSP_MASTER_ACK, b'')
        print("[OK] RTC updated")

    except Exception as e:
        print(f"[!] Exception in handle_send_rtc_stm32: {e}")
        logger.exception(f"[!] Exception in handle_send_rtc_stm32: {e}")
        # modfsp.send(MODFSP_MASTER_NAK, b'')


# Register
modfsp.register_command(CMD_REQUEST_MAKE_FOLDER_TIMEPOINT, handle_request_make_folder_timepoint)
modfsp.register_command(CMD_SET_CAM_POSITION, handle_set_cam)
modfsp.register_command(CMD_TAKE_IMAGE, handle_take_image)
modfsp.register_command(CMD_CHUNK, handle_chunk)
modfsp.register_command(CMD_CURRENT, handle_current)
modfsp.register_command(CMD_LOG, handle_log)
modfsp.register_command(TEST_CONNECTION_CM4_CMD, handle_test_connection)
modfsp.register_command(RUN_EXPERIMENT_ACK, handle_run_exp_ack)
modfsp.register_command(CMD_REQUEST_SCRIPT, handle_request_script)
modfsp.register_command(CMD_SEND_RTC_STM32, handle_send_rtc_stm32)

# RX Thread
def serial_rx_thread():
    while True:
        modfsp.process()
        time.sleep(0.001)

# TX Thread (tùy chọn)
def serial_tx_thread():
    while True:
        if not tx_queue.empty():
            cmd_id, data = tx_queue.get()
            modfsp.send(cmd_id, data)
        time.sleep(0.01)

def run_experiment():
    print("Sending RUN EXPERIMENT command...")
    result = modfsp.send(RUN_EXPERIMENT_CMD, b'')
    if result == MODFSPReturn.OK:
        print("Experiment command sent successfully!")
    else:
        print(f"Failed to send experiment command (Error={result.name})")

# Main
def show_menu():
    print("\n========= BG-Handler Menu =========")
    print("q. Quit")
    print("================================")
    choice = input("-> Choose option: ")
    return choice

if __name__ == "__main__":
    try:
        print(f"[*] Listening on {SERIAL_PORT} @ {SERIAL_BAUDRATE}")
        rx_thread = threading.Thread(target=serial_rx_thread, daemon=True)
        tx_thread = threading.Thread(target=serial_tx_thread, daemon=True)

        rx_thread.start()
        tx_thread.start()

        time.sleep(1.0)

        run_experiment()

        while True:
            choice = show_menu()
            if choice == "1":
                run_experiment()
            elif choice.lower() == "q":
                print("[OK] Quit requested by user.")
                break
            else:
                print("[!] Invalid option, please try again.")

    except KeyboardInterrupt:
        print("\n[!] Interrupted by user.")
    finally:
        spi.close()
        ser.close()
        print("[OK] Resources released. Bye!")
