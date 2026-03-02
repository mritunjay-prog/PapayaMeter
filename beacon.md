# Arduino Nano LED Beacon Control

## Python–Arduino Integration Documentation

---

# 1. System Overview

This system consists of:

* **Arduino Nano (ATmega328P)** running LED control firmware
* **Python control script (`beacon_light.py`)** running on Jetson/Linux
* Serial communication at **9600 baud**
* PWM control of:

  * RED LED → Pin 9
  * AMBER LED → Pin 10
  * GREEN LED → Pin 11

The Python script sends structured ASCII commands over serial to control LED behavior.

---

# 2. Serial Communication Settings

| Parameter   | Value          |
| ----------- | -------------- |
| Baudrate    | 9600           |
| Data Bits   | 8              |
| Parity      | None           |
| Stop Bits   | 1              |
| Line Ending | `\n` (newline) |

⚠ Ensure Arduino IDE Serial Monitor is closed when using the Python script.

---

# 3. Communication Protocol

## Command Format

```
COLOR,ON_MS,OFF_MS,BRIGHTNESS
```

### Parameters

| Field      | Range               | Description                  |
| ---------- | ------------------- | ---------------------------- |
| COLOR      | RED / GREEN / AMBER | Select LED                   |
| ON_MS      | 1–10000             | ON duration in milliseconds  |
| OFF_MS     | 1–10000             | OFF duration in milliseconds |
| BRIGHTNESS | 0–255               | PWM brightness level         |

---

## STOP Command

```
STOP
```

Immediately turns off all LEDs and returns the system to idle state.

---

# 4. Python Script Behaviour

## On Startup

When the Python script runs:

1. Opens specified serial port
2. Waits 2 seconds (Arduino auto-reset handling)
3. Flushes serial input buffer
4. Sends command
5. Reads one response from Arduino
6. Closes serial port

The script is **command-driven**, not streaming.

---

# 5. LED Behaviour

## Continuous Blink Mode

When a blink command is sent:

1. Arduino enters blinking state
2. Selected LED:

   * Turns ON for `ON_MS`
   * Turns OFF for `OFF_MS`
   * Repeats continuously
3. Continues until a STOP command is issued

---

## One-Shot Mode (If `--oneshot` Flag Used)

When `--oneshot` is used:

1. Python sends blink command
2. Waits for one complete ON + OFF cycle
3. Automatically sends STOP
4. LED turns OFF

---

# 6. Python Command Usage

Replace `/dev/ttyUSB4` with your actual serial device.

---

## GREEN LED

### Continuous Blink

```bash
python3 beacon_light.py --port /dev/ttyUSB4 blink GREEN 200 800 50
```

Meaning:

* ON = 200 ms
* OFF = 800 ms
* Brightness = 50
* Repeats indefinitely

### Single Blink

```bash
python3 beacon_light.py --port /dev/ttyUSB4 blink GREEN 200 800 50 --oneshot
```

---

## RED LED

### Continuous Blink

```bash
python3 beacon_light.py --port /dev/ttyUSB4 blink RED 500 500 255
```

* Full brightness
* Equal ON/OFF timing

### Single Blink

```bash
python3 beacon_light.py --port /dev/ttyUSB4 blink RED 500 500 255 --oneshot
```

---

## AMBER LED

### Continuous Blink

```bash
python3 beacon_light.py --port /dev/ttyUSB4 blink AMBER 100 100 120
```

### Single Blink

```bash
python3 beacon_light.py --port /dev/ttyUSB4 blink AMBER 100 100 120 --oneshot
```

---

## STOP – Turn Off All LEDs

```bash
python3 beacon_light.py --port /dev/ttyUSB4 stop
```

Effect:

* Stops blinking
* All LEDs OFF

---

# 7. Operational Rules

* Only one LED can blink at a time.
* A new blink command overrides the previous state.
* STOP command immediately halts blinking.
* Brightness uses Arduino PWM (0–255).
* Serial port must not be shared by other applications.
* Correct device path must be used (`/dev/ttyUSBx` or `/dev/ttyACMx`).

---

# 8. Behaviour Summary Table

| Python Command  | Arduino State  | LED Result   |
| --------------- | -------------- | ------------ |
| blink RED ...   | STATE_BLINKING | RED blinks   |
| blink GREEN ... | STATE_BLINKING | GREEN blinks |
| blink AMBER ... | STATE_BLINKING | AMBER blinks |
| stop            | STATE_IDLE     | All LEDs OFF |

---

# 9. Example Application Scenarios

### Error Indicator

```bash
python3 beacon_light.py --port /dev/ttyUSB4 blink RED 200 200 255
```

### System OK Indicator

```bash
python3 beacon_light.py --port /dev/ttyUSB4 blink GREEN 1000 1000 80
```

### Warning Indicator

```bash
python3 beacon_light.py --port /dev/ttyUSB4 blink AMBER 300 300 180
```

### System Shutdown

```bash
python3 beacon_light.py --port /dev/ttyUSB4 stop
```

---

# 10. Deployment Context

Suitable for:

* Jetson Nano / Xavier systems
* Robotics status indication
* Industrial signal towers
* Embedded diagnostics systems
* Autonomous platforms

---

# 11. Expected Arduino Responses

Examples of responses from Arduino:

```
OK: GREEN ON=200 OFF=800 BRIGHT=50
OK: STOPPED
ERR: Invalid color
ERR: Time must be 1-10000 ms
ERR: Brightness 0-255
```

These responses confirm command parsing and execution.

---

# 12. System Architecture Summary

Python Script
↓ (Serial ASCII Command @ 9600 baud)
Arduino Nano
↓
PWM Output → LED Driver → Physical LED

---

End of Documentation
