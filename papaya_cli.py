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
from services.telemetry_publisher import publish_telemetry, set_mqtt_token
from services.ssh_service import SshService


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

def launch_gui():
    """Launch the GUI application in a separate process"""
    try:
        sys_log("🖥️ Launching PapayaMeter GUI...")
        # Launch the GUI using the same Python interpreter
        gui_process = subprocess.Popen([sys.executable, "main.py"])
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

    # 3. Start SSH Management Service
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.properties")
    ssh_service = SshService(config_path)
    ssh_service.start()
    sys_log("🛡️ Reverse SSH Service active.")

    # 4. Launch GUI after successful provisioning
    gui_process = launch_gui()


    # 4. Start LiDAR collection and transmission
    sys_log("🚀 Starting LiDAR data collection...")
    try:
        # This will run in a loop if hardware is available
        # If hardware is not available, it will return and we continue
        run_detector(callback=lidar_callback)
        
        # If we reach here, LiDAR hardware wasn't available
        sys_log("📡 LiDAR hardware not available, but device provisioning completed successfully!")
        sys_log("🔄 System will continue running for other operations...")
        
        # Keep the program running for other potential operations
        while True:
            sys_log(f"⏰ System running without LiDAR at {datetime.now().strftime('%H:%M:%S')}")
            
            # Check if GUI is still running
            if gui_process and gui_process.poll() is not None:
                sys_log("🖥️ GUI has been closed by user.")
                break
                
            time.sleep(30)  # Check every 30 seconds
            
    except KeyboardInterrupt:
        sys_log("\n👋 System stopped by user.")
        if gui_process:
            sys_log("🔄 Closing GUI...")
            gui_process.terminate()
        ssh_service.stop()
    except Exception as e:
        sys_log(f"❌ Critical error in detector: {e}")
        sys_log("🔄 But device provisioning was completed successfully!")
        if gui_process:
            sys_log("🔄 Closing GUI...")
            gui_process.terminate()
        ssh_service.stop()


if __name__ == "__main__":
    main()