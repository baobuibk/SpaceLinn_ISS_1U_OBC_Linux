#!/bin/bash
USER_NAME=$(whoami) 
PYTHON_PATH="/home/$USER_NAME/.venv/bin/python"
SCRIPT_DIR="/home/$USER_NAME/.app_src/03_Source"
HANDLER_PATH="$SCRIPT_DIR/handler"
CAMERA_PATH="$SCRIPT_DIR/camera"
FOLDER_CLEAN_PATH="$SCRIPT_DIR/folderclean"
GPIO_BINARY="/home/$USER_NAME/.app_src/00_AliveBehavior/gpio_behavior"
LOG_DIR="/home/$USER_NAME/Data/logs"
mkdir -p "$LOG_DIR"
DMESG_LOG="$LOG_DIR/dmesg.log"

log_with_timestamp() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_DIR/bootstrap.log"
}

if [ -f "$DMESG_LOG" ]; then
    FILE_SIZE=$(stat -c%s "$DMESG_LOG")
    MAX_SIZE=$((30 * 1024 * 1024))
    if [ "$FILE_SIZE" -gt "$MAX_SIZE" ]; then
        echo "[BOOT] Clearing dmesg.log (size=$FILE_SIZE bytes)" >> "$LOG_DIR/bootstrap.log"
        : > "$DMESG_LOG"
    fi
fi

if ! pgrep -f "dmesg -w" > /dev/null; then
    echo "[BOOT] Starting dmesg logging..." >> "$LOG_DIR/bootstrap.log"
    nohup dmesg -w >> "$DMESG_LOG" 2>&1 &
    disown
fi

# Start existing services
if ! pgrep -f "$GPIO_BINARY" > /dev/null; then
    log_with_timestamp "[BOOT] Starting gpio_behavior..."
    nohup "$GPIO_BINARY" >> "$LOG_DIR/gpio.log" 2>&1 &
    disown
fi

if ! pgrep -f "handler.py" > /dev/null; then
    log_with_timestamp "[BOOT] Starting handler.py..."
    nohup "$PYTHON_PATH" "$HANDLER_PATH/handler.py" >> "$LOG_DIR/handler.log" 2>&1 &
    disown
fi

if ! pgrep -f "folder_clean.py" > /dev/null; then
    log_with_timestamp "[BOOT] Starting folder_clean.py..."
    nohup "$PYTHON_PATH" "$FOLDER_CLEAN_PATH/folder_clean.py" >> "$LOG_DIR/folder_clean.log" 2>&1 &
    disown
fi

if ! pgrep -f "cpu_temp_logger.py" > /dev/null; then
    log_with_timestamp "[BOOT] Starting cpu_temp_logger.py..."
    : > "$LOG_DIR/cpu_temp_logger.log"
    nohup "$PYTHON_PATH" "$HANDLER_PATH/cpu_temp_logger.py" >> "$LOG_DIR/cpu_temp_logger.log" 2>&1 &
    disown
fi

# Additional initialization commands - run sequentially with delays
log_with_timestamp "[BOOT] Starting additional initialization commands..."

# Run switchlane.py 0
log_with_timestamp "[BOOT] Running switch_lane.py 0..."
"$PYTHON_PATH" "$CAMERA_PATH/switch_lane.py" 0 >> "$LOG_DIR/switch_lane.log" 2>&1
if [ $? -eq 0 ]; then
    log_with_timestamp "[BOOT] switch_lane.py 0 completed successfully"
else
    log_with_timestamp "[ERROR] switch_lane.py 0 failed with exit code $?"
fi
sleep 0.5

# Run switchsensor.py 0
log_with_timestamp "[BOOT] Running switch_sensor.py 0..."
"$PYTHON_PATH" "$CAMERA_PATH/switch_sensor.py" 0 >> "$LOG_DIR/switch_sensor.log" 2>&1
if [ $? -eq 0 ]; then
    log_with_timestamp "[BOOT] switch_sensor.py 0 completed successfully"
else
    log_with_timestamp "[ERROR] switch_sensor.py 0 failed with exit code $?"
fi
sleep 0.5

# Run kernel module commands
log_with_timestamp "[BOOT] Running kernel module operations..."

# Rebuild module dependencies
sudo depmod -a >> "$LOG_DIR/kernel_modules.log" 2>&1
if [ $? -eq 0 ]; then
    log_with_timestamp "[BOOT] depmod -a completed successfully"
else
    log_with_timestamp "[ERROR] depmod -a failed with exit code $?"
fi
sleep 2

# Remove ar2020 module
log_with_timestamp "[BOOT] Removing ar2020 module..."
sudo modprobe -r ar2020 >> "$LOG_DIR/kernel_modules.log" 2>&1
if [ $? -eq 0 ]; then
    log_with_timestamp "[BOOT] ar2020 module removed successfully"
else
    log_with_timestamp "[WARNING] Failed to remove ar2020 module (may not be loaded)"
fi
sleep 2

# Load ar2020 module
log_with_timestamp "[BOOT] Loading ar2020 module..."
sudo modprobe ar2020 >> "$LOG_DIR/kernel_modules.log" 2>&1
if [ $? -eq 0 ]; then
    log_with_timestamp "[BOOT] ar2020 module loaded successfully"
else
    log_with_timestamp "[ERROR] Failed to load ar2020 module with exit code $?"
fi

log_with_timestamp "[BOOT] Boot sequence completed"
echo "[BOOT] Boot sequence completed - check $LOG_DIR/bootstrap.log for details"