import sys
from smbus2 import SMBus

# Default I2C address of PCA9544APW
I2C_ADDRESS = 0x70

# Values for each channel
CHANNELS = {
    0: 0x04,
    1: 0x05,
    2: 0x06,
    3: 0x07
}

def switch_channel(bus, channel):
    if channel not in CHANNELS:
        print(f"Error: Invalid channel {channel}. Must be 0-3.", file=sys.stderr)
        return 1  # Return error code
    try:
        bus.write_byte(I2C_ADDRESS, CHANNELS[channel])
        print(f"Switched to channel {channel}")
        return 0
    except Exception as e:
        print(f"Error switching channel {channel}: {e}", file=sys.stderr)
        return 2

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 switch.py <channel1> <channel2> ...", file=sys.stderr)
        sys.exit(1)

    # Open I2C bus
    try:
        bus = SMBus(2)  # Adjust bus number if necessary
    except Exception as e:
        print(f"Error opening I2C bus: {e}", file=sys.stderr)
        sys.exit(3)

    exit_code = 0
    try:
        for arg in sys.argv[1:]:
            try:
                channel = int(arg)
                result = switch_channel(bus, channel)
                if result != 0:
                    exit_code = result  # capture error but continue trying others
            except ValueError:
                print(f"Error: '{arg}' is not a valid number.", file=sys.stderr)
                exit_code = 1
    finally:
        bus.close()

    sys.exit(exit_code)

if __name__ == "__main__":
    main()
