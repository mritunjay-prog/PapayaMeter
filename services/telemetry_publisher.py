import json
import time
import queue
import threading
import paho.mqtt.client as mqtt
import configparser
import os
from typing import Dict, Any

CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', 'config.properties')

class TelemetryPublisher:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(TelemetryPublisher, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        
        self.config = configparser.ConfigParser()
        self.config.read(CONFIG_PATH)
        
        self.url = self.config.get('thingsboard', 'url').replace('https://', '').replace('http://', '').split(':')[0]
        self.port = 1883
        
        # We'll set the token later after provisioning or read from config if already there
        self.token = None
        self.mqtt_client = None
        self.telemetry_queue = queue.Queue()
        self.publish_count = 0
        self.stop_event = threading.Event()
        self._initialized = True
        
        self.worker_thread = threading.Thread(target=self._publishing_worker, daemon=True)
        self.worker_thread.start()

    def set_token(self, token: str):
        self.token = token
        if self.mqtt_client:
            self.mqtt_client.disconnect()
        
        self.mqtt_client = mqtt.Client()
        self.mqtt_client.username_pw_set(self.token)
        
        try:
            self.mqtt_client.connect(self.url, self.port, 60)
            self.mqtt_client.loop_start()
            print(f"📡 MQTT Connected to {self.url} with token {self.token[:5]}...")
        except Exception as e:
            print(f"❌ Failed to connect to MQTT: {e}")

    def publish(self, data: Dict[str, Any]):
        """Queue telemetry data for publishing."""
        self.telemetry_queue.put(data)

    def _publishing_worker(self):
        while not self.stop_event.is_set():
            try:
                # Wait for data with a timeout so we can check stop_event
                payload = self.telemetry_queue.get(timeout=1)
                
                if not self.mqtt_client or not self.mqtt_client.is_connected():
                    # If not connected, we might want to wait or try reconnecting if we have a token
                    if self.token:
                        try:
                            self.mqtt_client.reconnect()
                        except:
                            pass
                    time.sleep(1)
                    # Re-queue the payload
                    self.telemetry_queue.put(payload)
                    continue

                topic = "v1/devices/me/telemetry"
                self.mqtt_client.publish(topic, json.dumps(payload))
                self.publish_count += 1
                self.telemetry_queue.task_done()
                
            except queue.Empty:
                continue
            except Exception as e:
                print(f"❌ Error in publishing worker: {e}")
                time.sleep(1)

    def stop(self):
        self.stop_event.set()
        if self.mqtt_client:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()

# Singleton helper
_publisher = TelemetryPublisher()

def publish_telemetry(data: Dict[str, Any]):
    _publisher.publish(data)

def set_mqtt_token(token: str):
    _publisher.set_token(token)
