import sys
import os
import time
from datetime import datetime
from typing import Dict, Optional, Callable

# Use PyQt5 as requested
from PyQt5 import QtCore, QtWidgets, QtGui

# Map PyQt5 names to match the code's expected Qt6 style (if needed)
Qt = QtCore.Qt
AlignmentFlag = QtCore.Qt
AspectRatioMode = QtCore.Qt
TransformationMode = QtCore.Qt
FrameShape = QtWidgets.QFrame

from sensor_backend import SensorBackend, LIDAR_SENSOR_NAME
from services.system_service import SystemService

# Color constants to match the image
COLOR_BG = "#12171e"
COLOR_SPOT_BG = "#1a222c"
COLOR_ACCENT_GREEN = "#39ff5a"
COLOR_ACCENT_BLUE = "#3498db"
COLOR_TEXT_WHITE = "#ffffff"
COLOR_TEXT_GRAY = "#8a97a5"
COLOR_BORDER = "#2a323d"

class SpotWidget(QtWidgets.QWidget):
    """Encapsulated widget for a single parking spot."""
    def __init__(self, name: str, id_code: str, parent=None):
        super().__init__(parent)
        self.spot_name = name
        self.id_code = id_code
        self.is_occupied = False
        self.plate_number = ""
        self.start_time: Optional[float] = None
        self.elapsed: float = 0
        
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self._update_timer)
        self.timer.setInterval(1000)

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

        self.main_layout.addStretch()

        # STACKED CONTENT (Available / Input / Occupied / Payment)
        self.content_stack = QtWidgets.QStackedWidget()
        self.main_layout.addWidget(self.content_stack)

        # 1. Available View
        self.avail_view = QtWidgets.QWidget()
        av_layout = QtWidgets.QVBoxLayout(self.avail_view)
        av_layout.setAlignment(AlignmentFlag.AlignCenter)
        
        self.avail_icon = QtWidgets.QLabel()
        self.avail_icon.setPixmap(QtGui.QPixmap("/home/mritunjay/Desktop/PapayaMeter/gui/static/available.png").scaled(120, 120, AspectRatioMode.KeepAspectRatio, TransformationMode.SmoothTransformation))
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
        self.car_icon.setPixmap(QtGui.QPixmap("/home/mritunjay/Desktop/PapayaMeter/gui/static/car.png").scaled(200, 200, AspectRatioMode.KeepAspectRatio, TransformationMode.SmoothTransformation))
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
        self.timer_label.setStyleSheet(f"color: {COLOR_ACCENT_GREEN}; font-size: 36px; font-weight: bold; margin-top: 20px;")
        oc_layout.addWidget(self.timer_label, alignment=AlignmentFlag.AlignCenter)
        
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

        # 4. Payment View
        self.pay_view = QtWidgets.QWidget()
        py_layout = QtWidgets.QVBoxLayout(self.pay_view)
        py_layout.setAlignment(AlignmentFlag.AlignCenter)
        
        pay_title = QtWidgets.QLabel("SESSION ENDED")
        pay_title.setStyleSheet(f"color: {COLOR_ACCENT_BLUE}; font-size: 18px; font-weight: bold;")
        py_layout.addWidget(pay_title, alignment=AlignmentFlag.AlignCenter)
        
        self.summary_label = QtWidgets.QLabel("Total Time: 00:00:00")
        self.summary_label.setStyleSheet("font-size: 14px; margin-bottom: 20px;")
        py_layout.addWidget(self.summary_label, alignment=AlignmentFlag.AlignCenter)
        
        self.pay_btn = QtWidgets.QPushButton("PAY FOR PARKING")
        self.pay_btn.setStyleSheet(self._button_style("#f39c12"))
        self.pay_btn.clicked.connect(self._process_payment)
        py_layout.addWidget(self.pay_btn, alignment=AlignmentFlag.AlignCenter)
        
        self.content_stack.addWidget(self.pay_view)

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
        self.content_stack.setCurrentIndex(2)

    def _update_timer(self):
        self.elapsed = time.time() - self.start_time
        self.timer_label.setText(f"⏱️ {self._format_time(self.elapsed)}")

    def _stop_session(self):
        self.timer.stop()
        self.summary_label.setText(f"Plate: {self.plate_number}\nTotal Time: {self._format_time(self.elapsed)}")
        self.content_stack.setCurrentIndex(3)

    def _process_payment(self):
        # Simulated payment
        QtWidgets.QMessageBox.information(self, "Payment Successful", f"Payment processed for {self.plate_number}.\nThank you!")
        self._set_state_available()

    def _format_time(self, seconds):
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

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

class DashboardWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PapayaMeter Dashboard")
        self.setMinimumSize(1200, 800)
        self.setStyleSheet(f"background-color: {COLOR_BG}; color: {COLOR_TEXT_WHITE}; font-family: 'Inter', sans-serif;")

        # Services
        self.backend = SensorBackend()
        self.system_service = SystemService()
        self.system_service.start()
        
        self.lidar_monitor = LidarMonitorDialog(self)

        self._init_ui()
        self._setup_shortcuts()
        self._start_refresh_timers()

    def _setup_shortcuts(self):
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

    def _handle_shortcut(self, spot, action):
        if action == "start":
            if spot.content_stack.currentIndex() == 0: # Available
                spot._set_state_input()
            elif spot.content_stack.currentIndex() == 1: # Input
                spot._start_session()
        elif action == "stop":
            if spot.content_stack.currentIndex() == 2: # Occupied
                spot._stop_session()
            elif spot.content_stack.currentIndex() == 3: # Payment
                spot._process_payment()

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
        self.left_spot = SpotWidget("LEFT SPOT", "SP-047")
        body_layout.addWidget(self.left_spot)

        # Vertical Divider
        divider = QtWidgets.QFrame()
        divider.setFrameShape(FrameShape.VLine)
        divider.setStyleSheet(f"background-color: {COLOR_BORDER}; min-width: 1px; max-width: 1px;")
        body_layout.addWidget(divider)

        # Right Spot
        self.right_spot = SpotWidget("RIGHT SPOT", "SP-048")
        body_layout.addWidget(self.right_spot)

        main_layout.addWidget(body, 1)

        # 3. Bottom Battery/Power Bar
        footer_bars = self._create_footer_bars()
        main_layout.addWidget(footer_bars)

        # 4. Footer Icons/Language
        footer = self._create_footer()
        main_layout.addWidget(footer)

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
        
        self.aqi_label = QtWidgets.QLabel("🌬️ AQT 38 Good")
        self.aqi_label.setStyleSheet(f"font-size: 14px; color: {COLOR_ACCENT_GREEN};")

        layout.addWidget(self.temp_label)
        layout.addWidget(self.aqi_label)

        return header

    def _create_footer_bars(self):
        container = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(20, 10, 20, 10)
        layout.setSpacing(20)

        # Left Progress Bar (Battery)
        self.battery_info_label = QtWidgets.QLabel("0%")
        self.battery_info_label.setStyleSheet("font-size: 12px; font-weight: bold; margin-right: 10px;")
        
        self.battery_bar = QtWidgets.QProgressBar()
        self.battery_bar.setFixedHeight(12)
        self.battery_bar.setTextVisible(False)
        self.battery_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {COLOR_SPOT_BG};
                border: 1px solid {COLOR_BORDER};
                border-radius: 6px;
            }}
            QProgressBar::chunk {{
                background-color: {COLOR_ACCENT_GREEN};
                border-radius: 5px;
            }}
        """)
        
        self.battery_info_right = QtWidgets.QLabel("0.0kW")
        self.battery_info_right.setStyleSheet(f"color: {COLOR_ACCENT_GREEN}; font-size: 12px; font-weight: bold; margin-left: 10px;")

        bar_inner_layout = QtWidgets.QHBoxLayout()
        bolt_icon = QtWidgets.QLabel("⚡")
        bar_inner_layout.addWidget(bolt_icon)
        bar_inner_layout.addWidget(self.battery_info_label)
        bar_inner_layout.addWidget(self.battery_bar, 1)
        bar_inner_layout.addWidget(self.battery_info_right)
        
        left_bar_widget = QtWidgets.QWidget()
        left_bar_widget.setFixedHeight(40)
        left_bar_widget.setStyleSheet(f"border: 1px solid {COLOR_BORDER}; border-radius: 20px; background-color: {COLOR_BG};")
        left_bar_widget.setLayout(bar_inner_layout)
        
        # Right "NO CHARGER" bar
        no_charger_bar = QtWidgets.QWidget()
        no_charger_bar.setFixedHeight(40)
        no_charger_bar.setStyleSheet(f"border: 1px solid {COLOR_BORDER}; border-radius: 20px; background-color: {COLOR_BG};")
        nc_layout = QtWidgets.QHBoxLayout(no_charger_bar)
        nc_icon = QtWidgets.QLabel("🔌")
        nc_label = QtWidgets.QLabel("NO CHARGER")
        nc_label.setStyleSheet(f"color: {COLOR_TEXT_GRAY}; font-size: 12px; font-weight: bold;")
        nc_layout.addWidget(nc_icon)
        nc_layout.addWidget(nc_label)
        nc_layout.addStretch()

        layout.addWidget(left_bar_widget, 1)
        layout.addWidget(no_charger_bar, 1)

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
        globe_pixmap = QtGui.QPixmap("/home/mritunjay/Desktop/PapayaMeter/gui/static/globe.png")
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

        for text in ["⚙️ Hi-Contrast", "🔍 Enlarge"]:
            btn = QtWidgets.QPushButton(text)
            btn.setStyleSheet(f"background: transparent; border: 1px solid {COLOR_BORDER}; border-radius: 5px; padding: 5px 15px; font-size: 11px;")
            btn_layout.addWidget(btn)
        
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

        # Update battery and location from system service
        stats = self.system_service.get_stats()
        bat_percent = stats["battery_percent"]
        bat_power = stats["battery_power"]
        
        self.battery_info_label.setText(f"{int(bat_percent)}%")
        self.battery_bar.setValue(int(bat_percent))
        self.battery_info_right.setText(f"{bat_power}kW")
        
        # Update Temperature from backend
        try:
            readings = self.backend.get_latest_readings()
            temp = readings.get("Temperature")
            if temp:
                # Convert Celsius to Fahrenheit
                f_temp = (temp.value * 9/5) + 32
                self.temp_label.setText(f"🌡️ {int(f_temp)}°F")
            
            # Update Lidar Monitor if visible
            lidar = readings.get(LIDAR_SENSOR_NAME)
            if lidar and self.lidar_monitor.isVisible():
                self.lidar_monitor.update_value(lidar.value)
        except:
            pass

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
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("PapayaMeter")
    window = DashboardWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
