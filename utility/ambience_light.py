import minimalmodbus
import time
import json
import os
import configparser
from datetime import datetime

def get_config():
    config = configparser.ConfigParser()
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config.properties')
    config.read(config_path)
    return config

def get_status(lux, night_threshold, day_threshold):
    """Categorizes the light level into a status."""
    if lux < night_threshold:
        return "NIGHT"
    elif lux > day_threshold:
        return "DAY"
    else:
        return "TWILIGHT"

def update_json(data, output_dir):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    json_path = os.path.join(output_dir, 'ambience_light.json')
    with open(json_path, "w") as f:
        json.dump(data, f, indent=2)

def run_ambience_light_listener(callback=None):
    config = get_config()
    port = config.get('ambience_light', 'serial_port', fallback='/dev/ttyUSB2')
    slave_id = config.getint('ambience_light', 'slave_id', fallback=1)
    baud = config.getint('ambience_light', 'baud_rate', fallback=9600)
    interval = config.getfloat('ambience_light', 'polling_interval_s', fallback=5.0)
    night_thresh = config.getfloat('ambience_light', 'night_threshold', fallback=10.0)
    day_thresh = config.getfloat('ambience_light', 'day_threshold', fallback=50.0)
    output_dir = config.get('ambience_light', 'output_dir', fallback='output')

    try:
        sensor = minimalmodbus.Instrument(port, slave_id)
        sensor.serial.baudrate = baud
        sensor.serial.timeout = 1
        print(f"✅ Ambience Light: Connected to {port} (ID: {slave_id})...")
    except Exception as e:
        print(f"⚠️ Ambience Light: Failed to connect on {port}: {e}")
        return

    while True:
        try:
            # Read 32-bit value from Register 2
            raw_value = sensor.read_long(2, functioncode=3, signed=False, byteorder=0)
            lux = round(raw_value / 1000.0, 3)
            status = get_status(lux, night_thresh, day_thresh)
            
            data = {
                "lux": lux,
                "status": status,
                "last_updated": datetime.utcnow().isoformat() + "Z"
            }
            
            # Save to JSON
            update_json(data, output_dir)
            
            if callback:
                callback(data)
                
            # print(f"📢 Ambience Light: {lux} LUX ({status})")
            
        except Exception as e:
            print(f"❌ Ambience Light Error: {e}")
            if callback:
                callback({"error": str(e), "lux": None, "status": "UNKNOWN"})
                
        time.sleep(interval)

if __name__ == "__main__":
    run_ambience_light_listener(lambda d: print(f"Data: {d}"))
