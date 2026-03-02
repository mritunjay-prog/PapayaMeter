import configparser
from typing import Dict, Optional, Callable

# === FIX: Prevent cv2 from conflicting with PyQt5 ===
# This must happen BEFORE any other imports that might touch Qt or cv2
import os
import sys

# Force PyQt5 to use its own plugins instead of cv2's conflicting ones
venv_base = os.path.dirname(os.path.abspath(__file__))
QT_PLUGINS_PATH = os.path.join(venv_base, 'venv', 'lib', 'python3.10', 'site-packages', 'PyQt5', 'Qt5', 'plugins')
if os.path.exists(QT_PLUGINS_PATH):
    os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = QT_PLUGINS_PATH

# Disable cv2's internal Qt GUI support to prevent "xcb" loading errors
# Let Qt decide the platform (xcb or wayland) but point to the correct plugin path
os.environ["OPENCV_VIDEOIO_PRIORITY_MSMF"] = "0"
# ==================================================

# Use PyQt5 as requested
from PyQt5 import QtCore, QtWidgets, QtGui

# Map PyQt5 names to match the code's expected Qt6 style (if needed)
# Map PyQt5 names to match the code's expected Qt6 style (if needed)
Qt = QtCore.Qt
AlignmentFlag = QtCore.Qt
AspectRatioMode = QtCore.Qt
TransformationMode = QtCore.Qt
FrameShape = QtWidgets.QFrame

# Import time and datetime here after the fix
import time
from datetime import datetime

from sensor_backend import SensorBackend, LIDAR_SENSOR_NAME
from services.system_service import SystemService
from services.database_service import get_db

# Color constants to match the image
COLOR_BG = "#12171e"
COLOR_SPOT_BG = "#1a222c"
COLOR_ACCENT_GREEN = "#39ff5a"
COLOR_ACCENT_BLUE = "#3498db"
COLOR_TEXT_WHITE = "#ffffff"
COLOR_TEXT_GRAY = "#8a97a5"
COLOR_BORDER = "#2a323d"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "gui", "static")

# Load configuration
config = configparser.ConfigParser()
config.read(os.path.join(BASE_DIR, 'config.properties'))
HOURLY_RATE = config.getfloat('parking', 'hourly_rate', fallback=4.25)

class NotificationBar(QtWidgets.QFrame):
    """A floating notification bar for critical alerts."""
    ignored = QtCore.pyqtSignal()
    baseline_requested = QtCore.pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("NotificationBar")
        self.setFixedHeight(60)
        self.setFixedWidth(650)
        self.setStyleSheet(f"""
            #NotificationBar {{
                background-color: #ff0000;
                border-radius: 15px;
                border: 4px solid #ffffff;
            }}
            QLabel {{
                color: white;
                font-weight: bold;
                font-size: 14px;
            }}
            QPushButton {{
                background-color: rgba(255, 255, 255, 0.2);
                color: white;
                border: 1px solid white;
                border-radius: 6px;
                padding: 6px 15px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: rgba(255, 255, 255, 0.3);
            }}
            #BaselineBtn {{
                background-color: #2ecc71;
                border: 1px solid #27ae60;
            }}
            #BaselineBtn:hover {{
                background-color: #27ae60;
            }}
        """)
        
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(20, 0, 20, 0)
        
        self.icon_label = QtWidgets.QLabel("🚨")
        self.icon_label.setStyleSheet("font-size: 24px;")
        layout.addWidget(self.icon_label)
        
        self.msg_label = QtWidgets.QLabel("CRITICAL ALERT: Object detected nearby!")
        layout.addWidget(self.msg_label)
        
        layout.addStretch()

        self.baseline_btn = QtWidgets.QPushButton("SET AS BASELINE")
        self.baseline_btn.setObjectName("BaselineBtn")
        self.baseline_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.baseline_btn.clicked.connect(self.hide_notification)
        self.baseline_btn.clicked.connect(self.baseline_requested.emit)
        layout.addWidget(self.baseline_btn)
        
        self.ignore_btn = QtWidgets.QPushButton("IGNORE ALERT")
        self.ignore_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.ignore_btn.clicked.connect(self.hide_notification)
        self.ignore_btn.clicked.connect(self.ignored.emit)
        layout.addWidget(self.ignore_btn)
        
        self.hide() # Start hidden
        
    def paintEvent(self, event):
        super().paintEvent(event)
        # print(f"[GUI DEBUG] PaintEvent triggered for NotificationBar (Visible: {self.isVisible()})")

    def show_alert(self, message, show_baseline=False):
        self.msg_label.setText(message)
        self.baseline_btn.setVisible(show_baseline)
        
        # Super-forceful visibility
        self.setWindowFlags(QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.FramelessWindowHint | QtCore.Qt.ToolTip)
        
        # Center relative to screen (since it is now a top-level ToolTip for testing)
        if self.parent():
            p_geom = self.parent().geometry()
            x = p_geom.x() + (p_geom.width() - self.width()) // 2
            y = p_geom.y() + 150
            self.move(x, y)
        
        self.show()
        self.raise_()
        self.activateWindow()
        print(f"[GUI DEBUG] !! FORCED TOP-LEVEL SHOW_ALERT !! Msg: {message} at {self.pos()}")

    def hide_notification(self):
        self.hide()

class LogManager(QtCore.QObject):
    """Singleton log manager to capture and distribute logs."""
    log_updated = QtCore.pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self._logs = []
        self._max_lines = 1000
        # Use absolute path to ensure both CLI and GUI point to the same file
        self.log_file = os.path.join(BASE_DIR, "system.log")
        self._last_size = 0
        
        # Initial pull to get existing history
        self._pull_from_file()
        
        # Timer to tail the system.log file for CLI logs
        self.pull_timer = QtCore.QTimer()
        self.pull_timer.timeout.connect(self._pull_from_file)
        self.pull_timer.start(500) # Check faster (every 0.5s)

    def _pull_from_file(self):
        if not os.path.exists(self.log_file):
            return
        
        try:
            current_size = os.path.getsize(self.log_file)
            if current_size > self._last_size:
                with open(self.log_file, "r") as f:
                    f.seek(self._last_size)
                    new_lines = f.readlines()
                    for line in new_lines:
                        # Only show logs that DID NOT come from the GUI process
                        # to avoid double-printing what we just wrote
                        if "[GUI]" not in line:
                            self._logs.append(line)
                            self.log_updated.emit(line)
                self._last_size = current_size
            elif current_size < self._last_size:
                # File was reset
                self._last_size = 0
                self._logs = []
        except Exception as e:
            # Don't print error here or we'll loop!
            pass

    def write(self, text):
        if text.strip():
            timestamp = datetime.now().strftime("[%H:%M:%S]")
            # Tag GUI logs so we can distinguish them from CLI logs in the shared file
            formatted_text = f"{timestamp} [GUI] {text.strip()}\n"
            
            # 1. Update internal log and emit to UI immediately (merged view)
            self._logs.append(formatted_text)
            self.log_updated.emit(formatted_text)
            
            # 2. Persist to shared log file
            try:
                with open(self.log_file, "a") as f:
                    f.write(formatted_text)
            except:
                pass
        sys.__stdout__.write(text)

    def flush(self):
        sys.__stdout__.flush()

    def get_all_logs(self):
        return "".join(self._logs)

# Global logger placeholder
log_manager = None

class SpotWidget(QtWidgets.QWidget):
    """Encapsulated widget for a single parking spot."""
    def __init__(self, name: str, id_code: str, side: str = "left", parent=None):
        super().__init__(parent)
        self.spot_name = name
        self.id_code = id_code
        self.camera_side = side
        self.db_session_id = None
        self.is_occupied = False
        self.plate_number = ""
        self.start_time: Optional[float] = None
        self.elapsed: float = 0
        
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self._update_timer)
        self.timer.setInterval(1000)

        # Camera logic
        self.camera_handler = None
        self.cam_timer = QtCore.QTimer()
        self.cam_timer.timeout.connect(self._update_camera_frame)

        self._init_ui()
        self._set_state_available()

    def _init_ui(self):
        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setContentsMargins(30, 20, 30, 20)

        # TOP ROW: Spot Name and Status
        top_row = QtWidgets.QHBoxLayout()
        self.name_label = QtWidgets.QLabel(f"● {self.spot_name} /{self.id_code}")
        self.name_label.setStyleSheet(f"color: {COLOR_TEXT_GRAY}; font-size: 12px; font-weight: bold;")
        
        self.status_label = QtWidgets.QLabel("VACANT")
        self.status_label.setStyleSheet(f"color: {COLOR_ACCENT_GREEN}; font-size: 12px; font-weight: bold;")
        
        top_row.addWidget(self.name_label)
        top_row.addStretch()
        top_row.addWidget(self.status_label)
        self.main_layout.addLayout(top_row)

        # Camera Feed Placeholder (As seen in image)
        self.camera_feed_label = QtWidgets.QLabel(f"{self.camera_side.capitalize()} Camera Feed")
        self.camera_feed_label.setFixedSize(240, 180)
        self.camera_feed_label.setAlignment(QtCore.Qt.AlignCenter)
        self.camera_feed_label.setStyleSheet(f"""
            background-color: #f7f7f7;
            border: 1px solid #dcdcdc;
            border-radius: 4px;
            color: #333333;
            font-size: 14px;
            font-weight: bold;
        """)
        
        cam_row = QtWidgets.QHBoxLayout()
        cam_row.addStretch()
        cam_row.addWidget(self.camera_feed_label)
        self.main_layout.addLayout(cam_row)

        self.main_layout.addStretch()

        # STACKED CONTENT (Available / Input / Occupied / Payment)
        self.content_stack = QtWidgets.QStackedWidget()
        self.main_layout.addWidget(self.content_stack)

        # 1. Available View
        self.avail_view = QtWidgets.QWidget()
        av_layout = QtWidgets.QVBoxLayout(self.avail_view)
        av_layout.setAlignment(AlignmentFlag.AlignCenter)
        
        self.avail_icon = QtWidgets.QLabel()
        self.avail_icon.setPixmap(QtGui.QPixmap(os.path.join(STATIC_DIR, "available.png")).scaled(120, 120, AspectRatioMode.KeepAspectRatio, TransformationMode.SmoothTransformation))
        av_layout.addWidget(self.avail_icon, alignment=AlignmentFlag.AlignCenter)
        
        av_text = QtWidgets.QLabel("AVAILABLE")
        av_text.setStyleSheet(f"color: {COLOR_ACCENT_GREEN}; font-size: 18px; font-weight: bold; margin-top: 10px;")
        av_layout.addWidget(av_text, alignment=AlignmentFlag.AlignCenter)
        
        wait_text = QtWidgets.QLabel("Waiting for vehicle")
        wait_text.setStyleSheet(f"color: {COLOR_TEXT_GRAY}; font-size: 12px;")
        av_layout.addWidget(wait_text, alignment=AlignmentFlag.AlignCenter)
        
        self.start_btn = QtWidgets.QPushButton("START PARKING")
        self.start_btn.setStyleSheet(self._button_style(COLOR_ACCENT_GREEN))
        self.start_btn.clicked.connect(self._set_state_input)
        av_layout.addWidget(self.start_btn, alignment=AlignmentFlag.AlignCenter)
        
        self.content_stack.addWidget(self.avail_view)

        # 2. Input View
        self.input_view = QtWidgets.QWidget()
        in_layout = QtWidgets.QVBoxLayout(self.input_view)
        in_layout.setAlignment(AlignmentFlag.AlignCenter)
        
        in_label = QtWidgets.QLabel("ENTER PLATE NUMBER")
        in_label.setStyleSheet(f"color: {COLOR_TEXT_WHITE}; font-size: 14px; font-weight: bold;")
        in_layout.addWidget(in_label, alignment=AlignmentFlag.AlignCenter)
        
        self.plate_input = QtWidgets.QLineEdit()
        self.plate_input.setPlaceholderText("e.g. 7FGH-829")
        self.plate_input.setFixedWidth(200)
        self.plate_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {COLOR_BG};
                color: {COLOR_TEXT_WHITE};
                border: 1px solid {COLOR_BORDER};
                border-radius: 5px;
                padding: 10px;
                font-size: 16px;
                text-align: center;
            }}
        """)
        in_layout.addWidget(self.plate_input, alignment=AlignmentFlag.AlignCenter)
        
        self.confirm_btn = QtWidgets.QPushButton("CONFIRM")
        self.confirm_btn.setStyleSheet(self._button_style(COLOR_ACCENT_BLUE))
        self.confirm_btn.clicked.connect(self._start_session)
        in_layout.addWidget(self.confirm_btn, alignment=AlignmentFlag.AlignCenter)
        
        self.cancel_btn = QtWidgets.QPushButton("Cancel")
        self.cancel_btn.setStyleSheet("color: #e74c3c; border: none; background: transparent; font-size: 12px;")
        self.cancel_btn.clicked.connect(self._set_state_available)
        in_layout.addWidget(self.cancel_btn, alignment=AlignmentFlag.AlignCenter)
        
        self.content_stack.addWidget(self.input_view)

        # 3. Occupied View
        self.occ_view = QtWidgets.QWidget()
        oc_layout = QtWidgets.QVBoxLayout(self.occ_view)
        oc_layout.setAlignment(AlignmentFlag.AlignCenter)
        
        self.car_icon = QtWidgets.QLabel()
        self.car_icon.setPixmap(QtGui.QPixmap(os.path.join(STATIC_DIR, "car.png")).scaled(200, 200, AspectRatioMode.KeepAspectRatio, TransformationMode.SmoothTransformation))
        oc_layout.addWidget(self.car_icon, alignment=AlignmentFlag.AlignCenter)
        
        self.plate_display_box = QtWidgets.QWidget()
        self.plate_display_box.setStyleSheet(f"background-color: {COLOR_BG}; border: 1px solid {COLOR_BORDER}; border-radius: 8px; padding: 10px;")
        pd_layout = QtWidgets.QVBoxLayout(self.plate_display_box)
        self.plate_label = QtWidgets.QLabel("-----")
        self.plate_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        self.type_label = QtWidgets.QLabel("🚙 SUV Detected")
        self.type_label.setStyleSheet(f"color: {COLOR_TEXT_GRAY}; font-size: 11px;")
        pd_layout.addWidget(self.plate_label, alignment=AlignmentFlag.AlignCenter)
        pd_layout.addWidget(self.type_label, alignment=AlignmentFlag.AlignCenter)
        oc_layout.addWidget(self.plate_display_box, alignment=AlignmentFlag.AlignCenter)
        
        self.timer_label = QtWidgets.QLabel("⏱️ 00:00:00")
        self.timer_label.setStyleSheet(f"color: {COLOR_ACCENT_GREEN}; font-size: 32px; font-weight: bold; margin-top: 10px;")
        oc_layout.addWidget(self.timer_label, alignment=AlignmentFlag.AlignCenter)

        # Rate and Live Amount Display
        self.live_billing_box = QtWidgets.QWidget()
        self.live_billing_box.setStyleSheet(f"background-color: {COLOR_BG}; border: 1px solid {COLOR_BORDER}; border-radius: 12px; padding: 10px; margin-top: 5px;")
        lb_layout = QtWidgets.QVBoxLayout(self.live_billing_box)
        
        self.hourly_rate_label = QtWidgets.QLabel(f"Rate: ${HOURLY_RATE:.2f} / hr")
        self.hourly_rate_label.setStyleSheet(f"color: {COLOR_TEXT_GRAY}; font-size: 13px; font-weight: bold;")
        lb_layout.addWidget(self.hourly_rate_label, alignment=AlignmentFlag.AlignCenter)
        
        self.live_amount_label = QtWidgets.QLabel("Amount: $ 0.00")
        self.live_amount_label.setStyleSheet(f"color: {COLOR_ACCENT_BLUE}; font-size: 20px; font-weight: bold;")
        lb_layout.addWidget(self.live_amount_label, alignment=AlignmentFlag.AlignCenter)
        
        oc_layout.addWidget(self.live_billing_box, alignment=AlignmentFlag.AlignCenter)
        
        btn_row = QtWidgets.QHBoxLayout()
        self.add_time_btn = QtWidgets.QPushButton("+ ADD TIME")
        self.add_time_btn.setStyleSheet(self._button_style(COLOR_ACCENT_GREEN))
        
        self.stop_btn = QtWidgets.QPushButton("STOP")
        self.stop_btn.setStyleSheet(self._button_style("#e74c3c"))
        self.stop_btn.clicked.connect(self._stop_session)
        
        btn_row.addWidget(self.add_time_btn)
        btn_row.addWidget(self.stop_btn)
        oc_layout.addLayout(btn_row)
        
        self.content_stack.addWidget(self.occ_view)

        # 4. Depart View (Screen 1)
        self.depart_view = QtWidgets.QWidget()
        dp_layout = QtWidgets.QVBoxLayout(self.depart_view)
        dp_layout.setAlignment(AlignmentFlag.AlignCenter)
        dp_layout.setSpacing(15)

        self.depart_icon = QtWidgets.QLabel()
        self.depart_icon.setFixedSize(100, 100)
        self.depart_icon.setStyleSheet("""
            background-color: #1a222c;
            border-radius: 20px;
            padding: 20px;
            border: 1px solid #2a323d;
        """)
        self.depart_icon.setPixmap(QtGui.QPixmap(os.path.join(STATIC_DIR, "car.png")).scaled(60, 60, AspectRatioMode.KeepAspectRatio, TransformationMode.SmoothTransformation))
        self.depart_icon.setAlignment(AlignmentFlag.AlignCenter)
        dp_layout.addWidget(self.depart_icon, alignment=AlignmentFlag.AlignCenter)

        dp_title = QtWidgets.QLabel("Ready to Depart?")
        dp_title.setStyleSheet("color: white; font-size: 32px; font-weight: bold; margin-top: 20px;")
        dp_layout.addWidget(dp_title, alignment=AlignmentFlag.AlignCenter)

        dp_desc = QtWidgets.QLabel("Enter your ticket or select the button\nbelow to process your parking\npayment.")
        dp_desc.setAlignment(AlignmentFlag.AlignCenter)
        dp_desc.setStyleSheet(f"color: {COLOR_TEXT_GRAY}; font-size: 16px; line-height: 1.4;")
        dp_layout.addWidget(dp_desc, alignment=AlignmentFlag.AlignCenter)

        self.depart_btn = QtWidgets.QPushButton("Pay For Parking   >")
        self.depart_btn.setFixedSize(380, 70)
        self.depart_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.depart_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: white;
                color: black;
                border: none;
                border-radius: 35px;
                font-weight: bold;
                font-size: 18px;
                margin-top: 30px;
            }}
            QPushButton:hover {{
                background-color: #e0e0e0;
            }}
        """)
        self.depart_btn.clicked.connect(self._show_payment_details)
        dp_layout.addWidget(self.depart_btn, alignment=AlignmentFlag.AlignCenter)
        
        self.content_stack.addWidget(self.depart_view)

        # 5. Payment Detail View (Screen 2)
        self.pay_detail_view = QtWidgets.QWidget()
        pd_v_layout = QtWidgets.QVBoxLayout(self.pay_detail_view)
        pd_v_layout.setContentsMargins(20, 20, 20, 20)

        # Back Button
        self.back_btn = QtWidgets.QPushButton("←")
        self.back_btn.setFixedSize(50, 50)
        self.back_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.back_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #1a222c;
                color: white;
                border: 1px solid {COLOR_BORDER};
                border-radius: 12px;
                font-size: 20px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #2a323d;
            }}
        """)
        self.back_btn.clicked.connect(self._on_back_clicked)
        pd_v_layout.addWidget(self.back_btn)
        
        pd_v_layout.addSpacing(20)

        # Info Card
        self.info_card = QtWidgets.QFrame()
        self.info_card.setStyleSheet(f"background-color: #1a222c; border: 1px solid {COLOR_BORDER}; border-radius: 20px;")
        ic_layout = QtWidgets.QVBoxLayout(self.info_card)
        ic_layout.setContentsMargins(25, 25, 25, 25)

        # Duration Row
        dur_row = QtWidgets.QHBoxLayout()
        self.clock_icon = QtWidgets.QLabel("🕒")
        self.clock_icon.setFixedSize(40, 40)
        self.clock_icon.setStyleSheet("background-color: #263238; border-radius: 20px; font-size: 18px;")
        self.clock_icon.setAlignment(AlignmentFlag.AlignCenter)
        
        dur_texts = QtWidgets.QVBoxLayout()
        dur_title = QtWidgets.QLabel("TOTAL DURATION")
        dur_title.setStyleSheet(f"color: {COLOR_TEXT_GRAY}; font-size: 11px; font-weight: bold; letter-spacing: 1px;")
        self.dur_value = QtWidgets.QLabel("00h 00m")
        self.dur_value.setStyleSheet("color: white; font-size: 24px; font-weight: bold;")
        dur_texts.addWidget(dur_title)
        dur_texts.addWidget(self.dur_value)
        
        dur_row.addWidget(self.clock_icon)
        dur_row.addLayout(dur_texts)
        dur_row.addStretch()
        ic_layout.addLayout(dur_row)

        # Separator
        sep = QtWidgets.QFrame()
        sep.setFrameShape(FrameShape.HLine)
        sep.setStyleSheet(f"background-color: {COLOR_BORDER}; min-height: 1px; max-height: 1px; margin: 15px 0;")
        ic_layout.addWidget(sep)

        # Amount Row
        amt_row = QtWidgets.QHBoxLayout()
        amt_texts = QtWidgets.QVBoxLayout()
        amt_title = QtWidgets.QLabel("AMOUNT DUE")
        amt_title.setStyleSheet(f"color: {COLOR_TEXT_GRAY}; font-size: 11px; font-weight: bold; letter-spacing: 1px;")
        self.amt_value = QtWidgets.QLabel("$ 0.00")
        self.amt_value.setStyleSheet("color: white; font-size: 42px; font-weight: bold;")
        amt_texts.addWidget(amt_title)
        amt_texts.addWidget(self.amt_value)
        
        billing_badge = QtWidgets.QLabel(f"● Billed at ${HOURLY_RATE:.2f}/hr")
        billing_badge.setStyleSheet(f"""
            background-color: #263238;
            color: #3498db;
            padding: 5px 12px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: bold;
        """)
        
        amt_row.addLayout(amt_texts)
        amt_row.addStretch()
        amt_row.addWidget(billing_badge, alignment=AlignmentFlag.AlignBottom)
        ic_layout.addLayout(amt_row)

        pd_v_layout.addWidget(self.info_card)
        pd_v_layout.addStretch()

        # NFC / Mobile Payment Icon
        self.nfc_container = QtWidgets.QWidget()
        nfc_layout = QtWidgets.QVBoxLayout(self.nfc_container)
        
        self.nfc_icon = QtWidgets.QLabel("📱") # Placeholder for icon
        self.nfc_icon.setFixedSize(120, 120)
        self.nfc_icon.setAlignment(AlignmentFlag.AlignCenter)
        self.nfc_icon.setStyleSheet("""
            QLabel {
                background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5, stop:0 #4c51f7, stop:1 transparent);
                border-radius: 60px;
                font-size: 50px;
                color: white;
            }
        """)
        
        # Add ripples (simulated with stylesheet or multiple rings)
        nfc_layout.addWidget(self.nfc_icon, alignment=AlignmentFlag.AlignCenter)
        
        # Clickable icon to simulate payment
        self.nfc_btn = QtWidgets.QPushButton("Simulate NFC Tap")
        self.nfc_btn.setStyleSheet("background: transparent; border: none; color: #3498db; font-size: 10px;")
        self.nfc_btn.clicked.connect(self._process_payment)
        nfc_layout.addWidget(self.nfc_btn, alignment=AlignmentFlag.AlignCenter)

        pd_v_layout.addWidget(self.nfc_container)
        pd_v_layout.addStretch()
        
        self.content_stack.addWidget(self.pay_detail_view)

        self.main_layout.addStretch()

    def _button_style(self, color):
        return f"""
            QPushButton {{
                background-color: {color};
                color: black;
                border: none;
                border-radius: 5px;
                padding: 10px 25px;
                font-weight: bold;
                font-size: 13px;
                margin-top: 10px;
            }}
            QPushButton:hover {{
                opacity: 0.8;
                background-color: {color};
            }}
        """

    def _set_state_available(self):
        self.is_occupied = False
        self.status_label.setText("VACANT")
        self.status_label.setStyleSheet(f"color: {COLOR_ACCENT_GREEN}; font-size: 12px; font-weight: bold;")
        self.content_stack.setCurrentIndex(0)

    def _set_state_input(self):
        # Bypass manual input, use default plate
        self.plate_number = "7FGH-829"
        self._start_session()

    def _start_session(self):
        if not hasattr(self, 'plate_number') or not self.plate_number:
            self.plate_number = "7FGH-829"
        self.plate_label.setText(self.plate_number)
        self.is_occupied = True
        self.status_label.setText("OCCUPIED")
        self.status_label.setStyleSheet(f"color: {COLOR_ACCENT_BLUE}; font-size: 12px; font-weight: bold;")
        self.start_time = time.time()
        self.elapsed = 0
        self.timer.start()
        
        # Create database record
        self.db_session_id = get_db().create_session(self.camera_side, self.plate_number)
        
        self.content_stack.setCurrentIndex(2)

    def _update_timer(self):
        self.elapsed = time.time() - self.start_time
        self.timer_label.setText(f"⏱️ {self._format_time(self.elapsed)}")
        
        # Live amount calculation
        hours = self.elapsed / 3600
        live_amount = max(0.00, hours * HOURLY_RATE)
        self.live_amount_label.setText(f"Amount: $ {live_amount:.2f}")

    def _stop_session(self):
        self.timer.stop()
        # Update end time in DB
        get_db().update_session_on_stop(self.db_session_id)
        self.content_stack.setCurrentIndex(3) # Show Depart View (Screen 1)

    def _show_payment_details(self):
        # Calculate rates
        hours = self.elapsed / 3600
        total_price = max(0.00, hours * HOURLY_RATE)
        
        # Update UI
        h = int(self.elapsed // 3600)
        m = int((self.elapsed % 3600) // 60)
        self.dur_value.setText(f"{h:02d}h {m:02d}m")
        self.amt_value.setText(f"$ {total_price:.2f}")
        
        self.content_stack.setCurrentIndex(4) # Show Payment Details (Screen 2)

    def _on_back_clicked(self):
        self.content_stack.setCurrentIndex(3)

    def _process_payment(self):
        # Calculate final amount for DB
        hours = self.elapsed / 3600
        total_price = max(0.00, hours * HOURLY_RATE)
        
        # Finalize database record
        get_db().complete_payment(self.db_session_id, total_price)

        # Simulated payment
        QtWidgets.QMessageBox.information(self, "Payment Successful", f"Payment processed successfully.\nThank you!")
        self._set_state_available()

    def _format_time(self, seconds):
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    def start_camera(self):
        """Initialize and start the camera feed."""
        try:
            from utility.camera import CameraHandler
            if not self.camera_handler:
                self.camera_handler = CameraHandler(self.camera_side)
            if self.camera_handler.start():
                self.cam_timer.start(33) # ~30 FPS
                return True
            else:
                self.camera_feed_label.setText(f"❌ {self.camera_side.capitalize()} Cam Error")
        except Exception as e:
            print(f"Error starting {self.camera_side} camera: {e}")
        return False

    def stop_camera(self):
        """Stop and release the camera."""
        self.cam_timer.stop()
        if self.camera_handler:
            self.camera_handler.stop()
            self.camera_handler = None
        self.camera_feed_label.setText(f"{self.camera_side.capitalize()} Camera Feed")

    def _update_camera_frame(self):
        """Fetch and display frame from camera."""
        if not self.camera_handler:
            return
            
        frame = self.camera_handler.get_frame()
        if frame is not None:
            h, w, ch = frame.shape
            bytes_per_line = ch * w
            q_img = QtGui.QImage(frame.data, w, h, bytes_per_line, QtGui.QImage.Format_RGB888)
            pixmap = QtGui.QPixmap.fromImage(q_img)
            self.camera_feed_label.setPixmap(pixmap.scaled(
                self.camera_feed_label.width(), 
                self.camera_feed_label.height(), 
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation
            ))

class LidarMonitorDialog(QtWidgets.QDialog):
    """A sleek dialog to monitor live LiDAR data."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("LiDAR Live Monitor")
        self.setFixedSize(400, 300)
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)
        self.setStyleSheet(f"background-color: {COLOR_BG}; color: {COLOR_TEXT_WHITE}; font-family: 'Inter', sans-serif;")
        
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        
        title = QtWidgets.QLabel("📡 LIVE LiDAR STREAM")
        title.setStyleSheet(f"color: {COLOR_ACCENT_BLUE}; font-size: 16px; font-weight: bold; letter-spacing: 1px;")
        layout.addWidget(title, alignment=QtCore.Qt.AlignCenter)
        
        layout.addStretch()
        
        self.value_label = QtWidgets.QLabel("----")
        self.value_label.setStyleSheet("font-size: 64px; font-weight: bold; color: #8a97a5;")
        layout.addWidget(self.value_label, alignment=QtCore.Qt.AlignCenter)
        
        self.unit_label = QtWidgets.QLabel("CENTIMETERS")
        self.unit_label.setStyleSheet(f"color: {COLOR_TEXT_GRAY}; font-size: 12px; font-weight: bold;")
        layout.addWidget(self.unit_label, alignment=QtCore.Qt.AlignCenter)
        
        layout.addStretch()
        
        self.status_label = QtWidgets.QLabel("Status: Waiting for data...")
        self.status_label.setStyleSheet(f"background-color: {COLOR_SPOT_BG}; padding: 8px; border-radius: 5px; font-size: 11px;")
        layout.addWidget(self.status_label, alignment=QtCore.Qt.AlignCenter)
        
        self.close_btn = QtWidgets.QPushButton("CLOSE MONITOR")
        self.close_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_BORDER};
                color: white;
                border: none;
                border-radius: 5px;
                padding: 10px;
                font-weight: bold;
                font-size: 12px;
                margin-top: 20px;
            }}
            QPushButton:hover {{
                background-color: #3d4754;
            }}
        """)
        self.close_btn.clicked.connect(self.close)
        layout.addWidget(self.close_btn)

    def update_value(self, value):
        if value is None or value < 0:
            self.value_label.setText("OOR")
            self.value_label.setStyleSheet("font-size: 64px; font-weight: bold; color: #e74c3c;")
            self.status_label.setText("⚠️ Status: OUT OF RANGE")
        else:
            self.value_label.setText(f"{int(value)}")
            self.value_label.setStyleSheet(f"font-size: 64px; font-weight: bold; color: {COLOR_ACCENT_GREEN};")
            self.status_label.setText("✅ Status: RECEIVING DATA")

class LogViewerDialog(QtWidgets.QDialog):
    """A professional terminal-style log viewer."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("System Operation Logs")
        self.resize(700, 500)
        self.setStyleSheet(f"background-color: #0d1117; color: #c9d1d9; font-family: 'Consolas', 'Monaco', monospace;")
        
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # Header
        header = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("📂 SYSTEM CONSOLE")
        title.setStyleSheet("color: #58a6ff; font-weight: bold; font-size: 14px;")
        header.addWidget(title)
        
        header.addStretch()
        
        self.clear_btn = QtWidgets.QPushButton("Clear Logs")
        self.clear_btn.setStyleSheet("background: #21262d; border: 1px solid #30363d; border-radius: 4px; padding: 4px 10px; font-size: 11px;")
        self.clear_btn.clicked.connect(self._clear_logs)
        header.addWidget(self.clear_btn)
        
        layout.addLayout(header)
        
        # Log Area
        self.log_display = QtWidgets.QPlainTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setStyleSheet("""
            QPlainTextEdit {
                background-color: #161b22;
                border: 1px solid #30363d;
                border-radius: 6px;
                padding: 10px;
                font-size: 12px;
                line-height: 1.5;
            }
        """)
        layout.addWidget(self.log_display)
        
        # Sync current logs
        self.log_display.setPlainText(log_manager.get_all_logs())
        self.log_display.verticalScrollBar().setValue(self.log_display.verticalScrollBar().maximum())
        
        # Connect to real-time updates
        log_manager.log_updated.connect(self._append_log)

    def _append_log(self, text):
        self.log_display.insertPlainText(text)
        self.log_display.verticalScrollBar().setValue(self.log_display.verticalScrollBar().maximum())

    def _clear_logs(self):
        log_manager._logs = []
        self.log_display.clear()

class CameraDialog(QtWidgets.QDialog):
    """A dialog to display live feed from a USB camera with ROI drawing support."""

    def __init__(self, side="left", parent=None):
        super().__init__(parent)
        self.side = side
        self.setWindowTitle(f"Live Camera Feed - {side.capitalize()}")
        self.setMinimumSize(720, 620)
        self.setStyleSheet(f"background-color: {COLOR_BG}; color: white; border: 1px solid {COLOR_BORDER};")

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # ── Video area (label + canvas overlay) ──────────────────────── #
        self.video_container = QtWidgets.QWidget()
        self.video_container.setStyleSheet("background-color: black; border-radius: 10px;")
        self.video_container.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        v_layout = QtWidgets.QVBoxLayout(self.video_container)
        v_layout.setContentsMargins(0, 0, 0, 0)

        self.video_label = QtWidgets.QLabel(f"Starting {side.capitalize()} Camera...")
        self.video_label.setAlignment(AlignmentFlag.AlignCenter)
        self.video_label.setStyleSheet("background-color: transparent;")
        self.video_label.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        v_layout.addWidget(self.video_label)

        layout.addWidget(self.video_container, 1)

        # ROI canvas – transparent overlay on top of video_label
        from utility.roi_canvas import RoiCanvas
        self.roi_canvas = RoiCanvas(self.video_label)
        self.roi_canvas.roi_confirmed.connect(self._on_roi_draw_confirmed)
        self.roi_canvas.roi_cleared.connect(self._on_roi_cleared)

        # ── ROI Toolbar ───────────────────────────────────────────────── #
        roi_bar = QtWidgets.QWidget()
        roi_bar.setStyleSheet("background-color: #1a2332; border-radius: 8px; padding: 4px;")
        roi_layout = QtWidgets.QHBoxLayout(roi_bar)
        roi_layout.setContentsMargins(10, 5, 10, 5)
        roi_layout.setSpacing(8)

        roi_label = QtWidgets.QLabel("🔲 ROI:")
        roi_label.setStyleSheet("color: #aaa; font-size: 12px; font-weight: bold;")
        roi_layout.addWidget(roi_label)

        self.draw_roi_btn = QtWidgets.QPushButton("✏️ Draw ROI")
        self.draw_roi_btn.setCheckable(True)
        self.draw_roi_btn.setStyleSheet("""
            QPushButton {
                background-color: #2980b9; color: white; font-weight: bold;
                padding: 6px 14px; border-radius: 6px; font-size: 12px;
            }
            QPushButton:checked { background-color: #e67e22; }
            QPushButton:hover { background-color: #3498db; }
        """)
        self.draw_roi_btn.clicked.connect(self._toggle_draw_roi)
        roi_layout.addWidget(self.draw_roi_btn)

        self.set_roi_btn = QtWidgets.QPushButton("✅ Set ROI")
        self.set_roi_btn.setEnabled(False)
        self.set_roi_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60; color: white; font-weight: bold;
                padding: 6px 14px; border-radius: 6px; font-size: 12px;
            }
            QPushButton:disabled { background-color: #3d4a3d; color: #777; }
            QPushButton:hover:enabled { background-color: #2ecc71; }
        """)
        self.set_roi_btn.clicked.connect(self._save_roi)
        roi_layout.addWidget(self.set_roi_btn)

        self.clear_roi_btn = QtWidgets.QPushButton("🗑️ Clear ROI")
        self.clear_roi_btn.setStyleSheet("""
            QPushButton {
                background-color: #7f8c8d; color: white; font-weight: bold;
                padding: 6px 14px; border-radius: 6px; font-size: 12px;
            }
            QPushButton:hover { background-color: #95a5a6; }
        """)
        self.clear_roi_btn.clicked.connect(self._clear_roi)
        roi_layout.addWidget(self.clear_roi_btn)

        self.roi_status_label = QtWidgets.QLabel("No ROI set")
        self.roi_status_label.setStyleSheet("color: #888; font-size: 11px; margin-left: 8px;")
        roi_layout.addWidget(self.roi_status_label)

        roi_layout.addStretch()
        layout.addWidget(roi_bar)

        # ── Hint label (shown only during drawing) ────────────────────── #
        self.hint_label = QtWidgets.QLabel(
            "🖱️  Click to place points  •  Double-click or press Set ROI to confirm  •  Right-click to undo last point")
        self.hint_label.setAlignment(QtCore.Qt.AlignCenter)
        self.hint_label.setStyleSheet(
            "color: #e67e22; font-size: 11px; background: transparent; padding: 2px;")
        self.hint_label.setVisible(False)
        layout.addWidget(self.hint_label)

        # ── Close button ──────────────────────────────────────────────── #
        self.close_btn = QtWidgets.QPushButton(f"CLOSE {side.upper()} CAMERA")
        self.close_btn.setStyleSheet(
            "background-color: #e74c3c; color: white; font-weight: bold; padding: 10px; border-radius: 5px;")
        self.close_btn.clicked.connect(self.close)
        layout.addWidget(self.close_btn)

        self.update_timer = QtCore.QTimer()
        self.update_timer.timeout.connect(self._fetch_frame)
        self.camera = None

        # Current video frame dimensions (needed for coordinate mapping)
        self._video_w = 640
        self._video_h = 480

    # ── Camera lifecycle ──────────────────────────────────────────────── #

    def showEvent(self, event):
        super().showEvent(event)
        try:
            from utility.camera import CameraHandler
            self.camera = CameraHandler(self.side)
            if self.camera.start():
                self.update_timer.start(33)
            else:
                self.video_label.setText(f"❌ ERROR: Could not open {self.side} camera")
        except Exception as e:
            self.video_label.setText(f"❌ ERROR: {e}")

        # Load existing ROI from DB after a short delay so layout is settled
        QtCore.QTimer.singleShot(500, self._load_existing_roi)

    def hideEvent(self, event):
        super().hideEvent(event)
        self.update_timer.stop()
        if self.camera:
            self.camera.stop()
            self.camera = None

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Keep roi_canvas exactly covering the video_label
        self.roi_canvas.setGeometry(self.video_label.geometry())

    def _fetch_frame(self):
        if not self.camera:
            return
        frame = self.camera.get_frame()
        if frame is not None:
            self._video_h, self._video_w = frame.shape[:2]
            h, w, ch = frame.shape
            q_img = QtGui.QImage(
                frame.data, w, h, ch * w, QtGui.QImage.Format_RGB888)
            pixmap = QtGui.QPixmap.fromImage(q_img)
            self.video_label.setPixmap(
                pixmap.scaled(
                    self.video_label.width(), self.video_label.height(),
                    AspectRatioMode.KeepAspectRatio,
                    TransformationMode.SmoothTransformation))
            # Keep canvas geometry in sync
            self.roi_canvas.setGeometry(self.video_label.geometry())

    # ── ROI Drawing logic ─────────────────────────────────────────────── #

    def _toggle_draw_roi(self, checked: bool):
        if checked:
            self.draw_roi_btn.setText("✏️ Drawing… (click to place points)")
            self.set_roi_btn.setEnabled(True)
            self.hint_label.setVisible(True)
            self.roi_canvas.setGeometry(self.video_label.geometry())
            self.roi_canvas.start_drawing()
        else:
            self.draw_roi_btn.setText("✏️ Draw ROI")
            self.set_roi_btn.setEnabled(False)
            self.hint_label.setVisible(False)
            self.roi_canvas.stop_drawing()

    def _save_roi(self):
        """Confirm the polygon, save to DB."""
        points = self.roi_canvas.get_video_points(self._video_w, self._video_h)
        if len(points) < 3:
            QtWidgets.QMessageBox.warning(
                self, "ROI Error", "Please place at least 3 points to define an ROI.")
            return

        # Mark confirmed on canvas
        self.roi_canvas._confirmed = True
        self.roi_canvas._drawing = False
        self.roi_canvas.setCursor(QtCore.Qt.ArrowCursor)
        self.roi_canvas.update()

        # Persist to DB
        try:
            from services.database_service import get_db
            ok = get_db().save_roi(self.side, points)
            if ok:
                self.roi_status_label.setText(f"✅ ROI saved ({len(points)} pts)")
                self.roi_status_label.setStyleSheet(
                    "color: #2ecc71; font-size: 11px; margin-left: 8px;")
            else:
                self.roi_status_label.setText("⚠️ Saved locally (DB unavailable)")
        except Exception as e:
            print(f"[ROI] DB save error: {e}")
            self.roi_status_label.setText("⚠️ DB error – ROI not persisted")

        # Reset toolbar state
        self.draw_roi_btn.setChecked(False)
        self.draw_roi_btn.setText("✏️ Draw ROI")
        self.set_roi_btn.setEnabled(False)
        self.hint_label.setVisible(False)

    def _clear_roi(self):
        self.roi_canvas.reset()
        self.draw_roi_btn.setChecked(False)
        self.draw_roi_btn.setText("✏️ Draw ROI")
        self.set_roi_btn.setEnabled(False)
        self.hint_label.setVisible(False)

    def _on_roi_draw_confirmed(self, pts):
        """Called by RoiCanvas double-click auto-confirm."""
        self._save_roi()

    def _on_roi_cleared(self):
        self.roi_status_label.setText("No ROI set")
        self.roi_status_label.setStyleSheet("color: #888; font-size: 11px; margin-left: 8px;")

    def _load_existing_roi(self):
        """Load and display any previously saved ROI from the database."""
        try:
            from services.database_service import get_db
            pts = get_db().load_roi(self.side)
            if pts:
                self.roi_canvas.setGeometry(self.video_label.geometry())
                self.roi_canvas.show_existing_roi(pts, self._video_w, self._video_h)
                self.roi_status_label.setText(f"✅ ROI loaded ({len(pts)} pts)")
                self.roi_status_label.setStyleSheet(
                    "color: #2ecc71; font-size: 11px; margin-left: 8px;")
        except Exception as e:
            print(f"[ROI] DB load error: {e}")

class BeaconDialog(QtWidgets.QDialog):
    """Control dialog for the Arduino Nano LED Beacon."""

    # Color accent map  (display color, button style)
    _COLOR_STYLES = {
        'RED':   ('#e74c3c', '#c0392b'),
        'AMBER': ('#f39c12', '#d68910'),
        'GREEN': ('#2ecc71', '#27ae60'),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🚨 LED Beacon Control")
        self.setFixedWidth(500)
        self.setStyleSheet(f"""
            QDialog {{ background-color: {COLOR_BG}; color: white; }}
            QLabel  {{ color: white; font-size: 12px; }}
            QGroupBox {{
                color: {COLOR_ACCENT_BLUE}; font-weight: bold; font-size: 12px;
                border: 1px solid {COLOR_BORDER}; border-radius: 8px;
                margin-top: 10px; padding: 10px;
            }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; }}
            QSpinBox, QSlider {{
                background: {COLOR_SPOT_BG}; color: white;
                border: 1px solid {COLOR_BORDER}; border-radius: 4px; padding: 4px;
            }}
        """)

        self._beacon = None   # BeaconController instance (lazy-connected)
        self._selected_color = 'GREEN'

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # ── Connection status bar ──────────────────────────────────────── #
        conn_bar = QtWidgets.QWidget()
        conn_bar.setStyleSheet(f"background: {COLOR_SPOT_BG}; border-radius: 6px; padding: 4px 10px;")
        conn_layout = QtWidgets.QHBoxLayout(conn_bar)
        conn_layout.setContentsMargins(10, 4, 10, 4)

        self._status_dot = QtWidgets.QLabel("●")
        self._status_dot.setStyleSheet("color: #e74c3c; font-size: 16px;")
        self._status_text = QtWidgets.QLabel("Not connected")
        self._status_text.setStyleSheet("color: #888; font-size: 11px;")

        self._connect_btn = QtWidgets.QPushButton("Connect")
        self._connect_btn.setFixedWidth(90)
        self._connect_btn.setStyleSheet(
            f"background: {COLOR_ACCENT_BLUE}; color: white; font-weight: bold; "
            f"border-radius: 5px; padding: 5px 10px; font-size: 11px;")
        self._connect_btn.clicked.connect(self._toggle_connection)

        conn_layout.addWidget(self._status_dot)
        conn_layout.addWidget(self._status_text)
        conn_layout.addStretch()
        conn_layout.addWidget(self._connect_btn)
        main_layout.addWidget(conn_bar)

        # ── Color Selector ─────────────────────────────────────────────── #
        color_group = QtWidgets.QGroupBox("LED Color")
        color_layout = QtWidgets.QHBoxLayout(color_group)
        self._color_buttons = {}
        for color, (bg, hover) in self._COLOR_STYLES.items():
            btn = QtWidgets.QPushButton(color)
            btn.setCheckable(True)
            btn.setFixedHeight(40)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {bg}; color: white; font-weight: bold;
                    border-radius: 8px; font-size: 13px; border: 3px solid transparent;
                }}
                QPushButton:checked {{ border: 3px solid white; }}
                QPushButton:hover   {{ background-color: {hover}; }}
            """)
            btn.clicked.connect(lambda _, c=color: self._select_color(c))
            color_layout.addWidget(btn)
            self._color_buttons[color] = btn
        main_layout.addWidget(color_group)
        self._select_color('GREEN')   # default

        # ── Timing Controls ────────────────────────────────────────────── #
        timing_group = QtWidgets.QGroupBox("Timing")
        timing_layout = QtWidgets.QFormLayout(timing_group)
        timing_layout.setSpacing(8)

        self._on_spin = QtWidgets.QSpinBox()
        self._on_spin.setRange(1, 10000)
        self._on_spin.setValue(500)
        self._on_spin.setSuffix(" ms")
        self._on_spin.setToolTip("How long the LED stays ON per blink")

        self._off_spin = QtWidgets.QSpinBox()
        self._off_spin.setRange(1, 10000)
        self._off_spin.setValue(500)
        self._off_spin.setSuffix(" ms")
        self._off_spin.setToolTip("How long the LED stays OFF per blink")

        timing_layout.addRow("ON Duration:", self._on_spin)
        timing_layout.addRow("OFF Duration:", self._off_spin)
        main_layout.addWidget(timing_group)

        # ── Brightness ─────────────────────────────────────────────────── #
        bright_group = QtWidgets.QGroupBox("Brightness")
        bright_layout = QtWidgets.QVBoxLayout(bright_group)

        bright_row = QtWidgets.QHBoxLayout()
        self._bright_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self._bright_slider.setRange(0, 255)
        self._bright_slider.setValue(128)
        self._bright_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: #2c3e50; height: 6px; border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #3498db; width: 16px; height: 16px;
                margin: -5px 0; border-radius: 8px;
            }
            QSlider::sub-page:horizontal { background: #3498db; border-radius: 3px; }
        """)
        self._bright_label = QtWidgets.QLabel("128")
        self._bright_label.setFixedWidth(32)
        self._bright_label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        self._bright_slider.valueChanged.connect(
            lambda v: self._bright_label.setText(str(v)))
        bright_row.addWidget(self._bright_slider)
        bright_row.addWidget(self._bright_label)
        bright_layout.addLayout(bright_row)

        bright_presets = QtWidgets.QHBoxLayout()
        for label, val in [("Dim (50)", 50), ("Half (128)", 128), ("Full (255)", 255)]:
            pb = QtWidgets.QPushButton(label)
            pb.setStyleSheet(
                f"background: {COLOR_SPOT_BG}; color: {COLOR_TEXT_GRAY}; "
                f"border: 1px solid {COLOR_BORDER}; border-radius: 4px; "
                f"padding: 3px 8px; font-size: 10px;")
            pb.clicked.connect(lambda _, v=val: self._bright_slider.setValue(v))
            bright_presets.addWidget(pb)
        bright_layout.addLayout(bright_presets)
        main_layout.addWidget(bright_group)

        # ── Presets ────────────────────────────────────────────────────── #
        preset_group = QtWidgets.QGroupBox("Quick Presets")
        preset_layout = QtWidgets.QGridLayout(preset_group)
        preset_layout.setSpacing(8)

        presets = [
            ("✅ System OK",   'GREEN', 1000, 1000,  80),
            ("⚠️ Warning",     'AMBER',  300,  300, 180),
            ("🚨 Error",       'RED',    200,  200, 255),
            ("🅿️ Parking",    'GREEN',  200,  800,  50),
        ]
        for i, (label, color, on, off, bright) in enumerate(presets):
            btn = QtWidgets.QPushButton(label)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {COLOR_SPOT_BG}; color: white; border-radius: 6px;
                    border: 1px solid {COLOR_BORDER}; padding: 8px; font-size: 11px;
                    font-weight: bold;
                }}
                QPushButton:hover {{ background: #2c3e50; }}
            """)
            btn.clicked.connect(
                lambda _, c=color, n=on, f=off, b=bright: self._apply_preset(c, n, f, b))
            preset_layout.addWidget(btn, i // 2, i % 2)
        main_layout.addWidget(preset_group)

        # ── Action Buttons ─────────────────────────────────────────────── #
        action_layout = QtWidgets.QHBoxLayout()

        self._blink_btn = QtWidgets.QPushButton("▶ Continuous Blink")
        self._blink_btn.setFixedHeight(42)
        self._blink_btn.setEnabled(False)
        self._blink_btn.setStyleSheet("""
            QPushButton {
                background: #2980b9; color: white; font-weight: bold;
                border-radius: 8px; font-size: 13px;
            }
            QPushButton:hover:enabled { background: #3498db; }
            QPushButton:disabled { background: #2c3e50; color: #555; }
        """)
        self._blink_btn.clicked.connect(self._do_blink)
        action_layout.addWidget(self._blink_btn)

        self._oneshot_btn = QtWidgets.QPushButton("⚡ Single Blink")
        self._oneshot_btn.setFixedHeight(42)
        self._oneshot_btn.setEnabled(False)
        self._oneshot_btn.setStyleSheet("""
            QPushButton {
                background: #8e44ad; color: white; font-weight: bold;
                border-radius: 8px; font-size: 13px;
            }
            QPushButton:hover:enabled { background: #9b59b6; }
            QPushButton:disabled { background: #2c3e50; color: #555; }
        """)
        self._oneshot_btn.clicked.connect(lambda: self._do_blink(oneshot=True))
        action_layout.addWidget(self._oneshot_btn)

        self._stop_btn = QtWidgets.QPushButton("⏹ STOP")
        self._stop_btn.setFixedHeight(42)
        self._stop_btn.setEnabled(False)
        self._stop_btn.setStyleSheet("""
            QPushButton {
                background: #c0392b; color: white; font-weight: bold;
                border-radius: 8px; font-size: 13px;
            }
            QPushButton:hover:enabled { background: #e74c3c; }
            QPushButton:disabled { background: #2c3e50; color: #555; }
        """)
        self._stop_btn.clicked.connect(self._do_stop)
        action_layout.addWidget(self._stop_btn)

        main_layout.addLayout(action_layout)

        # ── Response Log ───────────────────────────────────────────────── #
        log_label = QtWidgets.QLabel("Arduino Response:")
        log_label.setStyleSheet("color: #888; font-size: 11px;")
        self._response_log = QtWidgets.QPlainTextEdit()
        self._response_log.setReadOnly(True)
        self._response_log.setMaximumHeight(80)
        self._response_log.setStyleSheet(f"""
            background: #0d1117; color: #2ecc71;
            border: 1px solid {COLOR_BORDER}; border-radius: 6px;
            font-family: monospace; font-size: 11px; padding: 4px;
        """)
        main_layout.addWidget(log_label)
        main_layout.addWidget(self._response_log)

        # Close
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.setStyleSheet(
            f"background: {COLOR_SPOT_BG}; color: white; border-radius: 5px; padding: 8px;")
        close_btn.clicked.connect(self.close)
        main_layout.addWidget(close_btn)

    # ── Slots ──────────────────────────────────────────────────────────── #

    def _select_color(self, color: str):
        self._selected_color = color
        for c, btn in self._color_buttons.items():
            btn.setChecked(c == color)

    def _toggle_connection(self):
        if self._beacon and self._beacon.is_connected:
            self._beacon.disconnect()
            self._beacon = None
            self._set_connected(False)
        else:
            from utility.beacon import BeaconController
            self._beacon = BeaconController()
            ok = self._beacon.connect()
            self._set_connected(ok)
            if not ok:
                self._beacon = None
                self._log("❌ Connection failed – check port in config.properties")

    def _set_connected(self, connected: bool):
        if connected:
            self._status_dot.setStyleSheet("color: #2ecc71; font-size: 16px;")
            self._status_text.setText(
                f"Connected  •  {self._beacon.port}")
            self._connect_btn.setText("Disconnect")
            self._connect_btn.setStyleSheet(
                "background: #e74c3c; color: white; font-weight: bold; "
                "border-radius: 5px; padding: 5px 10px; font-size: 11px;")
        else:
            self._status_dot.setStyleSheet("color: #e74c3c; font-size: 16px;")
            self._status_text.setText("Not connected")
            self._connect_btn.setText("Connect")
            self._connect_btn.setStyleSheet(
                f"background: {COLOR_ACCENT_BLUE}; color: white; font-weight: bold; "
                f"border-radius: 5px; padding: 5px 10px; font-size: 11px;")

        for btn in [self._blink_btn, self._oneshot_btn, self._stop_btn]:
            btn.setEnabled(connected)

    def _do_blink(self, oneshot: bool = False):
        if not self._beacon:
            return
        try:
            resp = self._beacon.blink(
                color=self._selected_color,
                on_ms=self._on_spin.value(),
                off_ms=self._off_spin.value(),
                brightness=self._bright_slider.value(),
                oneshot=oneshot
            )
            mode = "Single" if oneshot else "Continuous"
            self._log(
                f"[{mode}] {self._selected_color}  "
                f"ON={self._on_spin.value()}ms  OFF={self._off_spin.value()}ms  "
                f"BRIGHT={self._bright_slider.value()}\n"
                f"  → Arduino: {resp or '(no response)'}")
        except Exception as e:
            self._log(f"❌ Error: {e}")

    def _do_stop(self):
        if not self._beacon:
            return
        try:
            resp = self._beacon.stop()
            self._log(f"[STOP] All LEDs OFF  → Arduino: {resp or '(no response)'}")
        except Exception as e:
            self._log(f"❌ Error: {e}")

    def _apply_preset(self, color: str, on: int, off: int, bright: int):
        self._select_color(color)
        self._on_spin.setValue(on)
        self._off_spin.setValue(off)
        self._bright_slider.setValue(bright)
        self._do_blink()

    def _log(self, text: str):
        self._response_log.appendPlainText(text)

    def closeEvent(self, event):
        if self._beacon and self._beacon.is_connected:
            self._beacon.disconnect()
        super().closeEvent(event)


class HistoryViewerDialog(QtWidgets.QDialog):
    """A dialog to display parking history from the database."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Parking History Records")
        self.resize(800, 500)
        self.setStyleSheet(f"background-color: {COLOR_BG}; color: white; font-family: 'Inter', sans-serif;")
        
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Header
        header = QtWidgets.QLabel("📋 PARKING HISTORY")
        header.setStyleSheet(f"color: {COLOR_ACCENT_BLUE}; font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(header)
        
        # Table
        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Side", "Plate Number", "Start Time", "End Time", "Amount", "Paid"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {COLOR_SPOT_BG};
                color: white;
                gridline-color: {COLOR_BORDER};
                border: 1px solid {COLOR_BORDER};
                border-radius: 8px;
            }}
            QHeaderView::section {{
                background-color: #2c3e50;
                color: white;
                padding: 5px;
                border: 1px solid {COLOR_BORDER};
                font-weight: bold;
            }}
        """)
        layout.addWidget(self.table)
        
        # Footer buttons
        btn_layout = QtWidgets.QHBoxLayout()
        self.refresh_btn = QtWidgets.QPushButton("REFRESH DATA")
        self.refresh_btn.setStyleSheet(f"background-color: {COLOR_ACCENT_BLUE}; color: white; padding: 10px; border-radius: 5px; font-weight: bold;")
        self.refresh_btn.clicked.connect(self.load_data)
        btn_layout.addWidget(self.refresh_btn)
        
        self.close_btn = QtWidgets.QPushButton("CLOSE")
        self.close_btn.setStyleSheet(f"background-color: #34495e; color: white; padding: 10px; border-radius: 5px; font-weight: bold;")
        self.close_btn.clicked.connect(self.close)
        btn_layout.addWidget(self.close_btn)
        
        layout.addLayout(btn_layout)
        
    def showEvent(self, event):
        super().showEvent(event)
        self.load_data()

    def load_data(self):
        """Fetch data from DB and populate table."""
        try:
            from services.database_service import get_db
            records = get_db().fetch_history()
            
            self.table.setRowCount(0)
            for row_idx, row_data in enumerate(records):
                self.table.insertRow(row_idx)
                for col_idx, value in enumerate(row_data):
                    # Format data for display
                    display_val = str(value)
                    if col_idx == 2 or col_idx == 3: # Timestamps
                        if value:
                            display_val = value.strftime("%Y-%m-%d %H:%M:%S")
                        else:
                            display_val = "---"
                    elif col_idx == 4: # Amount
                        display_val = f"${float(value or 0):.2f}"
                    elif col_idx == 5: # Paid
                        display_val = "✅ Yes" if value else "❌ No"
                    
                    item = QtWidgets.QTableWidgetItem(display_val)
                    item.setTextAlignment(QtCore.Qt.AlignCenter)
                    self.table.setItem(row_idx, col_idx, item)
        except Exception as e:
            print(f"Error loading history: {e}")

class DashboardWindow(QtWidgets.QMainWindow):
    proximity_alert_signal = QtCore.pyqtSignal(str, bool)

    def __init__(self):
        super().__init__()
        # Ensure the window stays on top and bypasses some window manager focus stealing rules
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)
        self.setWindowTitle("PapayaMeter Dashboard")
        self.setMinimumSize(800, 480) 
        self.setStyleSheet(f"background-color: {COLOR_BG}; color: {COLOR_TEXT_WHITE}; font-family: 'Inter', sans-serif;")

        # Services
        self.backend = SensorBackend()
        self.system_service = SystemService()
        self.system_service.start()
        
        self.lidar_monitor = LidarMonitorDialog(self)
        self.log_viewer = LogViewerDialog(self)
        self.camera_left = CameraDialog("left", self)
        self.camera_right = CameraDialog("right", self)
        self.history_viewer = HistoryViewerDialog(self)
        self.beacon_dialog   = BeaconDialog(self)

        self._ignored_sensors = {} # Store sensor_name: timestamp
        self._last_alert_time = 0

        self._init_ui()
        self._setup_shortcuts()
        self._start_refresh_timers()

        # Connect internal signals for thread-safety
        self.proximity_alert_signal.connect(self.notification_bar.show_alert)
        print("[GUI DEBUG] Proximity signal connected to notification bar.")

        # Connect signals after UI is initialized
        self.backend.set_nfc_callback(self._handle_nfc_tap)
        self.backend.set_air_callback(self._handle_air_update)
        self.backend.set_ultrasonic_callback(self._handle_ultrasonic_callback)
        self.backend.set_tamper_callback(self._handle_tamper_callback)
        
        if hasattr(self, 'notification_bar'):
            self.notification_bar.baseline_requested.connect(self._on_tamper_baseline_requested)
            
        # Bring window to front and ensure it's not minimized
        self.setWindowState(self.windowState() & ~QtCore.Qt.WindowMinimized | QtCore.Qt.WindowActive | QtCore.Qt.WindowMaximized)
        self.showMaximized()
        self.raise_()
        self.activateWindow()
        
        # Some window managers require a short delay to properly accept focus after the window is shown
        QtCore.QTimer.singleShot(100, self.activateWindow)
        QtCore.QTimer.singleShot(200, self.raise_)

    def showEvent(self, event):
        super().showEvent(event)
        # Start cameras when dashboard is shown
        QtCore.QTimer.singleShot(500, self.left_spot.start_camera)
        QtCore.QTimer.singleShot(1000, self.right_spot.start_camera)

    def closeEvent(self, event):
        # Stop cameras when closing
        self.left_spot.stop_camera()
        self.right_spot.stop_camera()
        super().closeEvent(event)

    def _open_cam_left(self):
        """Pause dashboard left cam and open full view."""
        self.left_spot.stop_camera()
        # Connect finished signal to restart the dashboard camera
        try:
            self.camera_left.finished.disconnect()
        except: pass
        self.camera_left.finished.connect(lambda: self.left_spot.start_camera())
        self.camera_left.show()

    def _open_cam_right(self):
        """Pause dashboard right cam and open full view."""
        self.right_spot.stop_camera()
        # Connect finished signal to restart the dashboard camera
        try:
            self.camera_right.finished.disconnect()
        except: pass
        self.camera_right.finished.connect(lambda: self.right_spot.start_camera())
        self.camera_right.show()

    def _setup_shortcuts(self):
        # Test Shortcut
        self.test_alert = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+T"), self)
        self.test_alert.activated.connect(lambda: self.notification_bar.show_alert("TEST ALERT: System check ok!"))

        # Status monitor to debug notification state
        self.status_timer = QtCore.QTimer()
        self.status_timer.timeout.connect(self._check_notification_status)
        self.status_timer.start(5000)

    def _check_notification_status(self):
        visible = self.notification_bar.isVisible()
        # print(f"[GUI DEBUG] Status: NotificationBar Visible={visible}")
        if visible:
             self.notification_bar.raise_() # Keep it on top

        # Left Spot Shortcuts
        self.lc_start = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+N"), self)
        self.lc_start.activated.connect(lambda: self._handle_shortcut(self.left_spot, "start"))
        
        self.lc_stop = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+B"), self)
        self.lc_stop.activated.connect(lambda: self._handle_shortcut(self.left_spot, "stop"))
        
        # Right Spot Shortcuts
        self.rc_start = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+T"), self)
        self.rc_start.activated.connect(lambda: self._handle_shortcut(self.right_spot, "start"))
        
        self.rc_stop = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+U"), self)
        self.rc_stop.activated.connect(lambda: self._handle_shortcut(self.right_spot, "stop"))

        # NFC Simulation Shortcut (Credit Card Tap)
        self.nfc_sim = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+E"), self)
        self.nfc_sim.activated.connect(self._simulate_nfc_tap)

    def _handle_shortcut(self, spot, action):
        if action == "start":
            if spot.content_stack.currentIndex() == 0: # Available
                spot._set_state_input()
            elif spot.content_stack.currentIndex() == 1: # Input
                spot._start_session()
        elif action == "stop":
            curr_idx = spot.content_stack.currentIndex()
            if curr_idx == 2: # Occupied
                spot._stop_session()
            elif curr_idx == 3: # Ready to Depart (Screen 1)
                spot._show_payment_details()
            elif curr_idx == 4: # Payment Details (Screen 2)
                spot._process_payment()

    def _simulate_nfc_tap(self):
        """Manually trigger the NFC tap logic via shortcut."""
        self._handle_nfc_tap({"method": "shortcut"})

    def _handle_nfc_tap(self, data):
        """Called when a physical NFC card is scanned."""
        # Check if any spot is currently on the Payment Detail Screen (index 4)
        for spot in [self.left_spot, self.right_spot]:
            if spot.content_stack.currentIndex() == 4:
                # Use QTimer to ensure thread safety when updating UI from background thread
                QtCore.QTimer.singleShot(0, spot._process_payment)

    def _handle_air_update(self, data):
        """Update GUI when new Air Quality data arrives."""
        pm25 = data.get("PM2.5", 0)
        
        # Determine status and color based on PM2.5
        if pm25 < 12:
            status, color = "Good", "#39ff5a"
        elif pm25 < 35:
            status, color = "Moderate", "#f1c40f"
        else:
            status, color = "Unhealthy", "#e74c3c"
            
        # UI update via thread-safe timer
        QtCore.QTimer.singleShot(0, lambda: self.aqi_label.setText(f"🌬️ PM2.5: {pm25} {status}"))
        QtCore.QTimer.singleShot(0, lambda: self.aqi_label.setStyleSheet(f"font-size: 14px; color: {color};"))
        self._last_air_time = time.time()

    def _handle_ultrasonic_callback(self, data):
        """Called when ultrasonic sensor data arrives from backend thread."""
        sensor_name = data.get("sensor", "unknown")
        is_alert = data.get("alert", False)
        distance = data.get("distance_cm", 0)
        
        if is_alert:
            # Check if this sensor is currently ignored (for 60 seconds)
            if sensor_name in self._ignored_sensors:
                if time.time() - self._ignored_sensors[sensor_name] < 60:
                    return
                else:
                    del self._ignored_sensors[sensor_name]

            msg = f"ALERT: Object is too near on {sensor_name}! ({distance:.1f} cm)"
            print(f"[Ultrasonic] Alert triggered for {sensor_name}: {distance:.1f} cm")
            self.proximity_alert_signal.emit(msg, False)

    def _handle_tamper_callback(self, data):
        """Called when a tamper event is detected by the hardware."""
        # Check if tamper is currently ignored (for 60 seconds)
        if "tamper" in self._ignored_sensors:
            if time.time() - self._ignored_sensors["tamper"] < 60:
                return
            else:
                del self._ignored_sensors["tamper"]

        msg = f"🚨 TAMPER DETECTED: {data.get('msg', 'Device moved or shaken')}"
        print(f"[GUI DEBUG] Emitting tamper alert: {msg}")
        self.proximity_alert_signal.emit(msg, True)

    def _on_tamper_baseline_requested(self):
        """Called when user wants to set the current state as the new baseline."""
        print("[GUI] Recalibrating tamper baseline as requested by user.")
        self.backend.recalibrate_tamper()

    def _on_sensor_ignored(self):
        """Mark current active alert's sensor as ignored."""
        msg = self.notification_bar.msg_label.text()
        # Handle ultrasonic sensors
        for sensor in ["ultrasonic_front", "ultrasonic_back", "ultrasonic"]:
            if sensor in msg:
                self._ignored_sensors[sensor] = time.time()
                print(f"[GUI] Ignoring {sensor} alerts for 60 seconds.")

        # Handle tamper alerts
        if "TAMPER" in msg:
            self._ignored_sensors["tamper"] = time.time()
            print(f"[GUI] Ignoring tamper alerts for 60 seconds.")

    def _check_air_quality(self):
        """Check if sensor data has stopped coming and show NULL if so."""
        if not hasattr(self, '_last_air_time') or (time.time() - self._last_air_time > 30):
            # No update for 10 seconds or never updated
            self.aqi_label.setText("🌬️ PM2.5: NULL")
            self.aqi_label.setStyleSheet(f"font-size: 14px; color: {COLOR_TEXT_GRAY};")

    def _init_ui(self):
        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QtWidgets.QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Header
        header = self._create_header()
        main_layout.addWidget(header)

        # 2. Body (Split view)
        body = QtWidgets.QWidget()
        body_layout = QtWidgets.QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # Left Spot
        self.left_spot = SpotWidget("LEFT SPOT", "SP-047", side="left")
        body_layout.addWidget(self.left_spot)

        # Vertical Divider
        divider = QtWidgets.QFrame()
        divider.setFrameShape(FrameShape.VLine)
        divider.setStyleSheet(f"background-color: {COLOR_BORDER}; min-width: 1px; max-width: 1px;")
        body_layout.addWidget(divider)

        # Right Spot
        self.right_spot = SpotWidget("RIGHT SPOT", "SP-048", side="right")
        body_layout.addWidget(self.right_spot)

        main_layout.addWidget(body, 1)

        # 3. Bottom Battery/Power Bar
        footer_bars = self._create_footer_bars()
        main_layout.addWidget(footer_bars)

        # 4. Footer Icons/Language
        footer = self._create_footer()
        main_layout.addWidget(footer)

        # 0. Floating Notification Bar (Child of MainWindow to stay on top)
        self.notification_bar = NotificationBar(self)
        self.notification_bar.ignored.connect(self._on_sensor_ignored)
        
        # Force it on top every second if it's visible
        self.raise_timer = QtCore.QTimer(self)
        self.raise_timer.timeout.connect(lambda: self.notification_bar.visibleRegion().isEmpty() or self.notification_bar.raise_())
        self.raise_timer.start(1000)

    def _create_header(self):
        header = QtWidgets.QWidget()
        header.setFixedHeight(60)
        header.setStyleSheet(f"background-color: {COLOR_BG}; border-bottom: 1px solid {COLOR_BORDER};")
        layout = QtWidgets.QHBoxLayout(header)
        layout.setContentsMargins(20, 0, 20, 0)

        # Left: Zone and Time
        zone_info = QtWidgets.QLabel("● Zone A-12 / SP-047/048")
        zone_info.setStyleSheet(f"color: {COLOR_ACCENT_BLUE}; font-weight: bold; font-size: 14px;")
        
        self.clock_label = QtWidgets.QLabel()
        self.clock_label.setStyleSheet(f"color: {COLOR_TEXT_GRAY}; margin-left: 20px; font-size: 14px;")
        
        layout.addWidget(zone_info)
        layout.addWidget(self.clock_label)
        layout.addStretch()

        # Middle: Available Badge
        avail_badge = QtWidgets.QLabel("AVAILABLE")
        avail_badge.setStyleSheet(f"""
            background-color: {COLOR_ACCENT_GREEN};
            color: black;
            padding: 4px 12px;
            border-radius: 10px;
            font-weight: bold;
            font-size: 12px;
        """)
        avail_badge.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(avail_badge)
        layout.addStretch()


        # Right: Weather/Temp
        self.temp_label = QtWidgets.QLabel("🌡️ --°F")
        self.temp_label.setStyleSheet("font-size: 14px; margin-right: 15px;")
        
        self.aqi_label = QtWidgets.QLabel("🌬️ PM2.5: NULL")
        self.aqi_label.setStyleSheet(f"font-size: 14px; color: {COLOR_TEXT_GRAY};")

        layout.addWidget(self.temp_label)
        layout.addWidget(self.aqi_label)

        return header

    def _create_footer_bars(self):
        container = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(20, 10, 20, 10)
        layout.setSpacing(20)

        # ── Left Monitor Bar ─────────────────────────────────────────── #
        self.battery_info_label = QtWidgets.QLabel("0.00V")
        self.battery_info_label.setStyleSheet("font-size: 12px; font-weight: bold; margin-right: 10px;")
        
        self.battery_bar = QtWidgets.QProgressBar()
        self.battery_bar.setFixedHeight(12)
        self.battery_bar.setTextVisible(False)
        self.battery_bar.setStyleSheet(f"""
            QProgressBar {{ background-color: {COLOR_SPOT_BG}; border: 1px solid {COLOR_BORDER}; border-radius: 6px; }}
            QProgressBar::chunk {{ background-color: {COLOR_ACCENT_GREEN}; border-radius: 5px; }}
        """)
        
        self.battery_info_right = QtWidgets.QLabel("0.000A")
        self.battery_info_right.setStyleSheet(f"color: {COLOR_ACCENT_GREEN}; font-size: 12px; font-weight: bold; margin-left: 10px;")

        left_inner = QtWidgets.QHBoxLayout()
        left_inner.addWidget(QtWidgets.QLabel("⚡"))
        left_inner.addWidget(self.battery_info_label)
        left_inner.addWidget(self.battery_bar, 1)
        left_inner.addWidget(self.battery_info_right)
        
        left_bar = QtWidgets.QWidget()
        left_bar.setFixedHeight(40)
        left_bar.setStyleSheet(f"border: 1px solid {COLOR_BORDER}; border-radius: 20px; background-color: {COLOR_BG};")
        left_bar.setLayout(left_inner)
        
        # ── Right Monitor Bar (Mirrored) ──────────────────────────────── #
        self.battery_info_label_r = QtWidgets.QLabel("0.00V")
        self.battery_info_label_r.setStyleSheet("font-size: 12px; font-weight: bold; margin-right: 10px;")
        
        self.battery_bar_r = QtWidgets.QProgressBar()
        self.battery_bar_r.setFixedHeight(12)
        self.battery_bar_r.setTextVisible(False)
        self.battery_bar_r.setStyleSheet(f"""
            QProgressBar {{ background-color: {COLOR_SPOT_BG}; border: 1px solid {COLOR_BORDER}; border-radius: 6px; }}
            QProgressBar::chunk {{ background-color: {COLOR_ACCENT_GREEN}; border-radius: 5px; }}
        """)
        
        self.battery_info_right_r = QtWidgets.QLabel("0.000A")
        self.battery_info_right_r.setStyleSheet(f"color: {COLOR_ACCENT_GREEN}; font-size: 12px; font-weight: bold; margin-left: 10px;")

        right_inner = QtWidgets.QHBoxLayout()
        right_inner.addWidget(QtWidgets.QLabel("⚡"))
        right_inner.addWidget(self.battery_info_label_r)
        right_inner.addWidget(self.battery_bar_r, 1)
        right_inner.addWidget(self.battery_info_right_r)
        
        right_bar = QtWidgets.QWidget()
        right_bar.setFixedHeight(40)
        right_bar.setStyleSheet(f"border: 1px solid {COLOR_BORDER}; border-radius: 20px; background-color: {COLOR_BG};")
        right_bar.setLayout(right_inner)

        layout.addWidget(left_bar, 1)
        layout.addWidget(right_bar, 1)

        return container

    def _create_footer(self):
        footer = QtWidgets.QWidget()
        footer.setFixedHeight(50)
        footer.setStyleSheet(f"background-color: {COLOR_BG}; border-top: 1px solid {COLOR_BORDER};")
        layout = QtWidgets.QHBoxLayout(footer)
        layout.setContentsMargins(20, 0, 20, 0)

        # Left: Language/Flags
        lang_layout = QtWidgets.QHBoxLayout()
        globe_icon = QtWidgets.QLabel()
        globe_pixmap = QtGui.QPixmap(os.path.join(STATIC_DIR, "globe.png"))
        if not globe_pixmap.isNull():
            globe_icon.setPixmap(globe_pixmap.scaled(20, 20, QtCore.Qt.AspectRatioMode.KeepAspectRatio, QtCore.Qt.TransformationMode.SmoothTransformation))
        lang_layout.addWidget(globe_icon)

        self.country_flag_label = QtWidgets.QLabel("🇺🇸")
        self.country_flag_label.setStyleSheet("font-size: 16px; margin-left: 5px;")
        lang_layout.addWidget(self.country_flag_label)

        # Other flags (placeholders for selector as in image)
        for flag in ["🇪🇸", "🇫🇷", "🇨🇳", "🇰🇷"]:
            f_label = QtWidgets.QLabel(flag)
            f_label.setStyleSheet("font-size: 16px; margin-left: 10px; opacity: 0.6;")
            lang_layout.addWidget(f_label)

        layout.addLayout(lang_layout)
        layout.addStretch()

        # Right: Buttons
        btn_layout = QtWidgets.QHBoxLayout()
        
        self.lidar_btn = QtWidgets.QPushButton("📡 LiDAR Monitor")
        self.lidar_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.lidar_btn.setStyleSheet(f"background: {COLOR_SPOT_BG}; border: 1px solid {COLOR_ACCENT_BLUE}; color: {COLOR_ACCENT_BLUE}; border-radius: 5px; padding: 5px 15px; font-size: 11px; font-weight: bold;")
        self.lidar_btn.clicked.connect(self.lidar_monitor.show)
        btn_layout.addWidget(self.lidar_btn)

        self.logs_btn = QtWidgets.QPushButton("📋 System Logs")
        self.logs_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.logs_btn.setStyleSheet(f"background: {COLOR_SPOT_BG}; border: 1px solid {COLOR_TEXT_GRAY}; color: {COLOR_TEXT_WHITE}; border-radius: 5px; padding: 5px 15px; font-size: 11px; font-weight: bold;")
        self.logs_btn.clicked.connect(self.log_viewer.show)
        btn_layout.addWidget(self.logs_btn)

        self.history_btn = QtWidgets.QPushButton("📋 Parking History")
        self.history_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.history_btn.setStyleSheet(f"background: {COLOR_SPOT_BG}; border: 1px solid {COLOR_ACCENT_GREEN}; color: {COLOR_ACCENT_GREEN}; border-radius: 5px; padding: 5px 15px; font-size: 11px; font-weight: bold;")
        self.history_btn.clicked.connect(self.history_viewer.show)
        btn_layout.addWidget(self.history_btn)

        self.cam_left_btn = QtWidgets.QPushButton("📷 Cam Left")
        self.cam_left_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.cam_left_btn.setStyleSheet(f"background: {COLOR_SPOT_BG}; border: 1px solid {COLOR_ACCENT_BLUE}; color: {COLOR_ACCENT_BLUE}; border-radius: 5px; padding: 5px 15px; font-size: 11px; font-weight: bold;")
        self.cam_left_btn.clicked.connect(self._open_cam_left)
        btn_layout.addWidget(self.cam_left_btn)

        self.beacon_btn = QtWidgets.QPushButton("🚨 Beacon")
        self.beacon_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.beacon_btn.setStyleSheet(f"background: {COLOR_SPOT_BG}; border: 1px solid #e67e22; color: #e67e22; border-radius: 5px; padding: 5px 15px; font-size: 11px; font-weight: bold;")
        self.beacon_btn.clicked.connect(self.beacon_dialog.show)
        btn_layout.addWidget(self.beacon_btn)

        self.cam_right_btn = QtWidgets.QPushButton("📷 Cam Right")
        self.cam_right_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.cam_right_btn.setStyleSheet(f"background: {COLOR_SPOT_BG}; border: 1px solid {COLOR_ACCENT_BLUE}; color: {COLOR_ACCENT_BLUE}; border-radius: 5px; padding: 5px 15px; font-size: 11px; font-weight: bold;")
        self.cam_right_btn.clicked.connect(self._open_cam_right)
        btn_layout.addWidget(self.cam_right_btn)

        for text in ["⚙️ Hi-Contrast", "🔍 Enlarge"]:
            btn = QtWidgets.QPushButton(text)
            btn.setStyleSheet(f"background: transparent; border: 1px solid {COLOR_BORDER}; border-radius: 5px; padding: 5px 15px; font-size: 11px;")
            btn_layout.addWidget(btn)

        # Minimize and Close buttons
        self.min_btn = QtWidgets.QPushButton("➖")
        self.min_btn.setStyleSheet(f"background: #2c3e50; border-radius: 5px; padding: 5px 10px; font-size: 12px;")
        self.min_btn.clicked.connect(self.showMinimized)
        btn_layout.addWidget(self.min_btn)

        self.close_btn = QtWidgets.QPushButton("❌")
        self.close_btn.setStyleSheet(f"background: #c0392b; border-radius: 5px; padding: 5px 10px; font-size: 12px;")
        self.close_btn.clicked.connect(self.close)
        btn_layout.addWidget(self.close_btn)
        
        layout.addLayout(btn_layout)
        return footer

    def _start_refresh_timers(self):
        # UI Refresh timer (Fast)
        self.ui_timer = QtCore.QTimer()
        self.ui_timer.timeout.connect(self._refresh_ui)
        self.ui_timer.start(1000)

        # Slow refresh timer for weather and location
        self.slow_timer = QtCore.QTimer()
        self.slow_timer.timeout.connect(self._refresh_slow_data)
        self.slow_timer.start(30000)
        self._refresh_slow_data() # Initial call

    def _refresh_ui(self):
        # Update clock
        now = datetime.now()
        self.clock_label.setText(now.strftime("%a, %b %d • %I:%M:%S %p"))

        # Update electrical and location from system service
        stats = self.system_service.get_stats()
        elec = stats.get("electrical", {})
        
        bus_v = elec.get("bus_voltage", 0.0)
        current = elec.get("current", 0.0)
        power = elec.get("power", 0.0)
        
        # Display Voltage on both sides
        self.battery_info_label.setText(f"{bus_v:.2f}V")
        self.battery_info_label_r.setText(f"{bus_v:.2f}V")
        
        # Bar reflects voltage level (assuming a 12V system: 10V empty, 15V full)
        v_min, v_max = 10.0, 15.0
        v_percent = max(0, min(100, (bus_v - v_min) / (v_max - v_min) * 100))
        self.battery_bar.setValue(int(v_percent))
        self.battery_bar_r.setValue(int(v_percent))
        
        # Display Current on both sides
        self.battery_info_right.setText(f"{current:.3f}A")
        self.battery_info_right_r.setText(f"{current:.3f}A")
        
        # Update Temperature from backend
        try:
            readings = self.backend.get_latest_readings()
            temp = readings.get("Temperature")
            if temp and temp.value is not None:
                # Convert Celsius to Fahrenheit
                f_temp = (temp.value * 9/5) + 32
                self.temp_label.setText(f"🌡️ {int(f_temp)}°F")
            else:
                self.temp_label.setText("🌡️ NULL")
            
            # Update Lidar Monitor if visible
            lidar = readings.get(LIDAR_SENSOR_NAME)
            if lidar and self.lidar_monitor.isVisible():
                self.lidar_monitor.update_value(lidar.value)
        except:
            pass

        # Check Air Quality Status
        self._check_air_quality()

        # Update Flag if country code changed
        country_code = stats["country_code"]
        self.country_flag_label.setText(self._get_flag_emoji(country_code))

    def _refresh_slow_data(self):
        # Logic for slow background updates
        pass

    def _get_flag_emoji(self, country_code):
        if not country_code or len(country_code) != 2:
            return "🏳️"
        return chr(ord(country_code[0]) + 127397) + chr(ord(country_code[1]) + 127397)

def main():
    try:
        global log_manager
        app = QtWidgets.QApplication(sys.argv)
        
        # Initialize global logger after QApplication is ready
        log_manager = LogManager()
        sys.stdout = log_manager
        sys.stderr = log_manager
        
        # Apply library path fix
        if 'QT_PLUGINS_PATH' in globals() and os.path.exists(QT_PLUGINS_PATH):
            app.addLibraryPath(QT_PLUGINS_PATH)
            
        app.setApplicationName("PapayaMeter")
        window = DashboardWindow()
        window.showMaximized()
        window.raise_()
        window.activateWindow()
        sys.exit(app.exec_())
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
