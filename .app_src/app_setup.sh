#!/bin/bash

# === CONFIG TIME TO RUN auto_compress.py ===
# Note: The time must be within the [start time] and [end time] range

HOUR=5
MINUTE=15

dir="$HOME"
echo $dir

if [ ! -e "$1" ]; then
    echo "$1 not exist"
    exit 1
fi

echo "1. Cleanning current app"
echo "1.1 Remove .app_src"
sudo rm -rf $dir/.app_src
# echo "1.2 Remove Configuration"
# sudo rm -rf $dir/Configuration
echo "1.2 Remove FirmwareUpdate" 
sudo rm -rf $dir/FirmwareUpdate

echo "1.3 Create Configuration if not exists"
if [ ! -d "$dir/Configuration" ]; then
    mkdir -p "$dir/Configuration"
    echo "-> Configuration directory created."
else
    echo "-> Configuration directory already exists. Skipped."
fi

echo "1.4 Create ./Data/logs if not exists"
if [ ! -d "$dir/Data/logs" ]; then
    mkdir -p "$dir/Data/logs"
    echo "-> Data/logs directory created."
else
    echo "-> Data/logs directory already exists. Skipped."
fi

echo "2. Unzipping $1"
unzip $1 -d $dir

echo "3. Update script mode"
sudo chmod +x $dir/.app_src/*.sh $dir/.app_src/00_AliveBehavior/gpio_behavior $dir/.app_src/01_RunOnBoot/*.sh

echo "4. Updating crontab time for auto_compress.py"

crontab -l > /tmp/current_cron || touch /tmp/current_cron

# Replace the old line with the new time
sed -i "/auto_compress\.py/ s/^[0-9]\+ [0-9]\+ /$MINUTE $HOUR /" /tmp/current_cron

crontab /tmp/current_cron

echo "Crontab updated to run auto_compress.py at $HOUR:$MINUTE"

echo "Done./."