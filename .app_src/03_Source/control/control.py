#!/usr/bin/env python3
"""
BEE-PC1 Control Script
Control script for BEE-PC1 system using MODFSP protocol
"""
import json
import time
import serial
import os
import glob
import threading
import subprocess
from datetime import datetime
from typing import Optional, List, Tuple
from modfsp import MODFSP, MODFSPReturn
from pathlib import Path
from queue import Queue

# Protocol Command IDs
HALT_CMD = 0xFA
HALT_ACK = 0xAA

SEND_TIME_CMD = 0x01
SEND_TIME_ACK = 0x11

RUN_EXPERIMENT_CMD = 0x02
RUN_EXPERIMENT_ACK = 0x12

UPDATE_OBC_CMD = 0x03
UPDATE_OBC_ACK = 0x13

UPDATE_EXP_CMD = 0x04
UPDATE_EXP_ACK = 0x14

CONFIG_CMD_1 = 0xF0
CONFIG_CMD_2 = 0xF1
CONFIG_CMD_3 = 0xF2

CONFIG_ACK_1 = 0xA0
CONFIG_ACK_2 = 0xA1
CONFIG_ACK_3 = 0xA2

GET_LASER_INT_CMD = 0x61
GET_LASER_INT_ACK = 0x71

GET_LASER_EXT_CMD = 0x62
GET_LASER_EXT_ACK = 0x72

SELF_TEST_CMD = 0xCB
SELF_TEST_ACK = 0xCC

FRAME_PAUSE_CMD  = 0xB0
FRAME_PAUSE_ACK  = 0xB1
FRAME_RESUME_CMD = 0xB2
FRAME_RESUME_ACK = 0xB3

# Configuration
SERIAL_BAUDRATE = 115200
SERIAL_TIMEOUT = 2.0
CONNECTION_RETRIES = 3
RETRY_DELAY = 3

CONFIG_DIR = Path.home() / ".app_src/02_ConfigSystem"
SCRIPT_DIR = Path.home() / "Configuration"
converter_script = Path.home() / ".app_src/03_Source/script/script_converter.py"
binarybuild_script = Path.home() / ".app_src/03_Source/script/build_script_to_binary.py"
SELF_LOG_DIR = Path.home() / "Data/logs"

# Predefined serial ports to try
SERIAL_PORTS = ["/dev/ttyAMA3"]

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

class BeePC1Controller:
    def __init__(self):
        self.serial_port: Optional[serial.Serial] = None
        self.modfsp = MODFSP(timeout_ms=2000, debug=False)
        self.response_received = False
        self.expected_response = None
        self.response_lock = threading.Lock()
        self.config_responses = set()
        self.last_ack_payload = None

        # Setup MODFSP callbacks

        self.tx_queue = Queue()
        self.rx_thread = None
        self.tx_thread = None
        self._threads_running = False

        self.setup_modfsp()
        
    def setup_modfsp(self):
        """Setup MODFSP protocol callbacks"""
        self.modfsp.set_read_callback(self.read_byte_callback)
        self.modfsp.set_send_callback(self.send_byte_callback)
        self.modfsp.set_space_callback(self.space_callback)
        
        # Register response handlers
        self.modfsp.register_command(HALT_ACK, self.handle_halt_ack)
        self.modfsp.register_command(SEND_TIME_ACK, self.handle_time_ack)
        self.modfsp.register_command(RUN_EXPERIMENT_ACK, self.handle_experiment_ack)
        self.modfsp.register_command(UPDATE_OBC_ACK, self.handle_update_obc_ack)
        self.modfsp.register_command(UPDATE_EXP_ACK, self.handle_update_exp_ack)
        self.modfsp.register_command(CONFIG_ACK_1, self.handle_config_ack_1)
        self.modfsp.register_command(CONFIG_ACK_2, self.handle_config_ack_2)
        self.modfsp.register_command(CONFIG_ACK_3, self.handle_config_ack_3)

        self.modfsp.register_command(FRAME_RESUME_ACK, self.handle_resume_ack)
        self.modfsp.register_command(FRAME_PAUSE_ACK, self.handle_pause_ack)
        self.modfsp.register_command(SELF_TEST_ACK, self.handle_selftest_ack)
        
    def _serial_rx_thread(self):
        """Background thread to continuously process incoming serial data."""
        while self._threads_running:
            try:
                self.modfsp.process()
            except Exception as e:
                print(f"Error in RX thread: {e}")
            time.sleep(0.001) # Prevent high CPU usage

    def _serial_tx_thread(self):
        """Background thread to send data from a queue."""
        while self._threads_running:
            if not self.tx_queue.empty():
                try:
                    cmd_id, payload = self.tx_queue.get()
                    result = self.modfsp.send(cmd_id, payload)
                    if result != MODFSPReturn.OK:
                        print(f"Failed to send command {cmd_id:02X} via TX thread")
                except Exception as e:
                    print(f"Error in TX thread: {e}")
            time.sleep(0.01)

    def _start_threads(self):
        """Starts the RX and TX threads."""
        if not self._threads_running:
            self._threads_running = True
            self.rx_thread = threading.Thread(target=self._serial_rx_thread, daemon=True)
            self.tx_thread = threading.Thread(target=self._serial_tx_thread, daemon=True)
            self.rx_thread.start()
            self.tx_thread.start()
            print("Serial processing threads started.")
            
    def _stop_threads(self):
        """Stops the RX and TX threads."""
        if self._threads_running:
            self._threads_running = False
            if self.rx_thread: self.rx_thread.join(timeout=1)
            if self.tx_thread: self.tx_thread.join(timeout=1)
            print("Serial processing threads stopped.")
    # <<< CHANGE END

    def read_byte_callback(self) -> Tuple[bool, int]:
        """Callback for reading bytes from serial port"""
        if self.serial_port and self.serial_port.in_waiting > 0:
            byte_data = self.serial_port.read(1)
            if byte_data:
                return True, byte_data[0]
        return False, 0
    
    def send_byte_callback(self, byte: int):
        """Callback for sending bytes to serial port"""
        if self.serial_port:
            self.serial_port.write(bytes([byte]))
    
    def space_callback(self) -> int:
        """Callback for checking available space"""
        return 2048  # Assume we have enough space
    
    def handle_halt_ack(self, payload: bytes):
        """Handle HALT acknowledgment"""
        with self.response_lock:
            if self.expected_response == HALT_ACK:
                self.response_received = True
                print("HALT ACK received")
    
    def handle_time_ack(self, payload: bytes):
        """Handle time sync acknowledgment"""
        with self.response_lock:
            if self.expected_response == SEND_TIME_ACK:
                self.response_received = True
                self.last_ack_payload = payload if payload else b''
                print("Time sync successful")
    
    def handle_experiment_ack(self, payload: bytes):
        """Handle experiment start acknowledgment"""
        with self.response_lock:
            if self.expected_response == RUN_EXPERIMENT_ACK:
                self.response_received = True
                print("Experiment start successful")
    
    def handle_update_obc_ack(self, payload: bytes):
        """Handle OBC update acknowledgment"""
        with self.response_lock:
            if self.expected_response == UPDATE_OBC_ACK:
                self.response_received = True
                print("OBC update successful")
    
    def handle_update_exp_ack(self, payload: bytes):
        """Handle EXP update acknowledgment"""
        with self.response_lock:
            if self.expected_response == UPDATE_EXP_ACK:
                self.response_received = True
                print("EXP update successful")
    
    def handle_config_ack_1(self, payload: bytes):
        """Handle config command 1 acknowledgment"""
        with self.response_lock:
            self.config_responses.add(CONFIG_ACK_1)
            print("Config response 1 received")
    
    def handle_config_ack_2(self, payload: bytes):
        """Handle config command 2 acknowledgment"""
        with self.response_lock:
            self.config_responses.add(CONFIG_ACK_2)
            print("Config response 2 received")
    
    def handle_config_ack_3(self, payload: bytes):
        """Handle config command 3 acknowledgment"""
        with self.response_lock:
            self.config_responses.add(CONFIG_ACK_3)
            print("Config response 3 received")

    def handle_selftest_ack(self, payload: bytes):
        with self.response_lock:
            if self.expected_response == SELF_TEST_ACK:
                self.response_received = True
                self.last_ack_payload = payload  
                # print(f"SELF_TEST - ACK (payload={payload.hex().upper()})")


    def handle_resume_ack(self, payload: bytes):
        """Handle time sync acknowledgment"""
        with self.response_lock:
            if self.expected_response == FRAME_RESUME_ACK:
                self.response_received = True
                print("Resume! - ACK")


    def handle_pause_ack(self, payload: bytes):
        """Handle pause acknowledgment"""
        with self.response_lock:
            if self.expected_response == FRAME_PAUSE_ACK:
                self.response_received = True
                self.last_ack_payload = payload if payload else b''
                print("Paused! - ACK")

    
    def find_serial_port(self) -> Optional[str]:
        """Find available serial port from predefined list"""
        for port in SERIAL_PORTS:
            try:
                print(f"Trying port: {port}")
                test_serial = serial.Serial(port, SERIAL_BAUDRATE, timeout=3)
                test_serial.close()
                print(f"Port {port} is available")
                return port
            except (serial.SerialException, PermissionError, OSError) as e:
                print(f"Port {port} failed: {e}")
                continue
        return None
    
    def connect_serial(self) -> bool:
        """Connect to serial port with retries"""
        for attempt in range(CONNECTION_RETRIES):
            print(f"Attempting to connect to serial port (attempt {attempt + 1}/{CONNECTION_RETRIES})...")
            
            port = self.find_serial_port()
            if not port:
                print("No serial port found")
                if attempt < CONNECTION_RETRIES - 1:
                    print(f"Retrying in {RETRY_DELAY} seconds...")
                    time.sleep(RETRY_DELAY)
                continue
            
            try:
                self.serial_port = serial.Serial(
                    port, 
                    SERIAL_BAUDRATE, 
                    timeout=SERIAL_TIMEOUT
                )
                print(f"Connected to {port}")
                return True
                
            except serial.SerialException as e:
                print(f"Failed to connect to {port}: {e}")
                if attempt < CONNECTION_RETRIES - 1:
                    print(f"Retrying in {RETRY_DELAY} seconds...")
                    time.sleep(RETRY_DELAY)
        
        print("Failed to connect to serial port after all attempts")
        return False
    
    def send_frame_and_wait(self, cmd_id: int, payload: bytes = b'', 
                            expected_ack: int = None, timeout: float = 3.5) -> Optional[bytes]:
        with self.response_lock:
            self.response_received = False
            self.expected_response = expected_ack
            self.last_ack_payload = None

        # Put the command in the queue for the TX thread to send
        self.tx_queue.put((cmd_id, payload))

        start_time = time.time()
        while time.time() - start_time < timeout:
            # The background RX thread is calling self.modfsp.process()
            # We just need to wait for the response_received flag
            with self.response_lock:
                if self.response_received:
                    # In the handle_..._ack functions, make sure to set last_ack_payload
                    # to a non-None value (like b'') to indicate success.
                    return self.last_ack_payload
            time.sleep(0.01)

        print(f"Timeout waiting for response to command {cmd_id:02X}")
        return None
    
    def init_sequence(self) -> bool:
        """Perform initialization sequence"""
        print("Starting initialization sequence...")
        
        halt_success = False
        for i in range(3):
            print(f"Sending Pause! command {i + 1}/3...")
            # Set a non-None value in handle_pause_ack for this to work
            if self.send_frame_and_wait(FRAME_PAUSE_CMD, b'', FRAME_PAUSE_ACK) is not None:
                halt_success = True
                break
            time.sleep(0.5)
        
        
        if halt_success:
            print("Link established successfully!")
            return True
        else:
            print("Failed to establish link")
            # return False
            return True
    
    def sync_time(self):
        """Sync system time to device"""
        now = datetime.now()
        
        # Pack time as 6 bytes: HH, MM, SS, DD, MM, YY
        time_data = bytes([
            now.hour,
            now.minute, 
            now.second,
            now.day,
            now.month,
            now.year % 100  # YY (years since 2000)
        ])
        
        print(f"Syncing time: {now.strftime('%H:%M:%S %d/%m/%Y')}")
        
        if self.send_frame_and_wait(SEND_TIME_CMD, time_data, SEND_TIME_ACK) is not None:
            print("OK!")
        else:
            print("Time sync failed!")

    def self_test_test_function(self):
        data_trans = bytes([
            0x01,
            5, 
            50
        ])
        print(f"SEND TEST FUNCTION")
        
        if self.send_frame_and_wait(SELF_TEST_CMD, data_trans, SELF_TEST_ACK):
            print("OK!")
        else:
            print("FAIL!")


    def verify_config(self):
        """Allow user to select a JSON config file and run two conversion steps"""
        search_dir = SCRIPT_DIR

        # Find all JSON files in the directory
        json_files = glob.glob(os.path.join(search_dir, "*.json"))
        if not json_files:
            print("No .json files found in configuration directory.")
            return

        # Sort by newest modified time
        json_files.sort(key=os.path.getmtime, reverse=True)
        latest_file = json_files[0]

        print("\nFound JSON configuration files:")
        for i, file in enumerate(json_files, start=1):
            print(f"{i}. {os.path.basename(file)}")
        print(f"\nRecommended: Use the latest file: {os.path.basename(latest_file)}")

        # Ask user for selection
        try:
            choice = input(f"\nUse the latest file ({os.path.basename(latest_file)})? (1 = Yes, 2 = Choose another): ")
            if choice == "1":
                selected = latest_file
            elif choice == "2":
                index = int(input("Enter the number of the file to use: "))
                if 1 <= index <= len(json_files):
                    selected = json_files[index - 1]
                else:
                    print("Invalid selection.")
                    return
            else:
                print("Invalid input.")
                return
        except Exception as e:
            print(f"Error during selection: {e}")
            return
            
        # Step 1: Run converter.py
        print(f"\nConverting JSON config: {os.path.basename(selected)}")
        try:
            result = subprocess.run(
                [
                    "python3", str(converter_script),
                    "-f", selected,
                ],
                capture_output=True,
                text=True
            )

            print("\nStep 1 Output:")
            print(result.stdout)
            if result.returncode != 0:
                print("\nStep 1 Failed with errors:")
                print(result.stderr)
                return
            else:
                print("Step 1 completed successfully.")
        except Exception as e:
            print(f"Failed to run converter.py: {e}")
            return

        # Step 2: Run build_script_to_binary.py
        print(f"\nBuilding binary...")
        try:
            result2 = subprocess.run(
                [
                    "python3", str(binarybuild_script),
                    "--version", "1"
                ],
                capture_output=True,
                text=True
            )

            print("\nStep 2 Output:")
            print(result2.stdout)
            if result2.returncode != 0:
                print("\nStep 2 Failed with errors:")
                print(result2.stderr)
            else:
                print(f"Step 2 completed successfully.")
        except Exception as e:
            print(f"Failed to run binary builder script: {e}")

        # Step 3: Run build_script_to_binary.py

    def self_check_hard_config(self):
        """Perform self-check by sending SELF_TEST_CMD with type, intensity, and position"""
        print("Starting self-check hard-config...")
        log_path = os.path.join(SELF_LOG_DIR, "selftest.log")

        def log(msg):
            print(msg)
            with open(log_path, "a") as f:
                f.write(f"{datetime.now()} - {msg}\n")

        # === Internal Laser ===
        int_file = os.path.join(CONFIG_DIR, "int_laser.json")
        try:
            with open(int_file, "r") as f:
                int_sequences = json.load(f)
        except Exception as e:
            log(f"ERROR: Cannot read int_laser.json - {e}")
            return

        for item in int_sequences:
            index = item.get("index", "?")
            intensity = int(item.get("ld_current", 0))
            position = int(item.get("ld_pd_id", 0))
            payload = bytes([0x00, intensity, position])  # type=0 for internal

            print(f"[INT][#{index}] Testing laser (intensity={intensity}, position={position})")

            ack = self.send_frame_and_wait(SELF_TEST_CMD, payload, SELF_TEST_ACK, timeout=3.0)
            if ack:
                if len(ack) >= 2:
                    value_hex = (ack[1] << 8) | ack[0]
                    value_ma = value_hex
                    log(f"[INT][#{index}] Result: {value_ma} mA")
                    log(f"[INT][#{index}] Test successful - Current: {value_ma} mA")
                    log("----------------------------------------------------")

                else:
                    log(f"[INT][#{index}] Invalid response")
                    log(f"[INT][#{index}] Invalid ACK payload")
                    log("----------------------------------------------------")
            else:
                log(f"[INT][#{index}] No response")
                log(f"[INT][#{index}] Timeout or no ACK")
                log("----------------------------------------------------")

        # === External Laser ===
        ext_file = os.path.join(CONFIG_DIR, "ext_laser.json")
        try:
            with open(ext_file, "r") as f:
                ext_sequences = json.load(f)
        except Exception as e:
            log(f"ERROR: Cannot read ext_laser.json - {e}")
            return

        for item in ext_sequences:
            index = item.get("index", "?")
            intensity = int(item.get("ld_current", 0))
            ld_ids = item.get("ld_id", [])

            if not isinstance(ld_ids, list):
                ld_ids = [ld_ids]

            for ld in ld_ids:
                position = 1 << (int(ld) - 1)
                payload = bytes([0x01, intensity, position])

                print(f"[EXT][#{index}] Testing laser (ld_id={ld}, intensity={intensity}, bitmask={position:08b})")

                ack = self.send_frame_and_wait(SELF_TEST_CMD, payload, SELF_TEST_ACK, timeout=3.0)
                if ack:
                    if len(ack) >= 2:
                        value_hex = (ack[1] << 8) | ack[0]
                        value_ma = value_hex
                        log(f"[EXT][#{index}][ld_id={ld}] Result: {value_ma} mA")
                        log(f"[EXT][#{index}][ld_id={ld}] Test successful - Current: {value_ma} mA")
                        log("----------------------------------------------------")
                    else:
                        log(f"[EXT][#{index}][ld_id={ld}] Invalid response/ACK payload")
                        log("----------------------------------------------------")
                else:
                    log(f"[EXT][#{index}][ld_id={ld}] No response (Timeout or no ACK)")
                    log("----------------------------------------------------")





    def show_dir_for_test(sefl):
        print(f"[DEBUG] CONFIG_DIR is {CONFIG_DIR}")
        print(f"[DEBUG] Current working directory: {os.getcwd()}")

    def find_config_files(self) -> List[str]:
        """Find configuration files"""
        # Find epoch_time_config.bin files
        epoch_files = glob.glob(os.path.join(CONFIG_DIR, "*_config.bin"))
        
        # Find other .bin files
        all_bin_files = glob.glob(os.path.join(CONFIG_DIR, "*.bin"))
        other_files = [f for f in all_bin_files if f not in epoch_files]
        
        return epoch_files, other_files
    
    def get_latest_config_file(self, epoch_files: List[str]) -> Optional[str]:
        """Get the latest configuration file based on epoch time"""
        if not epoch_files:
            return None
        
        latest_file = None
        latest_time = 0
        
        for file_path in epoch_files:
            filename = os.path.basename(file_path)
            try:
                # Extract epoch time from filename
                epoch_str = filename.split('_')[0]
                epoch_time = int(epoch_str)
                
                if epoch_time > latest_time:
                    latest_time = epoch_time
                    latest_file = file_path
            except (ValueError, IndexError):
                continue
        
        return latest_file
    
    def send_config_file(self, file_path: str) -> bool:
        """Send configuration file to device"""
        try:
            with open(file_path, 'rb') as f:
                data = f.read()
            
            print(f"Sending configuration file: {os.path.basename(file_path)} ({len(data)} bytes)")
            
            # Reset config responses
            with self.response_lock:
                self.config_responses.clear()
            
            # Send raw binary data (contains F0, F1, F2 frames)
            if self.serial_port:
                self.serial_port.write(data)
            
            # Wait for all three responses
            timeout = 10.0
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                self.modfsp.process()
                
                with self.response_lock:
                    if len(self.config_responses) >= 3:
                        expected_responses = {CONFIG_ACK_1, CONFIG_ACK_2, CONFIG_ACK_3}
                        if self.config_responses >= expected_responses:
                            print("All configuration responses received!")
                            return True
                
                time.sleep(0.01)
            
            print("Timeout waiting for configuration responses")
            return False
            
        except FileNotFoundError:
            print(f"Configuration file not found: {file_path}")
            return False
        except Exception as e:
            print(f"Error sending configuration file: {e}")
            return False
    
    def update_background_config(self):
        """Update background configuration (.bin file starting with 'background')"""
        background_files = glob.glob(os.path.join(CONFIG_DIR, "background*.bin"))
        if not background_files:
            print("No background*.bin files found")
            return
        self._select_and_send(background_files)

    def update_experiment_config(self):
        """Update experiment configuration (.bin file starting with 'experiment')"""
        experiment_files = glob.glob(os.path.join(CONFIG_DIR, "experiment*.bin"))
        if not experiment_files:
            print("No experiment*.bin files found")
            return
        self._select_and_send(experiment_files)

    def _select_and_send(self, files: List[str]):
        """Helper: let user select file from list"""
        print("Available configuration files:")
        for i, file_path in enumerate(files):
            print(f"{i + 1}. {os.path.basename(file_path)}")
        print(f"{len(files) + 1}. Quit")

        try:
            choice = int(input("Choose file: "))
            if 1 <= choice <= len(files):
                selected_file = files[choice - 1]
                if self.send_config_file(selected_file):
                    print("Configuration update successful!")
                else:
                    print("Configuration update failed!")
            elif choice == len(files) + 1:
                print("Cancelled")
            else:
                print("Invalid choice")
        except ValueError:
            print("Invalid input")

    
    def select_config_file(self, files: List[str]):
        """Select configuration file from list"""
        if not files:
            print("No files available")
            return
        
        print("Available files:")
        for i, file_path in enumerate(files):
            print(f"{i + 1}. {os.path.basename(file_path)}")
        print(f"{len(files) + 1}. Quit")
        
        try:
            choice = int(input("Choose file: "))
            if 1 <= choice <= len(files):
                selected_file = files[choice - 1]
                if self.send_config_file(selected_file):
                    print("Configuration update successful!")
                else:
                    print("Configuration update failed!")
            elif choice == len(files) + 1:
                print("Cancelled")
            else:
                print("Invalid choice")
        except ValueError:
            print("Invalid input")
    
    def run_experiment(self):
        """Run experiment - sends RUN_EXPERIMENT_CMD with no payload."""
        print("Sending RUN EXPERIMENT command...")
        
        # Send RUN_EXPERIMENT_CMD with an empty payload (b'')
        if self.send_frame_and_wait(RUN_EXPERIMENT_CMD, b'', RUN_EXPERIMENT_ACK):
            print("Experiment command sent successfully! Waiting for device response...")
        else:
            print("Failed to send experiment command or no ACK received!")
    
    def emergency_stop(self):
        """Emergency stop - send 3 HALT commands via the TX queue"""
        print("Emergency stop - sending HALT commands...")
        
        for i in range(3):
            print(f"Queueing HALT {i + 1}/3...")
            # <<< CHANGE START: Use the queue instead of direct send
            self.tx_queue.put((HALT_CMD, b''))
            # <<< CHANGE END
            time.sleep(0.1)
    
    def show_menu(self):
        """Show main menu"""
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print("    ______ _______ ____  ___  _____")
        print("   / __/ //_  __(_) __ \\/ _ )/ ___/")
        print("  _\\ \\/ /__/ / _ / /_/ / _  / /__")
        print(" /___/____/_/ (_)\\____/____/\\___/")
        print("\n========BEE-PC1 Control Menu=======")
        print("1. Sync Time to System [now]")
        print("2. Verify Config (choose .json file)")
        print("3. Self Check Hardware-Config")
        print("4. Load Background Test Script")
        print("5. Update Experiment Configuration")
        # print("5. Run Experiment")
        print("6. Emergency Stop")
        print("---")
        print("7. Quit")
        print("-------------------------------------")
        
        choice = input("-> Choose option: ")
        return choice
    
    def run(self):
        """Main application loop"""
        # Connect to serial port
        if not self.connect_serial():
            print("Error: Failed to connect to serial port")
            return
        
        self._start_threads()
        
        # Perform initialization sequence
        if not self.init_sequence():
            print("Error: Failed to initialize connection")
            return
        
        # Main menu loop
        try:
            while True:
                choice = self.show_menu()
                
                if choice == "1":
                    self.sync_time()
                elif choice == "2":
                    self.verify_config()
                elif choice == "3":
                    self.self_check_hard_config()
                elif choice == "4":
                    self.update_background_config()
                elif choice == "5":
                    self.update_experiment_config()
                # elif choice == "5":
                #     self.run_experiment()
                elif choice == "6":
                    self.emergency_stop()
                elif choice == "7":
                    print("Quit!")
                    break
                elif choice == "9989":
                    self.self_test_test_function()
                elif choice == "9988":
                    self.show_dir_for_test()
                else:
                    print("Invalid choice. Please try again.")

                
        except KeyboardInterrupt:
            print("\nInterrupted by user")
        finally:
            # <<< CHANGE START: Stop threads and close port
            self._stop_threads()
            if self.serial_port and self.serial_port.is_open:
                self.serial_port.close()
                print("Serial port closed")

if __name__ == "__main__":
    controller = BeePC1Controller()
    # To ensure cleanup happens, let's call the stop method on exit
    try:
        controller.run()
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    finally:
        # This ensures threads are stopped even if run() crashes
        controller._stop_threads()
        print("Application finished.")
