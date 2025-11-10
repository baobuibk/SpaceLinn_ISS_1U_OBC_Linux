import serial
import time
import os
import struct
import threading
import sys
import argparse
import re
import hashlib
import json
from tqdm import tqdm
import serial.tools.list_ports
import RPi.GPIO as GPIO
from pathlib import Path
import subprocess

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


def GPIO9_Init():
    GPIO_PIN = 9
    GPIO.setup(GPIO_PIN, GPIO.OUT)
    GPIO9_Set_Output(True)
    return True

def GPIO9_Set_Output(state: bool) -> bool:
    GPIO_PIN = 9
    if not GPIO.gpio_function(GPIO_PIN) == GPIO.OUT:
        GPIO.setup(GPIO_PIN, GPIO.OUT)
    GPIO.output(GPIO_PIN, GPIO.HIGH if state else GPIO.LOW)
    return True



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

def list_bin_files(mcu):
    """List .bin files in ~/FirmwareUpdate and prompt for .bin and .json file selection"""
    output_dir = Path.home() / "FirmwareUpdate"

    if not output_dir.exists():
        print(f"[ERROR] Directory not found: {output_dir}")
        return None, None

    # Xác định key theo loại mcu
    if mcu == 0:
        mcu_key = 'exp'
    elif mcu == 1:
        mcu_key = 'm7'
    elif mcu == 2:
        mcu_key = 'm4'
    else:
        print("Invalid MCU type!")
        return None, None

    bin_files = [f for f in output_dir.glob("*.bin") if mcu_key in f.name.lower()]

    if not bin_files:
        print("No .bin files found for the selected MCU!")
    else:
        print("Available .bin files:")
        for idx, f in enumerate(bin_files, start=1):
            print(f"{idx}: {f.name}")

    # Lựa chọn .bin file
    while True:
        try:
            if bin_files:
                prompt = {
                    0: "Select a .bin file number or enter file path: ",
                    1: "Select a .bin file number or enter file path for core M7: ",
                    2: "Select a .bin file number or enter file path for core M4: "
                }.get(mcu, "Select a .bin file number or enter file path: ")
            else:
                prompt = {
                    0: "Enter .bin file path: ",
                    1: "Enter .bin file path for core M7: ",
                    2: "Enter .bin file path for core M4: "
                }.get(mcu, "Enter .bin file path: ")

            choice = input(prompt).strip().strip('"\' ')
            try:
                choice_num = int(choice)
                if 1 <= choice_num <= len(bin_files):
                    bin_file = bin_files[choice_num - 1]
                    break
                else:
                    print("Invalid number choice.")
            except ValueError:
                custom_path = Path(choice)
                if custom_path.is_file() and custom_path.suffix.lower() == '.bin':
                    bin_file = custom_path
                    break
                else:
                    print("Invalid file path or not a .bin file.")
        except KeyboardInterrupt:
            print("\nOperation cancelled by user.")
            return None, None

    # Xác định đường dẫn tới file .json tương ứng
    json_file = bin_file.with_suffix(".json")
    return str(bin_file), str(json_file)






#######################  VALID FIRMWARE BIN FILE  ######################
def calculate_sha256(file_path):
    sha256_hash = hashlib.sha256()
    try:
        with open(file_path, "rb") as file:
            for byte_block in iter(lambda: file.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest(), None
    except FileNotFoundError:
        return None, "Error: .bin file not found!"
    except Exception as e:
        return None, f"Error: {str(e)}!"

def get_file_size(file_path):
    try:
        return os.path.getsize(file_path), None
    except FileNotFoundError:
        return None, "Error: File not found!"
    except Exception as e:
        return None, f"Error: {str(e)}!"

def read_json_file(json_file):
    try:
        with open(json_file, "r") as file:
            data = json.load(file)
            if not data or not isinstance(data, list) or not data[0]:
                return None, None, None, "Error: Invalid JSON format!"
            record = data[0]
            return (record.get("file_name"), record.get("version"), 
                    record.get("sha256_hash"), record.get("file_size"))
    except FileNotFoundError:
        return None, None, None, "Error: .json file not found!"
    except json.JSONDecodeError:
        return None, None, None, "Error: Invalid JSON file!"
    except Exception as e:
        return None, None, None, f"Error: {str(e)}!"

def is_valid_bin_file(file_path):
    """Check if file has .bin extension"""
    return file_path.lower().endswith('.bin')

def is_valid_json_file(file_path):
    """Check if file has .json extension"""
    return file_path.lower().endswith('.json')

def valid_bin_file(bin_file, json_file):
    print(bin_file)
    print(json_file)
    file_name, version, stored_hash, stored_size = read_json_file(json_file)
    if stored_size and isinstance(stored_size, str) and stored_size.startswith("Error"):
        print(stored_size)
        return False, None
    
    current_hash, hash_error = calculate_sha256(bin_file)
    current_size, size_error = get_file_size(bin_file)
    
    if current_hash is None:
        print(hash_error)
        return False, None
    if current_size is None:
        print(size_error)
        return False, None   
    if current_hash == stored_hash and current_size == stored_size: #verify bin1 ok
        print(f"Verified {bin_file} done!")
        return True, version
    else:
        print(f"Verified {bin_file} failed!")
        return False, None
##################################################################

class STM32Bootloader:
    def __init__(self, mcu, port = '/dev/ttyAMA3', baudrate=115200):
        self.mcu = mcu
        self.port = port
        self.baudrate = baudrate
        self.serial = None
        self.firmware_number = None  # Store firmware selection
        self.NOT_ACKNOWLEDGE = 0xAB
        self.FOTA_SUCCEEDED = 0

    def send_board_reset(self):
        if self.mcu == 1:
            print("\rReseting EXP...", end='')
        else:
            print("\rReseting OBC...", end='')
        send_frame = None
        expected_frame = None
        SFP_START1_BYTE = 0xC0
        SFP_START2_BYTE = 0xDE
        if self.mcu == 2:
            send_frame = [0xC0, 0xDE, 0x03, 0x00, 0x00, 0x50, 0x59, 0xDA, 0xED]
            expected_frame = [0xC0, 0xDE, 0x13, 0x00, 0x00, 0x33, 0x1A, 0xDA, 0xED]
        elif self.mcu == 1:
            GPIO9_Set_Output(True)
            time.sleep(1)
            GPIO9_Set_Output(False)
            send_frame = [0xC0, 0xDE, 0x04, 0x00, 0x00, 0xC0, 0xDC, 0xDA, 0xED]
            expected_frame = [0xC0, 0xDE, 0x14, 0x00, 0x00, 0xA3, 0x9F, 0xDA, 0xED]
        else:
            return False
        
        self.serial.reset_input_buffer()
        self.serial.reset_output_buffer()
        self.serial.write(bytes(send_frame))
        
        start_time = time.time()
        state = "WAIT_START1"
        byte_index = 0
        
        while time.time() - start_time < 10:
            if self.serial.in_waiting > 0:
                data = self.serial.read(self.serial.in_waiting)
                for byte in data:
                    if state == "WAIT_START1":
                        if byte == SFP_START1_BYTE:
                            state = "WAIT_START2"
                            byte_index = 1
                    
                    elif state == "WAIT_START2":
                        if byte == SFP_START2_BYTE:
                            state = "CHECK_FRAME"
                            byte_index = 2
                        else:
                            state = "WAIT_START1"
                    
                    elif state == "CHECK_FRAME":
                        if byte != expected_frame[byte_index]:
                            state = "WAIT_START1"
                            byte_index = 0
                        else:
                            byte_index += 1
                            if byte_index == len(expected_frame):
                                print("   \033[32mDone ✓\033[0m")
                                return True
        print("   \033[31mFailed ✗\033[0m")
        return False


    def read_firmware_detail(self):
        """Read Firmware Version (0x16)"""
        if not self.firmware_number:
            print("No firmware selected! Please choose firmware first.")
            return False
        print(f"\rReading firmware {self.firmware_number}'s data...", end='')
        packet = bytearray(7)
        packet[0] = 6  # Packet length
        packet[1] = 0x16  # Read Version command
        packet[2] = self.firmware_number & 0xFF  # Firmware number (1 or 2)
        crc = calculate_crc32(packet[:3])
        struct.pack_into('<I', packet, 3, crc)
        
        response = self.send_packet(packet, 6, 10)  # Expecting 1 status byte + 3 version bytes
        if response and response[0] == self.FOTA_SUCCEEDED and len(response) == 6:
            print("   \033[32mDone ✓\033[0m")
            print(f"Firmware {self.firmware_number} Version: {response[1]}.{response[2]}.{response[3]}")
            print(f"Firmware {self.firmware_number} Size: {(response[4]<< 8) | response[5]}KB")
            return True
        print("   \033[31mFailed ✗\033[0m")
        return False
    
    def write_firmware_version(self, version_name):
        """Write Firmware Version (0x17)"""
        if not self.firmware_number:
            print("No firmware selected! Please choose firmware first.")
            return False
        version_name = version_name.strip()
        major, minor, patch = map(int, version_name.split('.'))

        print(f"\rWriting firmware {self.firmware_number} version {major}.{minor}.{patch}...", end='')
        packet = bytearray(10)
        packet[0] = 9  # Packet length
        packet[1] = 0x17  # Write Version command
        packet[2] = self.firmware_number & 0xFF  # Firmware number (1 or 2)
        packet[3] = major & 0xFF
        packet[4] = minor & 0xFF
        packet[5] = patch & 0xFF
        crc = calculate_crc32(packet[:6])
        struct.pack_into('<I', packet, 6, crc)
        
        response = self.send_packet(packet, 1, 20)
        if response and response[0] == self.FOTA_SUCCEEDED:
            print("   \033[32mDone ✓\033[0m")
            return True
        print("   \033[31mFailed ✗\033[0m")
        return False
    
    def connect_serial(self):
        """Connect to the STM32 bootloader via UART"""
        try:
            self.serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                bytesize=serial.EIGHTBITS,
                timeout=2
            )
            print(f"Port {self.port.upper()} opened.")
            return True
        except serial.SerialException as e:
            print(f"Serial connection error: {e}")
            return False

    def send_packet(self, packet, response_length, time_out):
        """Send a packet and wait for response"""
        self.serial.reset_input_buffer()
        self.serial.reset_output_buffer()
        self.serial.write(packet)
        start_time = time.time()
        while time.time() - start_time < time_out:  # Timeout
            if self.serial.in_waiting >= response_length:
                return self.serial.read(response_length)
        return None

    def read_chip_id(self):
        """Read Chip ID (0x10)"""
        packet = bytearray(6)
        packet[0] = 5
        packet[1] = 0x10
        crc = calculate_crc32(packet[:2])
        struct.pack_into('<I', packet, 2, crc)
        response = self.send_packet(packet, 2, 5)
        if response and response[0] != self.NOT_ACKNOWLEDGE:
            chip_id = (response[1] << 8) | response[0]
            print(f"Chip ID: 0x{chip_id:04X}")
            return True
        print("Failed to read Chip ID!")
        return False
    
    def check_connection(self):
        """Send 'bootmode' command to bootloader to jump to boot mode"""
        print("\rChecking connection...", end='')
        
        packet = bytearray(6)
        packet[0] = 5
        packet[1] = 0x15
        crc = calculate_crc32(packet[:2])
        struct.pack_into('<I', packet, 2, crc)
        response = self.send_packet(packet, 3, 5)
        if response and response[0] == self.FOTA_SUCCEEDED and response[1] == ord('O') and response[2] == ord('K'):
            print("   \033[32mDone ✓\033[0m")
            time.sleep(0.6)
            return True
        '''        
        # If MCU in App mode, call Reset to boot to bootloader mode
        packet_str = bytearray([ord('\r'), ord('r'), ord('e'), ord('s'), ord('e'), ord('t'), ord('\r')])
        self.serial.reset_input_buffer()
        self.serial.reset_output_buffer()
        self.serial.write(packet_str)
        start_time = time.time()
        response = bytearray()
        while time.time() - start_time < 5:
            if  self.serial.in_waiting > 0:
                response.extend( self.serial.read( self.serial.in_waiting))
                # Kiểm tra từng byte
                for i in range(len(response)):
                    if i + 2 < len(response):  # Đảm bảo đủ 3 byte
                        if (response[i] == 1 and response[i + 1] == ord('O') and response[i + 2] == ord('K')):
                            response = bytearray()
                            response = self.send_packet(packet, 3, 3)
                            if response and response[0] == self.FOTA_SUCCEEDED and response[1] == ord('O') and response[2] == ord('K'):
                                print("   \033[32mDone ✓\033[0m")
                                time.sleep(0.6)
                                return True
                            print("   \033[31mFailed ✗\033[0m")
                            time.sleep(0.6)
                            return False
            
            time.sleep(0.01)  # Ngủ ngắn để giảm tải CPU
        '''
        print("   \033[31mFailed ✗\033[0m")
        return False

    def select_firmware(self, mode):
        """Select firmware number (1 or 2)"""
        if mode == 0:
            while True:
                choice = input("Select core number (1 or 2): ")
                if self.mcu == 1:         #board is exp (1 core)
                    if choice == "1":
                        self.firmware_number = int(choice)
                        print(f"Firmware {self.firmware_number} selected")
                        return True
                    else:
                        print("Invalid input! board EXP have 1 core, pls enter 1.")
                elif self.mcu == 2:         #board is obc (2 core) 
                    if choice in ["1", "2"]:
                        self.firmware_number = int(choice)
                        print(f"Core {self.firmware_number} selected")
                        return True
                    print("Invalid input! Please enter 1 or 2.")
        else:
            self.firmware_number = mode 
            
            

    def erase_flash(self):
        """Erase Flash (0x13)"""
        if not self.firmware_number:
            print("No firmware selected! Please choose firmware first.")
            return False
        packet = bytearray(7)
        packet[0] = 6
        packet[1] = 0x13
        packet[2] = self.firmware_number & 0xFF
        
        crc = calculate_crc32(packet[:3])
        struct.pack_into('<I', packet, 3, crc)
        print(f"\rErasing firmware {self.firmware_number}...", end='')
        response = self.send_packet(packet, 1, 20)
        if response and response[0] == self.FOTA_SUCCEEDED:
            print("   \033[32mDone ✓\033[0m")#Erase Flash Successful")
            return True
        print("   \033[31mFailed ✗\033[0m")
        return False

    def upload_application(self, bin_path):
        """Upload firmware via UART"""
        if not self.firmware_number:
            print("No firmware selected! Please choose firmware (1 or 2) first.")
            return False
        if not os.path.exists(bin_path):
            print(f"File not found: {bin_path}")
            return False

        with open(bin_path, 'rb') as f:
            firmware_data = f.read()

        file_size = len(firmware_data)
        chunk_size = 128
        total_frames = (file_size + chunk_size - 1) // chunk_size
        frame_index = 0

        print(f"Firmware-Size: {file_size} bytes, Total frames: {total_frames}")
        print(f"Uploading firmware {self.firmware_number}:")
        for i in tqdm(range(0, file_size, chunk_size), desc="Processing", unit="frame", ncols=80):
        
        
        #for i in range(0, file_size, chunk_size):
            actual_chunk_size = min(chunk_size, file_size - i)
            packet_length = actual_chunk_size + 12  # 8 (header) + 4 (CRC)

            packet = bytearray(packet_length)
            packet[0] = packet_length - 1  # Độ dài gói (trừ đi byte này)
            packet[1] = 0x14  # Mã lệnh Upload Application
            packet[2] = self.firmware_number & 0xFF  # Firmware number (1 or 2)
            packet[3] = actual_chunk_size  # Chunk size

            struct.pack_into('<H', packet, 4, frame_index)  
            struct.pack_into('<H', packet, 6, total_frames)  

            chunk = firmware_data[i:i + actual_chunk_size]
            packet[8:8 + actual_chunk_size] = chunk  # Payload

            crc = calculate_crc32(packet[:8 + actual_chunk_size])
            struct.pack_into('<I', packet, 8 + actual_chunk_size, crc)  # CRC32
            #print(f"Send frame {frame_index + 1}/{total_frames}, Size: {actual_chunk_size} bytes")

            response = self.send_packet(packet, 1, 20)
            if not response or response[0] != self.FOTA_SUCCEEDED:
                print("\r\n\033[31mUpload failed!\033[0m")
                return False
            frame_index += 1

        print("\033[32mDone ✓\033[0m")
        return True

    def jump_to_application(self):
        """Jump to application (0x12)"""
        print("\rApplication Initialize...", end='')
        packet = bytearray(6)
        packet[0] = 5  # Độ dài gói tin
        packet[1] = 0x12  # Lệnh Jump
        
        crc = calculate_crc32(packet[:2])  # CRC trên 2 byte đầu
        struct.pack_into('<I', packet, 2, crc)  # Nhúng CRC vào packet
        response = self.send_packet(packet, 1, 10)
        if response and response[0] == self.FOTA_SUCCEEDED:
            print("   \033[32mDone ✓\033[0m")
            if(self.mcu == 1):
                GPIO9_Set_Output(True)
            return True
        print("   \033[31mFailed ✗\033[0m")
        return False
    

    def uart_terminal(self):
        """Real-time UART terminal mode"""
        if not self.serial:
            print("UART is not connected!")
            return
        print("STM32 Console. Enter commands (Ctrl+C to exit).")
        self.serial.reset_input_buffer()
        self.serial.reset_output_buffer()
        stop_event = threading.Event()
        def read_uart():
            """Thread to continuously read UART data"""
            while not stop_event.is_set():
                if self.serial.in_waiting:
                    data = self.serial.read(self.serial.in_waiting).decode(errors='ignore')
                    print(data.strip() + ' ', end='', flush=True)
                time.sleep(0.1)

        uart_thread = threading.Thread(target=read_uart, daemon=True)
        uart_thread.start()
        try:
            while True:
                command = input()  # Get user input
                if command.lower() == "exit":
                    stop_event.set()
                    break  # Exit terminal mode
                self.serial.write((command + '\r').encode('utf-8'))
                #self.send_packet((command + '\r').encode('utf-8'), 0, 0)  # Send input over UART
        except KeyboardInterrupt:
            stop_event.set()
            print("\nExiting STM32 Console mode...")
        

    def close(self):
        """Close the serial connection"""
        if self.serial and self.serial.is_open:
            self.serial.close()
            print("Serial connection closed")


####################################################################################
############################## BOOTLOADER OPTION MODE ##############################
####################################################################################

def process_opt_mode():
    
    print("Welcome to STM32 Bootloader Menu")
        
    while True:
        try:
            print("Choose board selection:")
            print("1: EXP (singlecore)")
            print("2: OBC (dualcore)")
            print("3: Exit")
            choice = input("Select an option: ")
            choice = int(choice)
            if 1 <= choice <= 2:
                mcu = choice
                print(f"Board {('EXP' if mcu == 1 else 'OBC')} selected.")
                break
            elif choice == 3:
                sys.exit(0)
            raise ValueError
        except ValueError as e:
            print(f"Invalid choice. Please select 1 to 2.")
        except KeyboardInterrupt:
            print("\nOperation cancelled by user.")
            return
        
    bootloader = STM32Bootloader(mcu)
    if not bootloader.connect_serial():
        return
            
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(True)
    GPIO9_Init()
    connection_checked = False 
    
    while True:
        try:
            print("\nMenu Options:")
            print("1: Reset to bootloader")
            print("2: Check Connection")
            print("3: Read Chip ID")
            print("4: Flash Firmware")
            print("5: Read Firmware Detail")
            print("6: Exit")

            choice = input("Select an option (1-6): ")
            if choice in ["3", "4", "5"]:
                if not connection_checked:
                    print("Error: Please select 'Check Connection' (option 2) first.")
                    continue
            if choice == "1":
                if not bootloader.send_board_reset():
                    continue
                   
            elif choice == "2":
                connection_checked = bootloader.check_connection()      
            elif choice == "3":
                bootloader.read_chip_id()
            elif choice == "4":
                if(mcu == 1):
                    bin_file1, json_file1 = list_bin_files(0)     # select .bin file
                else:
                    bin_file1, json_file1 = list_bin_files(1)     # select .bin file
                    
                if not bin_file1 or not json_file1:
                    bootloader.close()
                    sys.exit(0)
                else:
                    status, version1 = valid_bin_file(bin_file1, json_file1)
                    if not status:
                        continue

                if(mcu == 2):       #if obc have 2 core    
                    bin_file2, json_file2 = list_bin_files(2)     # select .bin file
                    if not bin_file2 or not json_file2:
                        bootloader.close()
                        sys.exit(0)
                    else:
                        status, version2 = valid_bin_file(bin_file2, json_file2)
                        if not status:
                            continue
                

                bootloader.select_firmware(1)   # select core using input
                if not bootloader.erase_flash():        # erase flash
                    bootloader.close()
                    sys.exit(0)
                if not bootloader.write_firmware_version(version1):
                    bootloader.close()
                    sys.exit(0) 
                if not bootloader.upload_application(bin_file1): #upload fw
                    bootloader.close()
                    sys.exit(0)
                    
                if(mcu == 2):
                    bootloader.select_firmware(2)   # select core using input
                    if not bootloader.erase_flash():        # erase flash
                        bootloader.close()
                        sys.exit(0)
                    if not bootloader.write_firmware_version(version2):
                        bootloader.close()
                        sys.exit(0) 
                    if not bootloader.upload_application(bin_file2): #upload fw
                        bootloader.close()
                        sys.exit(0)
                if not bootloader.jump_to_application():
                    bootloader.close()
                    sys.exit(0)
                else:
                    connection_checked = False
                    
            elif choice == "5":
                bootloader.select_firmware(1)
                bootloader.read_firmware_detail()
                
                bootloader.select_firmware(2)
                bootloader.read_firmware_detail()

            elif choice == "6":
                GPIO9_Set_Output(True)
                print("Exiting...")
                
                bootloader.close()
                break
            else:
                print("Invalid choice, please try again.")

        except KeyboardInterrupt:
            bootloader.close()
            print("\nKeyboard Interrupt detected. Exiting safely...")
            sys.exit(0)
    
    
####################################################################################
############################ BOOTLOADER SEQUENCE MODE ##############################
####################################################################################

def process_seq_mode(args):
    """
    Process arguments for sequential mode.
    """
    print("Processing in Sequential Mode:")
    
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(True)
    GPIO9_Init()
    
    if args.board in ["EXP", "exp"]:
        mcu = 1
    elif args.board in ["OBC", "obc"]:
        mcu = 2
        
    bootloader = STM32Bootloader(mcu, args.port)
    if not bootloader.connect_serial():
        return
    

    if mcu == 1:
        args.bin = args.bin.strip()
        if not os.path.exists(args.bin):
            print("Bin path not found! Try again.")
        else:
            if not args.bin.lower().endswith('.bin'):
                print("Bin path must end with '.bin'.")
                return
            print(f"Bin path: {args.bin}")
            
        args.meta = args.meta.strip()
        if not os.path.exists(args.meta):
            print("Metadata path not found! Try again.")
        else:
            if not args.meta.lower().endswith('.json'):
                print("Metadata path must end with '.json'.")
                return
            print(f"Metadata path: {args.meta}")
            
    elif mcu == 2:
        args.bin1 = args.bin1.strip()
        args.bin2 = args.bin2.strip()
        if not os.path.exists(args.bin1):
            print("ERROR: Bin path core 1 not found! Try again.")
        else:
            if not args.bin1.lower().endswith('.bin'):
                print("ERROR: Bin path core 1 must end with '.bin'!")
                return
            print(f"Bin path core 1: {args.bin1}")
            
        if not os.path.exists(args.bin2):
            print("ERROR: Bin path core 2 not found! Try again.")
        else:
            if not args.bin2.lower().endswith('.bin'):
                print("ERROR: Bin path core 2 must end with '.bin'!")
                return
            print(f"Bin path core 2: {args.bin2}")
            
            
        args.meta1 = args.meta1.strip()
        args.meta2 = args.meta2.strip()
        if not os.path.exists(args.meta1):
            print("ERROR: Metadata core 1 path not found! Try again.")
        else:
            if not args.meta1.lower().endswith('.json'):
                print("ERROR: Metadata core 1 must end with '.json'!")
                return
            print(f"Metadata core 1: {args.meta1}")
            
        if not os.path.exists(args.meta2):
            print("ERROR: Metadata core 2 not found! Try again.")
        else:
            if not args.meta2.lower().endswith('.json'):
                print("ERROR: Metadata core 2 must end with '.json'!")
                return
            print(f"Metadata core 2: {args.meta2}")
    
    if(mcu == 1):
        status, version1 = valid_bin_file(args.bin, args.meta)
        if not status:
            return
    else:
        status, version1 = valid_bin_file(args.bin1, args.meta1)
        if not status:
            return      
        status, version2 = valid_bin_file(args.bin2, args.meta2)
        if not status:
            return 
    
    '''Step 1: Check connection: jump to bootloader'''
    if not bootloader.send_board_reset():
        bootloader.close()
        sys.exit(1)
    time.sleep(0.5)
    
    '''Step 1: Check connection: jump to bootloader'''
    if not bootloader.check_connection():
        bootloader.close()
        sys.exit(1)
    
    '''Step 2: Select firmware 1'''
    bootloader.select_firmware(1)
    
    '''Step 3: Erase Flash bank 1'''
    if not bootloader.erase_flash():
        bootloader.close()
        sys.exit(1)

    '''Step 4: Flash metadata 1'''
    if not bootloader.write_firmware_version(version1):
        bootloader.close()
        sys.exit(1)
                    
    '''Step 5: Flash firmware 1'''    
    if mcu == 1:
        if not bootloader.upload_application(args.bin):
            bootloader.close()
            sys.exit(1)
    else:
        if not bootloader.upload_application(args.bin1):
            bootloader.close()
            sys.exit(1)
    
    '''Step 6: Firmware 2 if '''
    if mcu == 2:
        '''Select firmware 2 (option)'''
        bootloader.select_firmware(2)    
        
        '''Erase Flash bank 2 (option)'''
        if not bootloader.erase_flash():
            bootloader.close()
            sys.exit(1)
            
        '''Flash metadata 2 (option)'''
        if not bootloader.write_firmware_version(version2):
            bootloader.close()
            sys.exit(1)
            
        '''Flash firmware 2 (option)'''    
        if not bootloader.upload_application(args.bin2):
            bootloader.close()
            sys.exit(1)
    
    '''Step 7: Jump to application'''
    if not bootloader.jump_to_application():
        bootloader.close()
        sys.exit(1)
    
####################################################################################
####################################################################################
####################################################################################    
    
    
def validate_fw_args(args):
    # Check port
    if not args.port:
        raise argparse.ArgumentError(None, "Port argument (-port) is required.")
    
    # Check bin file for MCU
    if args.board in ["exp", "EXP"]:
        if not args.bin:
            raise argparse.ArgumentError(None, f"For board EXP, exactly one -bin argument is required.")
        if args.bin1 or args.bin2:
            raise argparse.ArgumentError(None, f"For board EXP, use -bin, not -bin1 or -bin2.")
    elif args.board in ["obc", "OBC"]:
        if not (args.bin1 and args.bin2):
            raise argparse.ArgumentError(None, "For board OBC, both -bin1 and -bin2 arguments are required.")
        if args.bin:
            raise argparse.ArgumentError(None, "For board OBC, use -bin1 and -bin2, not -bin.")
    else:
        raise argparse.ArgumentError(None, "Invalid MCU type. Must be 'EXP', or 'OBC'.")
    
    

def main():
    parser = argparse.ArgumentParser(description="FOTA update for STM32 MCU")
    parser.add_argument("-mode", type=str, default="opt", choices=["opt", "seq"], help="Option mode: 'option' for interactive menu, 'seq' for sequential FOTA")
    parser.add_argument("-port", type=str, default="/dev/ttyAMA3", help="Serial port (e.g., COMx or /dev/ttyUSB0)")
    parser.add_argument("-board", type=str, help="Board type (EXP or OBC)")
    
    parser.add_argument("-bin", type=str, help="Single .bin file for EXP board")
    parser.add_argument("-bin1", type=str, help="First .bin file for core M7 of OBC board")
    parser.add_argument("-bin2", type=str, help="Second .bin file for core M4 of OBC board")
    
    parser.add_argument("-meta", type=str, default="1.0.0", help="Single metadata for EXP")
    parser.add_argument("-meta1", type=str, default="1.0.0", help="First metadata file for OBC")
    parser.add_argument("-meta2", type=str, default="1.0.0", help="Second metadata file for OBC")
    try:
        args = parser.parse_args()
        
        # Process based on mode
        if args.mode == "seq":
            # Validate arguments
            validate_fw_args(args)
            process_seq_mode(args)
        elif args.mode == "opt":
            process_opt_mode()
            
    except argparse.ArgumentError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)
        


if __name__ == "__main__":
    main()
