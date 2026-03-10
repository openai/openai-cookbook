import os
import time
import hashlib
import logging

logging.basicConfig(filename="system_monitor.log", level=logging.INFO, format="%(asctime)s - %(message)s")

WATCHED_DIRS = ["/var/log", "/etc", "/home/user/important_files"]
HASH_MAP = {}

def get_file_hash(file_path):
    try:
        with open(file_path, "rb") as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()
        return file_hash
    except Exception as e:
        logging.error(f"Fehler beim Lesen der Datei {file_path}: {e}")
        return None

def initialize_hashes():
    for directory in WATCHED_DIRS:
        if os.path.exists(directory):
            for root, _, files in os.walk(directory):
                for file in files:
                    file_path = os.path.join(root, file)
                    HASH_MAP[file_path] = get_file_hash(file_path)

def monitor_changes():
    while True:
        for file_path in HASH_MAP.keys():
            if os.path.exists(file_path):
                new_hash = get_file_hash(file_path)
                if new_hash and HASH_MAP[file_path] != new_hash:
                    logging.warning(f"Manipulation erkannt: {file_path} wurde geändert!")
                    HASH_MAP[file_path] = new_hash  
        time.sleep(10)

initialize_hashes()
monitor_changes()
