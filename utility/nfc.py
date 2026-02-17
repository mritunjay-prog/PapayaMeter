import serial
import time
import json
import csv
import os
import configparser
from datetime import datetime

def get_config():
    config = configparser.ConfigParser()
    config_path = os.path.join(os.path.dirname(__file__), 'config.properties')
    # If not found in current dir, check parent (if this script is in utility/)
    if not os.path.exists(config_path):
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config.properties')
    config.read(config_path)
    return config

def run_nfc_listener(callback=None):
    config = get_config()
    
    # Configuration from config.properties
    SERIAL_PORT = config.get('nfc', 'serial_port', fallback='/dev/ttyACM0')
    BAUD_RATE = config.getint('nfc', 'baud_rate', fallback=115200)
    OUTPUT_DIR = config.get('nfc', 'output_dir', fallback='output')
    
    CSV_FILE = os.path.join(OUTPUT_DIR, "nfc_log.csv")
    JSON_FILE = os.path.join(OUTPUT_DIR, "nfc_data.json")

    # Ensure output directory exists
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    # Initialize Serial
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.1)
        ser.dtr = True
        print(f"✅ NFC: Connected to {SERIAL_PORT}. Saving to '{OUTPUT_DIR}'...")
    except Exception as e:
        print(f"❌ NFC Connection Error: {e}")
        # Allow program to continue without NFC if hardware is missing
        return

    def log_data(raw_line):
        try:
            # Split data from Pico: UID|TYPE|TIME
            parts = raw_line.split('|')
            if len(parts) < 3:
                return
                
            uid_raw = parts[0]
            card_type = parts[1]
            read_time = int(parts[2])
            
            now = datetime.now()
            timestamp_ms = int(now.timestamp() * 1000)
            formatted_uid = ":".join([uid_raw[i:i+2].upper() for i in range(0, len(uid_raw), 2)])

            # 1. Build JSON Object
            data = {
                "ts": timestamp_ms,
                "values": {
                    "nfc.card_detected": True,
                    "nfc.card_type": card_type,
                    "nfc.uid": formatted_uid,
                    "nfc.read_success": True,
                    "nfc.rssi_dbm": -45,
                    "nfc.read_time_ms": read_time,
                    "nfc.anti_collision_count": 0
                }
            }

            # 2. Save JSON (Overwrites with latest tap)
            with open(JSON_FILE, "w") as jf:
                json.dump(data, jf, indent=4)
                
            # 3. Save CSV (Appends to history)
            file_exists = os.path.isfile(CSV_FILE)
            with open(CSV_FILE, "a", newline='') as cf:
                writer = csv.writer(cf)
                if not file_exists:
                    writer.writerow(["Timestamp", "UID", "Type", "ReadTime_ms"])
                writer.writerow([now.strftime('%Y-%m-%d %H:%M:%S'), formatted_uid, card_type, read_time])
                
            print(f"📢 NFC Tap: {formatted_uid}")
            
            # Send to callback if provided (for GUI integration)
            if callback:
                callback(data)

        except Exception as e:
            print(f"⚠️ Error processing NFC data: {e}")

    try:
        while True:
            if ser.in_waiting > 0:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                if "|" in line:
                    log_data(line)
            time.sleep(0.01)
    except KeyboardInterrupt:
        print("Closing NFC listener...")
    finally:
        ser.close()

if __name__ == "__main__":
    run_nfc_listener()
