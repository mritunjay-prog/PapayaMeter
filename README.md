# 📟 Device Provisioning & Registration Guide

## 🌟 Overview
The **Device Provisioning Service** (`core/DeviceProvision.py`) is a critical component of the ThingsBoard IoT Sensor Management System. It automates the complex process of registering high-end IoT hardware into the cloud platform, establishing a hierarchical asset structure, and securing device credentials.

Instead of manual configuration in the ThingsBoard UI, this script ensures that every device is correctly placed within a geographical context (Country -> State -> Device) with zero-touch configuration.

---

## 🏗️ Core Architecture

The provisioning system relies on two primary Python modules:
1.  **`core/DeviceProvision.py`**: The main execution engine that handles asset creation, relationship linking, and initial telemetry handshake.
2.  **`core/get_jwt_token.py`**: A helper module that manages authentication with the ThingsBoard REST API and handles token refreshing.

---

## 🔄 The Provisioning Workflow

The system follows a 6-step automated process to ensure the device is ready for data collection.

### 1. 🔐 REST API Authentication
The script first attempts to use a stored JWT (JSON Web Token) from `config.properties`.
- **Validation**: It calls `/api/auth/user` to check if the token is still valid.
- **Auto-Refresh**: If invalid, it uses the provided Tenant Admin credentials to fetch a new token and updates the configuration file automatically.

### 2. 🌍 Intelligent Geolocation
The system uses the `ipapi.co` service to detect the device's physical location.
- **Process**: Performs an IP-based lookup to retrieve `latitude`, `longitude`, `city`, `region`, and `country`.
- **Fallthrough**: If location detection fails (e.g., due to firewall or no internet), it falls back to coordinates pre-defined in the configuration file.

### 3. 🏢 Asset Hierarchy Verification
ThingsBoard uses a hierarchical model. The script manages three levels:
- **Level 1: Country Asset**: Checks if an asset matching the `COUNTRY_NAME` exists. If missing, it creates it using the `COUNTRY_PROFILE_NAME`.
- **Level 2: State Asset**: Checks if a state/region asset exists. It creates it if necessary and assigns the detected (or config) coordinates.
- **Relationship Linking**: It establishes a "Contains" relation between the Country and the State.

### 4. 🛰️ Device Registration
- **Search**: Scans the tenant for a device matching the local system's `DEVICE_NAME`.
- **Creation**: If the device is new, it is registered under the specified `DEVICE_PROFILE_NAME`.
- **Linking**: The device is linked to the **State Asset**, completing the hierarchy: `Country -> State -> Device`.

### 5. 🔑 Credential Acquisition
Once the device is registered, the script makes a REST call to retrieve the **Device Access Token** (Credentials ID). This token is essential for:
- MQTT Authentication.
- Sending Sensor Telemetry.
- Receiving RPC (Remote Procedure Call) commands.

### 6. 👋 Initial Handshake (Telemetry)
To confirm the registration is successful, the device sends its first "heartbeat" telemetry packet containing:
- Serial Number
- Hardware Location (Lat/Lon)
- Local System Information

---

## 🛠️ Requirements & Prerequisites

### 1. Configuration (`config.properties`)
The following properties must be correctly set in `data/config/config.properties`:
```ini
[thingsboard]
url = https://your-thingsboard-instance.com
username = tenant_admin@example.com
password = your_secure_password

[profiles]
country_profile_name = Country
state_profile_name = State
device_profile_name = IoT-Gateway
```

### 2. ThingsBoard Profiles
The **Asset Profiles** and **Device Profile** referenced in the config must already exist in ThingsBoard. The script will fetch their internal IDs dynamically during execution.

<!-- ### 3. Network Access
- **Port 443 (HTTPS)**: For REST API calls and geolocation lookup.
- **Port 1883/8883 (MQTT)**: For telemetry (used by the main API service after provisioning). -->

---



## ⚠️ Troubleshooting

| Issue | Cause | Solution |
| :--- | :--- | :--- |
| **403 Forbidden** | User lacks TENANT_ADMIN rights. | Ensure the username in config has administrative permissions. |
| **Profile Not Found** | Profile name mismatch. | Verify the profile name in ThingsBoard UI matches `config.properties`. |
| **Token Refresh Failed**| Incorrect password. | Update the password in `config.properties`. |
| **Location Detection Error** | No internet or blocked IP. | The system will fallback to manual coordinates in config. |

---

**IoT Sensor Management System** - *Automated Device Lifecycle Management*


## 🖥️ Desktop Sensor Viewer (PapayaMeter GUI)

In addition to the provisioning scripts, this project now includes a **standalone Ubuntu desktop application** (non‑web) for viewing sensor data locally.

The GUI is built with **PyQt6** and **pyqtgraph** and is designed so you can later plug in your real sensor data source (hardware, database, MQTT, ThingsBoard, etc.).

### 🚀 Quick Start (GUI)

1. **Create & activate a virtual environment** (recommended):

   ```bash
   cd /home/mritunjay/Desktop/PapayaMeter
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. **Install dependencies**:

   ```bash
   pip install -r requirements.txt
   ```

3. **Run the desktop app**:

   ```bash
   python main.py
   ```

   This opens the **PapayaMeter - Sensor Monitor** window:
   - The **left table** shows the latest simulated readings for each sensor.
   - The **right plot** shows a time‑series graph for the selected sensor.
   - Use the **update interval** control to change how often data refreshes.

### 🧩 Wiring to Real Sensors

The GUI uses `sensor_backend.py` as a thin abstraction over the data source:

- `SensorBackend.get_available_sensors()` returns a list of sensor names.
- `SensorBackend.get_latest_readings()` returns a mapping from sensor name to a `SensorReading` (value, unit, timestamp).

Right now, `SensorBackend` generates smooth, simulated values so that the GUI is immediately usable. To connect to your real system, you can:

- Replace the body of `get_latest_readings()` to pull from:
  - Hardware interfaces (serial/I2C/SPI),
  - Local files/DB,
  - Or the existing ThingsBoard backend (e.g. via REST or MQTT, reusing your provisioning config).

If you'd like, you can ask the AI assistant to extend `SensorBackend` to talk directly to your real sensor stack.

---

## 🛡️ Reverse SSH service (auto-start at boot)

The SSH tunnel service (`services/ssh_service.py`) can be started automatically when the system boots using systemd.

**One-time setup:**

1. Edit `systemd/papaya-ssh.service` if your project path or username differs (update `User=`, `WorkingDirectory`, and `ExecStart` paths).

2. Install and enable the service (requires sudo):

   ```bash
   sudo cp systemd/papaya-ssh.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable papaya-ssh.service
   sudo systemctl start papaya-ssh.service
   ```

3. Check status: `sudo systemctl status papaya-ssh`

**Useful commands:**

- Start: `sudo systemctl start papaya-ssh`
- Stop: `sudo systemctl stop papaya-ssh`
- View logs: `journalctl -u papaya-ssh -f`

