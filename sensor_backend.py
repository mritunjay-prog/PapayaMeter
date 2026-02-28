import math
import random
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List

# LiDAR sensor name shown in the GUI
LIDAR_SENSOR_NAME = "LiDAR Distance (cm)"


@dataclass
class SensorReading:
    """Simple container for a single sensor reading."""

    name: str
    value: float
    unit: str
    timestamp: float  # seconds since epoch


class SensorBackend:
    """
    Backend responsible for providing the latest data from sensors.

    Right now this implementation is purely simulated so that the GUI
    can run even without real hardware connected. You can later replace
    or extend this class to pull data from:
      - Local hardware (serial, I2C, SPI, etc.)
      - A local database or CSV files
      - ThingsBoard / REST APIs / MQTT
    Includes optional LiDAR (utility.lidar); when include_lidar=True the
    LiDAR runs in a background thread and is shown as "LiDAR Distance (cm)".
    """

    def __init__(
        self,
        sensor_names: List[str] | None = None,
        include_lidar: bool = True,
    ) -> None:
        if sensor_names is None:
            sensor_names = [
                "Temperature",
                "Humidity",
                "Pressure",
            ]
        self._sensor_names = list(sensor_names)
        self._start_time = time.time()
        self._include_lidar = include_lidar
        self._lidar_latest: Dict[str, Any] | None = None
        self._nfc_latest: Dict[str, Any] | None = None
        self._air_latest: Dict[str, Any] | None = None
        self._temp_latest: Dict[str, Any] | None = None
        self._ultrasonic_latest: Dict[str, Any] | None = None
        self._lidar_lock = threading.Lock()
        self._nfc_lock = threading.Lock()
        self._air_lock = threading.Lock()
        self._temp_lock = threading.Lock()
        self._ultrasonic_lock = threading.Lock()
        self._lidar_thread: threading.Thread | None = None
        self._nfc_thread: threading.Thread | None = None
        self._air_thread: threading.Thread | None = None
        self._temp_thread: threading.Thread | None = None
        self._ultrasonic_thread: threading.Thread | None = None
        self._nfc_callback_external = None
        self._air_callback_external = None
        self._temp_callback_external = None
        self._ultrasonic_callback_external = None

        if include_lidar:
            self._sensor_names.append(LIDAR_SENSOR_NAME)
            self._start_lidar_thread()
        
        self._start_nfc_thread()
        self._start_air_thread()
        self._start_temp_thread()
        self._start_ultrasonic_thread()

    def set_nfc_callback(self, callback):
        self._nfc_callback_external = callback

    def set_air_callback(self, callback):
        self._air_callback_external = callback

    def set_temp_callback(self, callback):
        self._temp_callback_external = callback

    def set_ultrasonic_callback(self, callback):
        self._ultrasonic_callback_external = callback

    def _nfc_callback(self, data: Dict[str, Any]) -> None:
        """Called by nfc run_nfc_listener with each new tap."""
        with self._nfc_lock:
            self._nfc_latest = dict(data)
        if self._nfc_callback_external:
            self._nfc_callback_external(data)

    def _air_callback(self, data: Dict[str, Any]) -> None:
        """Called by air run_air_quality_listener with each new reading."""
        with self._air_lock:
            self._air_latest = dict(data)
        if self._air_callback_external:
            self._air_callback_external(data)

    def _temp_callback(self, data: Dict[str, Any]) -> None:
        """Called by temp_hum run_temp_hum_listener with each new reading."""
        with self._temp_lock:
            self._temp_latest = dict(data)
        if self._temp_callback_external:
            self._temp_callback_external(data)

    def _ultrasonic_callback(self, data: Dict[str, Any]) -> None:
        """Called by ultrasonic run_ultrasonic_check with each new reading/alert."""
        with self._ultrasonic_lock:
            self._ultrasonic_latest = dict(data)
        if self._ultrasonic_callback_external:
            self._ultrasonic_callback_external(data)

    def _lidar_callback(self, data: Dict[str, Any]) -> None:
        """Called by lidar run_detector with each new reading."""
        if "distance_cm" not in data:
            return
        with self._lidar_lock:
            self._lidar_latest = dict(data)

    def _start_lidar_thread(self) -> None:
        """Run LiDAR detector in a daemon thread so the GUI stays responsive."""
        def run() -> None:
            try:
                from utility.lidar import run_detector
                run_detector(callback=self._lidar_callback)
            except Exception as e:
                with self._lidar_lock:
                    self._lidar_latest = {
                        "distance_cm": -1,
                        "out_of_range": True,
                        "last_updated": time.time(),
                        "_error": str(e),
                    }

        self._lidar_thread = threading.Thread(target=run, daemon=True)
        self._lidar_thread.start()

    def _start_nfc_thread(self) -> None:
        """Run NFC listener in a daemon thread."""
        def run() -> None:
            try:
                from utility.nfc import run_nfc_listener
                run_nfc_listener(callback=self._nfc_callback)
            except Exception as e:
                print(f"NFC Thread Error: {e}")

        self._nfc_thread = threading.Thread(target=run, daemon=True)
        self._nfc_thread.start()

    def _start_air_thread(self) -> None:
        """Run Air Quality listener in a daemon thread."""
        def run() -> None:
            try:
                from utility.airquality import run_air_quality_listener
                run_air_quality_listener(callback=self._air_callback)
            except Exception as e:
                print(f"AirQuality Thread Error: {e}")

        self._air_thread = threading.Thread(target=run, daemon=True)
        self._air_thread.start()

    def _start_temp_thread(self) -> None:
        """Run Temperature/Humidity listener in a daemon thread."""
        def run() -> None:
            try:
                from utility.temp_hum import run_temp_hum_listener
                run_temp_hum_listener(callback=self._temp_callback)
            except Exception as e:
                print(f"Temp/Hum Thread Error: {e}")

        self._temp_thread = threading.Thread(target=run, daemon=True)
        self._temp_thread.start()

    def _start_ultrasonic_thread(self) -> None:
        """Run Ultrasonic listener in a daemon thread."""
        def run() -> None:
            try:
                from utility.ultrasonic import run_ultrasonic_check
                run_ultrasonic_check(callback=self._ultrasonic_callback)
            except Exception as e:
                print(f"Ultrasonic Thread Error: {e}")

        self._ultrasonic_thread = threading.Thread(target=run, daemon=True)
        self._ultrasonic_thread.start()

    def get_available_sensors(self) -> List[str]:
        """Return the list of available sensor names."""
        return list(self._sensor_names)

    def get_latest_readings(self) -> Dict[str, SensorReading]:
        """
        Return a mapping from sensor name to its latest reading.

        In this simulated version, we generate smooth, time‑varying values
        using sine waves plus a bit of random noise.
        """
        now = time.time()
        t = now - self._start_time

        readings: Dict[str, SensorReading] = {}
        for index, name in enumerate(self._sensor_names):
            if name == LIDAR_SENSOR_NAME:
                continue
            
            value = None
            unit = "units"

            # Use real data for Temp/Humidity
            if "temp" in name.lower():
                unit = "°C"
                with self._temp_lock:
                    if self._temp_latest:
                        value = self._temp_latest.get("temperature")
            elif "humid" in name.lower():
                unit = "%"
                with self._temp_lock:
                    if self._temp_latest:
                        value = self._temp_latest.get("humidity")
            elif "press" in name.lower():
                unit = "hPa"
                # Keep pressure simulated for now or set to None if no hardware
                value = None 

            readings[name] = SensorReading(
                name=name,
                value=value,
                unit=unit,
                timestamp=now,
            )

        # LiDAR: use cached reading from background thread
        if self._include_lidar:
            with self._lidar_lock:
                raw = self._lidar_latest
            if raw and "distance_cm" in raw:
                try:
                    ts = raw.get("last_updated")
                    if isinstance(ts, str):
                        from datetime import datetime
                        ts = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
                    elif not isinstance(ts, (int, float)):
                        ts = now
                    val = float(raw["distance_cm"])
                    if raw.get("out_of_range") and (val <= 0 or val == -100):
                        val = -1.0
                    readings[LIDAR_SENSOR_NAME] = SensorReading(
                        name=LIDAR_SENSOR_NAME,
                        value=val,
                        unit="cm",
                        timestamp=ts,
                    )
                except (TypeError, ValueError):
                    readings[LIDAR_SENSOR_NAME] = SensorReading(
                        name=LIDAR_SENSOR_NAME,
                        value=-1.0,
                        unit="cm",
                        timestamp=now,
                    )

        return readings

