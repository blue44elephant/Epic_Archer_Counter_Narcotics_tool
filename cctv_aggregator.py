"""
CCTV Aggregator Module for Epic Archer
Integrates maritime surveillance, coastal CCTV, and port monitoring systems
"""

import asyncio
import logging
import os
from typing import List, Dict, Optional
from datetime import datetime

logger = logging.getLogger("EPIC_ARCHER.CCTV")


class CCTVCamera:
    """Represents a CCTV camera with metadata and stream information"""
    
    def __init__(
        self,
        camera_id: str,
        name: str,
        lat: float,
        lng: float,
        city: str = "",
        country: str = "",
        camera_type: str = "surveillance",  # surveillance, port, coastal, maritime
        feed_url: Optional[str] = None,
        stream_url: Optional[str] = None,
        stream_type: str = "jpg",  # jpg, hls, iframe
        source: str = "Unknown",
        external_url: Optional[str] = None,
    ):
        self.id = camera_id
        self.name = name
        self.lat = lat
        self.lng = lng
        self.city = city
        self.country = country
        self.camera_type = camera_type
        self.feed_url = feed_url
        self.stream_url = stream_url
        self.stream_type = stream_type
        self.source = source
        self.external_url = external_url
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        return {
            "id": self.id,
            "lat": self.lat,
            "lng": self.lng,
            "name": self.name,
            "city": self.city,
            "country": self.country,
            "camera_type": self.camera_type,
            "feed_url": self.feed_url,
            "stream_url": self.stream_url,
            "stream_type": self.stream_type,
            "source": self.source,
            "external_url": self.external_url,
        }


class CCTVAggregator:
    """Aggregates CCTV cameras from multiple sources"""
    
    def __init__(self):
        self.cameras: List[CCTVCamera] = []
        self.source_counts = {}
    
    def add_camera(self, camera: CCTVCamera) -> None:
        """Add a camera to the aggregation"""
        self.cameras.append(camera)
        source = camera.source
        self.source_counts[source] = self.source_counts.get(source, 0) + 1
    
    def add_cameras(self, cameras: List[CCTVCamera]) -> None:
        """Add multiple cameras"""
        for camera in cameras:
            self.add_camera(camera)
    
    def get_by_region(self, region: str) -> List[CCTVCamera]:
        """Filter cameras by region"""
        if region.lower() == "all":
            return self.cameras
        
        region_lower = region.lower()
        return [c for c in self.cameras if c.city.lower() == region_lower or c.country.lower() == region_lower]
    
    def get_by_type(self, camera_type: str) -> List[CCTVCamera]:
        """Filter cameras by type (surveillance, port, coastal, maritime)"""
        return [c for c in self.cameras if c.camera_type == camera_type]
    
    def deduplicate(self) -> None:
        """Remove duplicate cameras by URL"""
        seen = set()
        unique = []
        
        for cam in self.cameras:
            key = (cam.feed_url or cam.stream_url or cam.external_url or cam.id)
            if key not in seen:
                seen.add(key)
                unique.append(cam)
        
        self.cameras = unique
    
    def to_geojson(self) -> Dict:
        """Convert to GeoJSON format for map rendering"""
        features = []
        
        for cam in self.cameras:
            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [cam.lng, cam.lat]
                },
                "properties": cam.to_dict()
            }
            features.append(feature)
        
        return {
            "type": "FeatureCollection",
            "features": features
        }
    
    def to_response(self) -> Dict:
        """Convert to API response format"""
        return {
            "cameras": [cam.to_dict() for cam in self.cameras],
            "total": len(self.cameras),
            "sources": self.source_counts,
            "camera_types": self._count_by_type(),
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
    
    def _count_by_type(self) -> Dict[str, int]:
        """Count cameras by type"""
        counts = {}
        for cam in self.cameras:
            cam_type = cam.camera_type
            counts[cam_type] = counts.get(cam_type, 0) + 1
        return counts


async def fetch_cctv_cameras() -> CCTVAggregator:
    """
    Fetch and aggregate CCTV cameras from all sources
    Includes: maritime ports, coastal surveillance, harbor monitoring
    """
    
    aggregator = CCTVAggregator()
    
    logger.info("Starting CCTV camera aggregation...")
    
    # Add sample maritime port cameras
    port_cameras = _get_sample_port_cameras()
    aggregator.add_cameras(port_cameras)
    
    # Add coastal surveillance cameras
    coastal_cameras = _get_sample_coastal_cameras()
    aggregator.add_cameras(coastal_cameras)
    
    # Deduplicate
    aggregator.deduplicate()
    
    logger.info(f"CCTV aggregation complete: {len(aggregator.cameras)} cameras from {len(aggregator.source_counts)} sources")
    
    return aggregator


def _get_sample_port_cameras() -> List[CCTVCamera]:
    """Sample port surveillance cameras from major maritime ports"""
    
    ports = [
        # Caribbean Ports (Counter-narcotics focus)
        CCTVCamera(
            camera_id="port-030001",
            name="Port of Port-au-Prince Terminal 1",
            lat=18.5433,
            lng=-72.2867,
            city="Port-au-Prince",
            country="Haiti",
            camera_type="port",
            stream_type="jpg",
            source="Port Authority of Haiti",
        ),
        CCTVCamera(
            camera_id="port-030002",
            name="Port of Port-au-Prince Terminal 2",
            lat=18.5440,
            lng=-72.2850,
            city="Port-au-Prince",
            country="Haiti",
            camera_type="port",
            stream_type="jpg",
            source="Port Authority of Haiti",
        ),
        
        # Dominican Republic
        CCTVCamera(
            camera_id="port-040001",
            name="Port of Santos de Báez",
            lat=19.2181,
            lng=-70.2050,
            city="Sánchez",
            country="Dominican Republic",
            camera_type="port",
            stream_type="jpg",
            source="Dominican Port Authority",
        ),
        
        # Panama
        CCTVCamera(
            camera_id="port-050001",
            name="Panama Canal Authority - Gatun Locks North",
            lat=9.2827,
            lng=-79.5869,
            city="Gatun",
            country="Panama",
            camera_type="port",
            stream_type="jpg",
            source="Panama Canal Authority",
        ),
        
        # Jamaica
        CCTVCamera(
            camera_id="port-060001",
            name="Kingston Freeport Terminal",
            lat=18.0039,
            lng=-76.8120,
            city="Kingston",
            country="Jamaica",
            camera_type="port",
            stream_type="jpg",
            source="Jamaica Port Authority",
        ),
        
        # Bahamas
        CCTVCamera(
            camera_id="port-070001",
            name="Port of Nassau",
            lat=25.0851,
            lng=-77.3492,
            city="Nassau",
            country="Bahamas",
            camera_type="port",
            stream_type="jpg",
            source="Bahamas Port Authority",
        ),
        
        # Colombia (Pacific)
        CCTVCamera(
            camera_id="port-080001",
            name="Port of Buenaventura",
            lat=3.8851,
            lng=-77.3180,
            city="Buenaventura",
            country="Colombia",
            camera_type="port",
            stream_type="jpg",
            source="Colombian Maritime Authority",
        ),
    ]
    
    return ports


def _get_sample_coastal_cameras() -> List[CCTVCamera]:
    """Sample coastal surveillance cameras from strategic locations"""
    
    coastal = [
        # Caribbean Coast Guard Stations
        CCTVCamera(
            camera_id="coastal-001001",
            name="Hispaniola Strait Watch Station",
            lat=19.7289,
            lng=-72.2852,
            city="Cap-Haïtien",
            country="Haiti",
            camera_type="coastal",
            stream_type="jpg",
            source="Caribbean Coast Guard Network",
        ),
        CCTVCamera(
            camera_id="coastal-001002",
            name="Windward Passage Surveillance",
            lat=19.9442,
            lng=-74.5250,
            city="Guantanamo Bay Area",
            country="Cuba",
            camera_type="coastal",
            stream_type="jpg",
            source="Regional Maritime Surveillance",
        ),
        
        # Dominican Coastline
        CCTVCamera(
            camera_id="coastal-002001",
            name="Northern Coast Surveillance - Puerto Plata",
            lat=19.8013,
            lng=-70.6631,
            city="Puerto Plata",
            country="Dominican Republic",
            camera_type="coastal",
            stream_type="jpg",
            source="Dominican Coastguard",
        ),
        
        # Panama Canal Approaches
        CCTVCamera(
            camera_id="coastal-003001",
            name="Panama Canal Caribbean Entrance",
            lat=9.3522,
            lng=-79.9289,
            city="Colón",
            country="Panama",
            camera_type="coastal",
            stream_type="jpg",
            source="Panama Port Authority",
        ),
        
        # Jamaica Coastline
        CCTVCamera(
            camera_id="coastal-004001",
            name="Montego Bay Harbor Watch",
            lat=18.4892,
            lng=-77.9452,
            city="Montego Bay",
            country="Jamaica",
            camera_type="coastal",
            stream_type="jpg",
            source="Jamaica Maritime Authority",
        ),
        
        # Bahamas Approaches
        CCTVCamera(
            camera_id="coastal-005001",
            name="Bimini Channel Maritime Observation",
            lat=25.7238,
            lng=-79.2965,
            city="Bimini",
            country="Bahamas",
            camera_type="coastal",
            stream_type="jpg",
            source="Bahamas Maritime Authority",
        ),
        
        # Colombia Pacific Coast
        CCTVCamera(
            camera_id="coastal-006001",
            name="Chocó Pacific Coast Surveillance",
            lat=5.8520,
            lng=-77.4050,
            city="Quibdó",
            country="Colombia",
            camera_type="coastal",
            stream_type="jpg",
            source="Colombian Maritime Police",
        ),
    ]
    
    return coastal


async def get_cctv_cameras(region: str = "all") -> Dict:
    """
    Main function to get CCTV cameras
    
    Args:
        region: Filter by region (all, caribbean, panama, etc.)
    
    Returns:
        Dictionary with cameras, totals, and metadata
    """
    aggregator = await fetch_cctv_cameras()
    
    # Filter by region if needed
    if region.lower() != "all":
        cameras = aggregator.get_by_region(region)
        filtered_aggregator = CCTVAggregator()
        filtered_aggregator.add_cameras(cameras)
        return filtered_aggregator.to_response()
    
    return aggregator.to_response()
