import serial
import time
import json
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

# UART Commands from Datasheet
CMD_START = b'\xFE\xA5\x00\x11\xB6'  # Start measurement
CMD_STOP  = b'\xFE\xA5\x00\x10\xB5'  # Stop measurement
CMD_READ  = b'\xFE\xA5\x00\x01\xA6'  # Read PM1.0, PM2.5, PM10

def verify_checksum(data):
    # Checksum = low byte of (Fixed code + length + command code + data)
    calculated_cs = sum(data[1:10]) & 0xFF
    return calculated_cs == data[10]

def get_measurements(ser):
    ser.reset_input_buffer()
    ser.write(CMD_READ)
    
    header = ser.read(1)
    if header == b'\xFE': 
        remaining = ser.read(10)
        if len(remaining) == 10:
            full_frame = header + remaining
            if verify_checksum(full_frame):
                # Data indices based on Table 10
                pm1_0 = (full_frame[4] * 256) + full_frame[5]
                pm2_5 = (full_frame[6] * 256) + full_frame[7]
                pm10  = (full_frame[8] * 256) + full_frame[9]
                return pm1_0, pm2_5, pm10
    return None

def update_airquality_json(pm1_0, pm2_5, pm10, output_dir):
    """Create or update airquality.json with the latest PM readings."""
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    json_path = os.path.join(output_dir, 'airquality.json')
    data = {
        "PM1.0": pm1_0,
        "PM2.5": pm2_5,
        "PM10": pm10,
        "last_updated": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
    }
    with open(json_path, "w") as f:
        json.dump(data, f, indent=2)

def run_air_quality_listener(callback=None):
    config = get_config()
    
    # Configuration from config.properties
    SERIAL_PORT = config.get('airquality', 'serial_port', fallback='/dev/ttyUSB2')
    BAUD_RATE = config.getint('airquality', 'baud_rate', fallback=1200)
    TIMEOUT = config.getint('airquality', 'timeout', fallback=1)
    OUTPUT_DIR = config.get('airquality', 'output_dir', fallback='output')

    # Initialize Serial
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=TIMEOUT)
        print(f"✅ AirQuality: Connected to {SERIAL_PORT}. Saving to '{OUTPUT_DIR}'...")
    except Exception as e:
        print(f"❌ AirQuality Connection Error: {e}")
        return

    try:
        while True:
            # Wake up sensor (Fan and laser start)
            ser.write(CMD_START)
            time.sleep(5) # Allow stabilization

            list_pm10, list_pm25, list_pm100 = [], [], []
            
            # Collect 5 readings with 1 second gap 
            while len(list_pm25) < 5:
                vals = get_measurements(ser)
                if vals:
                    list_pm10.append(vals[0])
                    list_pm25.append(vals[1])
                    list_pm100.append(vals[2])
                time.sleep(1)

            # Enter Standby Mode (Fan and laser off)
            ser.write(CMD_STOP)

            # Generate averages
            avg_pm1_0 = round(sum(list_pm10) / 5, 2)
            avg_pm2_5 = round(sum(list_pm25) / 5, 2)
            avg_pm10 = round(sum(list_pm100) / 5, 2)

            output_dict = {
                "PM1.0": avg_pm1_0,
                "PM2.5": avg_pm2_5,
                "PM10":  avg_pm10
            }

            print(f"📢 AirQuality Update: {output_dict}")
            
            # Save to JSON
            update_airquality_json(avg_pm1_0, avg_pm2_5, avg_pm10, OUTPUT_DIR)
            
            # Send to callback if provided
            if callback:
                callback(output_dict)
            
            # Duty cycle: Sleep before next measurement block
            time.sleep(1) # As requested by current script (though duty cycle usually longer)
            
    except KeyboardInterrupt:
        print("Closing AirQuality listener...")
    finally:
        ser.close()

if __name__ == "__main__":
    run_air_quality_listener()
