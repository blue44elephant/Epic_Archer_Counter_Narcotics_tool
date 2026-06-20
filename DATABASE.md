# Epic Archer - Database Documentation

## Overview

Epic Archer uses **SQLite** for persistent storage of dark ship events and tracking metadata. SQLite was chosen for:

- ✅ Zero configuration (no server needed)
- ✅ Portable (single file database)
- ✅ Sufficient for 100K+ events
- ✅ ACID compliance for data integrity
- ✅ Fast queries with proper indexing

**Database Location**: `{EPIC_ARCHER_DATA_DIR}/dark_ships.db` (default: `./epic_archer_data/dark_ships.db`)

---

## Database Schema

### Table 1: `dark_ship_events`

Immutable audit log of all dark ship detection events.

```sql
CREATE TABLE dark_ship_events (
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
```

#### Columns

| Column | Type | Nullable | Purpose | Example |
|--------|------|----------|---------|---------|
| `id` | INTEGER | NO | Auto-incrementing primary key | 1, 2, 3, ... |
| `mmsi` | TEXT | NO | Maritime Mobile Service Identity (9-digit ship ID) | "123456789" |
| `ship_name` | TEXT | YES | Vessel name | "Ocean Merchant" |
| `event_type` | TEXT | NO | Type of event: `WENT_DARK` or `CAME_ONLINE` | "WENT_DARK" |
| `event_time` | TIMESTAMP | NO | When the event occurred (ISO 8601) | "2026-06-21T15:30:00Z" |
| `latitude` | REAL | NO | Last known position latitude | 10.5234 |
| `longitude` | REAL | NO | Last known position longitude | -62.3456 |
| `distance_nm` | REAL | YES | Distance from monitoring center (nautical miles) | 145.2 |
| `ship_details` | TEXT | YES | Full metadata as JSON (callsign, flag, type, etc.) | `{"callsign": "ABCD123", "flag": "Panama", ...}` |
| `status` | TEXT | NO | Status code: `active`, `archived`, `investigated` | "active" |
| `created_at` | TIMESTAMP | NO | When record was created (for audit) | "2026-06-21T15:30:05Z" |

#### Indices

```sql
-- Fast queries by MMSI (to find all events for one ship)
CREATE INDEX idx_dark_ships_mmsi ON dark_ship_events(mmsi)

-- Fast queries by time range (to get recent events)
CREATE INDEX idx_dark_ships_event_time ON dark_ship_events(event_time)
```

#### Example Records

```sql
-- Ship going dark
INSERT INTO dark_ship_events 
VALUES (
  1,
  "123456789",
  "Ocean Merchant",
  "WENT_DARK",
  "2026-06-21T15:30:00Z",
  10.5234,
  -62.3456,
  145.2,
  '{"callsign": "ABCD123", "flag": "Panama", "type": "Cargo Ship", "destination": "Cartagena"}',
  "active",
  "2026-06-21T15:30:05Z"
);

-- Ship coming back online
INSERT INTO dark_ship_events
VALUES (
  2,
  "123456789",
  "Ocean Merchant",
  "CAME_ONLINE",
  "2026-06-21T17:30:00Z",
  10.5450,
  -62.3100,
  145.8,
  '{"callsign": "ABCD123", "flag": "Panama", "type": "Cargo Ship", "destination": "Cartagena"}',
  "active",
  "2026-06-21T17:30:05Z"
);
```

---

### Table 2: `tracked_ships`

Current state of all ships being monitored. Updates in real-time with each AIS update.

```sql
CREATE TABLE tracked_ships (
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
```

#### Columns

| Column | Type | Nullable | Purpose | Example |
|--------|------|----------|---------|---------|
| `mmsi` | TEXT | NO | Primary key - Maritime Mobile Service Identity | "123456789" |
| `ship_name` | TEXT | YES | Current vessel name | "Ocean Merchant" |
| `last_seen_time` | TIMESTAMP | NO | When we last received AIS from this ship | "2026-06-21T15:30:00Z" |
| `last_lat` | REAL | NO | Current/last known latitude | 10.5234 |
| `last_lon` | REAL | NO | Current/last known longitude | -62.3456 |
| `last_details` | TEXT | YES | Current metadata as JSON | `{"callsign": "ABCD123", ...}` |
| `is_dark` | INTEGER | NO | 1 if dark (no AIS), 0 if online (has AIS) | 1 |
| `dark_start_time` | TIMESTAMP | YES | When ship went dark (null if online) | "2026-06-21T15:30:00Z" |
| `distance_nm` | REAL | YES | Current distance from monitoring center | 145.2 |
| `tracking_since` | TIMESTAMP | NO | When we started tracking this ship | "2026-06-15T10:30:00Z" |

#### Example Records

```sql
-- Ship currently ONLINE
INSERT INTO tracked_ships
VALUES (
  "123456789",
  "Ocean Merchant",
  "2026-06-21T15:30:00Z",
  10.5234,
  -62.3456,
  '{"callsign": "ABCD123", ...}',
  0,
  NULL,
  145.2,
  "2026-06-15T10:30:00Z"
);

-- Ship currently DARK
INSERT INTO tracked_ships
VALUES (
  "987654321",
  "Caribbean Runner",
  "2026-06-21T13:00:00Z",
  11.2345,
  -63.4567,
  '{"callsign": "XYZ789", ...}',
  1,
  "2026-06-21T13:00:00Z",
  89.3,
  "2026-06-18T08:15:00Z"
);
```

---

## Data Types Explanation

### TIMESTAMP Format

All timestamps use **ISO 8601 UTC format**:
```
2026-06-21T15:30:00Z
└─ YYYY-MM-DD (date)
   └─ T (separator)
      └─ HH:MM:SS (time in 24-hour)
         └─ Z (UTC indicator)
```

SQLite stores as UTC; client reads/interprets time zone.

### JSON Format in `ship_details` and `last_details`

Complete ship metadata snapshot at time of event:

```json
{
  "callsign": "ABCD123",
  "flag": "Panama",
  "type": "Cargo Ship",
  "size_length": 190,
  "size_beam": 32,
  "draft": 8.5,
  "destination": "Cartagena",
  "status": "Underway",
  "speed_knots": 12.5
}
```

---

## Common Queries

### Get All Dark Ships

```sql
SELECT * FROM tracked_ships WHERE is_dark = 1;
```

**Result**: Ships with no AIS signal currently

### Get Recent Events (Last 72 Hours)

```sql
SELECT * FROM dark_ship_events
WHERE event_time > datetime('now', '-72 hours')
ORDER BY event_time DESC
LIMIT 100;
```

**Result**: Last 100 events from past 3 days

### Find All Events for a Specific Ship

```sql
SELECT * FROM dark_ship_events
WHERE mmsi = '123456789'
ORDER BY event_time DESC;
```

**Result**: Complete history for MMSI 123456789

### Calculate Average Dark Duration

```sql
SELECT 
  mmsi,
  ship_name,
  COUNT(*) as dark_events,
  AVG(
    (SELECT 
      strftime('%s', came_online.event_time) - 
      strftime('%s', went_dark.event_time)
    FROM dark_ship_events as went_dark
    JOIN dark_ship_events as came_online
    ON went_dark.mmsi = came_online.mmsi
    WHERE went_dark.event_type = 'WENT_DARK'
    AND came_online.event_type = 'CAME_ONLINE'
    AND came_online.event_time > went_dark.event_time
    ORDER BY came_online.event_time ASC
    LIMIT 1)
  ) as avg_offline_seconds
FROM dark_ship_events
WHERE event_type = 'WENT_DARK'
GROUP BY mmsi
ORDER BY dark_events DESC;
```

**Result**: Ships ranked by frequency of dark events

### Ships Currently Dark Over N Hours

```sql
SELECT 
  mmsi,
  ship_name,
  dark_start_time,
  CAST(
    (strftime('%s', 'now') - strftime('%s', dark_start_time)) / 3600.0 
    AS INTEGER
  ) as hours_dark
FROM tracked_ships
WHERE is_dark = 1
AND (strftime('%s', 'now') - strftime('%s', dark_start_time)) > 3600
ORDER BY hours_dark DESC;
```

**Result**: Ships dark for more than 1 hour

### Event Timeline for Ship

```sql
SELECT 
  event_number,
  event_type,
  event_time,
  latitude,
  longitude,
  distance_nm,
  CASE 
    WHEN event_type = 'CAME_ONLINE' THEN
      (SELECT strftime('%s', event_time) - strftime('%s', MAX(event_time))
       FROM dark_ship_events AS prev
       WHERE prev.mmsi = dark_ship_events.mmsi
       AND prev.event_type = 'WENT_DARK'
       AND prev.event_time < dark_ship_events.event_time) / 60.0
    ELSE NULL
  END as offline_minutes
FROM (
  SELECT 
    ROW_NUMBER() OVER (PARTITION BY mmsi ORDER BY event_time) as event_number,
    *
  FROM dark_ship_events
)
WHERE mmsi = '123456789'
ORDER BY event_time ASC;
```

**Result**: Timeline showing duration offline between events

---

## Maintenance Operations

### Backup Database

```bash
# Copy database file
cp epic_archer_data/dark_ships.db epic_archer_data/dark_ships.db.backup.$(date +%Y%m%d_%H%M%S)
```

### Check Database Integrity

```bash
sqlite3 epic_archer_data/dark_ships.db "PRAGMA integrity_check;"
```

**Expected output**: `ok`

### Optimize Database

```bash
sqlite3 epic_archer_data/dark_ships.db "VACUUM;"
```

(Reclaims space from deleted records)

### Purge Old Events

```sql
-- Delete events older than 1 year
DELETE FROM dark_ship_events 
WHERE event_time < datetime('now', '-1 year');

-- Vacuum to reclaim space
VACUUM;
```

### Archive Events to CSV

```bash
sqlite3 epic_archer_data/dark_ships.db <<EOF
.mode csv
.output events_export.csv
SELECT * FROM dark_ship_events WHERE event_time > datetime('now', '-30 days');
EOF
```

---

## Performance Characteristics

### Query Performance

| Query | Index | Time | Notes |
|-------|-------|------|-------|
| Get by MMSI | `idx_dark_ships_mmsi` | ~10ms | Fast single ship queries |
| Get by date range | `idx_dark_ships_event_time` | ~50ms | Fast time window queries |
| Get dark ships | No index needed | ~20ms | Full table scan (usually small set) |
| Insert event | N/A | ~50ms | Includes metadata JSON |
| Update ship state | Primary key | ~30ms | Very fast |

### Database Size

- **Per event**: ~500 bytes (with JSON metadata)
- **100,000 events**: ~50 MB
- **1,000,000 events**: ~500 MB

### Scaling Limits (SQLite)

- **Practical limit**: 1-2 million records
- **Sweet spot**: < 500K events (< 250 MB)
- **For larger scale**: Consider PostgreSQL migration

---

## Migration to PostgreSQL (Future)

For production deployments with high volume:

```sql
-- PostgreSQL equivalent schema
CREATE TABLE dark_ship_events (
    id SERIAL PRIMARY KEY,
    mmsi VARCHAR(20) NOT NULL,
    ship_name VARCHAR(100),
    event_type VARCHAR(20) NOT NULL,
    event_time TIMESTAMP NOT NULL,
    latitude DECIMAL(10, 6) NOT NULL,
    longitude DECIMAL(10, 6) NOT NULL,
    distance_nm DECIMAL(10, 2),
    ship_details JSONB,
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_dark_ships_mmsi ON dark_ship_events(mmsi);
CREATE INDEX idx_dark_ships_event_time ON dark_ship_events(event_time);
```

**Benefits**:
- Unlimited scale
- Better concurrent access
- Advanced features (JSONB, partitioning)
- Connection pooling (pgBouncer)

---

## Data Privacy & Security

### What's Stored
- Ship MMSI (public maritime identifier)
- Ship name (public)
- Position data (tactical intelligence)
- Ship metadata (public AIS data)
- Timestamps (operational data)

### Sensitivity
- **Not encrypted** by default (SQLite limitation)
- **Recommendation**: Use host OS encryption (BitLocker, FileVault)
- **Production**: Encrypt database file + restrict access

### Retention Policy (Recommended)
- Keep data for 1 year minimum (investigation/audit)
- Archive data older than 2 years
- Delete after 5 years (unless ongoing investigation)

---

## Backup Strategy

### Automated Backup (Recommended)

```bash
#!/bin/bash
# backup_dark_ships.sh
BACKUP_DIR="/backups/epic-archer"
DB_FILE="/path/to/epic_archer_data/dark_ships.db"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR
cp $DB_FILE $BACKUP_DIR/dark_ships.db.$TIMESTAMP

# Keep only last 30 days of backups
find $BACKUP_DIR -name "dark_ships.db.*" -mtime +30 -delete
```

**Schedule**: Daily via cron (e.g., 2 AM)

### Manual Backup

```bash
cp epic_archer_data/dark_ships.db epic_archer_data/dark_ships.db.backup
```

---

## Troubleshooting

### Database Locked Error

**Problem**: "database is locked"

**Cause**: Multiple processes accessing database simultaneously

**Solution**:
1. Increase SQLite timeout: `PRAGMA busy_timeout = 5000;`
2. Consider PostgreSQL for multi-process access
3. Restart application

### Large Database Size

**Problem**: `dark_ships.db` exceeds 1 GB

**Solution**:
1. Archive old events to CSV
2. Delete events older than N years
3. Run VACUUM to reclaim space
4. Consider PostgreSQL with partitioning

### Query Slowness

**Problem**: Queries running slowly

**Solution**:
1. Check index usage: `EXPLAIN QUERY PLAN ...`
2. Rebuild indices: `REINDEX;`
3. Update statistics: `ANALYZE;`
4. Consider query optimization

---

## Example: Building a Dark Ship Report

```python
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

db_path = Path("epic_archer_data/dark_ships.db")
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row  # Return rows as dicts
cursor = conn.cursor()

# Get events from last 7 days
seven_days_ago = (datetime.now() - timedelta(days=7)).isoformat()

cursor.execute("""
SELECT * FROM dark_ship_events 
WHERE event_time > ? 
ORDER BY event_time DESC
""", (seven_days_ago,))

events = cursor.fetchall()

# Generate report
print("=" * 80)
print(f"Dark Ships Event Report - Last 7 Days")
print("=" * 80)

for event in events:
    print(f"\n{event['ship_name']} (MMSI: {event['mmsi']})")
    print(f"  Event: {event['event_type']} at {event['event_time']}")
    print(f"  Position: {event['latitude']:.4f}, {event['longitude']:.4f}")
    print(f"  Distance: {event['distance_nm']:.1f} NM")

# Summary statistics
cursor.execute("""
SELECT 
  COUNT(*) as total_events,
  COUNT(DISTINCT mmsi) as unique_ships,
  COUNT(CASE WHEN event_type = 'WENT_DARK' THEN 1 END) as went_dark,
  COUNT(CASE WHEN event_type = 'CAME_ONLINE' THEN 1 END) as came_online
FROM dark_ship_events
WHERE event_time > ?
""", (seven_days_ago,))

stats = cursor.fetchone()
print(f"\n\nSummary Statistics:")
print(f"  Total Events: {stats['total_events']}")
print(f"  Unique Ships: {stats['unique_ships']}")
print(f"  Went Dark: {stats['went_dark']}")
print(f"  Came Online: {stats['came_online']}")

conn.close()
```

---

**Database Version**: 1.0.0  
**Last Updated**: June 21, 2026
