try:
    import smbus
except ImportError:
    try:
        from smbus2 import SMBus as smbus
    except ImportError:
        smbus = None
import time
import struct

# ==============================
# INA226 Configuration
# ==============================

I2C_BUS = 7
INA226_ADDRESS = 0x40

SHUNT_RESISTOR_OHMS = 0.005      # 5 milliohms
MAX_EXPECTED_CURRENT = 20.0      # Amps (adjust if needed)

bus = smbus.SMBus(I2C_BUS)

# ==============================
# INA226 Register Addresses
# ==============================

REG_CONFIG          = 0x00
REG_SHUNT_VOLTAGE   = 0x01
REG_BUS_VOLTAGE     = 0x02
REG_POWER           = 0x03
REG_CURRENT         = 0x04
REG_CALIBRATION     = 0x05
REG_MASK_ENABLE     = 0x06
REG_ALERT_LIMIT     = 0x07
REG_MANUFACTURER_ID = 0xFE
REG_DIE_ID          = 0xFF

# ==============================
# Helper Functions
# ==============================

def write_register(register, value):
    bus.write_word_data(INA226_ADDRESS, register, struct.unpack(">H", struct.pack("<H", value))[0])

def read_register(register):
    result = bus.read_word_data(INA226_ADDRESS, register)
    return struct.unpack("<H", struct.pack(">H", result))[0]

def read_signed(register):
    result = read_register(register)
    if result > 32767:
        result -= 65536
    return result

# ==============================
# Calibration Calculation
# ==============================

current_lsb = MAX_EXPECTED_CURRENT / 32768
calibration_value = int(0.00512 / (current_lsb * SHUNT_RESISTOR_OHMS))

power_lsb = 25 * current_lsb

# ==============================
# Configure INA226
# ==============================

def configure_ina226():
    # Reset device
    write_register(REG_CONFIG, 0x8000)
    time.sleep(0.1)

    # Configuration:
    # AVG = 16 samples
    # VBUSCT = 1.1ms
    # VSHCT = 1.1ms
    # MODE = Shunt + Bus Continuous
    config = 0x4127
    write_register(REG_CONFIG, config)

    # Write calibration
    write_register(REG_CALIBRATION, calibration_value)

    print("INA226 Configured")
    print(f"Calibration Value: {calibration_value}")
    print(f"Current LSB: {current_lsb:.6f} A/bit")
    print(f"Power LSB: {power_lsb:.6f} W/bit")

# ==============================
# Read All Parameters
# ==============================

def read_all():
    shunt_voltage = read_signed(REG_SHUNT_VOLTAGE) * 2.5e-6      # 2.5uV per bit
    bus_voltage   = read_register(REG_BUS_VOLTAGE) * 1.25e-3     # 1.25mV per bit
    current       = read_signed(REG_CURRENT) * current_lsb
    power         = read_register(REG_POWER) * power_lsb

    config        = read_register(REG_CONFIG)
    calibration   = read_register(REG_CALIBRATION)
    mask_enable   = read_register(REG_MASK_ENABLE)
    alert_limit   = read_register(REG_ALERT_LIMIT)
    manufacturer  = read_register(REG_MANUFACTURER_ID)
    die_id        = read_register(REG_DIE_ID)

    print("====================================")
    print(f"Bus Voltage      : {bus_voltage:.3f} V")
    print(f"Shunt Voltage    : {shunt_voltage*1000:.3f} mV")
    print(f"Current          : {current:.3f} A")
    print(f"Power            : {power:.3f} W")
    print("------------------------------------")
    print(f"Config Register  : 0x{config:04X}")
    print(f"Calibration Reg  : 0x{calibration:04X}")
    print(f"Mask/Enable Reg  : 0x{mask_enable:04X}")
    print(f"Alert Limit Reg  : 0x{alert_limit:04X}")
    print(f"Manufacturer ID  : 0x{manufacturer:04X}")
    print(f"Die ID           : 0x{die_id:04X}")
    print("====================================\n")

# ==============================
# Main
# ==============================

if __name__ == "__main__":
    configure_ina226()

    while True:
        read_all()
        time.sleep(1)
