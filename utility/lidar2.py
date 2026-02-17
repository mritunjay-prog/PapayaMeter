import serial
import struct
import time

# --- Configuration ---
SERIAL_PORT = '/dev/papaya_lidar'  # Common for USB adapters on Jetson
BAUD_RATE = 115200            # Default SF000/B baud rate 

def create_crc(data):
    """CRC-16-CCITT 0x1021 algorithm[cite: 559, 561]."""
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

def send_command(ser, command_id, data=None):
    """Packages and sends a command packet[cite: 541, 542]."""
    payload = bytearray([command_id])
    if data:
        payload.extend(data)
    
    # Flags: Payload length in bits 6-15, Write bit is bit 0 [cite: 545]
    # For a read command, write bit is 0. Payload length is len(payload).
    flags = len(payload) << 6
    packet_header = bytearray([0xAA]) + struct.pack('<H', flags)
    
    full_packet_for_crc = packet_header + payload
    crc = create_crc(full_packet_for_crc)
    
    packet = full_packet_for_crc + struct.pack('<H', crc)
    ser.write(packet)

def read_response(ser):
    """Reads and validates the incoming packet[cite: 568, 587]."""
    if ser.read(1) != b'\xAA':
        return None
    
    flags_raw = ser.read(2)
    flags = struct.unpack('<H', flags_raw)[0]
    payload_len = flags >> 6
    
    payload = ser.read(payload_len)
    crc_received = struct.unpack('<H', ser.read(2))[0]
    
    # Verify CRC [cite: 553]
    if create_crc(b'\xAA' + flags_raw + payload) == crc_received:
        return payload
    return None

def main():
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.1)
        print(f"Connected to {SERIAL_PORT}")

        # 1. Handshake: Request Product Name twice [cite: 534, 535]
        for _ in range(2):
            send_command(ser, 0)
            time.sleep(0.05)
        
        response = read_response(ser)
        if response:
            name = response[1:].decode('utf-8').strip('\x00')
            print(f"Sensor Identified: {name}")

        # 2. Continuous Reading Loop
        print("Starting distance readings (Press Ctrl+C to stop)...")
        while True:
            # Request Distance Data (ID 44) [cite: 622]
            send_command(ser, 44)
            res = read_response(ser)
            
            if res:
                # Command 44 returns varied data; assuming default 'First return raw' [cite: 622]
                # The first byte is the ID, following bytes are the data
                distance_cm = struct.unpack('<h', res[1:3])[0]
                
                if distance_cm == -100: # Out of range indicator [cite: 272]
                    print("Distance: Out of Range")
                else:
                    print(f"Distance: {distance_cm} cm")
            
            time.sleep(0.02) # Match sensor update rate [cite: 111]

    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        ser.close()

if __name__ == "__main__":
    main()
