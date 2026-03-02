#!/usr/bin/env python3

import serial
import time
import sys
import argparse


class LedController:
    """
    Arduino Nano LED Controller

    Supported Arduino Commands:
        COLOR,ON_MS,OFF_MS,BRIGHTNESS
        STOP
    """

    VALID_COLORS = ["RED", "AMBER", "GREEN"]

    def __init__(self, port: str, baudrate: int = 9600):
        self.port = port
        self.baudrate = baudrate
        self.ser = None

    # --------------------------------------------------
    # Connection Handling
    # --------------------------------------------------

    def connect(self):
        try:
            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=2
            )

            # Arduino auto-resets on serial open
            time.sleep(2)

            # Clear boot text
            self.ser.reset_input_buffer()

            print(f"[INFO] Connected to {self.port}")

        except serial.SerialException as e:
            print(f"[ERROR] Could not open serial port: {e}")
            sys.exit(1)

    def disconnect(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
            print("[INFO] Serial port closed")

    # --------------------------------------------------
    # Low-Level Send
    # --------------------------------------------------

    def _send(self, command: str):
        if not self.ser or not self.ser.is_open:
            raise RuntimeError("Serial port not open")

        full_cmd = command.strip() + "\n"

        print(f"[SEND] {command}")

        self.ser.write(full_cmd.encode("ascii"))
        self.ser.flush()

        # Read single response line
        response = self.ser.readline().decode("ascii", errors="ignore").strip()

        if response:
            print(f"[ARDUINO] {response}")

    # --------------------------------------------------
    # Public API
    # --------------------------------------------------

    def blink(self, color: str, on_ms: int, off_ms: int,
              brightness: int, oneshot: bool = False):

        color = color.upper()

        if color not in self.VALID_COLORS:
            raise ValueError("Color must be RED, AMBER, or GREEN")

        if not (1 <= on_ms <= 10000):
            raise ValueError("ON time must be 1–10000 ms")

        if not (1 <= off_ms <= 10000):
            raise ValueError("OFF time must be 1–10000 ms")

        if not (0 <= brightness <= 255):
            raise ValueError("Brightness must be 0–255")

        cmd = f"{color},{on_ms},{off_ms},{brightness}"
        self._send(cmd)

        if oneshot:
            # Wait exactly one full blink cycle
            total_time = (on_ms + off_ms) / 1000.0
            time.sleep(total_time)

            self.stop()

    def stop(self):
        self._send("STOP")


# =====================================================
# CLI Interface
# =====================================================

def main():

    parser = argparse.ArgumentParser(
        description="Control Arduino Nano LED Beacon"
    )

    parser.add_argument(
        "--port",
        required=True,
        help="Serial port (e.g. /dev/ttyUSB3 or COM3)"
    )

    subparsers = parser.add_subparsers(dest="command")

    # Blink command
    blink_parser = subparsers.add_parser("blink")
    blink_parser.add_argument("color", help="RED / AMBER / GREEN")
    blink_parser.add_argument("on", type=int, help="ON time (ms)")
    blink_parser.add_argument("off", type=int, help="OFF time (ms)")
    blink_parser.add_argument("brightness", type=int,
                              help="Brightness (0-255)")
    blink_parser.add_argument(
        "--oneshot",
        action="store_true",
        help="Blink only once instead of continuous"
    )

    # Stop command
    subparsers.add_parser("stop")

    args = parser.parse_args()

    controller = LedController(args.port)
    controller.connect()

    try:
        if args.command == "blink":
            controller.blink(
                args.color,
                args.on,
                args.off,
                args.brightness,
                oneshot=args.oneshot
            )

        elif args.command == "stop":
            controller.stop()

        else:
            parser.print_help()

    except Exception as e:
        print(f"[ERROR] {e}")

    finally:
        controller.disconnect()


if __name__ == "__main__":
    main()
