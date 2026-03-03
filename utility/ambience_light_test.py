import minimalmodbus
import time

# --- Setup ---
PORT = '/dev/ttyUSB2'
SLAVE_ID = 1
sensor = minimalmodbus.Instrument(PORT, SLAVE_ID)
sensor.serial.baudrate = 9600
sensor.serial.timeout = 1

# --- Thresholds ---
NIGHT_THRESHOLD = 10.0
DAY_THRESHOLD = 50.0

def get_status(lux):
    """Categorizes the light level into a legend."""
    if lux < NIGHT_THRESHOLD:
        return "NIGHT"
    elif lux > DAY_THRESHOLD:
        return "DAY"
    else:
        return "TWILIGHT"

def get_sensor_data():
    """Reads sensor and returns a structured dictionary."""
    try:
        # Read 32-bit value from Register 2 (as per your Arduino sketch)
        raw_value = sensor.read_long(2, functioncode=3, signed=False, byteorder=0)
        lux = raw_value / 1000.0
        
        # Construct the dictionary
        data = {
            "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
            "lux": round(lux, 3),
            "status": get_status(lux)
        }
        return data

    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    print("Starting sensor data stream (Dictionary format)...")
    print("-" * 50)
    
    while True:
        sensor_dict = get_sensor_data()
        
        # You can now access specific values easily:
        if "error" not in sensor_dict:
            print(f"Current Data: {sensor_dict}")
            
            # Example: Accessing a single key
            # current_lux = sensor_dict["lux"]
            # if sensor_dict["status"] == "NIGHT":
            #     dim_screen()
        else:
            print(f"Read Error: {sensor_dict['error']}")
            
        time.sleep(5)






































