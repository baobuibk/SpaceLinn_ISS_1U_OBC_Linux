#!/usr/bin/env python3
import json
import struct
import argparse
import logging
import sys
from typing import Dict, Any, List, Tuple
from datetime import datetime
from pathlib import Path

BUILDBINARY_LOG_DIR_FILE = Path.home() / "Data/logs/build_binary.log"
CONFIG_DIR = Path.home() / ".app_src/02_ConfigSystem"

# Setup logging
def setup_logging(verbose=False):
    level = logging.DEBUG if verbose else logging.INFO
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    
    file_handler = logging.FileHandler(BUILDBINARY_LOG_DIR_FILE, encoding='utf-8')
    file_handler.setFormatter(formatter)
    
    logger = logging.getLogger()
    logger.setLevel(level)
    logger.handlers.clear()
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    return logger

# Magic numbers and constants
MAGIC_HEADER = 0xC0DEDEAD
MAGIC_STEP = 0xDEADBEEF
MAX_PARAM_SIZE = 71

# MODFSP Frame IDs
FRAME_ID_INIT = 0xF0
FRAME_ID_DLS_ROUTINE = 0xF1
FRAME_ID_CAM_ROUTINE = 0xF2

# MODFSP Constants
SFP_START1_BYTE = 0xC0
SFP_START2_BYTE = 0xDE
SFP_STOP1_BYTE = 0xDA
SFP_STOP2_BYTE = 0xED

# Parameter types
PARAM_TYPE_UINT8 = 0x01
PARAM_TYPE_UINT16 = 0x02
PARAM_TYPE_UINT32 = 0x03
PARAM_TYPE_FLOAT = 0x04
PARAM_TYPE_STRING = 0x05

# Action IDs mapping
ACTION_IDS = {
    'halt': 0xFA,
    'delay': 0xFB,
    'jmp': 0xFC,
    'please_reset': 0xFD,

    'clear_profile': 0xFF,
    'test_connection': 0x00,

    # INIT actions
    'set_system': 0x01,
    'set_rtc': 0x02,
    'set_ntc_control': 0x03,
    'set_temp_profile': 0x04,
    'start_temp_profile': 0x05,
    'stop_temp_profile': 0x06,
    'set_override_tec_profile': 0x07,
    'start_override_tec_profile': 0x08,
    'stop_override_tec_profile': 0x09,
    'set_pda_profile': 0x0A,
    'set_camera_profile': 0x0B,

    # DLS_ROUTINE actions
    'set_dls_interval': 0x11,
    'set_laser_intensity': 0x12,
    'set_position': 0x13,
    'start_sample_cycle': 0x14,
    'obc_get_sample': 0x15,

    # CAM_ROUTINE actions
    'set_camera_interval': 0x21,
    'set_ext_laser_intensity': 0x22,
    'turn_on_ext_laser': 0x23,
    'set_camera_position': 0x24,
    'take_img_with_timeout': 0x25,
    'turn_off_ext_laser': 0x26
}

# Parameter definitions for each action
PARAM_DEFINITIONS = {
    'halt': [],
    'delay': [('duration', PARAM_TYPE_UINT32)],
    'jmp': [('step_id', PARAM_TYPE_UINT16)],
    'restart': [],
    'test_connection': [('value', PARAM_TYPE_UINT32)],

    'clear_profile': [
        ('run_limit_count', PARAM_TYPE_UINT16)
    ],
    'set_system': [
        ('start', PARAM_TYPE_UINT32),        # FF FF FF FF for 'now', FF HH MM SS for time
        ('release_time', PARAM_TYPE_UINT32), # FF HH MM SS format
        ('lockin_time', PARAM_TYPE_UINT32),  # FF HH MM SS format
        ('dls_interval', PARAM_TYPE_UINT32), # seconds
        ('cam_interval', PARAM_TYPE_UINT32)  # seconds
    ],
    'set_rtc': [
        ('source', PARAM_TYPE_UINT8),
        ('interval', PARAM_TYPE_UINT32)
    ],
    'set_ntc_control': [
        ('enable_index_0', PARAM_TYPE_UINT8),
        ('enable_index_1', PARAM_TYPE_UINT8),
        ('enable_index_2', PARAM_TYPE_UINT8),
        ('enable_index_3', PARAM_TYPE_UINT8),
        ('enable_index_4', PARAM_TYPE_UINT8),
        ('enable_index_5', PARAM_TYPE_UINT8),
        ('enable_index_6', PARAM_TYPE_UINT8),
        ('enable_index_7', PARAM_TYPE_UINT8)
    ],
    'set_temp_profile': [
        ('target_temp', PARAM_TYPE_UINT16),
        ('min_temp', PARAM_TYPE_UINT16),
        ('max_temp', PARAM_TYPE_UINT16),
        ('ntc_primary', PARAM_TYPE_UINT8),
        ('ntc_secondary', PARAM_TYPE_UINT8),
        ('tec_actuator_num', PARAM_TYPE_UINT8),
        ('heater_actuator_num', PARAM_TYPE_UINT8),
        ('tec_vol', PARAM_TYPE_UINT16),
        ('heater_duty', PARAM_TYPE_UINT8),
        ('auto_recover', PARAM_TYPE_UINT8)
    ],
    'start_temp_profile': [],
    'stop_temp_profile': [],
    'set_override_tec_profile': [
        ('interval', PARAM_TYPE_UINT16),
        ('tec_override_index', PARAM_TYPE_UINT8),
        ('tec_actuator_vol', PARAM_TYPE_UINT16)
    ],
    'start_override_tec_profile': [],
    'stop_override_tec_profile': [],
    'set_pda_profile': [
        ('sampling_rate', PARAM_TYPE_UINT32),
        ('pre_laser_period', PARAM_TYPE_UINT16),
        ('in_sample_period', PARAM_TYPE_UINT16),
        ('pos_laser_period', PARAM_TYPE_UINT16)
    ],
    'set_camera_profile': [
        ('resolution', PARAM_TYPE_UINT8),  # 0=Low, 1=Half, 2=Full
        ('compress_enable', PARAM_TYPE_UINT8),
        ('exposure', PARAM_TYPE_UINT16),
        ('gain', PARAM_TYPE_UINT16)
    ],
    'set_dls_interval': [
        ('interval', PARAM_TYPE_UINT32)
    ],    
    'set_laser_intensity': [('intensity', PARAM_TYPE_UINT8)],
    'set_position': [('position', PARAM_TYPE_UINT8)],
    'start_sample_cycle': [],
    'obc_get_sample': [],
    'set_camera_interval': [
        ('interval', PARAM_TYPE_UINT32)
    ],
    'set_ext_laser_intensity': [('intensity', PARAM_TYPE_UINT8)],
    'turn_on_ext_laser': [('position', PARAM_TYPE_UINT8)],
    'set_camera_position': [('cis_id', PARAM_TYPE_UINT8)],
    'turn_off_ext_laser': [],
    'take_img_with_timeout': []
}

def crc16_xmodem(data: bytes) -> int:
    """Calculate CRC16 XMODEM checksum"""
    crc = 0x0000
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc

def parse_time_string(time_str: str) -> int:
    """Parse time string to FF HH MM SS format"""
    logger = logging.getLogger(__name__)
    
    if time_str.lower() in ['now', '']:
        result = 0xFFFFFFFF
        logger.debug(f"Time string '{time_str}' -> 0x{result:08X} (now)")
        return result
    
    try:
        # Parse HH:MM:SS format
        parts = time_str.split(':')
        if len(parts) != 3:
            raise ValueError(f"Invalid time format: {time_str}, expected HH:MM:SS")
        
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = int(parts[2])
        
        # Validate ranges
        if not (0 <= hours <= 23):
            raise ValueError(f"Hours out of range: {hours}")
        if not (0 <= minutes <= 59):
            raise ValueError(f"Minutes out of range: {minutes}")
        if not (0 <= seconds <= 59):
            raise ValueError(f"Seconds out of range: {seconds}")
        
        # Build FF HH MM SS format
        result = (0xFF << 24) | (hours << 16) | (minutes << 8) | seconds
        logger.debug(f"Time string '{time_str}' -> 0x{result:08X} (FF {hours:02X} {minutes:02X} {seconds:02X})")
        return result
        
    except Exception as e:
        logger.error(f"Failed to parse time string '{time_str}': {e}")
        # Default to 'now' on error
        return 0xFFFFFFFF

def convert_array_to_bitmask(array_values: List[int]) -> int:
    """Convert array of indices to bit mask"""
    logger = logging.getLogger(__name__)
    
    if not array_values:
        return 0
    
    bitmask = 0
    for index in array_values:
        if 0 <= index <= 7:  # Support up to 8 actuators (0-7)
            bitmask |= (1 << index)
        else:
            logger.warning(f"Index {index} out of range (0-7), skipping")
    
    logger.debug(f"Converted array {array_values} to bitmask: 0x{bitmask:02X} (0b{bitmask:08b})")
    return bitmask

def convert_parameter_value(param_name: str, param_type: int, value: Any) -> Any:
    """Convert parameter values to appropriate types"""
    logger = logging.getLogger(__name__)
    
    logger.debug(f"Converting parameter: {param_name} = {value} (target type: {param_type})")
    
    try:
        if param_name == 'source' and isinstance(value, str):
            # Convert RTC source string to number
            source_map = {'obc_rtc': 0, 'nanode_ntp': 1}
            result = source_map.get(value, 0)
            logger.debug(f"Converted RTC source '{value}' -> {result}")
            return result
        elif param_name == 'resolution' and isinstance(value, str):
            # Convert camera resolution string to number
            res_map = {'Low': 0, 'Half': 1, 'Full': 2}
            result = res_map.get(value, 2)  # Default to Full
            logger.debug(f"Converted resolution '{value}' -> {result}")
            return result
        elif param_name in ['start', 'release_time', 'lockin_time'] and isinstance(value, str):
            # Convert time strings to FF HH MM SS format
            result = parse_time_string(value)
            logger.debug(f"Converted time string '{param_name}': '{value}' -> 0x{result:08X}")
            return result
        elif param_name in ['tec_actuator_num', 'heater_actuator_num'] and isinstance(value, list):
            # Convert actuator arrays to bit masks
            result = convert_array_to_bitmask(value)
            logger.debug(f"Converted actuator array '{param_name}': {value} -> 0x{result:02X}")
            return result
        elif param_name.startswith('position') and isinstance(value, str):
            result = int(value)
            logger.debug(f"Converted position '{value}' -> {result}")
            return result
        elif param_name.startswith('cis_id') and isinstance(value, str):
            result = int(value)
            logger.debug(f"Converted cis_id '{value}' -> {result}")
            return result
        elif isinstance(value, list):
            # Handle other array parameters
            result = len(value) if value else 0
            logger.debug(f"Converted array '{param_name}' length: {result}")
            return result
        else:
            # Direct conversion
            if param_type == PARAM_TYPE_UINT8:
                result = int(value) & 0xFF
            elif param_type == PARAM_TYPE_UINT16:
                result = int(value) & 0xFFFF
            elif param_type == PARAM_TYPE_UINT32:
                result = int(value) & 0xFFFFFFFF
            else:
                result = value
            
            logger.debug(f"Direct conversion '{param_name}': {value} -> {result}")
            return result
            
    except Exception as e:
        logger.error(f"Error converting parameter {param_name}: {e}")
        logger.error(f"Input value: {value} (type: {type(value)})")
        raise

def encode_parameter_value(param_type: int, value: Any) -> bytes:
    """Encode a single parameter value based on its type"""
    logger = logging.getLogger(__name__)
    
    try:
        if param_type == PARAM_TYPE_UINT8:
            int_val = int(value)
            if not (0 <= int_val <= 255):
                raise ValueError(f"UINT8 value {int_val} out of range (0-255)")
            logger.debug(f"Encoding UINT8: {value} -> {int_val}")
            return struct.pack('<B', int_val)
        elif param_type == PARAM_TYPE_UINT16:
            int_val = int(value)
            if not (0 <= int_val <= 65535):
                raise ValueError(f"UINT16 value {int_val} out of range (0-65535)")
            logger.debug(f"Encoding UINT16: {value} -> {int_val}")
            return struct.pack('<H', int_val)
        elif param_type == PARAM_TYPE_UINT32:
            int_val = int(value)
            if not (0 <= int_val <= 4294967295):
                raise ValueError(f"UINT32 value {int_val} out of range (0-4294967295)")
            logger.debug(f"Encoding UINT32: {value} -> {int_val}")
            return struct.pack('<I', int_val)
        elif param_type == PARAM_TYPE_FLOAT:
            float_val = float(value)
            logger.debug(f"Encoding FLOAT: {value} -> {float_val}")
            return struct.pack('<f', float_val)
        elif param_type == PARAM_TYPE_STRING:
            if isinstance(value, str):
                encoded = value.encode('utf-8')
                logger.debug(f"Encoding STRING: '{value}' -> {len(encoded)} bytes")
                return encoded
            else:
                encoded = bytes(value)
                logger.debug(f"Encoding BYTES: {value} -> {len(encoded)} bytes")
                return encoded
        else:
            raise ValueError(f"Unknown parameter type: {param_type}")
    except Exception as e:
        logger.error(f"Failed to encode parameter: type={param_type}, value={value}, error={e}")
        raise

def encode_parameters(action: str, parameters: Dict[str, Any]) -> bytes:
    """Encode parameters for a specific action into TLV format"""
    logger = logging.getLogger(__name__)
    
    if action not in PARAM_DEFINITIONS:
        raise ValueError(f"Unknown action: {action}")
    
    param_defs = PARAM_DEFINITIONS[action]
    logger.debug(f"Encoding parameters for action '{action}' with {len(param_defs)} parameter definitions")
    
    if not param_defs:
        # No parameters for this action
        logger.debug(f"No parameters for action '{action}', returning single zero byte")
        return bytes([0])  # num_fields = 0
    
    # Build TLV buffer
    tlv_buffer = bytearray()
    tlv_buffer.append(len(param_defs))  # num_fields
    logger.debug(f"Starting TLV encoding with {len(param_defs)} fields")
    
    for i, (param_name, param_type) in enumerate(param_defs):
        logger.debug(f"Processing parameter {i+1}/{len(param_defs)}: {param_name} (type {param_type})")
        
        if param_name not in parameters:
            logger.error(f"Missing parameter '{param_name}' for action '{action}'. Available: {list(parameters.keys())}")
            raise ValueError(f"Missing parameter '{param_name}' for action '{action}'")
        
        value = parameters[param_name]
        logger.debug(f"Raw parameter value: {param_name} = {value} (type: {type(value)})")
        
        try:
            # Convert parameter value if needed
            converted_value = convert_parameter_value(param_name, param_type, value)
            logger.debug(f"Converted value: {param_name} = {converted_value}")
            
            encoded_value = encode_parameter_value(param_type, converted_value)
            logger.debug(f"Encoded value: {param_name} -> {len(encoded_value)} bytes: {encoded_value.hex()}")
            
            # Add TLV entry
            tlv_buffer.append(param_type)  # Type
            tlv_buffer.append(len(encoded_value))  # Length
            tlv_buffer.extend(encoded_value)  # Value
            
            logger.debug(f"Added TLV entry: T={param_type}, L={len(encoded_value)}, V={encoded_value.hex()}")
            
        except Exception as e:
            logger.error(f"Failed to encode parameter '{param_name}': {e}")
            logger.error(f"Parameter details: name={param_name}, type={param_type}, value={value}")
            raise
    
    logger.debug(f"TLV encoding complete: {len(tlv_buffer)} total bytes")
    return bytes(tlv_buffer)

def create_step_binary(step_idx: int, step: Dict[str, Any]) -> bytes:
    """Create binary representation of a single step"""
    logger = logging.getLogger(__name__)
    
    action = step['action']
    parameters = step.get('parameters', {})
    
    logger.info(f"Processing step {step_idx + 1}: {action}")
    logger.debug(f"Step parameters: {parameters}")
    
    if action not in ACTION_IDS:
        logger.error(f"Unknown action: {action}")
        raise ValueError(f"Unknown action: {action}")
    
    action_id = ACTION_IDS[action]
    logger.debug(f"Action ID: 0x{action_id:02X}")
    
    try:
        param_buffer = encode_parameters(action, parameters)
        logger.debug(f"Parameter buffer created: {len(param_buffer)} bytes")
        
        if len(param_buffer) > (MAX_PARAM_SIZE - 7):
            logger.error(f"Step {step_idx + 1} parameters too large: {len(param_buffer)} bytes (max: {MAX_PARAM_SIZE - 7})")
            raise ValueError(f"Step {step_idx + 1} parameters too large: {len(param_buffer)} bytes")
        
        # Step header: <I (4) H (2) B (1) B (1)> = 8 bytes
        step_header = struct.pack('<IHBB', MAGIC_STEP, step_idx + 1, action_id, len(param_buffer))
        
        result = step_header + param_buffer
        logger.info(f"Step {step_idx + 1} binary created: {len(result)} bytes total")
        
        return result
        
    except Exception as e:
        logger.error(f"Failed to create binary for step {step_idx + 1}: {e}")
        logger.error(f"Step details: action={action}, parameters={parameters}")
        raise

def create_section_binary(section_name: str, steps: List[Dict[str, Any]], version: int = 1) -> bytes:
    """Create binary representation of a section (init/dls_routine/cam_routine)"""
    logger = logging.getLogger(__name__)
    
    if len(steps) > 200:
        raise ValueError(f"Too many steps in {section_name}: {len(steps)} (max: 200)")
    
    logger.info(f"Creating binary for {section_name} section with {len(steps)} steps")
    
    buffer = bytearray()
    # Reserve 10 bytes for header (will fill later)
    buffer.extend(b'\x00' * 10)
    
    for step_idx, step in enumerate(steps):
        step_binary = create_step_binary(step_idx, step)
        buffer.extend(step_binary)
    
    # Fill header (10 bytes)
    header_data = struct.pack('<IHH', MAGIC_HEADER, version, len(steps))  # 8 bytes
    header_crc = crc16_xmodem(header_data)
    header_complete = header_data + struct.pack('<H', header_crc)  # total 10 bytes
    
    buffer[0:10] = header_complete
    
    # Compute total CRC (excluding last 2 bytes)
    total_crc = crc16_xmodem(buffer)
    buffer.extend(struct.pack('<H', total_crc))
    
    logger.info(f"{section_name} binary created: {len(buffer)} bytes")
    return bytes(buffer)

def create_modfsp_frame(frame_id: int, data: bytes) -> bytes:
    """Create MODFSP frame with given ID and data"""
    logger = logging.getLogger(__name__)
    
    data_len = len(data)
    if data_len > 65535:
        raise ValueError(f"Data too large for MODFSP frame: {data_len} bytes")
    
    # Calculate CRC for ID + LENGTH + DATA
    crc = 0x0000
    
    # CRC for ID
    crc ^= frame_id << 8
    for _ in range(8):
        if crc & 0x8000:
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF
        else:
            crc = (crc << 1) & 0xFFFF
    
    # CRC for LENGTH (low byte first, then high byte)
    len_low = data_len & 0xFF
    len_high = (data_len >> 8) & 0xFF
    
    crc ^= len_low << 8
    for _ in range(8):
        if crc & 0x8000:
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF
        else:
            crc = (crc << 1) & 0xFFFF
    
    crc ^= len_high << 8
    for _ in range(8):
        if crc & 0x8000:
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF
        else:
            crc = (crc << 1) & 0xFFFF
    
    # CRC for DATA
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    
    # Build frame
    frame = bytearray()
    frame.append(SFP_START1_BYTE)  # 0xC0
    frame.append(SFP_START2_BYTE)  # 0xDE
    frame.append(frame_id)         # Frame ID
    frame.append(len_low)          # Length low byte
    frame.append(len_high)         # Length high byte
    frame.extend(data)             # Data
    frame.append(crc & 0xFF)       # CRC low byte
    frame.append((crc >> 8) & 0xFF) # CRC high byte
    frame.append(SFP_STOP1_BYTE)   # 0xDA
    frame.append(SFP_STOP2_BYTE)   # 0xED
    
    logger.info(f"MODFSP frame created: ID=0x{frame_id:02X}, data_len={data_len}, total_len={len(frame)}")
    return bytes(frame)

def convert_builttostep_to_binary(json_file: str, output_file: str, version: int = 1) -> bool:
    """Convert builttostep JSON to binary format with MODFSP frames"""
    logger = logging.getLogger(__name__)
    
    # Add separator
    separator = "=" * 80
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    separator2 = "[" + "-" * 78 + "]"

    logger.info(separator)
    logger.info(f"BINARY CONVERSION - {current_time}")
    logger.info(f"Input:  {json_file}")
    logger.info(f"Output: {output_file}")
    logger.info(separator2)
    
    try:
        # Read JSON file
        with open(json_file, 'r', encoding='utf-8') as f:
            script_data = json.load(f)
        
        logger.info(f"Successfully loaded JSON from {json_file}")
        
        # Extract sections
        init_steps = script_data.get('init', {}).get('steps', [])
        dls_steps = script_data.get('dls_routine', {}).get('steps', [])
        cam_steps = script_data.get('cam_routine', {}).get('steps', [])
        
        logger.info(f"Found sections: INIT({len(init_steps)}), DLS({len(dls_steps)}), CAM({len(cam_steps)})")
        
        # Create binary data for each section
        sections = [
            ('INIT', FRAME_ID_INIT, init_steps),
            ('DLS_ROUTINE', FRAME_ID_DLS_ROUTINE, dls_steps),
            ('CAM_ROUTINE', FRAME_ID_CAM_ROUTINE, cam_steps)
        ]
        
        final_binary = bytearray()
        
        for section_name, frame_id, steps in sections:
            if not steps:
                logger.warning(f"No steps found in {section_name} section, skipping")
                continue
            
            # Create section binary
            section_binary = create_section_binary(section_name, steps, version)
            
            # Wrap in MODFSP frame
            modfsp_frame = create_modfsp_frame(frame_id, section_binary)
            
            # Append to final binary
            final_binary.extend(modfsp_frame)
        
        # Write binary file
        with open(output_file, 'wb') as f:
            f.write(final_binary)
        
        logger.info(f"Successfully created binary file: {output_file}")
        logger.info(f"Final binary size: {len(final_binary)} bytes")
        
        # Summary
        logger.info("=== CONVERSION SUMMARY ===")
        total_steps = len(init_steps) + len(dls_steps) + len(cam_steps)
        logger.info(f"Total steps processed: {total_steps}")
        logger.info(f"INIT steps: {len(init_steps)}")
        logger.info(f"DLS_ROUTINE steps: {len(dls_steps)}")
        logger.info(f"CAM_ROUTINE steps: {len(cam_steps)}")
        logger.info(f"Binary file size: {len(final_binary)} bytes")
        logger.info("[SUCCESS] Binary conversion completed successfully!")
        
        return True
        
    except Exception as e:
        logger.error(f"Error during conversion: {e}")
        return False

def main():
    """Main function with command line argument parsing"""
    parser = argparse.ArgumentParser(description="Convert builttostep JSON to binary format with MODFSP frames")
    parser.add_argument(
        "-f", "--file", 
        default="beepc1_step.json",
        help="Input builttostep JSON file (default: beepc1_step.json)"
    )
    parser.add_argument(
        "-o", "--output",
        default="bee_pc1.bin",
        help="Output binary file (default: bee_pc1.bin)"
    )
    parser.add_argument(
        "--version", 
        type=int, 
        default=1, 
        help="Script version (default: 1)"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    logger = setup_logging(args.verbose)

    # ---- 1: step.json -> bee_pc1.bin ----
    file1 = str(CONFIG_DIR / "beepc1_step.json")
    out1  = str(CONFIG_DIR / "experiment_run.bin")
    success1 = convert_builttostep_to_binary(file1, out1, args.version)

    # ---- 2: background.json -> background_run_.bin ----
    file2 = str(CONFIG_DIR / "beepc1_background.json")
    out2  = str(CONFIG_DIR / "background_run.bin")
    success2 = convert_builttostep_to_binary(file2, out2, args.version)

    if success1 and success2:
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == '__main__':
    main()
