"""
Dark Ship Detection & Tracking Database Module
Tracks ships that go dark (turn off AIS) within 200 nautical miles
"""

import sqlite3
import json
import os
from datetime import datetime
from typing import List, Dict, Optional
import logging

logger = logging.getLogger("DARK_SHIPS")

# Database file path
DATA_DIR = os.getenv("EPIC_ARCHER_DATA_DIR", os.path.join(os.getcwd(), "epic_archer_data"))
DB_PATH = os.path.join(DATA_DIR, "dark_ships.db")
os.makedirs(DATA_DIR, exist_ok=True)


class DarkShipsDatabase:
    """SQLite database for tracking dark ship events"""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize database schema if it doesn't exist"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Dark ship events table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS dark_ship_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        mmsi TEXT NOT NULL,
                        ship_name TEXT,
                        event_type TEXT NOT NULL,
                        event_time TIMESTAMP NOT NULL,
                        latitude REAL NOT NULL,
                        longitude REAL NOT NULL,
                        distance_nm REAL,
                        ship_details TEXT,
                        status TEXT DEFAULT 'active',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Index for MMSI to quickly find related events
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_dark_ships_mmsi 
                    ON dark_ship_events(mmsi)
                """)
                
                # Index for event time to quickly find recent events
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_dark_ships_event_time 
                    ON dark_ship_events(event_time)
                """)
                
                # Active ships being tracked table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS tracked_ships (
                        mmsi TEXT PRIMARY KEY,
                        ship_name TEXT,
                        last_seen_time TIMESTAMP NOT NULL,
                        last_lat REAL NOT NULL,
                        last_lon REAL NOT NULL,
                        last_details TEXT,
                        is_dark INTEGER DEFAULT 0,
                        dark_start_time TIMESTAMP,
                        distance_nm REAL,
                        tracking_since TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                conn.commit()
                logger.info(f"Dark Ships database initialized at {self.db_path}")
        except Exception as e:
            logger.error(f"Failed to initialize dark ships database: {e}")
            raise

    def record_dark_event(self, mmsi: str, ship_name: str, event_type: str,
                         latitude: float, longitude: float, distance_nm: float,
                         ship_details: Dict = None) -> int:
        """
        Record a dark ship event (went offline or came back online)
        
        :param mmsi: Maritime Mobile Service Identity
        :param ship_name: Name of the ship
        :param event_type: "WENT_DARK" or "CAME_ONLINE"
        :param latitude: Last/current latitude
        :param longitude: Last/current longitude
        :param distance_nm: Distance from monitoring area in nautical miles
        :param ship_details: Dict of ship details (IMO, callsign, flag, etc.)
        :return: Event ID
        """
        try:
            details_json = json.dumps(ship_details) if ship_details else None
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO dark_ship_events 
                    (mmsi, ship_name, event_type, event_time, latitude, longitude, distance_nm, ship_details)
                    VALUES (?, ?, ?, datetime('now'), ?, ?, ?, ?)
                """, (mmsi, ship_name, event_type, latitude, longitude, distance_nm, details_json))
                conn.commit()
                event_id = cursor.lastrowid
                logger.info(f"Recorded dark event: {event_type} for {ship_name} (MMSI: {mmsi})")
                return event_id
        except Exception as e:
            logger.error(f"Failed to record dark event: {e}")
            raise

    def update_tracked_ship(self, mmsi: str, ship_name: str, latitude: float,
                           longitude: float, distance_nm: float, ship_details: Dict = None):
        """
        Update a tracked ship's latest position
        
        :param mmsi: Maritime Mobile Service Identity
        :param ship_name: Ship name
        :param latitude: Current latitude
        :param longitude: Current longitude
        :param distance_nm: Distance from monitoring area
        :param ship_details: Ship metadata
        """
        try:
            details_json = json.dumps(ship_details) if ship_details else None
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Check if ship already exists
                cursor.execute("SELECT mmsi FROM tracked_ships WHERE mmsi = ?", (mmsi,))
                exists = cursor.fetchone() is not None
                
                if exists:
                    # Update existing
                    cursor.execute("""
                        UPDATE tracked_ships
                        SET last_seen_time = datetime('now'),
                            last_lat = ?,
                            last_lon = ?,
                            last_details = ?,
                            distance_nm = ?,
                            ship_name = ?
                        WHERE mmsi = ?
                    """, (latitude, longitude, details_json, distance_nm, ship_name, mmsi))
                else:
                    # Insert new
                    cursor.execute("""
                        INSERT INTO tracked_ships 
                        (mmsi, ship_name, last_seen_time, last_lat, last_lon, distance_nm, last_details)
                        VALUES (?, ?, datetime('now'), ?, ?, ?, ?)
                    """, (mmsi, ship_name, latitude, longitude, distance_nm, details_json))
                
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to update tracked ship {mmsi}: {e}")

    def mark_ship_dark(self, mmsi: str):
        """Mark a ship as having gone dark"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE tracked_ships
                    SET is_dark = 1, dark_start_time = datetime('now')
                    WHERE mmsi = ?
                """, (mmsi,))
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to mark ship {mmsi} as dark: {e}")

    def mark_ship_online(self, mmsi: str):
        """Mark a previously dark ship as back online"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE tracked_ships
                    SET is_dark = 0, dark_start_time = NULL
                    WHERE mmsi = ?
                """, (mmsi,))
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to mark ship {mmsi} as online: {e}")

    def get_dark_ships(self) -> List[Dict]:
        """Get all currently dark ships"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT mmsi, ship_name, last_lat, last_lon, distance_nm, 
                           dark_start_time, last_details
                    FROM tracked_ships
                    WHERE is_dark = 1
                    ORDER BY dark_start_time DESC
                """)
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get dark ships: {e}")
            return []

    def get_recent_events(self, limit: int = 100, hours: int = 72) -> List[Dict]:
        """
        Get recent dark ship events
        
        :param limit: Max number of events to return
        :param hours: Only return events from last N hours
        :return: List of event dicts
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, mmsi, ship_name, event_type, event_time,
                           latitude, longitude, distance_nm, ship_details, status
                    FROM dark_ship_events
                    WHERE event_time > datetime('now', '-' || ? || ' hours')
                    ORDER BY event_time DESC
                    LIMIT ?
                """, (hours, limit))
                
                events = []
                for row in cursor.fetchall():
                    event_dict = dict(row)
                    # Parse ship_details JSON if present
                    if event_dict['ship_details']:
                        event_dict['ship_details'] = json.loads(event_dict['ship_details'])
                    events.append(event_dict)
                return events
        except Exception as e:
            logger.error(f"Failed to get recent events: {e}")
            return []

    def get_ship_history(self, mmsi: str) -> List[Dict]:
        """Get all events for a specific ship"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, mmsi, ship_name, event_type, event_time,
                           latitude, longitude, distance_nm, ship_details, status
                    FROM dark_ship_events
                    WHERE mmsi = ?
                    ORDER BY event_time DESC
                """, (mmsi,))
                
                events = []
                for row in cursor.fetchall():
                    event_dict = dict(row)
                    if event_dict['ship_details']:
                        event_dict['ship_details'] = json.loads(event_dict['ship_details'])
                    events.append(event_dict)
                return events
        except Exception as e:
            logger.error(f"Failed to get ship history for {mmsi}: {e}")
            return []

    def get_all_tracked_ships(self) -> List[Dict]:
        """Get all ships being tracked"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT mmsi, ship_name, last_seen_time, last_lat, last_lon,
                           distance_nm, is_dark, dark_start_time, last_details
                    FROM tracked_ships
                    ORDER BY last_seen_time DESC
                """)
                
                ships = []
                for row in cursor.fetchall():
                    ship_dict = dict(row)
                    if ship_dict['last_details']:
                        ship_dict['last_details'] = json.loads(ship_dict['last_details'])
                    ships.append(ship_dict)
                return ships
        except Exception as e:
            logger.error(f"Failed to get tracked ships: {e}")
            return []

    def delete_old_events(self, days: int = 30):
        """Delete events older than N days to keep DB manageable"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    DELETE FROM dark_ship_events
                    WHERE event_time < datetime('now', '-' || ? || ' days')
                """, (days,))
                conn.commit()
                logger.info(f"Deleted dark ship events older than {days} days")
        except Exception as e:
            logger.error(f"Failed to delete old events: {e}")
