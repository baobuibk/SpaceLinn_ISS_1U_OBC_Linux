#!/usr/bin/env python3
import os
import re
import time
import shutil
from pathlib import Path

BASE_DIR = Path.home() / "Data/Raw"
CHECK_INTERVAL = 60 * 5      
PATTERN = re.compile(r"^\d{8}$")

# Storage thresholds
STORAGE_THRESHOLD = 80.0  # 80%
EMERGENCY_KEEP_COUNT = 3  # Keep today + 2 recent days when storage > 80%
NORMAL_KEEP_COUNT = 4     # Normal mode: keep 4 most recent

def get_valid_folders(path: Path):
    """Get folders matching YYYYMMDD pattern, sorted by modification time (newest first)"""
    folders = [f for f in path.iterdir() if f.is_dir() and PATTERN.match(f.name)]
    folders.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return folders

def get_storage_usage(path: Path):
    """Get storage usage percentage for the given path"""
    try:
        stat = shutil.disk_usage(path)
        used_percent = (stat.used / stat.total) * 100
        return used_percent
    except Exception as e:
        print(f"[WARNING] Could not get storage usage: {e}")
        return 0.0

def clean_old_folders():
    """Clean old folders based on storage usage and retention policy"""
    folders = get_valid_folders(BASE_DIR)
    
    if not folders:
        print("[INFO] No folders found to clean")
        return
    
    # Get current storage usage
    storage_usage = get_storage_usage(BASE_DIR)
    print(f"[INFO] Current storage usage: {storage_usage:.1f}%")
    
    # Determine how many folders to keep based on storage usage
    if storage_usage > STORAGE_THRESHOLD:
        keep_count = EMERGENCY_KEEP_COUNT
        print(f"[WARNING] Storage usage above {STORAGE_THRESHOLD}% - Emergency mode: keeping only {keep_count} folders")
    else:
        keep_count = NORMAL_KEEP_COUNT
        print(f"[INFO] Normal mode: keeping {keep_count} folders")
    
    # Clean old folders if we have more than the keep count
    if len(folders) > keep_count:
        folders_to_keep = folders[:keep_count]
        folders_to_delete = folders[keep_count:]
        
        print(f"[INFO] Keeping folders: {[f.name for f in folders_to_keep]}")
        print(f"[INFO] Deleting {len(folders_to_delete)} old folders")
        
        for folder in folders_to_delete:
            try:
                print(f"[CLEANUP] Deleting {folder}")
                shutil.rmtree(folder, ignore_errors=True)
            except Exception as e:
                print(f"[ERROR] Failed to delete {folder}: {e}")
        
        # Check storage again after cleanup
        new_storage_usage = get_storage_usage(BASE_DIR)
        print(f"[INFO] Storage usage after cleanup: {new_storage_usage:.1f}%")
    else:
        print(f"[INFO] Only {len(folders)} folders found, no cleanup needed")

def main():
    """Main loop"""
    print(f"[START] Folder cleanup service started")
    print(f"[CONFIG] Base directory: {BASE_DIR}")
    print(f"[CONFIG] Check interval: {CHECK_INTERVAL} seconds")
    print(f"[CONFIG] Storage threshold: {STORAGE_THRESHOLD}%")
    print(f"[CONFIG] Normal keep count: {NORMAL_KEEP_COUNT}")
    print(f"[CONFIG] Emergency keep count: {EMERGENCY_KEEP_COUNT}")
    
    while True:
        try:
            print(f"\n[CHECK] {time.strftime('%Y-%m-%d %H:%M:%S')}")
            clean_old_folders()
        except Exception as e:
            print(f"[ERROR] {e}")
        
        print(f"[SLEEP] Waiting {CHECK_INTERVAL} seconds until next check...")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()