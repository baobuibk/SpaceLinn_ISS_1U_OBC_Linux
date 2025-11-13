from smbus2 import SMBus
import time

# I2C address of TCA6416APWR (default 0x20, change if needed)
I2C_ADDRESS = 0x20

# TCA6416APWR registers
OUTPUT_PORT0 = 0x02  # Output register Port 0
OUTPUT_PORT1 = 0x03  # Output register Port 1
INPUT_PORT0 = 0x00   # Input register Port 0
INPUT_PORT1 = 0x01   # Input register Port 1
CONFIG_PORT0 = 0x06  # Configuration register Port 0
CONFIG_PORT1 = 0x07  # Configuration register Port 1

# Initialize I2C4
bus = SMBus(4)  # Use I2C bus 4

def initialize_tca6416():
    """Initialize TCA6416APWR by setting all pins as outputs."""
    try:
        bus.write_byte_data(I2C_ADDRESS, CONFIG_PORT0, 0x00)  # Set Port 0 as all outputs
        bus.write_byte_data(I2C_ADDRESS, CONFIG_PORT1, 0x00)  # Set Port 1 as all outputs
        bus.write_byte_data(I2C_ADDRESS, OUTPUT_PORT0, 0x00)  # Clear Port 0 outputs
        bus.write_byte_data(I2C_ADDRESS, OUTPUT_PORT1, 0x00)  # Clear Port 1 outputs
        print("TCA6416APWR initialized successfully.")
    except Exception as e:
        print(f"Error during initialization: {e}")

def set_tca6416_pin(port, pin, state):
    """Set the state of a specific GPIO pin."""
    try:
        # Read current output value
        if port == 0:
            current_value = bus.read_byte_data(I2C_ADDRESS, OUTPUT_PORT0)
        else:
            current_value = bus.read_byte_data(I2C_ADDRESS, OUTPUT_PORT1)

        # Calculate new value
        if state == 1:
            new_value = current_value | (1 << pin)  # Set bit
        else:
            new_value = current_value & ~(1 << pin)  # Clear bit

        # Write new value
        if port == 0:
            bus.write_byte_data(I2C_ADDRESS, OUTPUT_PORT0, new_value)
            print(f"Set P0{pin} = {state}")
        else:
            bus.write_byte_data(I2C_ADDRESS, OUTPUT_PORT1, new_value)
            print(f"Set P1{pin} = {state}")

    except Exception as e:
        print(f"Error setting pin state: {e}")

def read_tca6416_ports():
    """Read and display the state of TCA6416APWR ports."""
    try:
        # Read output values from Port 0 and Port 1
        port0_value = bus.read_byte_data(I2C_ADDRESS, OUTPUT_PORT0)
        port1_value = bus.read_byte_data(I2C_ADDRESS, OUTPUT_PORT1)

        # Convert to binary
        port0_binary = format(port0_value, '08b')
        port1_binary = format(port1_value, '08b')

        # Display overview
        print("\nTCA6416APWR Status:")
        print(f"Port 0 value (hex): 0x{port0_value:02x}, binary: {port0_binary}")
        print(f"Port 1 value (hex): 0x{port1_value:02x}, binary: {port1_binary}")
        print("\nGPIO Pin States:")
        print("Port 0:")
        for i in range(8):
            pin_state = port0_binary[7 - i]
            print(f"P0{i}: {pin_state} ({'ON' if pin_state == '1' else 'OFF'})")
        print("\nPort 1:")
        for i in range(8):
            pin_state = port1_binary[7 - i]
            print(f"P1{i}: {pin_state} ({'ON' if pin_state == '1' else 'OFF'})")

    except Exception as e:
        print(f"Error reading port states: {e}")

def enable_sensor(sensor):
    """Execute script to enable a specific sensor (U1: Sen0, U2: Sen1, U3: Sen2, U4: Sen3)."""
    print(f"Enabling sensor {sensor}...")
    try:
        if sensor == "U1":
            # Script for U1: Sen0
            set_tca6416_pin(1, 7, 0)  # SEN_0_CLK_nENA[LOW] {P1-7}
            set_tca6416_pin(1, 6, 1)  # SEN_1_CLK_nENA[HIGH] {P1-6}
            set_tca6416_pin(1, 5, 1)  # SEN_2_CLK_nENA[HIGH] {P1-5}
            set_tca6416_pin(1, 4, 1)  # SEN_3_CLK_nENA[HIGH] {P1-4}
            time.sleep(0.01)  # Delay 10ms
            set_tca6416_pin(1, 0, 0)  # SEN_SEL_0[LOW] {P1-0}
            set_tca6416_pin(1, 1, 0)  # SEN_SEL_1[LOW] {P1-1}
            time.sleep(0.01)  # Delay 10ms
            set_tca6416_pin(0, 7, 1)  # SEN_0_nOFF[HIGH] {P0-7}
            set_tca6416_pin(0, 6, 0)  # SEN_1_nOFF[LOW] {P0-6}
            set_tca6416_pin(0, 5, 0)  # SEN_2_nOFF[LOW] {P0-5}
            set_tca6416_pin(0, 4, 0)  # SEN_3_nOFF[LOW] {P0-4}
            time.sleep(0.01)  # Delay 10ms

        elif sensor == "U2":
            # Script for U2: Sen1
            set_tca6416_pin(1, 7, 1)  # SEN_0_CLK_nENA[HIGH] {P1-7}
            set_tca6416_pin(1, 6, 0)  # SEN_1_CLK_nENA[LOW] {P1-6}
            set_tca6416_pin(1, 5, 1)  # SEN_2_CLK_nENA[HIGH] {P1-5}
            set_tca6416_pin(1, 4, 1)  # SEN_3_CLK_nENA[HIGH] {P1-4}
            time.sleep(0.01)  # Delay 10ms
            set_tca6416_pin(1, 0, 1)  # SEN_SEL_0[HIGH] {P1-0}
            set_tca6416_pin(1, 1, 0)  # SEN_SEL_1[LOW] {P1-1}
            time.sleep(0.01)  # Delay 10ms
            set_tca6416_pin(0, 7, 0)  # SEN_0_nOFF[LOW] {P0-7}
            set_tca6416_pin(0, 6, 1)  # SEN_1_nOFF[HIGH] {P0-6}
            set_tca6416_pin(0, 5, 0)  # SEN_2_nOFF[LOW] {P0-5}
            set_tca6416_pin(0, 4, 0)  # SEN_3_nOFF[LOW] {P0-4}
            time.sleep(0.01)  # Delay 10ms

        elif sensor == "U3":
            # Script for U3: Sen2
            set_tca6416_pin(1, 7, 1)  # SEN_0_CLK_nENA[HIGH] {P1-7}
            set_tca6416_pin(1, 6, 1)  # SEN_1_CLK_nENA[HIGH] {P1-6}
            set_tca6416_pin(1, 5, 0)  # SEN_2_CLK_nENA[LOW] {P1-5}
            set_tca6416_pin(1, 4, 1)  # SEN_3_CLK_nENA[HIGH] {P1-4}
            time.sleep(0.01)  # Delay 10ms
            set_tca6416_pin(1, 0, 0)  # SEN_SEL_0[LOW] {P1-0}
            set_tca6416_pin(1, 1, 1)  # SEN_SEL_1[HIGH] {P1-1}
            time.sleep(0.01)  # Delay 10ms
            set_tca6416_pin(0, 7, 0)  # SEN_0_nOFF[LOW] {P0-7}
            set_tca6416_pin(0, 6, 0)  # SEN_1_nOFF[LOW] {P0-6}
            set_tca6416_pin(0, 5, 1)  # SEN_2_nOFF[HIGH] {P0-5}
            set_tca6416_pin(0, 4, 0)  # SEN_3_nOFF[LOW] {P0-4}
            time.sleep(0.01)  # Delay 10ms

        elif sensor == "U4":
            # Script for U4: Sen3
            set_tca6416_pin(1, 7, 1)  # SEN_0_CLK_nENA[HIGH] {P1-7}
            set_tca6416_pin(1, 6, 1)  # SEN_1_CLK_nENA[HIGH] {P1-6}
            set_tca6416_pin(1, 5, 1)  # SEN_2_CLK_nENA[HIGH] {P1-5}
            set_tca6416_pin(1, 4, 0)  # SEN_3_CLK_nENA[LOW] {P1-4}
            time.sleep(0.01)  # Delay 10ms
            set_tca6416_pin(1, 0, 1)  # SEN_SEL_0[HIGH] {P1-0}
            set_tca6416_pin(1, 1, 1)  # SEN_SEL_1[HIGH] {P1-1}
            time.sleep(0.01)  # Delay 10ms
            set_tca6416_pin(0, 7, 0)  # SEN_0_nOFF[LOW] {P0-7}
            set_tca6416_pin(0, 6, 0)  # SEN_1_nOFF[LOW] {P0-6}
            set_tca6416_pin(0, 5, 0)  # SEN_2_nOFF[LOW] {P0-5}
            set_tca6416_pin(0, 4, 1)  # SEN_3_nOFF[HIGH] {P0-4}
            time.sleep(0.01)  # Delay 10ms

        # Verify configuration
        print(f"Verifying {sensor} configuration...")
        read_tca6416_ports()

    except Exception as e:
        print(f"Error enabling sensor {sensor}: {e}")

def main():
    # Initialize TCA6416APWR
    initialize_tca6416()
    
    while True:
        try:
            print("\nOptions:")
            print("  1. Set GPIO pin state (port, pin, state)")
            print("  2. Read TCA6416APWR status")
            print("  3. Enable U1: Sen0")
            print("  4. Enable U2: Sen1")
            print("  5. Enable U3: Sen2")
            print("  6. Enable U4: Sen3")
            print("  q. Quit program")
            choice = input("Enter choice: ")

            if choice.lower() == 'q':
                print("Program terminated.")
                break

            elif choice == '1':
                port = int(input("Enter port (0 or 1): "))
                pin = int(input("Enter pin number (0-7): "))
                state = int(input("Enter state (0 for OFF, 1 for ON): "))
                if port not in [0, 1] or pin not in range(8) or state not in [0, 1]:
                    print("Error: Port (0-1), Pin (0-7), State (0-1)!")
                    continue
                set_tca6416_pin(port, pin, state)
                read_tca6416_ports()

            elif choice == '2':
                read_tca6416_ports()

            elif choice == '3':
                enable_sensor("U1")

            elif choice == '4':
                enable_sensor("U2")

            elif choice == '5':
                enable_sensor("U3")

            elif choice == '6':
                enable_sensor("U4")

            else:
                print("Invalid choice!")

        except ValueError:
            print("Error: Please enter valid numbers!")
        except Exception as e:
            print(f"Unexpected error: {e}")

if __name__ == "__main__":
    try:
        main()
    finally:
        bus.close()  # Close I2C bus
