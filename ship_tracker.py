"""
Ship Tracking & Dark Detection Manager
Monitors live AIS data and detects ships going dark within 200 nautical miles
"""

import asyncio
import logging
from typing import Dict, Optional, Set
from datetime import datetime, timedelta
import json
from dark_ships_db import DarkShipsDatabase

logger = logging.getLogger("SHIP_TRACKER")

# 200 nautical miles in kilometers
DANGER_ZONE_NM = 200
KM_PER_NM = 1.852


def distance_between_coords(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate approximate distance in nautical miles using Haversine formula
    """
    from math import radians, sin, cos, sqrt, atan2
    
    R = 3440.065  # Earth radius in nautical miles
    
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    distance = R * c
    
    return distance


class ShipTracker:
    """
    Tracks ships in real-time and detects dark events
    Monitors if ships within 200 NM turn off AIS
    """

    def __init__(self, monitoring_lat: float = 0, monitoring_lon: float = 0,
                 danger_zone_nm: float = DANGER_ZONE_NM,
                 dark_timeout_seconds: int = 3600):
        """
        Initialize ship tracker
        
        :param monitoring_lat: Center latitude of monitoring area
        :param monitoring_lon: Center longitude of monitoring area
        :param danger_zone_nm: Radius in nautical miles to monitor
        :param dark_timeout_seconds: How long without AIS before marking ship as dark (default 1 hour)
        """
        self.monitoring_lat = monitoring_lat
        self.monitoring_lon = monitoring_lon
        self.danger_zone_nm = danger_zone_nm
        self.dark_timeout = timedelta(seconds=dark_timeout_seconds)
        
        # Track ships we're actively monitoring
        self.tracked_ships: Dict[str, Dict] = {}  # mmsi -> ship_data
        
        # Ships we know went dark
        self.dark_ships: Set[str] = set()  # mmsi of dark ships
        
        # Database
        self.db = DarkShipsDatabase()
        
        logger.info(f"ShipTracker initialized: monitoring ({monitoring_lat}, {monitoring_lon}), "
                   f"range {danger_zone_nm} NM, dark timeout {dark_timeout_seconds}s")

    def update_monitoring_area(self, lat: float, lon: float):
        """Update the monitoring area center"""
        self.monitoring_lat = lat
        self.monitoring_lon = lon
        logger.info(f"Updated monitoring area to ({lat}, {lon})")

    def is_in_danger_zone(self, ship_lat: float, ship_lon: float) -> float:
        """
        Check if ship is within danger zone
        
        :return: Distance in nautical miles (or -1 if outside danger zone)
        """
        distance = distance_between_coords(
            self.monitoring_lat, self.monitoring_lon,
            ship_lat, ship_lon
        )
        
        if distance <= self.danger_zone_nm:
            return distance
        return -1  # Outside danger zone

    def process_ais_update(self, mmsi: str, ship_data: Dict) -> Optional[Dict]:
        """
        Process an AIS update for a ship
        
        :param mmsi: Maritime Mobile Service Identity
        :param ship_data: Dict with lat, lon, name, callsign, flag, type, etc.
        :return: Event dict if something notable happened, None otherwise
        """
        try:
            ship_lat = ship_data.get('lat')
            ship_lon = ship_data.get('lon')
            ship_name = ship_data.get('name', 'Unknown')
            
            if not ship_lat or not ship_lon:
                return None
            
            # Check if ship is in danger zone
            distance_nm = self.is_in_danger_zone(ship_lat, ship_lon)
            
            if distance_nm < 0:
                # Ship is outside danger zone
                # If we were tracking it, mark it as left the zone
                if mmsi in self.tracked_ships:
                    logger.info(f"Ship {ship_name} ({mmsi}) left danger zone")
                    del self.tracked_ships[mmsi]
                return None
            
            # Ship is in danger zone
            current_time = datetime.now()
            
            # Update or create tracking record
            if mmsi in self.tracked_ships:
                # Update existing
                old_record = self.tracked_ships[mmsi]
                self.tracked_ships[mmsi] = {
                    'name': ship_name,
                    'lat': ship_lat,
                    'lon': ship_lon,
                    'distance_nm': distance_nm,
                    'last_update': current_time,
                    'details': {
                        'callsign': ship_data.get('callsign'),
                        'flag': ship_data.get('flag'),
                        'type': ship_data.get('type'),
                        'size_length': ship_data.get('size_length'),
                        'size_beam': ship_data.get('size_beam'),
                        'draft': ship_data.get('draft'),
                        'destination': ship_data.get('destination'),
                        'status': ship_data.get('status'),
                    }
                }
                
                # Check if ship was marked dark but is now back online
                if mmsi in self.dark_ships:
                    event = {
                        'type': 'CAME_ONLINE',
                        'mmsi': mmsi,
                        'ship_name': ship_name,
                        'lat': ship_lat,
                        'lon': ship_lon,
                        'distance_nm': distance_nm,
                        'timestamp': current_time.isoformat(),
                        'dark_duration': (current_time - old_record['dark_start']).total_seconds() if 'dark_start' in old_record else 0,
                    }
                    
                    # Record in database
                    self.db.record_dark_event(
                        mmsi, ship_name, 'CAME_ONLINE',
                        ship_lat, ship_lon, distance_nm,
                        ship_data
                    )
                    self.db.mark_ship_online(mmsi)
                    
                    self.dark_ships.discard(mmsi)
                    logger.warning(f"SHIP BACK ONLINE: {ship_name} ({mmsi}) - was dark for {event['dark_duration']}s")
                    return event
            else:
                # New ship in danger zone
                self.tracked_ships[mmsi] = {
                    'name': ship_name,
                    'lat': ship_lat,
                    'lon': ship_lon,
                    'distance_nm': distance_nm,
                    'last_update': current_time,
                    'details': {
                        'callsign': ship_data.get('callsign'),
                        'flag': ship_data.get('flag'),
                        'type': ship_data.get('type'),
                        'size_length': ship_data.get('size_length'),
                        'size_beam': ship_data.get('size_beam'),
                        'draft': ship_data.get('draft'),
                        'destination': ship_data.get('destination'),
                        'status': ship_data.get('status'),
                    }
                }
                
                logger.info(f"New ship in danger zone: {ship_name} ({mmsi}) at {distance_nm:.1f} NM")
            
            # Update database
            self.db.update_tracked_ship(
                mmsi, ship_name, ship_lat, ship_lon, distance_nm,
                self.tracked_ships[mmsi]['details']
            )
            
            return None
            
        except Exception as e:
            logger.error(f"Error processing AIS update for {mmsi}: {e}")
            return None

    def check_dark_ships(self) -> list:
        """
        Check which ships have gone dark (no AIS update in a while)
        Should be called periodically (e.g., every 30-60 seconds)
        
        :return: List of newly dark ship events
        """
        events = []
        current_time = datetime.now()
        
        for mmsi, ship_record in list(self.tracked_ships.items()):
            time_since_last_update = current_time - ship_record['last_update']
            
            # Check if ship should be marked dark
            if time_since_last_update > self.dark_timeout and mmsi not in self.dark_ships:
                # Ship has gone dark!
                event = {
                    'type': 'WENT_DARK',
                    'mmsi': mmsi,
                    'ship_name': ship_record['name'],
                    'lat': ship_record['lat'],
                    'lon': ship_record['lon'],
                    'distance_nm': ship_record['distance_nm'],
                    'timestamp': current_time.isoformat(),
                    'last_update_time': ship_record['last_update'].isoformat(),
                    'offline_for': time_since_last_update.total_seconds(),
                }
                
                # Record in database
                self.db.record_dark_event(
                    mmsi, ship_record['name'], 'WENT_DARK',
                    ship_record['lat'], ship_record['lon'],
                    ship_record['distance_nm'],
                    ship_record['details']
                )
                self.db.mark_ship_dark(mmsi)
                
                ship_record['dark_start'] = current_time
                self.dark_ships.add(mmsi)
                
                logger.warning(f"SHIP WENT DARK: {ship_record['name']} ({mmsi}) - "
                              f"no AIS for {time_since_last_update.total_seconds()}s")
                events.append(event)
        
        return events

    def get_dark_ships_list(self) -> list:
        """Get list of all currently dark ships"""
        return [
            {
                'mmsi': mmsi,
                'ship_name': ship_record['name'],
                'distance_nm': ship_record.get('distance_nm'),
                'last_lat': ship_record['lat'],
                'last_lon': ship_record['lon'],
                'dark_since': ship_record.get('dark_start', ship_record['last_update']).isoformat(),
            }
            for mmsi, ship_record in self.tracked_ships.items()
            if mmsi in self.dark_ships
        ]

    def get_tracked_ships_summary(self) -> Dict:
        """Get summary of all tracked ships"""
        return {
            'total_tracked': len(self.tracked_ships),
            'currently_dark': len(self.dark_ships),
            'ships': [
                {
                    'mmsi': mmsi,
                    'name': ship_record['name'],
                    'distance_nm': ship_record.get('distance_nm'),
                    'is_dark': mmsi in self.dark_ships,
                    'last_update': ship_record['last_update'].isoformat(),
                }
                for mmsi, ship_record in self.tracked_ships.items()
            ]
        }
