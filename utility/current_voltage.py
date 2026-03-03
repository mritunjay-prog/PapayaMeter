try:
    import smbus2 as smbus
except ImportError:
    try:
        import smbus
    except ImportError:
        smbus = None
import time
import struct
from typing import Dict, Optional

class CurrentVoltageMonitor:
    """
    INA226 Current and Voltage Monitor.
    Based on utility/cyrrent_volt_test.py
    """
    # INA226 Register Addresses
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

    def __init__(self, i2c_bus: int = 7, address: int = 0x40, 
                 shunt_resistor: float = 0.005, max_current: float = 20.0):
        self.i2c_bus = i2c_bus
        self.address = address
        self.shunt_resistor = shunt_resistor
        self.max_current = max_current
        self.bus = None
        
        # Calibration Calculation
        self.current_lsb = self.max_current / 32768
        self.calibration_value = int(0.00512 / (self.current_lsb * self.shunt_resistor))
        self.power_lsb = 25 * self.current_lsb
        
        self._is_connected = False

    def connect(self) -> bool:
        try:
            self.bus = smbus.SMBus(self.i2c_bus)
            self.configure()
            self._is_connected = True
            return True
        except Exception as e:
            print(f"Error connecting to INA226: {e}")
            self._is_connected = False
            return False

    def write_register(self, register, value):
        if not self.bus: return
        self.bus.write_word_data(self.address, register, struct.unpack(">H", struct.pack("<H", value))[0])

    def read_register(self, register):
        if not self.bus: return 0
        result = self.bus.read_word_data(self.address, register)
        return struct.unpack("<H", struct.pack(">H", result))[0]

    def read_signed(self, register):
        result = self.read_register(register)
        if result > 32767:
            result -= 65536
        return result

    def configure(self):
        # Reset device
        self.write_register(self.REG_CONFIG, 0x8000)
        time.sleep(0.1)

        # Configuration: 16 samples, 1.1ms conversion, Shunt+Bus Continuous
        config = 0x4127
        self.write_register(self.REG_CONFIG, config)

        # Write calibration
        self.write_register(self.REG_CALIBRATION, self.calibration_value)

    def read_all(self) -> Dict[str, float]:
        if not self._is_connected and not self.connect():
            return {
                "bus_voltage": 0.0,
                "shunt_voltage": 0.0,
                "current": 0.0,
                "power": 0.0
            }
        
        try:
            shunt_v = self.read_signed(self.REG_SHUNT_VOLTAGE) * 2.5e-6      # 2.5uV per bit
            bus_v   = self.read_register(self.REG_BUS_VOLTAGE) * 1.25e-3     # 1.25mV per bit
            current = self.read_signed(self.REG_CURRENT) * self.current_lsb
            power   = self.read_register(self.REG_POWER) * self.power_lsb
            
            return {
                "bus_voltage": bus_v,
                "shunt_voltage": shunt_v * 1000, # In mV
                "current": current,
                "power": power
            }
        except Exception as e:
            print(f"Error reading from INA226: {e}")
            self._is_connected = False
            return {
                "bus_voltage": 0.0,
                "shunt_voltage": 0.0,
                "current": 0.0,
                "power": 0.0
            }

if __name__ == "__main__":
    monitor = CurrentVoltageMonitor()
    if monitor.connect():
        while True:
            data = monitor.read_all()
            print(f"Voltage: {data['bus_voltage']:.3f}V, Current: {data['current']:.3f}A, Power: {data['power']:.3f}W")
            time.sleep(1)
