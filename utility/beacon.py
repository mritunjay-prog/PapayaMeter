#!/usr/bin/env python3
"""
beacon.py — Arduino Nano LED Beacon Controller
------------------------------------------------
Wraps the serial communication logic from beacon_test.py into a clean
importable service class for use by the PapayaMeter GUI and CLI.

Serial protocol (9600 baud, ASCII):
  Blink:  COLOR,ON_MS,OFF_MS,BRIGHTNESS\n
  Stop:   STOP\n

Supported colors: RED, AMBER, GREEN
"""

import serial
import time
import threading
import configparser
import os
from typing import Optional

CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', 'config.properties')


def _load_port() -> str:
    """Read beacon serial port from config.properties."""
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_PATH)
    return cfg.get('beacon', 'serial_port', fallback='/dev/papaya_beacon')


def _load_baudrate() -> int:
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_PATH)
    return cfg.getint('beacon', 'baud_rate', fallback=9600)


class BeaconController:
    """
    Thread-safe controller for the Arduino Nano LED beacon.

    Usage:
        beacon = BeaconController()
        beacon.connect()
        beacon.blink('GREEN', on_ms=500, off_ms=500, brightness=80)
        beacon.stop()
        beacon.disconnect()
    """

    VALID_COLORS = ['RED', 'AMBER', 'GREEN']

    def __init__(self, port: Optional[str] = None, baudrate: Optional[int] = None):
        self.port     = port     or _load_port()
        self.baudrate = baudrate or _load_baudrate()
        self._ser: Optional[serial.Serial] = None
        self._lock = threading.Lock()

    # ── Connection ──────────────────────────────────────────────────────

    def connect(self) -> bool:
        """Open the serial port. Returns True on success."""
        try:
            self._ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=2
            )
            time.sleep(2)                     # Arduino auto-reset time
            self._ser.reset_input_buffer()
            print(f"[Beacon] Connected on {self.port} @ {self.baudrate} baud")
            return True
        except serial.SerialException as e:
            print(f"[Beacon] Connection failed: {e}")
            self._ser = None
            return False

    def disconnect(self):
        with self._lock:
            if self._ser and self._ser.is_open:
                self._ser.close()
        print("[Beacon] Disconnected")

    @property
    def is_connected(self) -> bool:
        return self._ser is not None and self._ser.is_open

    # ── Commands ────────────────────────────────────────────────────────

    def blink(self,
              color: str,
              on_ms: int   = 500,
              off_ms: int  = 500,
              brightness: int = 128,
              oneshot: bool   = False) -> str:
        """
        Start blinking a LED.

        Args:
            color:      'RED' | 'AMBER' | 'GREEN'
            on_ms:      ON duration  (1–10000 ms)
            off_ms:     OFF duration (1–10000 ms)
            brightness: PWM value   (0–255)
            oneshot:    If True, blink once then auto-stop.

        Returns:
            Arduino response string.
        """
        color = color.upper()
        if color not in self.VALID_COLORS:
            raise ValueError(f"Color must be one of {self.VALID_COLORS}")
        if not (1 <= on_ms <= 10000):
            raise ValueError("on_ms must be 1–10000")
        if not (1 <= off_ms <= 10000):
            raise ValueError("off_ms must be 1–10000")
        if not (0 <= brightness <= 255):
            raise ValueError("brightness must be 0–255")

        cmd = f"{color},{on_ms},{off_ms},{brightness}"
        response = self._send(cmd)

        if oneshot:
            total = (on_ms + off_ms) / 1000.0
            time.sleep(total)
            self.stop()

        return response

    def stop(self) -> str:
        """Turn off all LEDs and return Arduino to idle."""
        return self._send("STOP")

    # ── Convenience presets ─────────────────────────────────────────────

    def signal_ok(self):
        """Green slow blink — system OK."""
        self.blink('GREEN', on_ms=1000, off_ms=1000, brightness=80)

    def signal_warning(self):
        """Amber medium blink — warning."""
        self.blink('AMBER', on_ms=300, off_ms=300, brightness=180)

    def signal_error(self):
        """Red fast blink — error."""
        self.blink('RED', on_ms=200, off_ms=200, brightness=255)

    # ── Internal ────────────────────────────────────────────────────────

    def _send(self, command: str) -> str:
        if not self.is_connected:
            raise RuntimeError("Beacon not connected. Call connect() first.")
        with self._lock:
            full_cmd = command.strip() + "\n"
            print(f"[Beacon] >> {command}")
            self._ser.write(full_cmd.encode('ascii'))
            self._ser.flush()
            response = self._ser.readline().decode('ascii', errors='ignore').strip()
            if response:
                print(f"[Beacon] << {response}")
            return response
