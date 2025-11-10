#!/usr/bin/env python3

import time
import logging
from datetime import datetime
from pathlib import Path

log_dir = Path.home() / "Data" / "logs"
log_dir.mkdir(parents=True, exist_ok=True)

log_file = log_dir / "cpu_temperature.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler(log_file, mode='a'),
        logging.StreamHandler()
    ]
)

cpu_temp_path = Path("/sys/class/thermal/thermal_zone0/temp")

def read_cpu_temp():
    try:
        temp_str = cpu_temp_path.read_text().strip()
        temp_celsius = int(temp_str) / 1000.0
        return temp_celsius
    except FileNotFoundError:
        logging.error("CPU temperature file not found.")
        return None
    except Exception as e:
        logging.exception(f"Unexpected error reading temperature: {e}")
        return None

def write_boot_separator():
    separator = "=" * 60
    boot_time = datetime.now().strftime("New boot at %Y-%m-%d %H:%M:%S")
    with open(log_file, "a") as f:
        f.write(f"\n{separator}\n{boot_time}\n{separator}\n\n")

def log_temperature_forever(interval_seconds=10):
    write_boot_separator()
    while True:
        temp = read_cpu_temp()
        if temp is not None:
            logging.info(f"CPU Temperature: {temp:.2f} °C")
        else:
            logging.warning("Could not read CPU temperature.")
        time.sleep(interval_seconds)

if __name__ == "__main__":
    log_temperature_forever()
