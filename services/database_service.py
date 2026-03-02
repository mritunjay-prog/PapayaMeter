import configparser
import os
import time
from datetime import datetime
from typing import Dict, Any, Optional
import psycopg2
from psycopg2 import sql

# Path to config.properties relative to this service
CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', 'config.properties')

class DatabaseService:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.config = configparser.ConfigParser()
        self.config.read(CONFIG_PATH)
        
        try:
            self.host = self.config.get('database', 'host', fallback='localhost')
            self.port = self.config.getint('database', 'port', fallback=5432)
            self.user = self.config.get('database', 'user', fallback='myuser')
            self.password = self.config.get('database', 'password', fallback='example')
            self.dbname = self.config.get('database', 'dbname', fallback='papaya_meter')
            
            # Asset info needed for every record
            self.device_name = self.config.get('assets', 'device_name', fallback='UNKNOWN_DEVICE')
            
            self.conn = None
            self._ensure_table_exists()
            self._ensure_roi_table_exists()
        except Exception as e:
            print(f"❌ Database setup error: {e}")

    def _ensure_table_exists(self):
        """Creates the parking_details table if it doesn't exist yet."""
        conn = self._get_connection()
        if not conn:
            return
        
        try:
            cur = conn.cursor()
            query = """
            CREATE TABLE IF NOT EXISTS parking_details (
                id SERIAL PRIMARY KEY,
                device_name VARCHAR(100) NOT NULL,
                camera_side VARCHAR(10) NOT NULL,
                car_number VARCHAR(50) NOT NULL,
                start_time TIMESTAMP NOT NULL,
                end_time TIMESTAMP,
                total_amount DECIMAL(10, 2),
                is_paid BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
            cur.execute(query)
            cur.close()
            print("✅ Database table 'parking_details' is ready.")
        except Exception as e:
            print(f"❌ Error creating table: {e}")

    def _ensure_roi_table_exists(self):
        """Creates the roi_config table to store camera ROI polygons."""
        conn = self._get_connection()
        if not conn:
            return
        try:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS roi_config (
                    id SERIAL PRIMARY KEY,
                    device_name VARCHAR(100) NOT NULL,
                    camera_side VARCHAR(10) NOT NULL,
                    points JSONB NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (device_name, camera_side)
                );
            """)
            cur.close()
            print("✅ Database table 'roi_config' is ready.")
        except Exception as e:
            print(f"❌ Error creating roi_config table: {e}")

    def save_roi(self, camera_side: str, points: list) -> bool:
        """Upsert the ROI polygon for a given camera side (left/right)."""
        import json
        conn = self._get_connection()
        if not conn:
            return False
        try:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO roi_config (device_name, camera_side, points, updated_at)
                VALUES (%s, %s, %s::jsonb, NOW())
                ON CONFLICT (device_name, camera_side)
                DO UPDATE SET points = EXCLUDED.points, updated_at = NOW();
            """, (self.device_name, camera_side, json.dumps(points)))
            cur.close()
            print(f"✅ ROI saved for camera '{camera_side}': {points}")
            return True
        except Exception as e:
            print(f"❌ DB save_roi error: {e}")
            return False

    def load_roi(self, camera_side: str) -> list:
        """Load the saved ROI polygon for a given camera side. Returns list of [x,y] or []."""
        conn = self._get_connection()
        if not conn:
            return []
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT points FROM roi_config
                WHERE device_name = %s AND camera_side = %s
                ORDER BY updated_at DESC LIMIT 1;
            """, (self.device_name, camera_side))
            row = cur.fetchone()
            cur.close()
            return row[0] if row else []
        except Exception as e:
            print(f"❌ DB load_roi error: {e}")
            return []

    def _get_connection(self):
        """Lazy connection to database with retry."""
        if self.conn and not self.conn.closed:
            return self.conn
        
        try:
            self.conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                dbname=self.dbname,
                connect_timeout=5
            )
            self.conn.autocommit = True
            return self.conn
        except Exception as e:
            # print(f"❌ Failed to connect to PostgreSQL: {e}")
            return None

    def create_session(self, camera_side: str, car_number: str) -> Optional[int]:
        """
        Inserts a new parking session record. Returns the record ID.
        """
        conn = self._get_connection()
        if not conn:
            return None
        
        try:
            cur = conn.cursor()
            query = """
                INSERT INTO parking_details (device_name, camera_side, car_number, start_time)
                VALUES (%s, %s, %s, %s)
                RETURNING id;
            """
            cur.execute(query, (self.device_name, camera_side, car_number, datetime.now()))
            session_id = cur.fetchone()[0]
            cur.close()
            return session_id
        except Exception as e:
            print(f"❌ DB insert error: {e}")
            return None

    def update_session_on_stop(self, session_id: int):
        """Sets the end time when a vehicle departs."""
        conn = self._get_connection()
        if not conn or session_id is None:
            return
        
        try:
            cur = conn.cursor()
            query = "UPDATE parking_details SET end_time = %s WHERE id = %s"
            cur.execute(query, (datetime.now(), session_id))
            cur.close()
        except Exception as e:
            print(f"❌ DB update error: {e}")

    def complete_payment(self, session_id: int, total_amount: float):
        """Finalizes the session with total amount and is_paid=True."""
        conn = self._get_connection()
        if not conn or session_id is None:
            return
        
        try:
            cur = conn.cursor()
            query = """
                UPDATE parking_details 
                SET total_amount = %s, is_paid = TRUE, end_time = COALESCE(end_time, %s)
                WHERE id = %s
            """
            cur.execute(query, (total_amount, datetime.now(), session_id))
            cur.close()
            print(f"✅ Database record updated for session {session_id} (${total_amount:.2f} paid)")
        except Exception as e:
            print(f"❌ DB finalize error: {e}")

    def fetch_history(self):
        """Fetches all parking history records."""
        conn = self._get_connection()
        if not conn:
            return []
        
        try:
            cur = conn.cursor()
            query = "SELECT camera_side, car_number, start_time, end_time, total_amount, is_paid FROM parking_details ORDER BY created_at DESC"
            cur.execute(query)
            rows = cur.fetchall()
            cur.close()
            return rows
        except Exception as e:
            print(f"❌ DB fetch error: {e}")
            return []

# Helper for singleton usage
def get_db():
    return DatabaseService.get_instance()
