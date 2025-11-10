#!/usr/bin/env python3

import os
import shutil
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path
import zipfile
import sys
import subprocess

from datetime import datetime, timedelta
import time

RUN_AT = (0, 30, 0)  # 00:30:00

# Cấu hình đường dẫn
BASE_DATA_DIR = Path.home() / "Data/Raw"
COMPRESS_DIR = Path.home() / "Data/Compress"
LOGS_DIR = Path.home() / "Data/logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOGS_DIR / "auto_compress.log"

# Tạo thư mục Compress nếu chưa tồn tại
COMPRESS_DIR.mkdir(parents=True, exist_ok=True)

# Cấu hình logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8")
    ]
)

logger = logging.getLogger("auto_compress")

def stop_existing_processes():
    script_name = os.path.basename(__file__)
    current_pid = os.getpid()
    
    logger.info(f"Checking for existing {script_name} processes...")
    
    try:
        result = subprocess.run(['pgrep', '-f', script_name], 
                              capture_output=True, text=True)
        
        if result.returncode == 0:
            pids = result.stdout.strip().split('\n')
            killed_count = 0
            
            for pid_str in pids:
                if pid_str.strip():
                    pid = int(pid_str.strip())
                    if pid != current_pid: 
                        try:
                            logger.info(f"Found existing process: PID {pid}")
                            os.kill(pid, 15)
                            time.sleep(1)

                            try:
                                os.kill(pid, 0)  
                                logger.warning(f"Forcefully killing PID {pid}")
                                os.kill(pid, 9)  # SIGKILL
                            except OSError:
                                # Process terminated
                                pass
                                
                            logger.info(f"Terminated PID {pid}")
                            killed_count += 1
                            
                        except OSError as e:
                            if e.errno != 3:  # "No such process"
                                logger.error(f"Error killing PID {pid}: {e}")
            
            if killed_count > 0:
                logger.info(f"Stopped {killed_count} existing process(es)")
                time.sleep(2)
        else:
            logger.info("No existing processes found")
            
    except FileNotFoundError:
        logger.warning("pgrep not found, skipping process cleanup")
    except Exception as e:
        logger.error(f"Error during process cleanup: {e}")

def get_yesterday_date():
    """Lấy ngày hôm trước theo định dạng YYYYMMDD"""
    yesterday = datetime.now() - timedelta(days=1)
    return yesterday.strftime("%Y%m%d")

def compress_folder_with_retry(source_folder, zip_path, max_retries=1):
    """
    Nén thư mục với cơ chế retry
    Returns: True nếu thành công, False nếu thất bại
    """
    for attempt in range(max_retries + 1):
        try:
            logger.info(f"Compressing attempt {attempt + 1}/{max_retries + 1}: {source_folder} -> {zip_path}")
            
            # Xóa file zip cũ nếu có (từ lần retry trước)
            if zip_path.exists():
                zip_path.unlink()
            
            # Tạo file zip
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zipf:
                # Thêm tất cả file và folder vào zip
                for root, dirs, files in os.walk(source_folder):
                    for file in files:
                        file_path = Path(root) / file
                        # Tạo relative path cho file trong zip
                        arcname = file_path.relative_to(source_folder.parent)
                        zipf.write(file_path, arcname)
                        
                        # Log progress cho những file lớn
                        if file_path.stat().st_size > 10 * 1024 * 1024:  # > 10MB
                            logger.info(f"Added large file: {arcname} ({file_path.stat().st_size / 1024 / 1024:.1f}MB)")
            
            # Kiểm tra file zip đã tạo thành công
            if zip_path.exists() and zip_path.stat().st_size > 0:
                original_size = sum(f.stat().st_size for f in source_folder.rglob('*') if f.is_file())
                compressed_size = zip_path.stat().st_size
                compression_ratio = (1 - compressed_size / original_size) * 100 if original_size > 0 else 0
                
                logger.info(f"Compression successful!")
                logger.info(f"Original: {original_size / 1024 / 1024:.1f}MB, Compressed: {compressed_size / 1024 / 1024:.1f}MB")
                logger.info(f"Compression ratio: {compression_ratio:.1f}%")
                return True
            else:
                logger.error(f"Zip file creation failed or empty: {zip_path}")
                
        except zipfile.BadZipFile as e:
            logger.error(f"Zip file error on attempt {attempt + 1}: {e}")
        except OSError as e:
            logger.error(f"OS error on attempt {attempt + 1}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error on attempt {attempt + 1}: {e}")
        
        # Nếu không phải lần cuối, chờ trước khi retry
        if attempt < max_retries:
            logger.info(f"Retrying in 30 seconds...")
            time.sleep(30)
    
    logger.error(f"All compression attempts failed for {source_folder}")
    return False

def cleanup_source_folder(source_folder):
    """
    Xóa thư mục nguồn sau khi nén thành công
    Returns: True nếu thành công
    """
    try:
        logger.info(f"Removing source folder: {source_folder}")
        shutil.rmtree(source_folder)
        logger.info("Source folder removed successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to remove source folder: {e}")
        return False

def daily_compression_job():
    """Job nén dữ liệu hàng ngày"""
    try:
        logger.info("="*60)
        logger.info("Starting daily compression job")
        
        # Lấy ngày hôm trước
        yesterday_str = get_yesterday_date()
        logger.info(f"Processing data for date: {yesterday_str}")
        
        # Đường dẫn thư mục nguồn
        source_folder = BASE_DATA_DIR / yesterday_str
        
        # Kiểm tra thư mục nguồn có tồn tại không
        if not source_folder.exists():
            logger.warning(f"Source folder does not exist: {source_folder}")
            logger.info("Daily compression job completed (nothing to compress)")
            return
        
        # Kiểm tra thư mục có dữ liệu không
        if not any(source_folder.rglob('*')):
            logger.warning(f"Source folder is empty: {source_folder}")
            # Vẫn xóa thư mục trống
            try:
                source_folder.rmdir()
                logger.info("Removed empty source folder")
            except:
                pass
            logger.info("Daily compression job completed (empty folder)")
            return
        
        # Đường dẫn file zip đích
        zip_filename = f"{yesterday_str}.zip"
        zip_path = COMPRESS_DIR / zip_filename
        
        # Kiểm tra xem file zip đã tồn tại chưa
        if zip_path.exists():
            logger.warning(f"Zip file already exists: {zip_path}")
            logger.info("Skipping compression (file already exists)")
            return
        
        # Thực hiện nén với retry
        success = compress_folder_with_retry(source_folder, zip_path, max_retries=1)
        
        if success:
            logger.info("Compression completed successfully")
            
            # # Xóa thư mục nguồn sau khi nén thành công
            # if cleanup_source_folder(source_folder):
            #     logger.info("Source folder cleanup completed")
            # else:
            #     logger.warning("Source folder cleanup failed, but compression was successful")
        else:
            logger.error("Daily compression job failed")
        
        logger.info("Daily compression job completed")
        logger.info("="*60)
        
    except Exception as e:
        logger.error(f"Unexpected error in daily compression job: {e}")
        logger.exception("Exception details:")

def seconds_until(h, m, s):
    now = datetime.now()
    target = now.replace(hour=h, minute=m, second=s, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()

def main():
    """Main function"""
    logger.info("Auto Daily Data Compression Script started")
    logger.info(f"Raw data directory: {BASE_DATA_DIR}")
    logger.info(f"Compress directory: {COMPRESS_DIR}")
    logger.info("Scheduled time: 00:30:00 daily")

    # Đăng ký job chạy hàng ngày lúc 00:30
    # schedule.every().day.at("00:30").do(daily_compression_job)
    
    # logger.info("Scheduler initialized, waiting for scheduled time...")
    daily_compression_job()
    # # Vòng lặp chính
    # try:
    #     while True:
    #         delay = int(seconds_until(*RUN_AT))
    #         logger.info(f"Sleeping {delay}s until next run")
    #         time.sleep(delay)
    #         daily_compression_job()
            
    # except KeyboardInterrupt:
    #     logger.info("Script interrupted by user")
    # except Exception as e:
    #     logger.error(f"Unexpected error in main loop: {e}")
    #     logger.exception("Exception details:")
    # finally:
    #     logger.info("Auto Daily Data Compression Script stopped")

if __name__ == "__main__":
    stop_existing_processes()

    main()