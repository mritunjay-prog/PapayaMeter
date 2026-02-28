import serial
import time
import configparser
import os

def get_config():
    config = configparser.ConfigParser()
    # Path to config.properties relative to this script
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config.properties')
    config.read(config_path)
    return config

class UltrasonicSensor:
    def __init__(self, name, port, baud, threshold):
        self.name = name
        self.port = port
        self.baud = baud
        self.threshold = threshold
        self.ser = None

    def connect(self):
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=0.1)
            print(f"✅ Connected to {self.name} on {self.port} successfully.")
            return True
        except Exception as e:
            print(f"⚠️ Failed to connect to {self.name} on {self.port}: {e}")
            return False

    def read_distance(self):
        """
        Reads distance from the SEN0207 sensor via Serial.
        Formula: Distance = (H<<8) + L (in mm)
        """
        if not self.ser:
            return None
        
        try:
            if self.ser.in_waiting >= 4:
                # Header byte 0xFF
                header = self.ser.read(1)
                if header == b'\xff':
                    data = self.ser.read(3)
                    if len(data) == 3:
                        h_data = data[0]
                        l_data = data[1]
                        checksum = data[2]
                        # Validate checksum
                        if (0x0FF + h_data + l_data) & 0xFF == checksum:
                            distance_mm = (h_data << 8) + l_data
                            distance_cm = distance_mm / 10.0
                            return distance_cm
                        else:
                            # print(f"[{self.name}] Checksum mismatch")
                            pass
        except Exception as e:
            print(f"❌ Error reading from {self.name}: {e}")
        return None

    def close(self):
        if self.ser:
            self.ser.close()

def run_ultrasonic_check(callback=None):
    """
    Main loop to poll distance from configured ultrasonic sensors.
    """
    config = get_config()
    
    sensors = []
    # Automatically identify all ultrasonic sections (e.g., [ultrasonic], [ultrasonic_front])
    ultrasonic_sections = [s for s in config.sections() if s.startswith('ultrasonic')]
    
    if not ultrasonic_sections:
        print("❌ No [ultrasonic*] sections found in config.properties.")
        return

    print(f"🔍 Found ultrasonic configurations: {ultrasonic_sections}")

    for name in ultrasonic_sections:
        try:
            port = config.get(name, 'serial_port')
            baud = config.getint(name, 'baud_rate', fallback=9600)
            threshold = config.getfloat(name, 'threshold_cm', fallback=30.0)
            
            sensor = UltrasonicSensor(name, port, baud, threshold)
            if sensor.connect():
                sensors.append(sensor)
        except Exception as e:
            print(f"⚠️ Error loading configuration for {name}: {e}")

    if not sensors:
        print("❌ No ultrasonic sensors could be connected. Check your serial ports andudev rules.")
        return

    print(f"🚀 Monitoring {len(sensors)} sensor(s) (Thresholds: {[f'{s.name}: {s.threshold}cm' for s in sensors]})")

    try:
        while True:
            for sensor in sensors:
                distance = sensor.read_distance()
                if distance is not None:
                    # distance_mm > 0 means valid range
                    if distance > 0:
                        # print(f"[{sensor.name}] Distance: {distance:>6.1f} cm")
                        if distance < sensor.threshold:
                            print(f"🚨 ALERT: Object is too near on {sensor.name}! (Distance: {distance:.1f} cm < Threshold: {sensor.threshold} cm)")
                        
                        if callback:
                            callback({
                                "sensor": sensor.name,
                                "distance_cm": distance,
                                "threshold_cm": sensor.threshold,
                                "alert": distance < sensor.threshold
                            })
                    else:
                        # Out of range / Dead zone (usually 0 or very small)
                        # print(f"[{sensor.name}] Distance: Out of Range")
                        pass
            
            # Small sleep to manage CPU usage
            time.sleep(0.05)

    except KeyboardInterrupt:
        print("\nStopping ultrasonic monitoring...")
    finally:
        for sensor in sensors:
            sensor.close()

if __name__ == "__main__":
    run_ultrasonic_check()
