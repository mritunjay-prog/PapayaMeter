import time
import json
import os
import configparser
from datetime import datetime
from smbus2 import SMBus

def get_config():
    config = configparser.ConfigParser()
    config_path = os.path.join(os.path.dirname(__file__), 'config.properties')
    if not os.path.exists(config_path):
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config.properties')
    config.read(config_path)
    return config

# SHT3x single-shot high repeatability command (no clock stretching)
MEASURE_CMD = [0x24, 0x00]

def read_sht3x(bus_id, address):
    try:
        with SMBus(bus_id) as bus:
            # Send measurement command
            bus.write_i2c_block_data(address, MEASURE_CMD[0], [MEASURE_CMD[1]])
            time.sleep(0.02)  # 20 ms measurement time

            # Read 6 bytes: T(msb,lsb,crc), RH(msb,lsb,crc)
            data = bus.read_i2c_block_data(address, 0x00, 6)

            temp_raw = data[0] << 8 | data[1]
            hum_raw  = data[3] << 8 | data[4]

            temperature = -45 + (175 * temp_raw / 65535.0)
            humidity = 100 * hum_raw / 65535.0

            return temperature, humidity
    except Exception as e:
        print(f"I2C Read Error on bus {bus_id}, address {hex(address)}: {e}")
        return None, None

def update_json(temp, hum, output_dir):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    json_path = os.path.join(output_dir, 'temp_hum.json')
    data = {
        "temperature": round(temp, 2) if temp is not None else None,
        "humidity": round(hum, 2) if hum is not None else None,
        "last_updated": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    }
    with open(json_path, "w") as f:
        json.dump(data, f, indent=2)

def run_temp_hum_listener(callback=None):
    config = get_config()
    bus_id = config.getint('temperature', 'i2c_bus', fallback=7)
    address = int(config.get('temperature', 'i2c_address', fallback='0x44'), 16)
    interval = config.getfloat('temperature', 'polling_interval_s', fallback=1.0)
    output_dir = config.get('temperature', 'output_dir', fallback='output')

    print(f"✅ Temp/Hum: Monitoring I2C Bus {bus_id} at {hex(address)}...")

    try:
        while True:
            t, h = read_sht3x(bus_id, address)
            
            # Save to JSON
            update_json(t, h, output_dir)
            
            # Print status
            if t is not None:
                print(f"📢 Temp/Hum Update: {t:.2f} °C, {h:.2f} %")
                if callback:
                    callback({"temperature": t, "humidity": h})
            else:
                print("⚠️ Temp/Hum: Sensor not responding")
                if callback:
                    callback({"temperature": None, "humidity": None})
            
            time.sleep(interval)
    except KeyboardInterrupt:
        print("Closing Temp/Hum listener...")

if __name__ == "__main__":
    run_temp_hum_listener()
