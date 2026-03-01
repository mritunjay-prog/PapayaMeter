from smbus2 import SMBus
import time
import math
from collections import deque
from datetime import datetime
import configparser
import os

def get_config():
    config = configparser.ConfigParser()
    # Path to config.properties relative to this script
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config.properties')
    config.read(config_path)
    return config

# ---------------- Helpers ----------------
def twos(v):
    if v & 0x8000:
        v -= 1 << 16
    return v

def read_gyro(bus, addr, reg):
    try:
        d = bus.read_i2c_block_data(addr, reg, 6)
        gx = twos(d[1]<<8 | d[0]) * 0.00875
        gy = twos(d[3]<<8 | d[2]) * 0.00875
        gz = twos(d[5]<<8 | d[4]) * 0.00875
        return gx, gy, gz
    except Exception as e:
        # print(f"Gyro read error: {e}")
        return 0,0,0

def read_accel(bus, addr, reg):
    try:
        d = bus.read_i2c_block_data(addr, reg, 6)
        ax = twos(d[1]<<8 | d[0]) * 0.000061
        ay = twos(d[3]<<8 | d[2]) * 0.000061
        az = twos(d[5]<<8 | d[4]) * 0.000061
        return ax, ay, az
    except Exception as e:
        # print(f"Accel read error: {e}")
        return 0,0,0

def angle(v1, v2):
    dot = sum(a*b for a,b in zip(v1,v2))
    n1 = math.sqrt(sum(a*a for a in v1))
    n2 = math.sqrt(sum(a*a for a in v2))
    if n1*n2 == 0:
        return 0
    return math.degrees(math.acos(max(-1,min(1,dot/(n1*n2)))))

# ---------------- Main Monitor ----------------
def run_tamper_monitor(callback=None, recalibrate_event=None):
    config = get_config()
    
    # ---------------- I2C Configuration ----------------
    i2c_bus = config.getint('tamper', 'i2c_bus', fallback=7)
    addr = int(config.get('tamper', 'i2c_address', fallback='0x6B'), 16)
    
    # LSM6DS3 Registers
    ctrl1_xl = 0x10
    ctrl2_g  = 0x11
    outx_l_g  = 0x22
    outx_l_xl = 0x28

    # ---------------- Detection Logic Parameters ----------------
    sample_hz = config.getint('tamper', 'sample_hz', fallback=20)
    dt = 1.0 / sample_hz
    window_sec = 0.8
    window_size = int(window_sec * sample_hz)

    tilt_ths_deg = config.getfloat('tamper', 'tilt_threshold_deg', fallback=12.0)
    gyro_ths_dps = config.getfloat('tamper', 'gyro_threshold_dps', fallback=25.0)
    linear_ths_g = config.getfloat('tamper', 'linear_threshold_g', fallback=0.12)
    cooldown_sec = config.getfloat('tamper', 'cooldown_sec', fallback=5.0)

    def calibrate(bus, addr, outx_l_xl, sample_hz, dt):
        print("Calibrating baseline... Please hold steady.")
        bx = by = bz = 0
        n_calib = int(1.0 * sample_hz) # 1 second calibration
        for _ in range(n_calib):
            ax, ay, az = read_accel(bus, addr, outx_l_xl)
            bx += ax; by += ay; bz += az
            time.sleep(dt)
        return (bx/n_calib, by/n_calib, bz/n_calib)

    try:
        bus = SMBus(i2c_bus)
        
        # Configure accelerometer and gyroscope to 52Hz (0x30) or similar
        bus.write_byte_data(addr, ctrl1_xl, 0x30)
        bus.write_byte_data(addr, ctrl2_g,  0x30)
        time.sleep(0.3)

        print(f"✅ Tamper monitoring started on I2C bus {i2c_bus}, addr {hex(addr)}")
        
        baseline = calibrate(bus, addr, outx_l_xl, sample_hz, dt)
        print(f"Calibration complete: {baseline}")

        gyro_window = deque(maxlen=window_size)
        lin_window = deque(maxlen=window_size)
        
        last_alert = 0

        while True:
            # Check for recalibration request
            if recalibrate_event and recalibrate_event.is_set():
                print("♻️ Recalibrating baseline as requested...")
                baseline = calibrate(bus, addr, outx_l_xl, sample_hz, dt)
                print(f"New calibration complete: {baseline}")
                recalibrate_event.clear()
                # Clear windows to avoid false triggers after move
                gyro_window.clear()
                lin_window.clear()

            ax, ay, az = read_accel(bus, addr, outx_l_xl)
            gx, gy, gz = read_gyro(bus, addr, outx_l_g)

            # Linear movement (difference from gravity baseline)
            lx = ax - baseline[0]
            ly = ay - baseline[1]
            lz = az - baseline[2]
            lin_mag = math.sqrt(lx*lx + ly*ly + lz*lz)
            gyro_mag = math.sqrt(gx*gx + gy*gy + gz*gz)

            lin_window.append(lin_mag)
            gyro_window.append(gyro_mag)

            tilt = angle((ax,ay,az), baseline)

            # Check for sustained movement (indicates actual displacement, not just vibration)
            sustained_gyro = sum(g > gyro_ths_dps for g in gyro_window) > 0.6 * len(gyro_window)
            sustained_lin  = sum(l > linear_ths_g for l in lin_window) > 0.6 * len(lin_window)
            
            # Absolute strong impact/shaking event
            strong_event = lin_mag > 0.4 or gyro_mag > 120

            now = time.time()
            if ((tilt > tilt_ths_deg and sustained_gyro) or sustained_lin or strong_event):
                if now - last_alert > cooldown_sec:
                    last_alert = now
                    
                    data = {
                        "event": "TAMPER",
                        "timestamp": datetime.now().isoformat(),
                        "tilt": round(tilt, 1),
                        "gyro": round(gyro_mag, 1),
                        "linear": round(lin_mag, 2),
                        "msg": "Tamper detected - Device moved or shaken"
                    }
                    
                    print(f"🚨 TAMPER DETECTED: {data}")
                    
                    if callback:
                        callback(data)

            time.sleep(dt)

    except Exception as e:
        print(f"❌ Tamper Monitor Error: {e}")
    finally:
        try:
            bus.close()
        except:
            pass

if __name__ == "__main__":
    run_tamper_monitor()
