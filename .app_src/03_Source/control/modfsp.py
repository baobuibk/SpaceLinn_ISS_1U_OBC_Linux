import time
import logging
from enum import IntEnum
from typing import Optional, Callable, Dict, List, Tuple, Any
from dataclasses import dataclass, field

# Constants
CRC16_XMODEM_POLY = 0x1021
CRC16_XMODEM_INIT = 0x0000

# Default timeout in milliseconds
MODFSP_TIMEOUT_MS = 300

SFP_START1_BYTE = 0xC0
SFP_START2_BYTE = 0xDE

SFP_STOP1_BYTE = 0xDA
SFP_STOP2_BYTE = 0xED

class MODFSPReturn(IntEnum):
    """Return codes for MODFSP operations"""
    OK = 0
    ERR = 1
    ERRMEM = 2
    ERRCRC = 3
    ERRSTOP = 4
    ERRTIMEOUT = 5
    VALID = 6
    INPROG = 7
    WAITDATA = 8

class DecodeState(IntEnum):
    """Decode state machine states"""
    START1 = 0
    START2 = 1
    ID = 2
    LEN_LOW = 3  # State to process the low byte of the length
    LEN_HIGH = 4 # State to process the high byte of the length
    DATA = 5
    CRC = 6
    STOP1 = 7
    STOP2 = 8
    END = 9

@dataclass
class CRC16:
    crc: int = CRC16_XMODEM_INIT
    
    def reset(self):
        self.crc = CRC16_XMODEM_INIT
    
    def update(self, data: int):
        self.crc = crc16_xmodem_update(self.crc, data)
    
    def finish(self) -> int:
        return self.crc

# CRC16 XMODEM update function
def crc16_xmodem_update(crc: int, data: int) -> int:
    crc ^= (data << 8)
    for _ in range(8):
        if crc & 0x8000:
            crc = (crc << 1) ^ CRC16_XMODEM_POLY
        else:
            crc <<= 1
    return crc & 0xFFFF

class MODFSP:
    """MODFSP Protocol Handler"""
    
    def __init__(self, timeout_ms: int = MODFSP_TIMEOUT_MS, debug: bool = False):
        """Initialize MODFSP instance
        
        Args:
            timeout_ms: Timeout in milliseconds for incomplete frames
            debug: Enable debug logging
        """
        self.timeout_ms = timeout_ms
        self.debug = debug
        
        # Setup logging
        self.logger = logging.getLogger(__name__)
        if debug:
            self.logger.setLevel(logging.DEBUG)
            if not self.logger.handlers:
                handler = logging.StreamHandler()
                formatter = logging.Formatter('%(levelname)s - %(message)s')
                handler.setFormatter(formatter)
                self.logger.addHandler(handler)
        
        # State machine variables
        self.state = DecodeState.START1
        self.data = bytearray(5120)  # Buffer size updated according to DATA_MAX_LENGTH in C
        self.index = 0
        self.length = 0 # Length will be 16-bit
        self.id = 0
        self.crc16_data = 0
        self.crc16 = CRC16()
        self.last_rx_time = 0
        
        # Command table
        self.command_table: Dict[int, Callable] = {}
        
        # Communication interface callbacks
        self.read_byte_callback: Optional[Callable[[], Tuple[bool, int]]] = None
        self.send_byte_callback: Optional[Callable[[int], None]] = None
        self.get_space_callback: Optional[Callable[[], int]] = None
        
        self.reset()
    
    def reset(self):
        """Reset the protocol state machine"""
        self.state = DecodeState.START1
        self.data = bytearray(5120) # Reset buffer with new size
        self.index = 0
        self.length = 0
        self.id = 0
        self.crc16_data = 0
        self.crc16.reset()
        
        if self.debug:
            self.logger.debug("Protocol state machine reset")
    
    def _log(self, message: str, *args):
        if self.debug:
            self.logger.debug(message, *args)
    
    def _go_to_next_state(self):
        next_state = DecodeState.END
        
        if self.state == DecodeState.START1:
            next_state = DecodeState.START2
        elif self.state == DecodeState.START2:
            next_state = DecodeState.ID
        elif self.state == DecodeState.ID:
            next_state = DecodeState.LEN_LOW # Transition to LEN_LOW state
        elif self.state == DecodeState.LEN_LOW:
            next_state = DecodeState.LEN_HIGH # Transition to LEN_HIGH state
        elif self.state == DecodeState.LEN_HIGH: # New state to process LEN_HIGH
            # If length is 0, transition directly to CRC, otherwise to DATA
            next_state = DecodeState.DATA if self.length > 0 else DecodeState.CRC 
        elif self.state == DecodeState.DATA:
            next_state = DecodeState.CRC
        elif self.state == DecodeState.CRC:
            next_state = DecodeState.STOP1
        elif self.state == DecodeState.STOP1:
            next_state = DecodeState.STOP2
        elif self.state == DecodeState.STOP2:
            next_state = DecodeState.START1
        
        if next_state != DecodeState.END:
            self.state = next_state
            self.index = 0
    
    def read_byte(self, byte: int) -> MODFSPReturn:
        """Process one received byte
        
        Args:
            byte: Byte to process (0-255)
            
        Returns:
            MODFSPReturn: Processing result
        """
        # Update last reception time when a byte arrives
        self.last_rx_time = int(time.time() * 1000)

        if self.state == DecodeState.START1:
            if byte == SFP_START1_BYTE:
                self._log("Start1 byte received (0x%02X)", byte)
                self.reset() # Reset state to be ready for a new packet
                self.crc16.reset()
                self._go_to_next_state()
                
        elif self.state == DecodeState.START2:
            if byte == SFP_START2_BYTE:
                self._log("Start2 byte received (0x%02X)", byte)
                self._go_to_next_state()
            else:
                self.reset() # Reset if the second byte is incorrect
                
        elif self.state == DecodeState.ID:
            self.id = byte
            self._log("ID byte received: 0x%02X (%d)", byte, byte)
            self.crc16.update(byte)
            self._go_to_next_state()
            
        elif self.state == DecodeState.LEN_LOW: # Process the low byte of the length
            self.length = byte
            self._log("Length low byte received: %d", byte)
            self.crc16.update(byte)
            self._go_to_next_state()
            
        elif self.state == DecodeState.LEN_HIGH: # Process the high byte of the length
            self.length |= (byte << 8)
            self._log("Length high byte received: %d (Total Length: %d)", byte, self.length)
            self.crc16.update(byte)
            
            # Check if the length exceeds the buffer size
            if self.length > len(self.data):
                self.reset()
                return MODFSPReturn.ERRMEM
            
            self._go_to_next_state()
                
        elif self.state == DecodeState.DATA:
            if self.index < self.length: # Compare with the received length
                if self.index < len(self.data): # Ensure no buffer overflow
                    self._log("Data byte received [%d]: 0x%02X (%d)", self.index, byte, byte)
                    self.data[self.index] = byte
                    self.index += 1
                    self.crc16.update(byte)
                    if self.index == self.length: # If enough data received, change state
                        self._go_to_next_state()
                else:
                    # This case should rarely happen if length > len(self.data) check is done above
                    self._log("Data buffer overflow during reception (index: %d, buffer_size: %d)", self.index, len(self.data))
                    self.reset()
                    return MODFSPReturn.ERRMEM
            else:
                # This should not happen if _go_to_next_state logic is correct
                # and self.index == self.length has been handled above
                self._log("Unexpected byte in DATA state, index >= length")
                self.reset()
                return MODFSPReturn.ERR

        elif self.state == DecodeState.CRC:
            if self.index < 2:
                self.crc16_data |= byte << (8 * self.index)
                self.index += 1
            
            if self.index == 2: # All 2 CRC bytes received
                calculated_crc = self.crc16.finish()
                if calculated_crc == self.crc16_data:
                    self._log("CRC OK: Received 0x%04X, Calculated 0x%04X", self.crc16_data, calculated_crc)
                    self._go_to_next_state()
                else:
                    self._log("CRC Error: Calculated=0x%04X, Received=0x%04X", calculated_crc, self.crc16_data)
                    self.reset()
                    return MODFSPReturn.ERRCRC # Return CRC error
                    
        elif self.state == DecodeState.STOP1:
            if byte == SFP_STOP1_BYTE:
                self._log("Stop1 byte received (0x%02X)", byte)
                self._go_to_next_state()
            else:
                self.reset()
                return MODFSPReturn.ERRSTOP # Return STOP error
                
        elif self.state == DecodeState.STOP2:
            if byte == SFP_STOP2_BYTE:
                self._log("Stop2 byte received (0x%02X)", byte)
                self._go_to_next_state() # Transition to START1 after a valid packet ends
                return MODFSPReturn.VALID # Packet is fully valid
            else:
                self.reset()
                return MODFSPReturn.ERRSTOP # Return STOP error
        else:
            self.reset()
            return MODFSPReturn.ERR
        
        # Return WAITDATA if in START1 state, otherwise INPROG
        return MODFSPReturn.WAITDATA if self.state == DecodeState.START1 else MODFSPReturn.INPROG
    
    def send(self, msg_id: int, data: bytes = b'') -> MODFSPReturn:
        """Send a message
        
        Args:
            msg_id: Message ID (0-255)
            data: Message payload
            
        Returns:
            MODFSPReturn: Send result
        """
        if not self.send_byte_callback:
            self._log("Send byte callback not set.")
            return MODFSPReturn.ERR
        
        data_len = len(data)
        # 2 start + 2 stop + 1 id + 2 len + 2 CRC + data = 9 + data_len
        min_mem = 9 + data_len
        
        if self.get_space_callback:
            available_space = self.get_space_callback()
            if available_space < min_mem:
                self._log("Not enough TX buffer space: needed %d, available %d", min_mem, available_space)
                return MODFSPReturn.ERRMEM # Return memory error
        
        crc = CRC16()
        
        # Send frame
        self._log("Sending packet: ID=0x%02X, Length=%d", msg_id, data_len)
        self.send_byte_callback(SFP_START1_BYTE)
        self.send_byte_callback(SFP_START2_BYTE)
        
        self.send_byte_callback(msg_id)
        crc.update(msg_id)
        
        # Send length low byte first
        self.send_byte_callback(data_len & 0xFF)
        crc.update(data_len & 0xFF)
        
        # Send length high byte
        self.send_byte_callback((data_len >> 8) & 0xFF)
        crc.update((data_len >> 8) & 0xFF)
        
        for byte in data:
            self.send_byte_callback(byte)
            crc.update(byte)
        
        crc_value = crc.finish()
        self.send_byte_callback(crc_value & 0xFF)
        self.send_byte_callback((crc_value >> 8) & 0xFF)
        
        self.send_byte_callback(SFP_STOP1_BYTE)
        self.send_byte_callback(SFP_STOP2_BYTE)
        
        return MODFSPReturn.OK
    
    def process(self) -> MODFSPReturn:
        """Process incoming data using callbacks
        
        Returns:
            MODFSPReturn: Processing result
        """
        if not self.read_byte_callback:
            self._log("Read byte callback not set.")
            return MODFSPReturn.ERR
        
        now = int(time.time() * 1000)  # Current time in milliseconds
        
        has_data, byte = self.read_byte_callback()

        if has_data:
            result = self.read_byte(byte)
            
            if result == MODFSPReturn.VALID:
                self.last_rx_time = now
                self._log("Packet valid, calling handler for ID: 0x%02X", self.id)
                self._application_handler(self.id, bytes(self.data[:self.length])) # Convert data to bytes
            elif result == MODFSPReturn.INPROG:
                self.last_rx_time = now
            elif result in [MODFSPReturn.ERRCRC, MODFSPReturn.ERRSTOP, MODFSPReturn.ERRMEM, MODFSPReturn.ERR]:
                # If there's an error, reset last_rx_time to prevent immediate timeout or no timeout
                self.last_rx_time = now 
            
            return result
        else:
            # If no data and currently in a middle of a packet, check for timeout
            if (self.state != DecodeState.START1 and 
                (now - self.last_rx_time) > self.timeout_ms):
                self._log("Timeout occurred - Resetting state machine (last RX: %d ms ago)", now - self.last_rx_time)
                self.reset()
                self.last_rx_time = now # Reset time to prevent continuous timeouts
                return MODFSPReturn.ERRTIMEOUT
        
        return MODFSPReturn.WAITDATA
    
    def register_command(self, msg_id: int, handler: Callable[[bytes], None]):
        """Register a command handler
        
        Args:
            msg_id: Message ID to handle
            handler: Handler function that takes payload bytes
        """
        if msg_id in self.command_table:
            self.logger.warning("Handler for ID 0x%02X is already registered. Overwriting.", msg_id)
        self.command_table[msg_id] = handler
        if self.debug:
            self.logger.debug("Registered handler for ID: 0x%02X", msg_id)
    
    def _application_handler(self, msg_id: int, payload: bytes):
        """Internal application handler, equivalent to MODFSP_ApplicationHandler in C"""
        if msg_id in self.command_table:
            try:
                self.command_table[msg_id](payload)
            except Exception as e:
                if self.debug:
                    self.logger.error("Error in handler for ID 0x%02X: %s", msg_id, e)
        else:
            if self.debug:
                self.logger.warning("No handler registered for ID: 0x%02X", msg_id)
    
    def set_read_callback(self, callback: Callable[[], Tuple[bool, int]]):
        """Set callback for reading bytes
        
        Args:
            callback: Function that returns (has_data: bool, byte: int)
        """
        self.read_byte_callback = callback
    
    def set_send_callback(self, callback: Callable[[int], None]):
        """Set callback for sending bytes
        
        Args:
            callback: Function that takes a byte to send
        """
        self.send_byte_callback = callback
    
    def set_space_callback(self, callback: Callable[[], int]):
        """Set callback for checking available space
        
        Args:
            callback: Function that returns available space in bytes
        """
        self.get_space_callback = callback
    
    def process_bytes(self, data: bytes) -> List[Tuple[int, bytes]]:
        """Process a sequence of bytes and return completed messages

        Args:
            data: Bytes to process

        Returns:
            List of (msg_id, payload) tuples for completed messages
        """
        messages = []

        for byte in data:
            result = self.read_byte(byte)
            if result == MODFSPReturn.VALID:
                self._log("Packet valid after processing bytes, calling handler for ID: 0x%02X", self.id)
                self._application_handler(self.id, bytes(self.data[:self.length]))
                messages.append((self.id, bytes(self.data[:self.length])))
            # For other return types (INPROG, ERRCRC, etc.), it implies an incomplete packet or an error.
            # We don't add incomplete/error packets to the 'messages' list.
        return messages