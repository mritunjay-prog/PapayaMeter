import requests
import threading
import time
from utility.current_voltage import CurrentVoltageMonitor

class SystemService:
    """Service to track system electrical and location information."""
    
    def __init__(self):
        self.electrical_data = {
            "bus_voltage": 0.0,
            "shunt_voltage": 0.0,
            "current": 0.0,
            "power": 0.0
        }
        self.country_code = "US"
        self.country_name = "United States"
        self.city = "Unknown"
        self._stop_event = threading.Event()
        self._thread = None
        
        # INA226 Monitor (I2C Bus 7, Address 0x40 as per user script)
        self.monitor = CurrentVoltageMonitor(i2c_bus=7, address=0x40)
        
    def start(self):
        """Start the background tracking thread."""
        self.monitor.connect()
        self._thread = threading.Thread(target=self._update_loop, daemon=True)
        self._thread.start()
        
    def stop(self):
        """Stop the background tracking thread."""
        self._stop_event.set()
        if self._thread:
            self._thread.join()
            
    def _update_loop(self):
        # Initial location check
        self._update_location()
        
        last_location_update = time.time()
        
        while not self._stop_event.is_set():
            self._update_electrical_data()
            
            # Update location every hour
            if time.time() - last_location_update > 3600:
                self._update_location()
                last_location_update = time.time()
                
            time.sleep(2)  # Update electrical data every 2 seconds
            
    def _update_electrical_data(self):
        try:
            self.electrical_data = self.monitor.read_all()
        except Exception as e:
            print(f"Error updating electrical data: {e}")
            
    def _update_location(self):
        try:
            response = requests.get("https://ipapi.co/json/", timeout=5)
            if response.status_code == 200:
                data = response.json()
                self.country_code = data.get("country_code", "US")
                self.country_name = data.get("country_name", "United States")
                self.city = data.get("city", "Unknown")
        except Exception as e:
            print(f"Error updating location: {e}")

    def get_stats(self):
        return {
            "electrical": self.electrical_data,
            "country_code": self.country_code,
            "country_name": self.country_name,
            "city": self.city
        }
