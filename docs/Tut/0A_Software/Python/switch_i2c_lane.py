from smbus2 import SMBus

# Default I2C address of PCA9544APW (change if A0, A1, A2 are configured differently)
I2C_ADDRESS = 0x70

# Values for each channel
CHANNELS = {
    0: 0x04,  # 00000100 - Channel 0
    1: 0x05,  # 00000101 - Channel 1
    2: 0x06,  # 00000110 - Channel 2
    3: 0x07   # 00000111 - Channel 3
}

# Initialize I2C bus (assuming I2C0)
bus = SMBus(0)  # Change bus number if using a different bus (e.g., 4 for I2C4)

def switch_channel(channel):
    try:
        if channel not in CHANNELS:
            print("Error: Only channels 0, 1, 2, or 3 are supported!")
            return
        
        # Write value to select channel
        bus.write_byte(I2C_ADDRESS, CHANNELS[channel])
        print(f"Switched PCA9544APW to channel {channel}.")

    except Exception as e:
        print(f"Error: {e}")

def main():
    while True:
        try:
            # Get user input
            user_input = input("Enter channel number to enable (0-3, or 'q' to quit): ")
            
            # Exit if user enters 'q'
            if user_input.lower() == 'q':
                print("Program terminated.")
                break
            
            # Convert input to integer and switch channel
            channel = int(user_input)
            switch_channel(channel)
        
        except ValueError:
            print("Error: Please enter a number from 0 to 3 or 'q' to quit!")
        except Exception as e:
            print(f"Unexpected error: {e}")

if __name__ == "__main__":
    try:
        main()
    finally:
        bus.close()  # Close I2C bus on exit
