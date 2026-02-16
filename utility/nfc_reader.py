"""
NFC Card Reader Module for PapayaMeter
Supports PN532, RC522, and ACR122U readers
Pattern follows the same structure as lidar.py
"""

import time
import json
from datetime import datetime
import configparser
import os

# =============================================
# INSTALLATION NOTES:
# =============================================
# For PN532 (UART/I2C/SPI):
#   pip install adafruit-circuitpython-pn532
#   pip install adafruit-blinka
#
# For RC522 (SPI):
#   pip install mfrc522  (Raspberry Pi only)
#   pip install spidev RPi.GPIO
#
# For ACR122U (USB):
#   pip install pyscard nfcpy
#   sudo apt-get install pcscd pcsc-tools libnfc-bin
# =============================================


def get_config():
    """Load configuration from config.properties"""
    config = configparser.ConfigParser()
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config.properties')
    config.read(config_path)
    return config


def initialize_reader(reader_type, config):
    """
    Initialize the NFC reader based on type.
    Returns the reader object or None if initialization fails.
    """
    reader = None
    
    if reader_type == "pn532_uart":
        try:
            import serial
            import adafruit_pn532.uart
            port = config.get('nfc', 'serial_port', fallback='/dev/ttyS0')
            baud = config.getint('nfc', 'baud_rate', fallback=115200)
            uart = serial.Serial(port, baud, timeout=1)
            reader = adafruit_pn532.uart.PN532_UART(uart, debug=False)
            reader.SAM_configuration()
            print(f"✅ PN532 (UART) initialized on {port}")
        except Exception as e:
            print(f"❌ Failed to initialize PN532 UART: {e}")
            
    elif reader_type == "pn532_i2c":
        try:
            import board
            import busio
            from adafruit_pn532.i2c import PN532_I2C
            i2c = busio.I2C(board.SCL, board.SDA)
            reader = PN532_I2C(i2c, debug=False)
            reader.SAM_configuration()
            print("✅ PN532 (I2C) initialized")
        except Exception as e:
            print(f"❌ Failed to initialize PN532 I2C: {e}")
            
    elif reader_type == "rc522":
        try:
            from mfrc522 import SimpleMFRC522
            reader = SimpleMFRC522()
            print("✅ RC522 initialized")
        except Exception as e:
            print(f"❌ Failed to initialize RC522: {e}")
            
    elif reader_type == "acr122u":
        try:
            import nfc
            reader = nfc.ContactlessFrontend('usb')
            if reader:
                print("✅ ACR122U (USB) initialized")
            else:
                print("❌ ACR122U not found")
        except Exception as e:
            print(f"❌ Failed to initialize ACR122U: {e}")
    
    return reader


def read_card_pn532(reader):
    """Read card using PN532 reader"""
    uid = reader.read_passive_target(timeout=0.5)
    if uid:
        return ''.join([format(x, '02X') for x in uid])
    return None


def read_card_rc522(reader):
    """Read card using RC522 reader"""
    try:
        uid, text = reader.read_no_block()
        if uid:
            return format(uid, '010X')
    except:
        pass
    return None


def read_card_acr122u(reader):
    """Read card using ACR122U reader"""
    try:
        import nfc.tag
        target = reader.sense(nfc.clf.RemoteTarget("106A"))
        if target:
            tag = nfc.tag.activate(reader, target)
            if tag:
                uid = tag.identifier.hex().upper()
                return uid
    except:
        pass
    return None


def run_nfc_reader(callback=None):
    """
    Main function to run the NFC card reader.
    Follows the same pattern as run_detector() in lidar.py
    
    Args:
        callback: Function to call when a card is detected or error occurs.
                  The callback receives a dict with card data or error info.
    """
    config = get_config()
    
    # Get NFC configuration
    reader_type = config.get('nfc', 'reader_type', fallback='pn532_uart')
    polling_interval = config.getint('nfc', 'polling_interval_ms', fallback=500) / 1000.0
    output_dir = config.get('nfc', 'nfc_output_path', fallback='./nfc_data/')
    debounce_time = config.getint('nfc', 'debounce_time_ms', fallback=2000) / 1000.0
    
    # Ensure output directory exists
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    retry_count = 0
    max_retries = 3
    last_error_time = 0
    last_card_time = 0
    last_card_uid = None
    error_cooldown = 30
    
    def send_error(error_desc, error_code="NFC_ERR_001"):
        """Report error to callback (ThingsBoard)"""
        nonlocal last_error_time
        current_time = time.time()
        if callback and (current_time - last_error_time > error_cooldown):
            error_payload = {
                "nfc.error.type": "reader_error",
                "nfc.error.code": error_code,
                "nfc.error.severity": "warning",
                "nfc.error.retry_count": retry_count,
                "nfc.error.description": error_desc
            }
            callback(error_payload)
            last_error_time = current_time
            print(f"⚠️ Error reported to ThingsBoard: {error_desc}")
    
    # Initialize the reader
    reader = initialize_reader(reader_type, config)
    if reader is None:
        send_error(f"Failed to initialize {reader_type} NFC reader", "NFC_ERR_002")
        return
    
    # Select the appropriate read function
    read_functions = {
        "pn532_uart": read_card_pn532,
        "pn532_i2c": read_card_pn532,
        "rc522": read_card_rc522,
        "acr122u": read_card_acr122u
    }
    read_card = read_functions.get(reader_type, read_card_pn532)
    
    print(f"🔄 NFC Reader running... (Polling every {polling_interval}s)")
    
    while True:
        try:
            uid = read_card(reader)
            current_time = time.time()
            
            if uid:
                # Debounce: Ignore if same card detected within debounce window
                if uid == last_card_uid and (current_time - last_card_time) < debounce_time:
                    time.sleep(polling_interval)
                    continue
                
                # Reset retry count on successful read
                retry_count = 0
                last_card_uid = uid
                last_card_time = current_time
                
                # Create status payload
                status = {
                    "nfc.card_uid": uid,
                    "nfc.card_detected": True,
                    "nfc.reader_type": reader_type,
                    "nfc.timestamp": datetime.utcnow().isoformat() + "Z",
                    "nfc.last_updated": datetime.utcnow().isoformat() + "Z"
                }
                
                print(f"💳 Card Detected: {uid}")
                print(json.dumps(status, indent=2))
                
                # Save to daily file
                try:
                    filename = datetime.now().strftime('%Y-%m-%d') + '_nfc.json'
                    full_path = os.path.join(output_dir, filename)
                    with open(full_path, 'a') as f:
                        f.write(json.dumps(status) + '\n')
                except Exception as e:
                    print(f"Error appending to file: {e}")
                
                # Send to callback (ThingsBoard)
                if callback:
                    callback(status)
            
            else:
                # No card present - this is normal, just continue polling
                pass
                
        except Exception as e:
            retry_count += 1
            print(f"❌ NFC Read Error: {e}")
            if retry_count >= max_retries:
                send_error(f"NFC communication error: {e}", "NFC_ERR_003")
            time.sleep(1)  # Extra wait on error
        
        time.sleep(polling_interval)


def cleanup_rc522():
    """Cleanup GPIO for RC522 reader"""
    try:
        import RPi.GPIO as GPIO
        GPIO.cleanup()
    except:
        pass


if __name__ == "__main__":
    try:
        run_nfc_reader()
    except KeyboardInterrupt:
        print("\n🛑 NFC Reader stopped")
        cleanup_rc522()
