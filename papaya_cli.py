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
    print(f"📤 Telemetry queued at {datetime.now().strftime('%H:%M:%S')}")

def launch_gui():
    """Launch the GUI application in a separate process"""
    try:
        print("🖥️ Launching PapayaMeter GUI...")
        # Launch the GUI using the same Python interpreter
        gui_process = subprocess.Popen([sys.executable, "main.py"])
        print("✅ GUI launched successfully!")
        return gui_process
    except Exception as e:
        print(f"⚠️ Failed to launch GUI: {e}")
        return None

def main():
    print("--- 📟 PapayaMeter System Starting ---")
    
    # 1. Provision the device
    try:
        device_token = provision()
        if not device_token:
            print("❌ Initial provisioning failed. Exiting.")
            return
    except Exception as e:
        print(f"❌ Error during provisioning: {e}")
        return

    # 2. Setup MQTT with the obtained token
    print(f"🔑 Setting up MQTT with Access Token: {device_token}")
    set_mqtt_token(device_token)

    # 3. Launch GUI after successful provisioning
    gui_process = launch_gui()

    # 4. Start LiDAR collection and transmission
    print("🚀 Starting LiDAR data collection...")
    try:
        # This will run in a loop if hardware is available
        # If hardware is not available, it will return and we continue
        run_detector(callback=lidar_callback)
        
        # If we reach here, LiDAR hardware wasn't available
        print("📡 LiDAR hardware not available, but device provisioning completed successfully!")
        print("🔄 System will continue running for other operations...")
        
        # Keep the program running for other potential operations
        while True:
            print(f"⏰ System running without LiDAR at {datetime.now().strftime('%H:%M:%S')}")
            
            # Check if GUI is still running
            if gui_process and gui_process.poll() is not None:
                print("🖥️ GUI has been closed by user.")
                break
                
            time.sleep(30)  # Check every 30 seconds
            
    except KeyboardInterrupt:
        print("\n👋 System stopped by user.")
        if gui_process:
            print("🔄 Closing GUI...")
            gui_process.terminate()
    except Exception as e:
        print(f"❌ Critical error in detector: {e}")
        print("🔄 But device provisioning was completed successfully!")
        if gui_process:
            print("🔄 Closing GUI...")
            gui_process.terminate()

if __name__ == "__main__":
    main()