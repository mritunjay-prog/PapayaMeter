from smbus2 import SMBus
import time
import math
from collections import deque
from datetime import datetime

# ---------------- I2C ----------------
I2C_BUS = 7
ADDR = 0x6B

CTRL1_XL = 0x10
CTRL2_G  = 0x11
OUTX_L_G  = 0x22
OUTX_L_XL = 0x28

# ---------------- Sampling ----------------
SAMPLE_HZ = 40
DT = 1.0 / SAMPLE_HZ
WINDOW = int(0.8 * SAMPLE_HZ)

# ---------------- Thresholds ----------------
TILT_THS_DEG = 12.0
GYRO_THS_DPS = 25.0
LINEAR_THS_G = 0.12

COOLDOWN_SEC = 5.0

# ---------------- Helpers ----------------
def twos(v):
    if v & 0x8000:
        v -= 1 << 16
    return v

def read_gyro(bus):
    d = bus.read_i2c_block_data(ADDR, OUTX_L_G, 6)
    gx = twos(d[1]<<8 | d[0]) * 0.00875
    gy = twos(d[3]<<8 | d[2]) * 0.00875
    gz = twos(d[5]<<8 | d[4]) * 0.00875
    return gx, gy, gz

def read_accel(bus):
    d = bus.read_i2c_block_data(ADDR, OUTX_L_XL, 6)
    ax = twos(d[1]<<8 | d[0]) * 0.000061
    ay = twos(d[3]<<8 | d[2]) * 0.000061
    az = twos(d[5]<<8 | d[4]) * 0.000061
    return ax, ay, az

def angle(v1, v2):
    dot = sum(a*b for a,b in zip(v1,v2))
    n1 = math.sqrt(sum(a*a for a in v1))
    n2 = math.sqrt(sum(a*a for a in v2))
    if n1*n2 == 0:
        return 0
    return math.degrees(math.acos(max(-1,min(1,dot/(n1*n2)))))

# ---------------- Main ----------------
bus = SMBus(I2C_BUS)

bus.write_byte_data(ADDR, CTRL1_XL, 0x30)
bus.write_byte_data(ADDR, CTRL2_G,  0x30)
time.sleep(0.3)

print("Calibrating baseline orientation...")

bx = by = bz = 0
N = 200
for _ in range(N):
    ax, ay, az = read_accel(bus)
    bx += ax; by += ay; bz += az
    time.sleep(DT)

baseline = (bx/N, by/N, bz/N)
print("Baseline:", baseline)

gyro_window = deque(maxlen=WINDOW)
lin_window = deque(maxlen=WINDOW)

last_alert = 0

print("Tamper monitoring (multi-event mode)")

try:
    while True:
        ax, ay, az = read_accel(bus)
        gx, gy, gz = read_gyro(bus)

        lx = ax - baseline[0]
        ly = ay - baseline[1]
        lz = az - baseline[2]
        lin_mag = math.sqrt(lx*lx + ly*ly + lz*lz)
        gyro_mag = math.sqrt(gx*gx + gy*gy + gz*gz)

        lin_window.append(lin_mag)
        gyro_window.append(gyro_mag)

        tilt = angle((ax,ay,az), baseline)

        sustained_gyro = sum(g > GYRO_THS_DPS for g in gyro_window) > 0.6*WINDOW
        sustained_lin  = sum(l > LINEAR_THS_G for l in lin_window) > 0.6*WINDOW

        strong_event = lin_mag > 0.4 or gyro_mag > 120

        now = time.time()

        if ((tilt > TILT_THS_DEG and sustained_gyro) or sustained_lin or strong_event):
            if now - last_alert > COOLDOWN_SEC:
                last_alert = now
                print(f"🚨 TAMPER {datetime.now().isoformat()}")
                print(f"   tilt={tilt:.1f}° gyro={gyro_mag:.1f} dps lin={lin_mag:.2f} g")

        time.sleep(DT)

except KeyboardInterrupt:
    print("Stopped")

finally:
    bus.close()
