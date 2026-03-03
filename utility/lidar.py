import serial
import time
import json
import struct
from datetime import datetime
import configparser
import os

# CRC-16-CCITT calculation as specified in the SF000/B manual [cite: 559, 561]
def create_crc(data):
    """CRC-16-CCITT 0x1021 algorithm."""
    crc = 0
    for byte in data:
        code = (crc >> 8) & 0xFF
        code ^= byte & 0xFF
        code ^= code >> 4
        crc = (crc << 8) & 0xFFFF
        crc ^= code
        code = (code << 5) & 0xFFFF
        crc ^= code
        code = (code << 7) & 0xFFFF
        crc ^= code
    return crc

def get_config():
    config = configparser.ConfigParser()
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config.properties')
    config.read(config_path)
    return config

def send_command(ser, command_id, data=None):
    """Packages and sends a command packet."""
    payload = bytearray([command_id])
    if data:
        payload.extend(data)
    
    # Flags: Payload length in bits 6-15, Write bit is bit 0
    flags = len(payload) << 6
    packet_header = bytearray([0xAA]) + struct.pack('<H', flags)
    
    full_packet_for_crc = packet_header + payload
    crc = create_crc(full_packet_for_crc)
    
    packet = full_packet_for_crc + struct.pack('<H', crc)
    ser.write(packet)

def read_response(ser):
    """Reads and validates the incoming packet."""
    start_byte = ser.read(1)
    if start_byte != b'\xAA':
        return None
    
    flags_raw = ser.read(2)
    if len(flags_raw) < 2: return None
    flags = struct.unpack('<H', flags_raw)[0]
    payload_len = flags >> 6
    
    payload = ser.read(payload_len)
    if len(payload) < payload_len: return None

    crc_raw = ser.read(2)
    if len(crc_raw) < 2: return None
    crc_received = struct.unpack('<H', crc_raw)[0]
    
    # Verify CRC
    if create_crc(b'\xAA' + flags_raw + payload) == crc_received:
        return payload
    return None

def run_detector(section_name='lidar_left', callback=None):
    config = get_config()
    
    port = config.get(section_name, 'serial_port', fallback='/dev/papaya_lidar')
    baud = config.getint(section_name, 'baud_rate', fallback=115200)
    max_range = config.getint(section_name, 'max_range_cm', fallback=500)
    interval = config.getint(section_name, 'polling_interval_ms', fallback=100) / 1000.0
    output_dir = config.get(section_name, 'lidar_output_path', fallback=f'./lidar_data/{section_name}/')
    
    # Ensure directory exists
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    retry_count = 0
    max_retries = 3
    last_error_time = 0
    error_cooldown = 30

    def send_error(error_desc):
        nonlocal last_error_time
        current_time = time.time()
        if callback and (current_time - last_error_time > error_cooldown):
            error_payload = {
                "sensor": section_name,
                "lidar.error.type": "communication_timeout",
                "lidar.error.code": "LD_ERR_001",
                "lidar.error.severity": "warning",
                "lidar.error.retry_count": retry_count,
                "lidar.error.description": error_desc
            }
            callback(error_payload)
            last_error_time = current_time
            print(f"⚠️ [{section_name}] Error reported: {error_desc}")

    try:
        ser = serial.Serial(port, baud, timeout=0.1)
        print(f"✅ Connected to SF000/B ({section_name}) on {port}")
        
        # 1. Handshake: Request Product Name twice (Logic from lidar2.py)
        # This seems critical for initializing the session properly
        for _ in range(2):
            send_command(ser, 0)
            time.sleep(0.05)
        
        response = read_response(ser)
        if response:
            try:
                name = response[1:].decode('utf-8', errors='ignore').strip('\x00')
                print(f"✅ Sensor [{section_name}] Identified: {name}")
            except:
                pass

    except Exception as e:
        error_msg = f"Failed to open/init serial port {port}: {e}"
        print(f"⚠️ [{section_name}] {error_msg}")
        send_error(error_msg)
        return

    # 2. Continuous Reading Loop
    print(f"🚀 Starting LiDAR [{section_name}] data collection...")
    while True:
        try:
            # Request Distance Data (ID 44)
            send_command(ser, 44)
            res = read_response(ser)
            
            if res:
                retry_count = 0
                
                # Command 44 returns varied data; assuming default 'First return raw'
                # The first byte is the ID, following bytes are the data
                try:
                    distance_cm = struct.unpack('<h', res[1:3])[0]
                except Exception as ex:
                    print(f"[{section_name}] Error unpacking: {ex}")
                    continue
                
                out_of_range = False
                if distance_cm == -100 or distance_cm <= 0:
                    out_of_range = True
                
                # Logic: Occupancy is detected if distance is within configured max_range
                if not out_of_range and distance_cm <= max_range:
                    status = {
                        "sensor": section_name,
                        "distance_cm": distance_cm,
                        "out_of_range": False,
                        "last_updated": datetime.utcnow().isoformat() + "Z"
                    }
                else:
                    status = {
                        "sensor": section_name,
                        "distance_cm": distance_cm if not out_of_range else -1,
                        "out_of_range": True,
                        "last_updated": datetime.utcnow().isoformat() + "Z"
                    }
                
                # print(f"[{section_name}] {json.dumps(status, indent=2)}")
                
                # Save to daily file (Appending)
                try:
                    filename = datetime.now().strftime('%Y-%m-%d') + '.json'
                    full_path = os.path.join(output_dir, filename)
                    with open(full_path, 'a') as f:
                        f.write(json.dumps(status) + '\n')
                except Exception as e:
                    print(f"Error appending to file {filename} for {section_name}: {e}")

                # Send to callback
                if callback:
                    callback(status)
            else:
                retry_count += 1
                # Only warn if retries pile up, to avoid spamming tight loops
                if retry_count % 10 == 0:
                    print(f"⚠️ LiDAR [{section_name}] Timeout/Invalid Data (Retry {retry_count})")
                
                if retry_count >= 50 and (retry_count % 50 == 0):
                    send_error(f"No response from LiDAR [{section_name}] module after {retry_count} attempts")

        except Exception as e:
            retry_count += 1
            print(f"❌ Serial Error [{section_name}]: {e}")
            time.sleep(1)

        time.sleep(interval)

if __name__ == "__main__":
    import sys
    section = sys.argv[1] if len(sys.argv) > 1 else 'lidar_left'
    run_detector(section_name=section)