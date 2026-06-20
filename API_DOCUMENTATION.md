# Epic Archer - API Documentation

## Base URL

```
http://localhost:8000
```

Or wherever your Epic Archer instance is deployed.

---

## Common Response Format

All endpoints return JSON responses with consistent structure:

### Success Response (HTTP 200)
```json
{
  "status": "success",
  "data": { /* endpoint-specific data */ },
  "timestamp": "2026-06-21T15:30:00Z"
}
```

### Error Response (HTTP 4xx/5xx)
```json
{
  "detail": "Error message describing what went wrong"
}
```

---

## Authentication

Most endpoints require **no authentication**. However, sensitive operations may require:
- Environment variable configuration (Copernicus, AISStream keys)
- These are configured server-side only

---

# Dark Ships API Endpoints (NEW)

## Overview

Track vessels that go dark (turn off AIS) within 200 nautical miles of your monitoring area. All dark ship events are logged with full metadata snapshots.

---

## 1. Get Recent Dark Ship Events

**Endpoint**: `GET /api/dark-ships/logs`

**Purpose**: Retrieve recent dark ship events from the last N hours

**Query Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | integer | 100 | Max number of events to return |
| `hours` | integer | 72 | Look back period in hours |

**Example Requests**:

```bash
# Get last 100 events from past 72 hours
GET /api/dark-ships/logs

# Get last 50 events from past 24 hours
GET /api/dark-ships/logs?limit=50&hours=24

# Get detailed history (all events, last 7 days)
GET /api/dark-ships/logs?limit=1000&hours=168
```

**Response Format**:

```json
{
  "count": 5,
  "events": [
    {
      "id": 1,
      "mmsi": "123456789",
      "ship_name": "Ocean Merchant",
      "event_type": "WENT_DARK",
      "event_time": "2026-06-21T15:30:00Z",
      "latitude": 10.5234,
      "longitude": -62.3456,
      "distance_nm": 145.2,
      "ship_details": {
        "callsign": "ABCD123",
        "flag": "Panama",
        "type": "Cargo Ship",
        "size_length": 190,
        "size_beam": 32,
        "draft": 8.5,
        "destination": "Cartagena",
        "status": "Underway",
        "speed_knots": 12.5
      },
      "status": "active",
      "created_at": "2026-06-21T15:30:05Z"
    },
    {
      "id": 2,
      "mmsi": "987654321",
      "ship_name": "Caribbean Runner",
      "event_type": "CAME_ONLINE",
      "event_time": "2026-06-21T15:45:00Z",
      "latitude": 11.2345,
      "longitude": -63.4567,
      "distance_nm": 89.3,
      "ship_details": { /* ... */ },
      "status": "active",
      "created_at": "2026-06-21T15:45:05Z"
    }
  ]
}
```

**Event Types**:

- `WENT_DARK` — Ship stopped transmitting AIS (signal loss)
- `CAME_ONLINE` — Ship resumed transmitting AIS (signal recovery)

**Notes**:
- Ordered by `event_time` (newest first)
- Includes full ship metadata at time of event
- Perfect for historical analysis and audit trails

---

## 2. Get Currently Dark Ships

**Endpoint**: `GET /api/dark-ships/current`

**Purpose**: List all ships currently dark (no AIS signal)

**Query Parameters**: None

**Example Request**:

```bash
GET /api/dark-ships/current
```

**Response Format**:

```json
{
  "count": 3,
  "dark_ships": [
    {
      "mmsi": "123456789",
      "ship_name": "Ocean Merchant",
      "last_seen_time": "2026-06-21T14:30:00Z",
      "last_lat": 10.5234,
      "last_lon": -62.3456,
      "distance_nm": 145.2,
      "is_dark": 1,
      "dark_start_time": "2026-06-21T15:30:00Z",
      "dark_duration_seconds": 3600,
      "dark_duration_formatted": "1h 0m",
      "last_details": {
        "callsign": "ABCD123",
        "flag": "Panama",
        "type": "Cargo Ship",
        "destination": "Cartagena"
      }
    },
    {
      "mmsi": "456789123",
      "ship_name": "Caribbean Trader",
      "last_seen_time": "2026-06-21T15:00:00Z",
      "last_lat": 11.1234,
      "last_lon": -63.2345,
      "distance_nm": 98.5,
      "is_dark": 1,
      "dark_start_time": "2026-06-21T15:15:00Z",
      "dark_duration_seconds": 1800,
      "dark_duration_formatted": "30m",
      "last_details": { /* ... */ }
    }
  ]
}
```

**Response Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `count` | integer | Number of currently dark ships |
| `dark_ships` | array | Array of dark ship records |
| `mmsi` | string | Maritime Mobile Service Identity |
| `dark_duration_seconds` | integer | Seconds since going dark |
| `dark_duration_formatted` | string | Human-readable duration (e.g., "2h 30m") |
| `is_dark` | integer | 1 = dark, 0 = online |

**Use Cases**:
- Display current threats on dashboard
- Alert operators to active dark ships
- Operational decision support

---

## 3. Get Tracking System Status

**Endpoint**: `GET /api/dark-ships/status`

**Purpose**: Get current monitoring configuration and statistics

**Query Parameters**: None

**Example Request**:

```bash
GET /api/dark-ships/status
```

**Response Format**:

```json
{
  "enabled": true,
  "monitoring": {
    "center_lat": 10.5,
    "center_lon": -62.3,
    "radius_nm": 200,
    "dark_timeout_seconds": 3600
  },
  "tracking": {
    "total_tracked": 156,
    "currently_dark": 3,
    "online": 153
  },
  "database": {
    "total_events": 2847,
    "events_24h": 42,
    "events_72h": 127,
    "ships_tracked_ever": 1023
  },
  "system": {
    "uptime_seconds": 604800,
    "last_update": "2026-06-21T15:30:00Z"
  }
}
```

**Response Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `enabled` | boolean | Is dark ships tracking active? |
| `monitoring.radius_nm` | number | Monitoring zone radius in nautical miles |
| `monitoring.dark_timeout_seconds` | number | Timeout before marking ship as dark (default 3600) |
| `tracking.total_tracked` | integer | Ships actively being monitored |
| `tracking.currently_dark` | integer | Ships currently without AIS signal |
| `database.total_events` | integer | Total dark ship events recorded |

**Use Cases**:
- Dashboard status displays
- System health monitoring
- Configuration verification

---

## 4. Get Ship History

**Endpoint**: `GET /api/dark-ships/ship-history`

**Purpose**: Complete event history for a specific ship (all dark/online events)

**Query Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `mmsi` | string | YES | Maritime Mobile Service Identity |

**Example Requests**:

```bash
# Get history for ship MMSI 123456789
GET /api/dark-ships/ship-history?mmsi=123456789
```

**Response Format**:

```json
{
  "mmsi": "123456789",
  "ship_name": "Ocean Merchant",
  "count": 5,
  "first_seen": "2026-06-15T10:30:00Z",
  "last_event": "2026-06-21T15:30:00Z",
  "events": [
    {
      "event_number": 1,
      "event_type": "FIRST_SEEN",
      "event_time": "2026-06-15T10:30:00Z",
      "latitude": 10.5234,
      "longitude": -62.3456,
      "distance_nm": 145.2
    },
    {
      "event_number": 2,
      "event_type": "WENT_DARK",
      "event_time": "2026-06-18T14:20:00Z",
      "latitude": 10.5234,
      "longitude": -62.3456,
      "distance_nm": 145.2,
      "offline_duration_seconds": null
    },
    {
      "event_number": 3,
      "event_type": "CAME_ONLINE",
      "event_time": "2026-06-18T15:45:00Z",
      "latitude": 10.5400,
      "longitude": -62.3300,
      "distance_nm": 146.1,
      "offline_duration_seconds": 5100
    },
    {
      "event_number": 4,
      "event_type": "WENT_DARK",
      "event_time": "2026-06-21T13:00:00Z",
      "latitude": 10.5234,
      "longitude": -62.3456,
      "distance_nm": 145.2
    },
    {
      "event_number": 5,
      "event_type": "CAME_ONLINE",
      "event_time": "2026-06-21T15:30:00Z",
      "latitude": 10.5450,
      "longitude": -62.3100,
      "distance_nm": 145.8,
      "offline_duration_seconds": 9000
    }
  ],
  "statistics": {
    "total_dark_events": 2,
    "total_online_events": 2,
    "average_offline_duration_seconds": 7050,
    "longest_offline_duration_seconds": 9000,
    "darkest_time_period": "2026-06-21T13:00:00Z to 2026-06-21T15:30:00Z"
  }
}
```

**Use Cases**:
- Investigate specific vessel behavior
- Pattern analysis (recurrent dark episodes)
- Audit trails for enforcement
- Evidence collection

---

## 5. Update Monitoring Area

**Endpoint**: `POST /api/dark-ships/monitoring-area`

**Purpose**: Change the monitoring center and/or radius

**Query Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `lat` | float | YES | New center latitude |
| `lon` | float | YES | New center longitude |
| `radius_nm` | float | NO | New radius in nautical miles (default 200) |

**Example Requests**:

```bash
# Change monitoring center to Port of Cartagena (10.5°N, 62.3°W), 200 NM radius
POST /api/dark-ships/monitoring-area?lat=10.5&lon=-62.3&radius_nm=200

# Change center only (keep existing radius)
POST /api/dark-ships/monitoring-area?lat=11.0&lon=-63.0
```

**Response Format**:

```json
{
  "status": "success",
  "monitoring": {
    "center_lat": 10.5,
    "center_lon": -62.3,
    "radius_nm": 200
  },
  "message": "Monitoring area updated successfully"
}
```

**Notes**:
- Changes apply immediately to new AIS updates
- Existing tracked ships remain in database
- Useful for dynamic operational areas

---

# Real-time Data Endpoints

## 6. Get Live Ships

**Endpoint**: `GET /api/realtime/ships`

**Purpose**: Real-time AIS ship positions in a bounding box

**Query Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `min_lat` | float | YES | Minimum latitude |
| `min_lon` | float | YES | Minimum longitude |
| `max_lat` | float | YES | Maximum latitude |
| `max_lon` | float | YES | Maximum longitude |
| `sample_seconds` | integer | NO | Data sample period (default 8s) |
| `max_items` | integer | NO | Max ships to return (default 500) |

**Example Request**:

```bash
GET /api/realtime/ships?min_lat=10.0&min_lon=-63.0&max_lat=11.0&max_lon=-62.0
```

**Response Format**:

```json
{
  "source": "AISStream",
  "sample_seconds": 8.3,
  "count": 42,
  "items": [
    {
      "id": "123456789",
      "mmsi": 123456789,
      "name": "Ocean Merchant",
      "callsign": "ABCD123",
      "flag": "Panama",
      "type": "Cargo Ship",
      "size_length": 190,
      "size_beam": 32,
      "draft": 8.5,
      "destination": "Cartagena",
      "status": "Underway",
      "lat": 10.5234,
      "lon": -62.3456,
      "speed_knots": 12.5,
      "course": 180.0,
      "timestamp": "2026-06-21T15:30:00Z"
    },
    { /* more ships... */ }
  ],
  "dark_events": [
    {
      "mmsi": 456789123,
      "event_type": "WENT_DARK",
      "event_time": "2026-06-21T15:30:00Z"
    }
  ]
}
```

---

## 7. Get Live Aircraft

**Endpoint**: `GET /api/realtime/aircraft`

**Purpose**: Real-time aircraft positions in a bounding box

**Query Parameters**: Same as ships endpoint

**Response Format**: Similar to ships, but with aircraft-specific data

---

# Health & Status Endpoints

## 8. Health Check

**Endpoint**: `GET /health`

**Purpose**: Simple health check for monitoring

**Response**:

```json
{
  "status": "healthy",
  "timestamp": "2026-06-21T15:30:00Z"
}
```

---

# Error Handling

## HTTP Status Codes

| Code | Meaning | Example |
|------|---------|---------|
| 200 | OK | Request succeeded |
| 400 | Bad Request | Missing/invalid parameters |
| 404 | Not Found | Endpoint doesn't exist |
| 500 | Server Error | Unexpected server error |
| 502 | Bad Gateway | External service unavailable (AISStream, Copernicus) |

## Error Response Example

```json
{
  "detail": "AISStream connection failed: timeout"
}
```

---

# Rate Limiting

**Current**: No explicit rate limiting

**Recommended for Production**:
- 100 requests per minute per IP
- 1000 requests per minute per authenticated user

---

# Usage Examples

### Example 1: Monitor Dark Ships Every 30 Seconds

```javascript
setInterval(async () => {
  const response = await fetch('/api/dark-ships/current');
  const data = await response.json();
  
  if (data.count > 0) {
    console.log(`⚠️ ${data.count} dark ships detected!`);
    data.dark_ships.forEach(ship => {
      console.log(`${ship.ship_name} (MMSI: ${ship.mmsi}) - Dark for ${ship.dark_duration_formatted}`);
    });
  }
}, 30000);
```

### Example 2: Get Complete Ship History

```bash
curl "http://localhost:8000/api/dark-ships/ship-history?mmsi=123456789" | jq
```

### Example 3: Change Monitoring Area via cURL

```bash
curl -X POST "http://localhost:8000/api/dark-ships/monitoring-area?lat=15.2&lon=-61.5&radius_nm=250"
```

### Example 4: Python Integration

```python
import requests

# Get recent dark ship events
response = requests.get(
    'http://localhost:8000/api/dark-ships/logs',
    params={'limit': 50, 'hours': 24}
)
events = response.json()

for event in events['events']:
    print(f"{event['ship_name']} went dark at {event['event_time']}")
```

---

# API Changelog

## Version 1.0.0 (June 21, 2026)

### New Endpoints
- ✅ `/api/dark-ships/logs` — Event history
- ✅ `/api/dark-ships/current` — Currently dark ships
- ✅ `/api/dark-ships/status` — System status
- ✅ `/api/dark-ships/ship-history` — Individual ship history
- ✅ `/api/dark-ships/monitoring-area` — Update monitoring zone

### Features
- Dark ship event logging with metadata snapshots
- Haversine-based distance calculations
- 1-hour configurable dark timeout
- SQLite persistence

---

**API Version**: 1.0.0  
**Last Updated**: June 21, 2026
