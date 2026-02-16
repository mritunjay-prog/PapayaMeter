import serial
import time
import json
import struct
from datetime import datetime
import configparser
import os

# CRC-16-CCITT calculation as specified in the SF000/B manual [cite: 559, 561]
def create_crc(data):
    crc = 0
    for byte in data:
        code = (crc >> 8) & 0xFF
        code ^= byte & 0xFF
        code ^= (code >> 4)
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

def build_request_packet(command_id):
    # Header: Start byte (0xAA) [cite: 546]
    # Flags: 16-bit. Payload length (ID byte = 1) and Read bit (0) [cite: 545, 547]
    start_byte = 0xAA
    flags = 1 << 1 # Payload length of 1, Read mode [cite: 545]
    payload = [command_id]
    
    packet_header = struct.pack('<BH', start_byte, flags)
    packet_payload = bytearray(payload)
    
    # Calculate CRC on everything except CRC itself [cite: 554]
    crc = create_crc(packet_header + packet_payload)
    return packet_header + packet_payload + struct.pack('<H', crc)

def run_detector(callback=None):
    config = get_config()
    
    port = config.get('lidar', 'serial_port', fallback='COM3')
    baud = config.getint('lidar', 'baud_rate', fallback=115200)
    max_range = config.getint('lidar', 'max_range_cm', fallback=500)
    interval = config.getint('lidar', 'polling_interval_ms', fallback=100) / 1000.0
    output_dir = config.get('lidar', 'lidar_output_path', fallback='./lidar_data/')
    
    # Ensure directory exists
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    retry_count = 0
    max_retries = 3
    last_error_time = 0
    error_cooldown = 30  # Don't spam errors more than once every 30 seconds

    def send_error(error_desc):
        nonlocal last_error_time
        current_time = time.time()
        if callback and (current_time - last_error_time > error_cooldown):
            error_payload = {
                "lidar.error.type": "communication_timeout",
                "lidar.error.code": "LD_ERR_001",
                "lidar.error.severity": "warning",
                "lidar.error.retry_count": retry_count,
                "lidar.error.description": error_desc
            }
            callback(error_payload)
            last_error_time = current_time
            print(f"⚠️ Error reported to ThingsBoard: {error_desc}")



    try:
        ser = serial.Serial(port, baud, timeout=0.1)
        print(f"✅ Connected to SF000/B on {port}")
    except Exception as e:
        error_msg = f"Failed to open serial port {port}: {e}"
        print(f"⚠️ {error_msg}")
        print(f"🔄 LiDAR hardware not available, skipping sensor data collection...")
        send_error(error_msg)
        # Return early - don't send simulated data, let main program continue
        return

    # Main data collection loop - only runs if hardware is available
    request = build_request_packet(44)
    while True:
        try:
            ser.write(request)
            # Response: Start(1) + Flags(2) + ID(1) + Data(2) + CRC(2) = 8 bytes
            response = ser.read(8)
            
            if len(response) == 8 and response[0] == 0xAA:
                retry_count = 0  # Reset on success
                # Distance is a signed 16-bit integer at index 4-5
                distance_cm = struct.unpack('<h', response[4:6])[0]
                
                # -1.00 indicates out-of-range
                out_of_range = False
                if distance_cm == -100 or distance_cm <= 0:
                    out_of_range = True
                
                # Logic: Occupancy is detected if distance is within configured max_range
                if not out_of_range and distance_cm <= max_range:
                    status = {
                        "distance_cm": distance_cm,
                        "out_of_range": False,
                        "last_updated": datetime.utcnow().isoformat() + "Z"
                    }
                else:
                    status = {
                        "distance_cm": distance_cm if not out_of_range else -1,
                        "out_of_range": True,
                        "last_updated": datetime.utcnow().isoformat() + "Z"
                    }
                
                print(json.dumps(status, indent=2))
                
                # Save to daily file (Appending)
                try:
                    filename = datetime.now().strftime('%Y-%m-%d') + '.json'
                    full_path = os.path.join(output_dir, filename)
                    with open(full_path, 'a') as f:
                        f.write(json.dumps(status) + '\n')
                except Exception as e:
                    print(f"Error appending to file {filename}: {e}")

                # Send to callback
                if callback:
                    callback(status)
            else:
                retry_count += 1
                print(f"⚠️ LiDAR Timeout/Invalid Data (Retry {retry_count}/{max_retries})")
                if retry_count >= max_retries:
                    send_error(f"No response from LiDAR module after {max_retries} attempts")

        except Exception as e:
            retry_count += 1
            print(f"❌ Serial Error: {e}")
            if retry_count >= max_retries:
                send_error(f"Serial communication error: {e}")
            time.sleep(1) # Extra wait on physical/serial error

        time.sleep(interval)

if __name__ == "__main__":
    run_detector()