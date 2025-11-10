import sys
import time
from smbus2 import SMBus

I2C_ADDRESS = 0x20

OUTPUT_PORT0 = 0x02
OUTPUT_PORT1 = 0x03
CONFIG_PORT0 = 0x06
CONFIG_PORT1 = 0x07

bus = SMBus(2)  # Change if using different I2C bus

def initialize_tca6416():
    try:
        bus.write_byte_data(I2C_ADDRESS, CONFIG_PORT0, 0x00)
        bus.write_byte_data(I2C_ADDRESS, CONFIG_PORT1, 0x00)
        bus.write_byte_data(I2C_ADDRESS, OUTPUT_PORT0, 0x00)
        bus.write_byte_data(I2C_ADDRESS, OUTPUT_PORT1, 0x00)
    except Exception as e:
        print(f"Initialization error: {e}", file=sys.stderr)
        sys.exit(2)

def set_tca6416_pin(port, pin, state):
    reg = OUTPUT_PORT0 if port == 0 else OUTPUT_PORT1
    try:
        current = bus.read_byte_data(I2C_ADDRESS, reg)
        new_value = (current | (1 << pin)) if state else (current & ~(1 << pin))
        bus.write_byte_data(I2C_ADDRESS, reg, new_value)
    except Exception as e:
        print(f"Failed to set P{port}{pin} to {state}: {e}", file=sys.stderr)
        sys.exit(3)

def enable_sensor(sensor):
    try:
        if sensor == 0:  # U1
            set_tca6416_pin(1, 7, 0)
            set_tca6416_pin(1, 6, 1)
            set_tca6416_pin(1, 5, 1)
            set_tca6416_pin(1, 4, 1)
            time.sleep(0.01)
            set_tca6416_pin(1, 0, 0)
            set_tca6416_pin(1, 1, 0)
            time.sleep(0.01)
            set_tca6416_pin(0, 7, 1)
            set_tca6416_pin(0, 6, 0)
            set_tca6416_pin(0, 5, 0)
            set_tca6416_pin(0, 4, 0)

        elif sensor == 1:  # U2
            set_tca6416_pin(1, 7, 1)
            set_tca6416_pin(1, 6, 0)
            set_tca6416_pin(1, 5, 1)
            set_tca6416_pin(1, 4, 1)
            time.sleep(0.01)
            set_tca6416_pin(1, 0, 1)
            set_tca6416_pin(1, 1, 0)
            time.sleep(0.01)
            set_tca6416_pin(0, 7, 0)
            set_tca6416_pin(0, 6, 1)
            set_tca6416_pin(0, 5, 0)
            set_tca6416_pin(0, 4, 0)

        elif sensor == 2:  # U3
            set_tca6416_pin(1, 7, 1)
            set_tca6416_pin(1, 6, 1)
            set_tca6416_pin(1, 5, 0)
            set_tca6416_pin(1, 4, 1)
            time.sleep(0.01)
            set_tca6416_pin(1, 0, 0)
            set_tca6416_pin(1, 1, 1)
            time.sleep(0.01)
            set_tca6416_pin(0, 7, 0)
            set_tca6416_pin(0, 6, 0)
            set_tca6416_pin(0, 5, 1)
            set_tca6416_pin(0, 4, 0)

        elif sensor == 3:  # U4
            set_tca6416_pin(1, 7, 1)
            set_tca6416_pin(1, 6, 1)
            set_tca6416_pin(1, 5, 1)
            set_tca6416_pin(1, 4, 0)
            time.sleep(0.01)
            set_tca6416_pin(1, 0, 1)
            set_tca6416_pin(1, 1, 1)
            time.sleep(0.01)
            set_tca6416_pin(0, 7, 0)
            set_tca6416_pin(0, 6, 0)
            set_tca6416_pin(0, 5, 0)
            set_tca6416_pin(0, 4, 1)
        else:
            print(f"Invalid sensor index: {sensor}", file=sys.stderr)
            sys.exit(1)

        print(f"Sensor U{sensor+1} enabled.")

    except Exception as e:
        print(f"Error enabling sensor U{sensor+1}: {e}", file=sys.stderr)
        sys.exit(4)

def main():
    if len(sys.argv) != 2:
        print("Usage: python3 sensor_switch.py <sensor_index 0-3>", file=sys.stderr)
        sys.exit(1)

    try:
        sensor_index = int(sys.argv[1])
        if sensor_index not in [0, 1, 2, 3]:
            raise ValueError
    except ValueError:
        print("Sensor index must be 0, 1, 2, or 3.", file=sys.stderr)
        sys.exit(1)

    try:
        initialize_tca6416()
        enable_sensor(sensor_index)
    finally:
        bus.close()

if __name__ == "__main__":
    main()
