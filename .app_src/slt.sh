#!/bin/bash

USER_NAME=$(whoami)
PYTHON_PATH="/home/$USER_NAME/.venv/bin/python"
SCRIPT_DIR="/home/$USER_NAME/.app_src/03_Source"

BG_HANDLER_PATH="$HANDLER_PATH/bg_handler.py"

HANDLER_PATH="$SCRIPT_DIR/handler"
CONTROL_PATH="$SCRIPT_DIR/control"
FOTA_PATH="$SCRIPT_DIR/fota"
LOG_FILE="$HANDLER_PATH/handler.log"

if [ ! -x "$PYTHON_PATH" ]; then
    echo "[!] <ERROR> Could not find Python at $PYTHON_PATH"
    exit 1
fi

# Function to check if handler.py is running
is_monitoring_running() {
    pgrep -f "handler.py" > /dev/null
}

# Function to get last log line if available
tail_last_log_line() {
    if [ -f "$LOG_FILE" ]; then
        tail -n 1 "$LOG_FILE"
    else
        echo "[INFO] No log file found."
    fi
}

while true; do
    clear
    if is_monitoring_running; then
        # Show last log line at very top
        echo "[Monitor]: $(tail_last_log_line)"
    fi

    echo "   ____ ___ ______  ___  ____ ___      ___  _____  __"
    echo "  / __// / /_  __/ / _ )/ __/ __/____ / _ \/ ___/<  /"
    echo " _\ \ / /__ / /   / _  / _// _/ /___// ___/ /__  / / "
    echo "/___//____//_/   /____/___/___/     /_/   \___/ /_/  "
    echo "========== System Control Panel [Rev 3.5b] =========="

    if is_monitoring_running; then
        echo "[WARNING] Monitoring is running. Please stop it before doing anything else."
        echo "1. [Stop] Monitoring"
        echo "2. [Disabled] SLT - Main Control Menu"
        echo "3. [Disabled] SLT - Firmware Update"
        echo "4. [Disabled] Run BG-Test Handler"
    else
        echo "1. [Start] Monitoring"
        echo "2. SLT - Main Control Menu"
        echo "3. SLT - Firmware Update"
        echo "4. Run BG-Test Handler"
    fi
    echo "---------"
    echo "5. Quit"
    echo "==================================================="
    read -p "Select an option (1-5): " choice

    case $choice in
        1)
            if is_monitoring_running; then
                echo -n "[INFO] Stopping monitoring (handler.py)... "
                sudo pkill -f "FOTA.py"
                sudo pkill -f "control.py"     
                sudo pkill -f "handler.py"
                sudo pkill -f "bg_handler.py"
                echo "Done."
            else
                echo "[INFO] Starting monitoring (handler.py) in background..."
                "$PYTHON_PATH" "$HANDLER_PATH/handler.py" &>/dev/null &
                echo "[INFO] Monitoring started."
            fi
            read -p "Press Enter to return to menu..."
            ;;
        2)
            if is_monitoring_running; then
                echo "[ERROR] Monitoring is active. Stop it before running control.py."
                read -p "Press Enter to return to menu..."
            else
                echo "[INFO] Stopping all Python processes..."
                sudo pkill -f "FOTA.py"
                sudo pkill -f "control.py"     
                sudo pkill -f "handler.py"
                sudo pkill -f "bg_handler.py"
                echo "[INFO] Running control.py..."
                "$PYTHON_PATH" "$CONTROL_PATH/control.py"
                read -p "Press Enter to return to menu..."
            fi
            ;;
        3)
            if is_monitoring_running; then
                echo "[ERROR] Monitoring is active. Stop it before running ota.py."
                read -p "Press Enter to return to menu..."
            else
                echo "[INFO] Stopping all Python processes..."
                sudo pkill -f "FOTA.py"
                sudo pkill -f "control.py"     
                sudo pkill -f "handler.py"
                sudo pkill -f "bg_handler.py"
                echo "[INFO] Running ota.py..."
                "$PYTHON_PATH" "$FOTA_PATH/FOTA.py"
                read -p "Press Enter to return to menu..."
            fi
            ;;
        4)
            if is_monitoring_running; then
                echo "[ERROR] Monitoring is active. Stop it before running bg_handler.py."
                read -p "Press Enter to return to menu..."
            else
                echo "[INFO] Stopping all Python processes..."
                sudo pkill -f "FOTA.py"
                sudo pkill -f "control.py"
                sudo pkill -f "handler.py"
                sudo pkill -f "bg_handler.py"
                echo "[INFO] Running bg_handler.py..."
                "$PYTHON_PATH" "$HANDLER_PATH/bg_handler.py"
                read -p "Press Enter to return to menu..."
            fi
            ;;
        5)
            if is_monitoring_running; then
                echo "[INFO] Monitoring is running. Exiting..."
                echo "[OK] Quit."
                exit 0
            else
                echo "[WARNING] Monitoring is not running!"
                read -p "Are you sure you want to quit without starting monitoring? (y/N): " confirm_quit
                case "$confirm_quit" in
                    [yY][eE][sS]|[yY])
                        echo "[OK] Quit."
                        exit 0
                        ;;
                    *)
                        echo "[INFO] Returning to menu..."
                        ;;
                esac
            fi
            ;;
        *)
            echo "[ERROR] Invalid selection. Please choose between 1 and 4."
            read -p "Press Enter to return to menu..."
            ;;
    esac
done
