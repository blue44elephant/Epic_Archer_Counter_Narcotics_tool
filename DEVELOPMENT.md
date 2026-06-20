# Epic Archer - Development Guide

## Overview

This guide is for developers who want to:
- Set up a local development environment
- Understand the codebase structure
- Make code changes
- Test modifications
- Contribute to the project

---

## Development Setup

### Prerequisites

- **Python 3.11+** ([download](https://www.python.org/downloads/))
- **Git** ([download](https://git-scm.com/))
- **Virtual Environment** (recommended: `venv`)
- **Text Editor/IDE** (VS Code, PyCharm, etc.)

### Step 1: Clone Repository

```bash
git clone https://github.com/blue44elephant/Epic-Archer-Counter-Narcotics-tool-.git
cd "Epic Archer"
```

### Step 2: Create Virtual Environment

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

### Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 4: Configure Environment

Create `.env` file in project root:

```env
COPERNICUS_CLIENT_ID=your-client-id
COPERNICUS_CLIENT_SECRET=your-client-secret
AISSTREAM_API_KEY=your-aisstream-key
EPIC_ARCHER_DATA_DIR=./epic_archer_data
RF_MODEL_PATH=./rf_model.pickle
```

### Step 5: Run Application

```bash
# Development mode (auto-reload on file changes)
uvicorn Epic_Archer:app --reload --port 8000

# Or run direct Python
python Epic_Archer.py
```

Visit **http://localhost:8000** in browser.

---

## Project Structure

```
Epic Archer/
├── Epic_Archer.py              # Main FastAPI application
│   ├── API endpoints (realtime, dark ships, etc.)
│   ├── Data processing pipelines
│   ├── External service integrations
│   └── Frontend static file serving
│
├── ship_tracker.py             # Dark ship detection engine
│   ├── ShipTracker class
│   ├── Haversine distance calculation
│   ├── Dark event detection logic
│   └── Ship state management
│
├── dark_ships_db.py            # Database abstraction layer
│   ├── DarkShipsDatabase class
│   ├── SQLite schema & migrations
│   ├── CRUD operations
│   └── Query builders
│
├── frontend/                   # Web UI
│   ├── index.html             # Markup (Leaflet map, views)
│   ├── app.js                 # Application logic (vanilla JS)
│   └── styles.css             # Tactical design system
│
├── requirements.txt            # Python dependencies
├── Dockerfile                  # Container definition
├── .env                        # Environment variables (NOT committed)
├── .gitignore                  # Git ignore rules
│
├── README.md                   # User guide
├── ARCHITECTURE.md             # System design
├── API_DOCUMENTATION.md        # API reference
├── DATABASE.md                 # Database schema
└── DEVELOPMENT.md              # This file
```

---

## Code Style & Conventions

### Python (PEP 8)

**Naming**:
- Classes: `PascalCase` (e.g., `ShipTracker`, `DarkShipsDatabase`)
- Functions: `snake_case` (e.g., `process_ais_update`, `get_dark_ships`)
- Constants: `UPPER_SNAKE_CASE` (e.g., `DANGER_ZONE_NM`, `DARK_TIMEOUT`)
- Private members: `_leading_underscore` (e.g., `_session`)

**Docstrings**:
```python
def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate distance between two points using Haversine formula.
    
    Args:
        lat1: Starting latitude in degrees
        lon1: Starting longitude in degrees
        lat2: Ending latitude in degrees
        lon2: Ending longitude in degrees
    
    Returns:
        Distance in nautical miles
    
    Example:
        >>> distance = calculate_distance(10.5, -62.3, 11.0, -63.0)
        >>> print(f"{distance:.1f} NM")
        67.2 NM
    """
```

**Type Hints**:
```python
def get_dark_ships(self, limit: int = 100) -> List[Dict[str, Any]]:
    """..."""
```

### JavaScript

**Naming**:
- Classes: `PascalCase` (e.g., `EpicArcherDashboard`)
- Functions: `camelCase` (e.g., `switchView`, `loadDarkShipsLogs`)
- Constants: `UPPER_SNAKE_CASE` (e.g., `MONITORING_RADIUS_NM`)

**Comments**:
```javascript
// Single-line comments for brief explanations
// Use above the code it explains

/*
 * Multi-line comments for complex logic
 * or detailed explanations that need more space
 */
```

---

## Common Development Tasks

### Add New API Endpoint

**Step 1: Define in `Epic_Archer.py`**

```python
from fastapi import FastAPI

@app.get("/api/example-endpoint")
async def example_endpoint(param: str) -> dict:
    """
    Brief description of what this endpoint does.
    """
    try:
        # Your logic here
        result = {"status": "success", "data": param}
        return result
    except Exception as e:
        logger.error(f"Error in example_endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

**Step 2: Test with curl**

```bash
curl http://localhost:8000/api/example-endpoint?param=test
```

**Step 3: Document in `API_DOCUMENTATION.md`**

### Add New Database Table

**Step 1: Add schema to `dark_ships_db.py`**

```python
def _init_db(self):
    """Initialize database schema if it doesn't exist"""
    try:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Add new table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS new_table (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    column_name TEXT NOT NULL,
                    ...
                )
            """)
            
            # Add index
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_new_table_column 
                ON new_table(column_name)
            """)
            
            conn.commit()
```

**Step 2: Add CRUD methods to `DarkShipsDatabase`**

```python
def insert_new_record(self, data: dict) -> int:
    """Insert new record and return ID."""
    with sqlite3.connect(self.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO new_table (column_name, ...) 
            VALUES (?, ...)
        """, (data['value'], ...))
        conn.commit()
        return cursor.lastrowid

def get_new_records(self, filter_by: str) -> List[dict]:
    """Query new records."""
    with sqlite3.connect(self.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM new_table WHERE column = ?", (filter_by,))
        return [dict(row) for row in cursor.fetchall()]
```

**Step 3: Document in `DATABASE.md`**

### Modify Dark Ship Detection Logic

**File**: `ship_tracker.py` → `ShipTracker` class

**Key Methods**:
- `process_ais_update()` — Called on each AIS message
- `check_dark_ships()` — Called periodically to detect dark ships
- `is_in_danger_zone()` — Distance calculation

**Example: Reduce dark timeout to 30 minutes**

```python
# In Epic_Archer.py, where ShipTracker is instantiated
ship_tracker = ShipTracker(
    monitoring_lat=0, 
    monitoring_lon=0,
    danger_zone_nm=200,
    dark_timeout_seconds=1800  # Changed from 3600 (1h) to 1800 (30m)
)
```

### Update Frontend UI

**Files**: 
- `frontend/index.html` — Markup
- `frontend/app.js` — Logic
- `frontend/styles.css` — Styling

**Example: Add new button to Dark Ships view**

```html
<!-- In index.html -->
<button id="new-button" class="btn btn-primary">
    <i class="fas fa-icon"></i> New Feature
</button>
```

```javascript
// In app.js - setupEventListeners()
document.getElementById('new-button')?.addEventListener('click', () => {
    this.handleNewFeature();
});

// Add method to EpicArcherDashboard class
async handleNewFeature() {
    try {
        const response = await fetch('/api/new-endpoint');
        const data = await response.json();
        // Process and display data
    } catch (e) {
        console.error('Error:', e);
    }
}
```

---

## Testing

### Manual Testing

**Dark Ship Detection**:

1. Start application
2. Wait for ships to appear on map
3. Simulate signal loss by:
   - Stopping AIS stream (external)
   - Or manually updating database: `UPDATE tracked_ships SET is_dark = 1 WHERE mmsi = '...'`
4. Verify dark event appears in logs

**API Testing**:

```bash
# Get dark ships
curl http://localhost:8000/api/dark-ships/current

# Get event history
curl http://localhost:8000/api/dark-ships/logs?hours=24

# Get system status
curl http://localhost:8000/api/dark-ships/status
```

### Database Testing

```bash
# Open SQLite shell
sqlite3 epic_archer_data/dark_ships.db

# Check tables
.tables
.schema dark_ship_events

# Query recent events
SELECT * FROM dark_ship_events ORDER BY event_time DESC LIMIT 5;
```

### Frontend Testing

Open browser DevTools (F12):
- **Console**: View JavaScript errors
- **Network**: Monitor API calls
- **Elements**: Inspect HTML/CSS

---

## Debugging

### Enable Debug Logging

```python
# In Epic_Archer.py
logging.basicConfig(level=logging.DEBUG)  # Changed from INFO
```

**Output**:
```
DEBUG: Processing AIS message MMSI 123456789
DEBUG: Distance calculated: 145.2 NM
DEBUG: Ship in danger zone, tracking...
```

### Print Debugging

```python
# Temporary debug prints (remove later!)
print(f"DEBUG: variable_name = {variable_name}")
```

### Breakpoint Debugging (VSCode)

1. Install Python extension
2. Add breakpoint: Click line number in gutter
3. Run with debugger: `F5` (requires `.vscode/launch.json`)

**Example `.vscode/launch.json`**:

```json
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Epic Archer",
            "type": "python",
            "request": "launch",
            "module": "uvicorn",
            "args": ["Epic_Archer:app", "--reload"],
            "jinja": true,
            "justMyCode": true
        }
    ]
}
```

---

## Performance Profiling

### CPU Profiling

```python
import cProfile
import pstats

# Profile a function
pr = cProfile.Profile()
pr.enable()

# ... code to profile ...

pr.disable()
stats = pstats.Stats(pr)
stats.sort_stats('cumulative').print_stats(10)
```

### Memory Profiling

```bash
pip install memory-profiler

python -m memory_profiler Epic_Archer.py
```

---

## Version Control Workflow

### Branch Naming

```
feature/dark-ships-alerts      # New feature
bugfix/distance-calculation    # Bug fix
docs/api-documentation         # Documentation
refactor/database-queries      # Code refactoring
```

### Commit Messages

```
[FEATURE] Add dark ships webhook notifications

- Implement webhook endpoint for dark ship alerts
- Send JSON payload with full ship details
- Add retry logic for failed deliveries

Resolves #42
```

### Pull Request Template

```markdown
## Description
Brief summary of changes

## Type of Change
- [ ] New feature
- [ ] Bug fix
- [ ] Documentation
- [ ] Breaking change

## Testing
How to test this change

## Checklist
- [ ] Code follows style guide
- [ ] Tests pass
- [ ] Documentation updated
```

---

## Dependencies Management

### Current Dependencies

```
fastapi==0.104.0          # Web framework
uvicorn==0.24.0           # ASGI server
requests==2.31.0          # HTTP client
geopandas==0.14.0         # Geospatial analysis
pandas==2.1.0             # Data manipulation
sentinelhub==3.8.0        # Sentinel-2/1 data
osmnx==1.9.0              # OpenStreetMap queries
imageio==2.33.0           # Image processing
numpy==1.24.0             # Numerical computing
shapely==2.0.0            # Geometric operations
python-dotenv==1.0.0      # Environment variables
```

### Adding New Dependency

```bash
# Install
pip install package-name

# Update requirements.txt
pip freeze > requirements.txt

# Commit
git add requirements.txt
git commit -m "Add package-name for feature X"
```

### Removing Dependency

```bash
# Uninstall
pip uninstall package-name

# Update requirements.txt
pip freeze > requirements.txt

# Commit
git add requirements.txt
git commit -m "Remove package-name"
```

---

## Deployment from Development

### Build Docker Image

```bash
docker build -t epic-archer:dev .
```

### Test Docker Image

```bash
docker run -p 8000:8000 --env-file .env epic-archer:dev
```

### Publish to Registry (if applicable)

```bash
docker tag epic-archer:dev myregistry/epic-archer:latest
docker push myregistry/epic-archer:latest
```

---

## Common Issues & Solutions

### Issue: "ModuleNotFoundError: No module named 'dark_ships_db'"

**Solution**: Ensure you're in correct directory and virtual environment activated

```bash
cd "Epic Archer"
source venv/bin/activate  # or: venv\Scripts\activate (Windows)
```

### Issue: Database locked error

**Solution**: Close other processes accessing database

```bash
# Linux
lsof | grep dark_ships.db
kill -9 <PID>

# Windows
taskkill /F /IM python.exe
```

### Issue: AISStream connection fails

**Solution**: Verify API key and internet connection

```bash
# Test connectivity
curl https://stream.aisstream.io/v0/stream
```

### Issue: Slow performance

**Solution**: 
1. Check database indices: `sqlite3 epic_archer_data/dark_ships.db ".indices"`
2. Profile code with cProfile
3. Check system resources (CPU, RAM)

---

## Contributing Guidelines

1. **Fork** the repository
2. **Create** feature branch (`git checkout -b feature/amazing-feature`)
3. **Make** your changes with clear commits
4. **Test** thoroughly (manual + automated)
5. **Document** changes (code comments, README updates)
6. **Push** to your fork
7. **Open** Pull Request with description

### Code Review Checklist

- [ ] Code follows project style guide
- [ ] All tests pass
- [ ] No hardcoded values (use environment variables)
- [ ] Error handling implemented
- [ ] Logging added for debugging
- [ ] Documentation updated
- [ ] No breaking changes (or clearly noted)

---

## Useful Commands

```bash
# Virtual environment
python -m venv venv           # Create
source venv/bin/activate      # Activate (macOS/Linux)
venv\Scripts\activate         # Activate (Windows)
deactivate                    # Deactivate

# Dependencies
pip install -r requirements.txt  # Install all
pip list                         # List installed
pip freeze > requirements.txt    # Update file

# Running
python Epic_Archer.py          # Direct
uvicorn Epic_Archer:app --reload  # Development
uvicorn Epic_Archer:app --port 9000  # Custom port

# Database
sqlite3 epic_archer_data/dark_ships.db  # Open shell
.tables                                  # List tables
.schema table_name                       # Show schema

# Git
git status                     # Check status
git add .                      # Stage all
git commit -m "message"        # Commit
git push                       # Push
git log --oneline              # View history
```

---

## Resources

- **FastAPI Documentation**: https://fastapi.tiangolo.com/
- **SQLite Documentation**: https://www.sqlite.org/docs.html
- **Leaflet.js Documentation**: https://leafletjs.com/
- **Python PEP 8**: https://www.python.org/dev/peps/pep-0008/
- **Git Cheatsheet**: https://education.github.com/git-cheat-sheet-education.pdf

---

**Development Guide Version**: 1.0.0  
**Last Updated**: June 21, 2026
