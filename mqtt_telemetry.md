# 📡 PapayaMeter — Complete MQTT Telemetry Reference

## Connection Details

| Property | Value |
|---|---|
| **Protocol** | MQTT over TCP/IP |
| **Host** | `thingsboard-poc.papayaparking.com` |
| **Port** | `1883` (plain) · `8883` (TLS) |
| **Authentication** | Device Access Token as **MQTT username** (no password) |
| **Topic** | `v1/devices/me/telemetry` |

> **All events and sensor readings are published to the single topic:** `v1/devices/me/telemetry`  
> Records are differentiated in ThingsBoard using the **key prefixes** inside the `values` object (e.g. `parking.*`, `ultrasonic.*`, `tamper.*`).

---

## Payload Envelope

Every message uses this standard ThingsBoard envelope:

```json
{
  "ts": 1706623628000,
  "values": {
    "key": "value"
  }
}
```

`ts` is always Unix epoch in **milliseconds**, taken from the device system clock at the moment the event fires.

---

## � Published Topics Summary

| Prefix | Source | Frequency |
|---|---|---|
| `parking.*` | Parking lifecycle | On event (start / stop / payment) |
| `ultrasonic.*` | Ultrasonic sensors | ~20 Hz per sensor (continuous) |
| `proximity_alert.*` | Ultrasonic alert threshold breach | Only when alert fires |
| `tamper.*` | IMU tamper detection | Only when tamper is detected |
| `airquality.*` | PM2.5 / PM10 sensor | Every ~6 seconds (5 reading average) |
| `temperature.*` | SHT4x temperature & humidity | Every 1 second |

---

## 🚗 Parking Events

### 1. `parking_start` — Vehicle Arrives

Published when the operator confirms a session has started.

```json
{
  "ts": 1741010158000,
  "values": {
    "parking.event":       "parking_start",
    "parking.spot":        "LEFT SPOT",
    "parking.spot_id":     "SP-047",
    "parking.plate":       "7FGH-829",
    "parking.start_time":  "2026-03-03T17:15:58",
    "parking.start_ts_ms": 1741010158000,
    "parking.hourly_rate": 3.0
  }
}
```

| Field | Type | Description |
|---|---|---|
| `parking.event` | `string` | Always `"parking_start"` |
| `parking.spot` | `string` | Human-readable spot name (`LEFT SPOT` / `RIGHT SPOT`) |
| `parking.spot_id` | `string` | DB spot code (`SP-047` / `SP-048`) |
| `parking.plate` | `string` | Licence plate entered by operator |
| `parking.start_time` | `string` | ISO 8601 session start (device local time) |
| `parking.start_ts_ms` | `integer` | Session start in Unix milliseconds |
| `parking.hourly_rate` | `float` | Configured rate — currency per hour |

---

### 2. `parking_stop` — Operator Presses STOP

Published when STOP is pressed. Payment has **not yet** been collected. Use this to show elapsed time and accrued charge.

```json
{
  "ts": 1741012558000,
  "values": {
    "parking.event":          "parking_stop",
    "parking.spot":           "LEFT SPOT",
    "parking.spot_id":        "SP-047",
    "parking.plate":          "7FGH-829",
    "parking.start_time":     "2026-03-03T17:15:58",
    "parking.start_ts_ms":    1741010158000,
    "parking.stop_time":      "2026-03-03T17:55:58",
    "parking.stop_ts_ms":     1741012558000,
    "parking.duration_secs":  2400.0,
    "parking.duration_mins":  40.0,
    "parking.hourly_rate":    3.0,
    "parking.accrued_amount": 2.0,
    "parking.paid":           false
  }
}
```

| Field | Type | Description |
|---|---|---|
| `parking.event` | `string` | Always `"parking_stop"` |
| `parking.stop_time` | `string` | ISO 8601 stop time |
| `parking.stop_ts_ms` | `integer` | Stop time in Unix milliseconds |
| `parking.duration_secs` | `float` | Total parked time in seconds |
| `parking.duration_mins` | `float` | Total parked time in minutes |
| `parking.accrued_amount` | `float` | Amount owed — not yet paid |
| `parking.paid` | `boolean` | Always `false` at this point |

---

### 3. `parking_payment` — Payment Collected

Published when NFC payment is confirmed. The session is fully complete.

```json
{
  "ts": 1741012600000,
  "values": {
    "parking.event":          "parking_payment",
    "parking.spot":           "LEFT SPOT",
    "parking.spot_id":        "SP-047",
    "parking.plate":          "7FGH-829",
    "parking.start_time":     "2026-03-03T17:15:58",
    "parking.start_ts_ms":    1741010158000,
    "parking.payment_time":   "2026-03-03T17:56:40",
    "parking.payment_ts_ms":  1741012600000,
    "parking.duration_secs":  2400.0,
    "parking.duration_mins":  40.0,
    "parking.hourly_rate":    3.0,
    "parking.total_amount":   2.0,
    "parking.paid":           true
  }
}
```

| Field | Type | Description |
|---|---|---|
| `parking.event` | `string` | Always `"parking_payment"` |
| `parking.payment_time` | `string` | ISO 8601 timestamp of successful payment |
| `parking.payment_ts_ms` | `integer` | Payment time in Unix milliseconds |
| `parking.total_amount` | `float` | Final amount charged and collected |
| `parking.paid` | `boolean` | Always `true` |

---

## 📻 Ultrasonic Sensor Telemetry

Published **continuously on every reading** (~20 readings/second per sensor). Keys are dynamic based on the `config.properties` section name.

```json
{
  "ts": 1741010200050,
  "values": {
    "ultrasonic.ultrasonic_front.distance_cm":  28.4,
    "ultrasonic.ultrasonic_front.threshold_cm": 30.0,
    "ultrasonic.ultrasonic_front.alert":         true,
    "ultrasonic.ultrasonic_front.timestamp":     "2026-03-03T17:16:40.050000"
  }
}
```

```json
{
  "ts": 1741010200100,
  "values": {
    "ultrasonic.ultrasonic_back.distance_cm":  55.7,
    "ultrasonic.ultrasonic_back.threshold_cm": 30.0,
    "ultrasonic.ultrasonic_back.alert":         false,
    "ultrasonic.ultrasonic_back.timestamp":     "2026-03-03T17:16:40.100000"
  }
}
```

| Field Pattern | Type | Description |
|---|---|---|
| `ultrasonic.<sensor>.distance_cm` | `float` | Measured distance in centimetres |
| `ultrasonic.<sensor>.threshold_cm` | `float` | Alert threshold from `config.properties` |
| `ultrasonic.<sensor>.alert` | `boolean` | `true` if distance < threshold |
| `ultrasonic.<sensor>.timestamp` | `string` | ISO 8601 reading timestamp |

> `<sensor>` = `ultrasonic_front` or `ultrasonic_back` (matches config section name)

---

## 🚨 Proximity Alert Telemetry

Published **only when an alert fires** (i.e. `distance_cm < threshold_cm`) — a separate, dedicated event on top of the continuous ultrasonic stream above.

```json
{
  "ts": 1741010200050,
  "values": {
    "proximity_alert.sensor":       "ultrasonic_front",
    "proximity_alert.distance_cm":  28.4,
    "proximity_alert.threshold_cm": 30.0,
    "proximity_alert.message":      "ALERT: Object is too near on ultrasonic_front! (28.4 cm)",
    "proximity_alert.timestamp":    "2026-03-03T17:16:40.050000"
  }
}
```

| Field | Type | Description |
|---|---|---|
| `proximity_alert.sensor` | `string` | Which sensor triggered the alert |
| `proximity_alert.distance_cm` | `float` | Measured distance at alert moment |
| `proximity_alert.threshold_cm` | `float` | Configured threshold that was breached |
| `proximity_alert.message` | `string` | Human-readable alert message (also shown on GUI) |
| `proximity_alert.timestamp` | `string` | ISO 8601 alert timestamp |

> **Note:** If the sensor is ignored by the operator for 60 seconds (via the GUI IGNORE button), proximity alert events are suppressed locally AND not published to MQTT during that window.

---

## 🔒 Tamper Detection Telemetry

Published **only when a tamper event is detected** by the IMU (LSM6DS3). A cooldown of `cooldown_sec` seconds (default 5 s, configurable) prevents flooding.

```json
{
  "ts": 1741010500000,
  "values": {
    "tamper.event":     "TAMPER",
    "tamper.tilt_deg":  14.3,
    "tamper.gyro_dps":  31.7,
    "tamper.linear_g":  0.17,
    "tamper.message":   "Tamper detected - Device moved or shaken",
    "tamper.timestamp": "2026-03-03T17:21:40.000000"
  }
}
```

| Field | Type | Description |
|---|---|---|
| `tamper.event` | `string` | Always `"TAMPER"` |
| `tamper.tilt_deg` | `float` | Tilt angle in degrees from calibrated baseline |
| `tamper.gyro_dps` | `float` | Gyroscope magnitude in degrees per second |
| `tamper.linear_g` | `float` | Linear acceleration magnitude in g-force |
| `tamper.message` | `string` | Human-readable description |
| `tamper.timestamp` | `string` | ISO 8601 timestamp |

> **Detection triggers:** tilt > 12°, sustained gyro > 25 dps, sustained linear > 0.12 g, or sudden spike > 0.4 g / 120 dps. Thresholds configurable in `config.properties [tamper]`.

---

## 🌬️ Air Quality Telemetry

Published every **~6 seconds** (average of 5 readings per cycle) from the SDS011-class PM sensor.

```json
{
  "ts": 1741010200000,
  "values": {
    "airquality.pm1_0":      5.2,
    "airquality.pm2_5":      8.7,
    "airquality.pm10":       12.4,
    "airquality.aqi_status": "Good",
    "airquality.timestamp":  "2026-03-03T17:16:40.000000"
  }
}
```

| Field | Type | Description |
|---|---|---|
| `airquality.pm1_0` | `float` | PM1.0 concentration (µg/m³) |
| `airquality.pm2_5` | `float` | PM2.5 concentration (µg/m³) — primary air quality index |
| `airquality.pm10` | `float` | PM10 concentration (µg/m³) |
| `airquality.aqi_status` | `string` | Computed status: `"Good"` (<12), `"Moderate"` (<35), `"Unhealthy"` (≥35) |
| `airquality.timestamp` | `string` | ISO 8601 reading timestamp |

---

## 🌡️ Temperature & Humidity Telemetry

Published every **1 second** from the SHT4x sensor over I2C.

```json
{
  "ts": 1741010201000,
  "values": {
    "temperature.celsius":      24.35,
    "temperature.humidity_pct": 61.20,
    "temperature.timestamp":    "2026-03-03T17:16:41.000000"
  }
}
```

| Field | Type | Description |
|---|---|---|
| `temperature.celsius` | `float` | Ambient temperature in °C |
| `temperature.humidity_pct` | `float` | Relative humidity in % |
| `temperature.timestamp` | `string` | ISO 8601 reading timestamp |

---

## 📊 Parking Session Lifecycle

```
parking_start ─────────────────────► parking_stop ──────► parking_payment
      │                                    │                      │
  start_time                           stop_time             payment_time
  plate / spot                         duration              total_amount
  hourly_rate                       accrued_amount            paid = true
                                       paid = false
```

### Recommended ThingsBoard Widgets

| Widget Type | Key(s) to use |
|---|---|
| Latest Telemetry card | `parking.plate`, `parking.spot`, `parking.paid` |
| Time-since card | `parking.start_ts_ms` → compute elapsed |
| Value card | `parking.total_amount`, `parking.duration_mins` |
| Time-series chart | `ultrasonic.ultrasonic_front.distance_cm`, `ultrasonic.ultrasonic_back.distance_cm` |
| Gauge | `temperature.celsius`, `temperature.humidity_pct` |
| Alarm widget | `tamper.event`, `proximity_alert.message` |
| Bar chart | `airquality.pm2_5`, `airquality.pm10` |

---

## ⚙️ Configuration Reference

All thresholds and sensor parameters are in `config.properties`:

```ini
[thingsboard]
url   = https://thingsboard-poc.papayaparking.com
token = <Device Access Token>               ; used as MQTT username

[parking]
hourly_rate = 3                             ; currency per hour

[ultrasonic_front]
serial_port  = /dev/papaya_ultrasonic_front
baud_rate    = 9600
threshold_cm = 30

[ultrasonic_back]
serial_port  = /dev/papaya_ultrasonic_back
baud_rate    = 9600
threshold_cm = 30

[tamper]
i2c_bus             = 7
i2c_address         = 0x6b
tilt_threshold_deg  = 12.0
gyro_threshold_dps  = 25.0
linear_threshold_g  = 0.12
cooldown_sec        = 5.0
sample_hz           = 10

[airquality]
serial_port = /dev/papaya_air
baud_rate   = 1200
timeout     = 1

[temperature]
i2c_bus          = 7
i2c_address      = 0x44
polling_interval_s = 1
```

---

*PapayaMeter IoT System — MQTT Telemetry Reference · Last updated: 2026-03-03*
