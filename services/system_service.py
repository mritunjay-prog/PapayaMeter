import requests
import psutil
import threading
import time

class SystemService:
    """Service to track system battery and location information."""
    
    def __init__(self):
        self.battery_percent = 0
        self.battery_power = 0.0  # Simulated power draw for display
        self.country_code = "US"
        self.country_name = "United States"
        self.city = "Unknown"
        self._stop_event = threading.Event()
        self._thread = None
        
    def start(self):
        """Start the background tracking thread."""
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
            self._update_battery()
            
            # Update location every hour
            if time.time() - last_location_update > 3600:
                self._update_location()
                last_location_update = time.time()
                
            time.sleep(5)  # Update battery every 5 seconds
            
    def _update_battery(self):
        try:
            battery = psutil.sensors_battery()
            if battery:
                self.battery_percent = battery.percent
                # Calculate simulated power if discharging, or just a sample value
                # Real power draw is hard to get via psutil uniformly
                self.battery_power = 7.2 # Dummy value as seen in image
            else:
                self.battery_percent = 100
                self.battery_power = 0.0
        except Exception as e:
            print(f"Error updating battery: {e}")
            
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
            "battery_percent": self.battery_percent,
            "battery_power": self.battery_power,
            "country_code": self.country_code,
            "country_name": self.country_name,
            "city": self.city
        }
