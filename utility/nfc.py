import serial
import time
import json
import csv
import os
from datetime import datetime

# Configuration
SERIAL_PORT = '/dev/ttyACM0'
BAUD_RATE = 115200
OUTPUT_DIR = "output"  # The folder must already exist
CSV_FILE = os.path.join(OUTPUT_DIR, "nfc_log.csv")
JSON_FILE = os.path.join(OUTPUT_DIR, "nfc_data.json")

# Initialize Serial
try:
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.1)
    ser.dtr = True
    print(f"Connected. Saving files to the '{OUTPUT_DIR}' folder...")
except Exception as e:
    print(f"Connection Error: {e}")
    exit()

def log_data(raw_line):
    try:
        # Split data from Pico: UID|TYPE|TIME
        parts = raw_line.split('|')
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
            # Add header if it's a new file
            if not file_exists:
                writer.writerow(["Timestamp", "UID", "Type", "ReadTime_ms"])
            writer.writerow([now.strftime('%Y-%m-%d %H:%M:%S'), formatted_uid, card_type, read_time])
            
        print(f"Logged: {formatted_uid} to {OUTPUT_DIR}/")

    except Exception as e:
        print(f"Error processing data: {e}")

while True:
    if ser.in_waiting > 0:
        line = ser.readline().decode('utf-8').strip()
        if "|" in line:
            log_data(line)
    time.sleep(0.01)
