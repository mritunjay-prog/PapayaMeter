# 📡 ThingsBoard Data Transmission & Protocol Guide

## 🌟 Overview
This document explains the technical protocols and mechanisms used by the IoT system to transmit sensor data to the ThingsBoard platform. It covers the underlying protocol, the background architecture for reliable delivery, and the specific code implementation.

---

## 🏗️ Protocol Architecture

The system standardizes on the **MQTT (Message Queuing Telemetry Transport)** protocol for all real-time sensor data.

### 📡 Network Details
*   **Protocol**: MQTT over TCP/IP.
*   **Port**: 1883 (Standard) or 8883 (Secure/TLS).
*   **Authentication**: The **Device Access Token** (obtained during provisioning) is used as the MQTT username. No password is required by ThingsBoard.
*   **Primary Topic**: `v1/devices/me/telemetry`

---

## 🔄 How Data is Sent (The Mechanism)

To ensure the system remains responsive, even during high-frequency sensor scans or network latency, we use a **Non-Blocking Background Worker** pattern.

### 1. The Queueing System (`services/telemetry_publisher.py`)
Instead of sending data immediately, sensors push their data into a thread-safe `queue.Queue`. 
- **Benefit**: If the internet is slow, the sensor doesn't wait; it just drops the data in the queue and moves on to the next reading.

### 2. The Publishing Worker
A dedicated background thread (`_publishing_worker`) runs in a continuous loop:
1.  **Wait**: It waits for data to appear in the queue.
2.  **JSON Packing**: It converts the Python dictionary into a JSON string.
3.  **MQTT Publish**: It uses the `paho-mqtt` library to send the packet to ThingsBoard.

---

## 💻 Code Implementation

### Data Structure (JSON)
ThingsBoard expects a specific JSON format. The system automatically wraps sensor readings into this structure:
```json
{
  "ts": 1706623628000, 
  "values": {
    "sensor.metric_name": 42.5,
    "sensor.status": "OK"
  }
}
```

### Core Logic (Python)
The actual transmission logic located in `services/telemetry_publisher.py`:

```python
def _publish_to_mqtt(self, topic: str, payload: Dict[str, Any]) -> bool:
    """
    The final step where data actually leaves the device.
    """
    try:
        if self.mqtt_client:
            # payload is converted to JSON string and sent
            self.mqtt_client.publish(topic, json.dumps(payload))
            self.publish_count += 1
            return True
        return False
    except Exception as e:
        print(f"❌ Error publishing to MQTT: {e}")
        return False
```

### Usage Example
To send data from any part of the program, developers use the convenience functions:
```python
from services.telemetry_publisher import publish_telemetry

# Just provide the values, the system handles the rest
data = {"ultrasonic.sensor_1": 150.5}
publish_telemetry({"values": data})
```

---

## 📊 Summary of Flow
1.  **Hardware**: Sensor reads raw voltage/signals.
2.  **Service**: Sensor service calculates the actual value (e.g., cm, °C).
3.  **Publisher**: Value is queued in `telemetry_publisher`.
4.  **MQTT Client**: Data is serialized to JSON and pushed to `v1/devices/me/telemetry`.
5.  **ThingsBoard**: Data appears on the dashboard in real-time.

---

**IoT Sensor Management System** - *Reliable Data Pipeline Documentation*
