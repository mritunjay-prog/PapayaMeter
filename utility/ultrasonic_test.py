import serial
import time

# For Jetson via CP2102, this is usually /dev/ttyUSB0 or /dev/ttyUSB1
SERIAL_PORT = '/dev/papaya_ultrasonic'
BAUD_RATE = 9600

def read_sen0207():
    try:
        # Initialize serial with a short timeout to prevent blocking
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.1)
        print(f"Connected to {SERIAL_PORT} successfully.")
    except Exception as e:
        print(f"Failed to connect: {e}")
        return

    try:
        while True:
            # Check if there is enough data in the buffer (4 bytes per packet)
            if ser.in_waiting >= 4:
                # Look for the header byte 0xFF
                header = ser.read(1)
                if header == b'\xff':
                    data = ser.read(3)
                    if len(data) == 3:
                        h_data = data[0]
                        l_data = data[1]
                        checksum = data[2]

                        # Validate packet integrity
                        if (0xFF + h_data + l_data) & 0xFF == checksum:
                            # Formula from Wiki: Distance = (H<<8) + L (in mm)
                            distance_mm = (h_data << 8) + l_data
                            distance_cm = distance_mm / 10.0

                            if distance_mm > 0:
                                print(f"Distance: {distance_cm:>6.1f} cm")
                            else:
                                print("Distance: Out of Range / Dead Zone")
                        else:
                            print("Checksum mismatch - ignoring packet.")

            # Small sleep to manage CPU usage on the Jetson
            time.sleep(0.05)

    except KeyboardInterrupt:
        print("\nClosing connection...")
    finally:
        ser.close()

if __name__ == "__main__":
    read_sen0207()

