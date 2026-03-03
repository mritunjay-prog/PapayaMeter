#!/usr/bin/env python3
"""
PapayaMeter CLI - Command Line Interface for the parking sensor system
"""

import time
import sys
import os
import threading
import subprocess
from datetime import datetime

# Add the project root to sys.path to allow imports from core and utility
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.DeviceProvision import provision
from utility.lidar import run_detector
from utility.ultrasonic import run_ultrasonic_check
from utility.ambience_light import run_ambience_light_listener
from utility.temp_hum import run_temp_hum_listener
from utility.tamper import run_tamper_monitor
from utility.airquality import run_air_quality_listener
from services.telemetry_publisher import publish_telemetry, set_mqtt_token


LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "system.log")

def sys_log(message):
    """Prints message to console and writes to system.log"""
    timestamp = datetime.now().strftime("[%H:%M:%S]")
    full_msg = f"{timestamp} {message}"
    print(message) # Original print
    try:
        with open(LOG_FILE, "a") as f:
            f.write(full_msg + "\n")
    except:
        pass

def lidar_callback(data):
    """
    Format and send LiDAR data to ThingsBoard.
    Structure: { "ts": timestamp, "values": data }
    """
    # Create the timestamp in milliseconds
    ts = int(time.time() * 1000)
    
    payload = {
        "ts": ts,
        "values": data
    }
    
    # Send to background worker
    publish_telemetry(payload)
    sys_log(f"📤 Telemetry queued at {datetime.now().strftime('%H:%M:%S')}")

_last_us_log_time = 0
def ultrasonic_callback(data):
    """
    Handle ultrasonic alerts in the CLI. 
    Prints alerts to terminal and logs them.
    """
    global _last_us_log_time
    is_alert = data.get("alert", False)
    sensor_name = data.get("sensor", "unknown")
    distance = data.get("distance_cm", 0)
    
    if is_alert:
        # High visibility alert in terminal
        sys_log(f"🚨 [PROXIMITY ALERT] Object too near on {sensor_name}! Distance: {distance:.1f} cm")
    else:
        # Subtle log for regular updates to show system is alive
        now = time.time()
        if now - _last_us_log_time > 5.0:
            print(f"📡 [Ultrasonic Status] {sensor_name}: {distance:.1f} cm (Normal)")
            _last_us_log_time = now

def ambience_callback(data):
    """Publish Ambient Light data to ThingsBoard."""
    ts = int(time.time() * 1000)
    payload = {
        "ts": ts,
        "values": {
            "ambience.lux": data.get("lux"),
            "ambience.status": data.get("status")
        }
    }
    publish_telemetry(payload)
    # sys_log(f"📤 Ambience Light queued at {datetime.now().strftime('%H:%M:%S')}")

def temp_hum_callback(data):
    """Publish Temperature and Humidity data to ThingsBoard."""
    ts = int(time.time() * 1000)
    # Convert Celsius to Fahrenheit for telemetry if desired, 
    # but usually best to send raw and convert in dashboard.
    # Sending raw Celsius.
    payload = {
        "ts": ts,
        "values": {
            "temperature": data.get("temperature"),
            "humidity": data.get("humidity")
        }
    }
    publish_telemetry(payload)
    sys_log(f"📤 Temp/Hum Telemetry queued at {datetime.now().strftime('%H:%M:%S')}")

def tamper_callback(data):
    """Publish Tamper data to ThingsBoard."""
    ts = int(time.time() * 1000)
    payload = {
        "ts": ts,
        "values": {
            "tamper.event": data.get("event"),
            "tamper.tilt": data.get("tilt"),
            "tamper.gyro": data.get("gyro"),
            "tamper.linear": data.get("linear"),
            "tamper.msg": data.get("msg")
        }
    }
    publish_telemetry(payload)
    sys_log(f"🚨 [TAMPER ALERT] {data.get('msg')} | Tilt: {data.get('tilt')}")

def air_quality_callback(data):
    """Publish Air Quality data to ThingsBoard."""
    ts = int(time.time() * 1000)
    payload = {
        "ts": ts,
        "values": {
            "air.pm25": data.get("PM2.5"),
            "air.pm10": data.get("PM10"),
            "air.pm1_0": data.get("PM1.0")
        }
    }
    publish_telemetry(payload)
    # sys_log(f"📤 Air Quality Telemetry queued at {datetime.now().strftime('%H:%M:%S')}")

def get_display_env():
    """
    Dynamically find the DISPLAY and XAUTHORITY from the currently running 
    desktop session. This works even when called from an SSH session.
    """
    try:
        # Find the PID of any process that has a DISPLAY set (e.g. the desktop session)
        result = subprocess.run(
            ["bash", "-c",
             "for pid in /proc/*/environ; do "
             "  strings $pid 2>/dev/null | grep -q '^DISPLAY=:' && echo $pid && break; "
             "done"],
            capture_output=True, text=True, timeout=5
        )
        proc_env_path = result.stdout.strip()
        if not proc_env_path:
            return {}
        
        # Read all env vars from that process
        with open(proc_env_path, 'r', errors='replace') as f:
            raw = f.read()
        
        env_vars = {}
        for entry in raw.split('\x00'):
            if '=' in entry:
                k, _, v = entry.partition('=')
                env_vars[k] = v
        
        display = env_vars.get("DISPLAY", "")
        xauthority = env_vars.get("XAUTHORITY", "")
        
        found = {}
        if display:
            found["DISPLAY"] = display
        if xauthority and os.path.exists(xauthority):
            found["XAUTHORITY"] = xauthority
        
        return found
    except Exception as e:
        sys_log(f"⚠️ Could not auto-detect display env: {e}")
        return {}


def launch_gui():
    """Launch the GUI application in a separate process, rendering on the physical screen."""
    try:
        sys_log("🖥️ Launching PapayaMeter GUI...")
        
        # Build environment — start from current env and override display settings
        gui_env = os.environ.copy()
        
        # Auto-detect DISPLAY and XAUTHORITY from the running desktop session
        detected = get_display_env()
        if detected:
            gui_env.update(detected)
            sys_log(f"🖥️ Using display: {detected.get('DISPLAY','?')} XAUTH: {detected.get('XAUTHORITY','none')}")
        else:
            # Fallback: try DISPLAY=:0 directly (works if xhost +local: was run)
            gui_env["DISPLAY"] = ":0"
            sys_log("⚠️ Could not auto-detect display, falling back to DISPLAY=:0")

        # Launch the GUI using the same Python interpreter
        gui_process = subprocess.Popen(
            [sys.executable, "main.py"],
            env=gui_env,
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        sys_log("✅ GUI launched successfully!")
        return gui_process
    except Exception as e:
        sys_log(f"⚠️ Failed to launch GUI: {e}")
        return None

def main():
    # Reset log file on start
    with open(LOG_FILE, "w") as f:
        f.write(f"--- 📟 PapayaMeter Session Start: {datetime.now()} ---\n")

    sys_log("--- 📟 PapayaMeter System Starting ---")
    
    # 1. Provision the device
    try:
        device_token = provision()
        if not device_token:
            sys_log("❌ Initial provisioning failed. Exiting.")
            return
    except Exception as e:
        sys_log(f"❌ Error during provisioning: {e}")
        return

    # 2. Setup MQTT with the obtained token
    sys_log(f"🔑 Setting up MQTT with Access Token: {device_token}")
    set_mqtt_token(device_token)

    # 3. Launch GUI after successful provisioning
    gui_process = launch_gui()

    # 4. Start Ultrasonic Monitoring in a background thread
    sys_log("🚀 Starting Ultrasonic proximity monitoring...")
    us_thread = threading.Thread(
        target=run_ultrasonic_check, 
        kwargs={'callback': ultrasonic_callback},
        daemon=True
    )
    us_thread.start()

    # 4b. Start Ambience Light monitoring
    sys_log("🚀 Starting Ambience Light monitoring...")
    ambience_thread = threading.Thread(
        target=run_ambience_light_listener,
        kwargs={'callback': ambience_callback},
        daemon=True
    )
    ambience_thread.start()

    # 4c. Start Temperature/Humidity monitoring
    sys_log("🚀 Starting Temperature/Humidity monitoring...")
    temp_hum_thread = threading.Thread(
        target=run_temp_hum_listener,
        kwargs={'callback': temp_hum_callback},
        daemon=True
    )
    temp_hum_thread.start()

    # 4d. Start Tamper monitoring
    sys_log("🚀 Starting Tamper monitoring...")
    tamper_thread = threading.Thread(
        target=run_tamper_monitor,
        kwargs={'callback': tamper_callback},
        daemon=True
    )
    tamper_thread.start()

    # 4e. Start Air Quality monitoring
    sys_log("🚀 Starting Air Quality monitoring...")
    air_thread = threading.Thread(
        target=run_air_quality_listener,
        kwargs={'callback': air_quality_callback},
        daemon=True
    )
    air_thread.start()

    # 5. Start LiDAR collection and transmission
    sys_log("🚀 Starting LiDAR data collection (Left & Right)...")
    
    def start_lidar(side):
        try:
            run_detector(section_name=side, callback=lidar_callback)
        except Exception as e:
            sys_log(f"⚠️ LiDAR {side} Thread Error: {e}")

    left_thread = threading.Thread(target=start_lidar, args=("lidar_left",), daemon=True)
    right_thread = threading.Thread(target=start_lidar, args=("lidar_right",), daemon=True)
    
    left_thread.start()
    right_thread.start()

    try:
        # Keep the main thread alive to monitor the GUI or wait for exit
        while True:
            # Check if GUI is still running
            if gui_process and gui_process.poll() is not None:
                sys_log("🖥️ GUI has been closed by user.")
                break
                
            time.sleep(5)
            
    except KeyboardInterrupt:
        sys_log("\n👋 System stopped by user.")
        if gui_process:
            sys_log("🔄 Closing GUI...")
            gui_process.terminate()
    except Exception as e:
        sys_log(f"❌ Critical error in main loop: {e}")
        if gui_process:
            sys_log("🔄 Closing GUI...")
            gui_process.terminate()


if __name__ == "__main__":
    main()