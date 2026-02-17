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

def build_request_packet(command_id, data=None):
    """Packages a command packet with dynamic flags[cite: 541, 542]."""
    payload = bytearray([command_id])
    if data:
        payload.extend(data)
    
    # Flags: Payload length in bits 6-15, Write bit is bit 0 [cite: 545]
    # For a read command, write bit is 0.
    flags = len(payload) << 6
    
    packet_header = bytearray([0xAA]) + struct.pack('<H', flags)
    packet_payload = payload
    
    # Calculate CRC on everything except CRC itself [cite: 554]
    crc = create_crc(packet_header + packet_payload)
    return packet_header + packet_payload + struct.pack('<H', crc)

def read_response(ser):
    """Reads and validates the incoming packet dynamically[cite: 568, 587]."""
    start_byte = ser.read(1)
    if start_byte != b'\xAA':
        return None
    
    flags_raw = ser.read(2)
    if not flags_raw or len(flags_raw) < 2:
        return None
        
    flags = struct.unpack('<H', flags_raw)[0]
    payload_len = flags >> 6
    
    payload = ser.read(payload_len)
    if not payload or len(payload) < payload_len:
        return None
        
    crc_raw = ser.read(2)
    if not crc_raw or len(crc_raw) < 2:
        return None
        
    crc_received = struct.unpack('<H', crc_raw)[0]
    
    # Verify CRC [cite: 553]
    if create_crc(b'\xAA' + flags_raw + payload) == crc_received:
        return payload
    return None

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
            
            # Use dynamic response reader instead of fixed 8-byte read
            res = read_response(ser)
            
            if res:
                retry_count = 0  # Reset on success
                
                # Command 44 returns varied data. 
                # According to SF000/B protocol, response payload starts with Command ID (1 byte)
                # Distance is usually a 2-byte signed integer at index 1-2 [cite: 622]
                distance_cm = struct.unpack('<h', res[1:3])[0]
                
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