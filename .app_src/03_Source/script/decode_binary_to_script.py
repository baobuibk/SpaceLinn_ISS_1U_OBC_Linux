#!/usr/bin/env python3
import json
import struct
import argparse
import logging
import sys
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime

# Setup logging
def setup_logging(verbose=False):
    level = logging.DEBUG if verbose else logging.INFO
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    
    file_handler = logging.FileHandler('decode_binary.log', encoding='utf-8')
    file_handler.setFormatter(formatter)
    
    logger = logging.getLogger()
    logger.setLevel(level)
    logger.handlers.clear()
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    return logger

# Magic numbers and constants (same as encoding)
MAGIC_HEADER = 0xC0DEDEAD
MAGIC_STEP = 0xDEADBEEF

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

# Reverse mapping: Action ID to action name
ACTION_NAMES = {
    0xFA: 'halt',
    0xFB: 'delay',
    0xFC: 'jmp',
    0xFD: 'please_reset',
    0xFF: 'clear_profile',
    0x00: 'test_connection',

    # INIT actions
    0x01: 'set_system',
    0x02: 'set_rtc',
    0x03: 'set_ntc_control',
    0x04: 'set_temp_profile',
    0x05: 'start_temp_profile',
    0x06: 'stop_temp_profile',
    0x07: 'set_override_tec_profile',
    0x08: 'start_override_tec_profile',
    0x09: 'stop_override_tec_profile',
    0x0A: 'set_pda_profile',
    0x0B: 'set_camera_profile',

    # DLS_ROUTINE actions
    0x11: 'set_dls_interval',
    0x12: 'set_laser_intensity',
    0x13: 'set_position',
    0x14: 'start_sample_cycle',
    0x15: 'obc_get_sample',

    # CAM_ROUTINE actions
    0x21: 'set_camera_interval',
    0x22: 'set_ext_laser_intensity',
    0x23: 'turn_on_ext_laser',
    0x24: 'set_camera_position',
    0x25: 'take_img_with_timeout',
    0x26: 'turn_off_ext_laser'
}

# Parameter definitions for each action (same as encoding)
PARAM_DEFINITIONS = {
    'halt': [],
    'delay': [('duration', PARAM_TYPE_UINT32)],
    'jmp': [('step_id', PARAM_TYPE_UINT16)],
    'restart': [],
    'clear_profile': [
        ('run_limit_count', PARAM_TYPE_UINT16)
    ],
    'test_connection': [('value', PARAM_TYPE_UINT32)],
    
    'set_system': [
        ('start', PARAM_TYPE_UINT32),
        ('release_time', PARAM_TYPE_UINT32),
        ('lockin_time', PARAM_TYPE_UINT32),
        ('dls_interval', PARAM_TYPE_UINT32),
        ('cam_interval', PARAM_TYPE_UINT32)
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
        ('tec_actuator_num', PARAM_TYPE_UINT8),  # Bit mask for TEC actuators
        ('heater_actuator_num', PARAM_TYPE_UINT8),  # Bit mask for heater actuators
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
        ('resolution', PARAM_TYPE_UINT8),
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

def format_time_value(value: int) -> str:
    """Convert FF HH MM SS format back to time string"""
    if value == 0xFFFFFFFF:
        return "now"
    
    # Extract components
    ff_byte = (value >> 24) & 0xFF
    hours = (value >> 16) & 0xFF
    minutes = (value >> 8) & 0xFF
    seconds = value & 0xFF
    
    if ff_byte == 0xFF:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    else:
        # If not FF format, return hex representation
        return f"0x{value:08X}"

def convert_bitmask_to_array(bitmask: int) -> List[int]:
    """Convert bit mask to array of indices"""
    logger = logging.getLogger(__name__)
    
    array_values = []
    for i in range(8):  # Check bits 0-7
        if bitmask & (1 << i):
            array_values.append(i)
    
    logger.debug(f"Converted bitmask 0x{bitmask:02X} (0b{bitmask:08b}) to array: {array_values}")
    return array_values

def convert_bitmask_to_array_ext_laser(bitmask: int) -> List[int]:
    """Convert bit mask to array of ld_id (1-based index)"""
    logger = logging.getLogger(__name__)
    
    array_values = []
    for i in range(8):  # Check bits 0-7
        if bitmask & (1 << i):
            array_values.append(i + 1)   # ld_id b?t d?u t? 1
    
    logger.debug(f"Converted bitmask 0x{bitmask:02X} (0b{bitmask:08b}) to array: {array_values}")
    return array_values

def convert_decoded_value(param_name: str, param_type: int, value: Any) -> Any:
    """Convert decoded parameter values back to readable format"""
    logger = logging.getLogger(__name__)
    
    try:
        if param_name == 'source' and param_type == PARAM_TYPE_UINT8:
            # Convert RTC source number back to string
            source_map = {0: 'obc_rtc', 1: 'nanode_ntp'}
            result = source_map.get(value, f'unknown({value})')
            logger.debug(f"Converted RTC source {value} -> '{result}'")
            return result
        elif param_name == 'resolution' and param_type == PARAM_TYPE_UINT8:
            # Convert camera resolution number back to string
            res_map = {0: 'Low', 1: 'Half', 2: 'Full'}
            result = res_map.get(value, f'unknown({value})')
            logger.debug(f"Converted resolution {value} -> '{result}'")
            return result
        elif param_name in ['start', 'release_time', 'lockin_time'] and param_type == PARAM_TYPE_UINT32:
            # Convert time value back to string
            result = format_time_value(value)
            logger.debug(f"Converted time value 0x{value:08X} -> '{result}'")
            return result
        elif param_name in ['tec_actuator_num', 'heater_actuator_num'] and param_type == PARAM_TYPE_UINT8:
            # Convert bit mask back to array
            result = convert_bitmask_to_array(value)
            logger.debug(f"Converted bitmask 0x{value:02X} -> {result}")
            return result
        elif param_name == 'position' and param_type == PARAM_TYPE_UINT8:
            # Convert bitmask back to array of ld_id
            result = convert_bitmask_to_array_ext_laser(value)
            logger.debug(f"Converted turn_on_ext_laser position {value} -> {result}")
            return result
        else:
            # Direct value
            logger.debug(f"Direct value '{param_name}': {value}")
            return value
            
    except Exception as e:
        logger.error(f"Error converting decoded parameter {param_name}: {e}")
        return value

def decode_parameter_value(param_type: int, data: bytes, offset: int) -> Tuple[Any, int]:
    """Decode a single parameter value based on its type"""
    logger = logging.getLogger(__name__)
    
    try:
        if param_type == PARAM_TYPE_UINT8:
            if offset + 1 > len(data):
                raise ValueError("Not enough data for UINT8")
            value = struct.unpack('<B', data[offset:offset+1])[0]
            logger.debug(f"Decoded UINT8: {value}")
            return value, 1
        elif param_type == PARAM_TYPE_UINT16:
            if offset + 2 > len(data):
                raise ValueError("Not enough data for UINT16")
            value = struct.unpack('<H', data[offset:offset+2])[0]
            logger.debug(f"Decoded UINT16: {value}")
            return value, 2
        elif param_type == PARAM_TYPE_UINT32:
            if offset + 4 > len(data):
                raise ValueError("Not enough data for UINT32")
            value = struct.unpack('<I', data[offset:offset+4])[0]
            logger.debug(f"Decoded UINT32: {value} (0x{value:08X})")
            return value, 4
        elif param_type == PARAM_TYPE_FLOAT:
            if offset + 4 > len(data):
                raise ValueError("Not enough data for FLOAT")
            value = struct.unpack('<f', data[offset:offset+4])[0]
            logger.debug(f"Decoded FLOAT: {value}")
            return value, 4
        elif param_type == PARAM_TYPE_STRING:
            # For string, we need to read the length first
            if offset >= len(data):
                raise ValueError("Not enough data for STRING length")
            # String length should be determined by TLV format
            raise ValueError("STRING parameters should not be used in this format")
        else:
            raise ValueError(f"Unknown parameter type: {param_type}")
    except Exception as e:
        logger.error(f"Failed to decode parameter: type={param_type}, offset={offset}, error={e}")
        raise

def decode_parameters(action: str, data: bytes) -> Dict[str, Any]:
    """Decode parameters for a specific action from TLV format"""
    logger = logging.getLogger(__name__)
    
    if action not in PARAM_DEFINITIONS:
        logger.warning(f"Unknown action: {action}")
        return {}
    
    param_defs = PARAM_DEFINITIONS[action]
    logger.debug(f"Decoding parameters for action '{action}' with {len(param_defs)} parameter definitions")
    
    if not param_defs:
        # No parameters for this action
        logger.debug(f"No parameters expected for action '{action}'")
        return {}
    
    if len(data) == 0:
        logger.warning(f"No parameter data for action '{action}' that expects parameters")
        return {}
    
    # Read number of fields
    if len(data) < 1:
        raise ValueError("Not enough data for num_fields")
    
    num_fields = data[0]
    logger.debug(f"Number of fields in TLV: {num_fields}")
    
    offset = 1
    parameters = {}
    field_index = 0
    
    while offset < len(data) and field_index < len(param_defs):
        if offset + 2 > len(data):
            logger.error(f"Not enough data for TLV header at offset {offset}")
            break
        
        # Read TLV header
        param_type = data[offset]
        length = data[offset + 1]
        offset += 2
        
        logger.debug(f"TLV entry {field_index}: Type={param_type}, Length={length}")
        
        if offset + length > len(data):
            logger.error(f"Not enough data for TLV value: need {length} bytes at offset {offset}")
            break
        
        # Get parameter name from definition
        param_name, expected_type = param_defs[field_index]
        
        if param_type != expected_type:
            logger.warning(f"Parameter type mismatch for '{param_name}': got {param_type}, expected {expected_type}")
        
        # Decode value
        try:
            value_data = data[offset:offset+length]
            logger.debug(f"Decoding parameter '{param_name}': {value_data.hex()}")
            
            # Use expected type for decoding
            if expected_type == PARAM_TYPE_UINT8 and length == 1:
                value = struct.unpack('<B', value_data)[0]
            elif expected_type == PARAM_TYPE_UINT16 and length == 2:
                value = struct.unpack('<H', value_data)[0]
            elif expected_type == PARAM_TYPE_UINT32 and length == 4:
                value = struct.unpack('<I', value_data)[0]
            elif expected_type == PARAM_TYPE_FLOAT and length == 4:
                value = struct.unpack('<f', value_data)[0]
            else:
                logger.warning(f"Unexpected length {length} for type {expected_type}")
                value = int.from_bytes(value_data, 'little')
            
            # Convert to readable format
            converted_value = convert_decoded_value(param_name, expected_type, value)
            parameters[param_name] = converted_value
            
            logger.debug(f"Decoded parameter '{param_name}': {value} -> {converted_value}")
            
        except Exception as e:
            logger.error(f"Failed to decode parameter '{param_name}': {e}")
            parameters[param_name] = f"decode_error({data[offset:offset+length].hex()})"
        
        offset += length
        field_index += 1
    
    logger.debug(f"Decoded {len(parameters)} parameters for action '{action}'")
    return parameters

def decode_step(data: bytes, offset: int) -> Tuple[Dict[str, Any], int]:
    """Decode a single step from binary data"""
    logger = logging.getLogger(__name__)
    
    if offset + 8 > len(data):
        raise ValueError("Not enough data for step header")
    
    # Decode step header: <I (4) H (2) B (1) B (1)> = 8 bytes
    magic, step_id, action_id, param_len = struct.unpack('<IHBB', data[offset:offset+8])
    
    if magic != MAGIC_STEP:
        raise ValueError(f"Invalid step magic: 0x{magic:08X}, expected 0x{MAGIC_STEP:08X}")
    
    logger.debug(f"Step header: magic=0x{magic:08X}, id={step_id}, action_id=0x{action_id:02X}, param_len={param_len}")
    
    # Get action name
    action = ACTION_NAMES.get(action_id, f'unknown_action_0x{action_id:02X}')
    logger.info(f"Decoding step {step_id}: {action}")
    
    # Decode parameters
    param_offset = offset + 8
    if param_offset + param_len > len(data):
        raise ValueError(f"Not enough data for step parameters: need {param_len} bytes")
    
    param_data = data[param_offset:param_offset + param_len]
    parameters = decode_parameters(action, param_data)
    
    step = {
        'action': action,
        'parameters': parameters
    }
    
    total_step_size = 8 + param_len
    logger.debug(f"Step {step_id} decoded: {total_step_size} bytes total")
    
    return step, total_step_size

def decode_section(data: bytes) -> Tuple[List[Dict[str, Any]], str]:
    """Decode a section (init/dls_routine/cam_routine) from binary data"""
    logger = logging.getLogger(__name__)
    
    if len(data) < 10:
        raise ValueError("Not enough data for section header")
    
    # Decode header (10 bytes)
    header_data = data[0:8]
    header_crc_data = data[8:10]
    
    magic, version, num_steps = struct.unpack('<IHH', header_data)
    header_crc = struct.unpack('<H', header_crc_data)[0]
    
    logger.debug(f"Section header: magic=0x{magic:08X}, version={version}, steps={num_steps}")
    
    if magic != MAGIC_HEADER:
        raise ValueError(f"Invalid section magic: 0x{magic:08X}, expected 0x{MAGIC_HEADER:08X}")
    
    # Verify header CRC
    calculated_header_crc = crc16_xmodem(header_data)
    if calculated_header_crc != header_crc:
        logger.warning(f"Header CRC mismatch: calc=0x{calculated_header_crc:04X}, got=0x{header_crc:04X}")
    else:
        logger.debug("Header CRC verified")
    
    # Verify total CRC
    total_crc_data = data[-2:]
    total_crc = struct.unpack('<H', total_crc_data)[0]
    calculated_total_crc = crc16_xmodem(data[:-2])
    
    if calculated_total_crc != total_crc:
        logger.warning(f"Total CRC mismatch: calc=0x{calculated_total_crc:04X}, got=0x{total_crc:04X}")
    else:
        logger.debug("Total CRC verified")
    
    # Decode steps
    steps = []
    offset = 10  # Start after header
    
    for i in range(num_steps):
        try:
            step, step_size = decode_step(data, offset)
            steps.append(step)
            offset += step_size
        except Exception as e:
            logger.error(f"Failed to decode step {i+1}: {e}")
            break
    
    logger.info(f"Decoded section: {len(steps)} steps")
    return steps, f"version_{version}"

def decode_modfsp_frame(data: bytes, offset: int) -> Tuple[int, bytes, int]:
    """Decode a single MODFSP frame"""
    logger = logging.getLogger(__name__)
    
    if offset + 9 > len(data):  # Minimum frame size
        raise ValueError("Not enough data for MODFSP frame header")
    
    # Check start bytes
    if data[offset] != SFP_START1_BYTE or data[offset+1] != SFP_START2_BYTE:
        raise ValueError(f"Invalid MODFSP start bytes: 0x{data[offset]:02X} 0x{data[offset+1]:02X}")
    
    frame_id = data[offset + 2]
    len_low = data[offset + 3]
    len_high = data[offset + 4]
    data_len = len_low | (len_high << 8)
    
    logger.debug(f"MODFSP frame: ID=0x{frame_id:02X}, length={data_len}")
    
    frame_size = 9 + data_len  # 2 start + 1 id + 2 len + data + 2 crc + 2 stop
    
    if offset + frame_size > len(data):
        raise ValueError(f"Not enough data for complete MODFSP frame: need {frame_size} bytes")
    
    # Extract payload
    payload = data[offset + 5:offset + 5 + data_len]
    
    # Extract and verify CRC
    crc_offset = offset + 5 + data_len
    frame_crc = data[crc_offset] | (data[crc_offset + 1] << 8)
    
    # Calculate expected CRC (ID + LENGTH + DATA)
    crc_data = data[offset + 2:offset + 5 + data_len]  # ID + LEN_LOW + LEN_HIGH + DATA
    calculated_crc = crc16_xmodem(crc_data)
    
    if calculated_crc != frame_crc:
        logger.warning(f"Frame CRC mismatch: calc=0x{calculated_crc:04X}, got=0x{frame_crc:04X}")
    else:
        logger.debug("Frame CRC verified")
    
    # Check stop bytes
    stop_offset = offset + 5 + data_len + 2
    if data[stop_offset] != SFP_STOP1_BYTE or data[stop_offset+1] != SFP_STOP2_BYTE:
        logger.warning(f"Invalid MODFSP stop bytes: 0x{data[stop_offset]:02X} 0x{data[stop_offset+1]:02X}")
    
    logger.info(f"Decoded MODFSP frame: ID=0x{frame_id:02X}, payload={data_len} bytes")
    return frame_id, payload, frame_size

def decode_binary_to_json(binary_file: str, output_file: str) -> bool:
    """Decode binary file back to JSON format"""
    logger = logging.getLogger(__name__)
    
    # Add separator
    separator = "=" * 80
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    separator2 = "[" + "-" * 78 + "]"

    logger.info("")
    logger.info(separator)
    logger.info(f"BINARY DECODE - {current_time}")
    logger.info(f"Input:  {binary_file}")
    logger.info(f"Output: {output_file}")
    logger.info(separator2)
    
    try:
        # Read binary file
        with open(binary_file, 'rb') as f:
            binary_data = f.read()
        
        logger.info(f"Successfully loaded binary data: {len(binary_data)} bytes")
        
        # Decode MODFSP frames
        result = {
            'init': {'steps': []},
            'dls_routine': {'steps': []},
            'cam_routine': {'steps': []}
        }
        
        offset = 0
        frame_count = 0
        
        while offset < len(binary_data):
            try:
                frame_id, payload, frame_size = decode_modfsp_frame(binary_data, offset)
                frame_count += 1
                
                # Decode section based on frame ID
                if frame_id == FRAME_ID_INIT:
                    steps, version_info = decode_section(payload)
                    result['init']['steps'] = steps
                    logger.info(f"Decoded INIT section: {len(steps)} steps")
                elif frame_id == FRAME_ID_DLS_ROUTINE:
                    steps, version_info = decode_section(payload)
                    result['dls_routine']['steps'] = steps
                    logger.info(f"Decoded DLS_ROUTINE section: {len(steps)} steps")
                elif frame_id == FRAME_ID_CAM_ROUTINE:
                    steps, version_info = decode_section(payload)
                    result['cam_routine']['steps'] = steps
                    logger.info(f"Decoded CAM_ROUTINE section: {len(steps)} steps")
                else:
                    logger.warning(f"Unknown frame ID: 0x{frame_id:02X}")
                
                offset += frame_size
                
            except Exception as e:
                logger.error(f"Failed to decode frame at offset {offset}: {e}")
                break
        
        # Write JSON file
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=4)
        
        logger.info(f"Successfully created JSON file: {output_file}")
        
        # Summary
        logger.info("=== DECODE SUMMARY ===")
        total_steps = len(result['init']['steps']) + len(result['dls_routine']['steps']) + len(result['cam_routine']['steps'])
        logger.info(f"Total frames decoded: {frame_count}")
        logger.info(f"Total steps decoded: {total_steps}")
        logger.info(f"INIT steps: {len(result['init']['steps'])}")
        logger.info(f"DLS_ROUTINE steps: {len(result['dls_routine']['steps'])}")
        logger.info(f"CAM_ROUTINE steps: {len(result['cam_routine']['steps'])}")
        logger.info("[SUCCESS] Binary decode completed successfully!")
        
        return True
        
    except Exception as e:
        logger.error(f"Error during decode: {e}")
        return False

def main():
    """Main function with command line argument parsing"""
    parser = argparse.ArgumentParser(description="Decode binary file back to builttostep JSON format")
    parser.add_argument(
        "-f", "--file", 
        default="bee_pc1.bin",
        help="Input binary file (default: bee_pc1.bin)"
    )
    parser.add_argument(
        "-o", "--output",
        default="decoded_steps.json",
        help="Output JSON file (default: decoded_steps.json)"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    logger = setup_logging(args.verbose)
    
    # Run decode
    success = decode_binary_to_json(args.file, args.output)
    
    if success:
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == '__main__':
    main()