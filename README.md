# Epic Archer - Counter-Narcotics Intelligence Tool

A multi-sensor tactical intelligence platform for real-time monitoring of maritime activity, featuring dark ship detection (AIS signal loss tracking) and satellite imagery analysis for counter-narcotics operations.

## Features

✅ **Real-time Ship Tracking** — Live AIS data from AISStream  
✅ **Dark Ship Detection** — Alert when vessels within 200 NM go offline (AIS signal loss)  
✅ **Event Logging** — Full metadata snapshots when ships go dark/come online  
✅ **Satellite Imagery** — Copernicus multispectral analysis for site detection  
✅ **Web Dashboard** — Interactive map with tactical analysis tools  
✅ **Docker Ready** — Containerized for instant deployment  

## Upcoming Features (2026-2028)
🎯**Boonidhi API Support** — API plugin option for ISRO's Boonidhi applications

🎯**Integration for open/compromised cameras** — IP Cameras that are left exposed to the internet are made visible on a map allowing for monitoring areas of interest. Users can also add their own cameras, or any cameras they have access to.

🎯**ALPR Integration** — Integrates ALPR, including API support from platerecognizer.com or in the form of local models

🎯**Narcotics/Weapons Smuggling Route Prediction** — Predict most likely route to be used between two cities based on user-entered parameters such as road conditions, police/security presence, corruption, etc. based on priorities such as stealth and speed. 

---

## Documentation Index

**Start here based on your role:**

| Role | Documents | Purpose |
|------|-----------|---------|
| **End User** | [README.md](README.md) (this file) | How to install and use Epic Archer |
| **System Admin** | [DOCKER_DEPLOY.md](DOCKER_DEPLOY.md) | Docker deployment guide |
| **Developer** | [DEVELOPMENT.md](DEVELOPMENT.md) | Setup dev environment & contribute |
| **API Consumer** | [API_DOCUMENTATION.md](API_DOCUMENTATION.md) | Complete API reference |
| **Architect** | [ARCHITECTURE.md](ARCHITECTURE.md) | System design & data flows |
| **Database Admin** | [DATABASE.md](DATABASE.md) | Schema, queries, maintenance |
| **Troubleshooting** | [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Common issues & solutions |

### Quick Links

- 🚀 [Quick Start](#getting-started) — 5-minute setup
- 🐳 [Docker Deployment](DOCKER_DEPLOY.md) — Run in container
- 🔌 [API Endpoints](API_DOCUMENTATION.md#dark-ships-api-endpoints-new) — Dark ships API
- 🏗️ [System Architecture](ARCHITECTURE.md) — How it works
- 💻 [Development Setup](DEVELOPMENT.md) — Contribute code
- 🗄️ [Database Schema](DATABASE.md) — Dark ships database
- 🔧 [Troubleshooting](TROUBLESHOOTING.md) — Common issues

---

## Getting Started

### Prerequisites

You need **2 API Keys** from external services:

1. **Copernicus Data Space** (Satellite Imagery)
2. **AISStream** (Real-time Ship Data)

Both are **free** to register.

---

## Step 1: Get Your API Keys

### 1a. Copernicus Data Space (For Satellite Imagery)

1. Visit: https://dataspace.copernicus.eu/
2. Click **"Register"** (top right)
3. Create account with email/password
4. Log in → Go to **"User Settings"** → **"Applications"**
5. Click **"Create New Application"**
6. Fill in:
   - **Application Name**: `Epic Archer`
   - **Description**: `Counter-narcotics intelligence platform`
   - Check all permission boxes
   - Click **"Create Application"**
7. You'll see:
   - **Client ID** (copy this)
   - **Client Secret** (copy this)

### 1b. AISStream (For Ship Tracking)

1. Visit: https://www.aisstream.io/
2. Click **"Sign Up"** (top right)
3. Create account with email/password
4. Log in → Go to **"Your Profile"** → **"API Key"**
5. Copy your **API Key**

---

## Step 2: Configure Environment Variables

### Create `.env` File

In the Epic Archer project root directory, create a file named `.env` with:

```env
# Copernicus Data Space Credentials
COPERNICUS_CLIENT_ID=your-client-id-here
COPERNICUS_CLIENT_SECRET=your-client-secret-here

# AISStream API Key
AISSTREAM_API_KEY=your-aisstream-key-here

# Data Storage
EPIC_ARCHER_DATA_DIR=./epic_archer_data
RF_MODEL_PATH=./rf_model.pickle
```

**Replace:**
- `your-client-id-here` → Your actual Copernicus Client ID
- `your-client-secret-here` → Your actual Copernicus Client Secret
- `your-aisstream-key-here` → Your actual AISStream API Key

**Example (REAL VALUES ONLY):**
```env
COPERNICUS_CLIENT_ID=a1b2c3d4-e5f6-7890-abcd-ef1234567890
COPERNICUS_CLIENT_SECRET=SecureSecretKey123!@#
AISSTREAM_API_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
EPIC_ARCHER_DATA_DIR=./epic_archer_data
RF_MODEL_PATH=./rf_model.pickle
```

### Alternative: Using the Template

Alternatively, copy the included `.env.example` template:

```bash
# Copy the template
cp .env.example .env

# Edit .env and fill in your credentials
# Your .env stays local (protected by .gitignore)
```

The `.env.example` file is checked into git and shows all required configuration options. This approach is convenient for new users.

---

## Step 3: Choose Your Deployment Method

### Option A: Docker Deployment (Recommended)

#### Prerequisites
- Install Docker Desktop: https://www.docker.com/products/docker-desktop
- Windows/Mac: Download and install
- Linux: `sudo apt-get install docker.io`

#### Deploy on Docker

1. **Build the Docker image:**
   ```bash
   docker build -t epic-archer:latest .
   ```
   *First build takes 3-5 minutes; subsequent builds are faster*

2. **Run the container:**
   ```bash
   docker run -p 8000:8000 --env-file .env epic-archer:latest
   ```

3. **Open in browser:**
   - Navigate to: **http://localhost:8000**

4. **Stop the container:**
   - Press `Ctrl+C` in terminal

#### Docker Commands Reference

```bash
# Build image
docker build -t epic-archer:latest .

# Run container (foreground)
docker run -p 8000:8000 --env-file .env epic-archer:latest

# Run container (background/detached)
docker run -d -p 8000:8000 --env-file .env --name epic-archer epic-archer:latest

# View running containers
docker ps

# View logs
docker logs epic-archer

# Stop container
docker stop epic-archer

# Remove container
docker rm epic-archer

# Remove image
docker rmi epic-archer:latest
```

---

### Option B: Local Deployment (Development)

#### Prerequisites
- Python 3.11+
- pip (Python package manager)
- Git

#### Deploy Locally

1. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Run the application:**
   ```bash
   uvicorn Epic_Archer:app --reload --host 0.0.0.0 --port 8000
   ```

3. **Open in browser:**
   - Navigate to: **http://localhost:8000**

4. **Stop the application:**
   - Press `Ctrl+C` in terminal

#### Local Commands Reference

```bash
# Install dependencies
pip install -r requirements.txt

# Run with auto-reload (development)
uvicorn Epic_Archer:app --reload

# Run in production mode
uvicorn Epic_Archer:app --host 0.0.0.0 --port 8000 --workers 4

# Run direct Python
python Epic_Archer.py
```

---

## Using the Application

### Dashboard Navigation

Once running at http://localhost:8000:

1. **Operations (Dashboard)**
   - View real-time ship positions on interactive map
   - Search locations
   - Toggle between satellite and standard basemap
   - Enable live aircraft/ships tracking

2. **Tactical Trends**
   - Historical detection analysis
   - Date range filtering
   - Trend visualization

3. **Dark Ships Event Log** ⭐ NEW
   - Currently dark ships within 200 NM
   - Event history (72-hour window)
   - Tracking status and monitoring parameters
   - Full ship metadata snapshots

4. **Copernicus Link**
   - Configure credentials
   - Test connection status

### Dark Ships Feature

The dark ships feature **automatically detects** when ships within 200 nautical miles lose their AIS signal:

- **Detection**: Continuous monitoring via AISStream
- **Logging**: Database records with full metadata
- **Alerts**: View in "Dark Ships Event Log"
- **Events Tracked**:
  - `WENT_DARK` — Ship stopped transmitting AIS
  - `CAME_ONLINE` — Ship resumed transmitting AIS

---

## Environment Variables Explained

| Variable | Purpose | Required |
|----------|---------|----------|
| `COPERNICUS_CLIENT_ID` | Authenticate with Copernicus API | Yes |
| `COPERNICUS_CLIENT_SECRET` | Authenticate with Copernicus API | Yes |
| `AISSTREAM_API_KEY` | Authenticate with AISStream WebSocket | Yes |
| `EPIC_ARCHER_DATA_DIR` | Where to store dark ship logs database | No (default: `./epic_archer_data`) |
| `RF_MODEL_PATH` | Path to random forest model | No (default: `./rf_model.pickle`) |

---

## Troubleshooting

### Docker Issues

**Container won't start:**
```bash
# Check logs
docker logs epic-archer

# Rebuild without cache
docker build --no-cache -t epic-archer:latest .
```

**Port 8000 already in use:**
```bash
# Use different port
docker run -p 9000:8000 --env-file .env epic-archer:latest
# Then access: http://localhost:9000
```

### API Errors

**"Invalid credentials" error:**
- Verify `.env` file has correct Client ID and Secret
- Check Copernicus credentials at: https://dataspace.copernicus.eu/user-settings/applications
- Regenerate credentials if needed

**"AIS data unavailable" error:**
- Verify AISStream API key is correct
- Check: https://www.aisstream.io/account/api-key
- Ensure you have internet connection

**Database errors:**
- Delete `epic_archer_data/` folder
- Restart application (will create fresh database)

### Performance

**Application running slow:**
- For Docker: Increase CPU/Memory allocation in Docker Desktop settings
- For local: Run fewer background processes
- Check system resources: `Task Manager` (Windows) or `Activity Monitor` (Mac)

---

## File Structure

```
Epic Archer/
├── Epic_Archer.py              # Main FastAPI application
├── ship_tracker.py             # Dark ship detection logic
├── dark_ships_db.py            # Database module for logs
├── requirements.txt            # Python dependencies
├── Dockerfile                  # Docker container definition
├── DOCKER_DEPLOY.md            # Extended Docker guide
├── rf_model.pickle             # ML model for site detection (~102 MB)
├── .env                        # Environment variables (NEVER commit)
├── .dockerignore               # Files to exclude from Docker
├── frontend/                   # Web dashboard
│   ├── index.html             # Main page
│   ├── app.js                 # Dashboard logic
│   └── styles.css             # Styling
└── epic_archer_data/          # Created at runtime
    └── dark_ships.db          # Dark ship event logs (SQLite)
```

---

## Security Notes

⚠️ **IMPORTANT:**

1. **Never commit `.env`** — It contains your API keys
2. **Never share your credentials** — They can be used by others
3. **Keep `.env` local only** — Only on your machine/server
4. **Rotate keys regularly** — Change credentials every 3-6 months
5. **Use `.gitignore`** — If committing to GitHub, ensure `.env` is ignored

---

## Development

### Running Tests

```bash
# Unit tests
pytest tests/

# With coverage
pytest --cov=. tests/
```

### Code Changes

1. **Local Development:**
   ```bash
   uvicorn Epic_Archer:app --reload
   ```
   Auto-reloads on file changes

2. **Docker Development:**
   ```bash
   docker run -v $(pwd):/app -p 8000:8000 --env-file .env epic-archer:latest
   ```
   Volume mount for live code updates

---

## API Endpoints

### Dark Ships Endpoints

```
GET  /api/dark-ships/logs?limit=100&hours=72
     Get recent dark ship events

GET  /api/dark-ships/current
     Get currently dark ships

GET  /api/dark-ships/status
     Get tracking system status

GET  /api/dark-ships/ship-history?mmsi=123456789
     Get event history for specific ship

POST /api/dark-ships/monitoring-area?lat=0&lon=0&radius_nm=200
     Update monitoring center/radius
```

### Other Endpoints

```
GET  /health
     Application health check

GET  /api/realtime/ships?min_lat=X&min_lon=Y&max_lat=X&max_lon=Y
     Real-time ship data

GET  /api/realtime/aircraft?min_lat=X&min_lon=Y&max_lat=X&max_lon=Y
     Real-time aircraft data
```

---

## Support & Issues

- **GitHub Issues**: https://github.com/blue44elephant/Epic-Archer-Counter-Narcotics-tool-/issues
- **Documentation**: See DOCKER_DEPLOY.md for extended Docker guide

---

## Full Documentation

### Core Documentation

| Document | Purpose | Audience |
|----------|---------|----------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | System design, components, data flows | Architects, DevOps |
| [API_DOCUMENTATION.md](API_DOCUMENTATION.md) | Complete API reference with examples | Developers, API consumers |
| [DATABASE.md](DATABASE.md) | Database schema, queries, maintenance | Database admins, developers |
| [DEVELOPMENT.md](DEVELOPMENT.md) | Development setup, contribution guide | Contributors, developers |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Common issues and solutions | All roles |
| [DOCKER_DEPLOY.md](DOCKER_DEPLOY.md) | Docker deployment extended guide | DevOps, system admins |

### Key Sections

**Installation & Configuration**:
- [Prerequisites](#prerequisites) — Required API keys
- [Step 1: Get Your API Keys](#step-1-get-your-api-keys) — API key registration
- [Step 2: Configure Environment Variables](#step-2-configure-environment-variables) — `.env` setup
- [Option A: Docker Deployment](#option-a-docker-deployment) — Containerized setup
- [Option B: Local Deployment](#option-b-local-deployment-development) — Direct Python setup

**Usage**:
- [Using the Application](#using-the-application) — Dashboard navigation
- [Dark Ships Feature](#dark-ships-feature) — Real-time dark ship detection
- [Environment Variables Explained](#environment-variables-explained) — Configuration reference

**Troubleshooting & Support**:
- [Troubleshooting Guide](TROUBLESHOOTING.md) — Common issues & solutions
- [Support & Issues](#support--issues) — Getting help

### Feature Documentation

**Dark Ships Tracking** (NEW):
- Automatic AIS signal loss detection
- 200 nautical mile monitoring zone
- Event logging with full metadata snapshots
- Real-time dashboard alerts
- Historical event analysis
- See: [Dark Ships Feature](#dark-ships-feature) & [API_DOCUMENTATION.md](API_DOCUMENTATION.md#dark-ships-api-endpoints-new)

**Real-time Maritime Tracking**:
- Live AIS vessel positioning
- Aircraft tracking via OpenSky
- Interactive Leaflet.js mapping
- Bounding box searches

**Satellite Imagery Analysis**:
- Copernicus Sentinel-2 data
- Multispectral analysis
- NDVI/NDWI indices
- Site detection

---

## License

© 2026 blue44elephant. All rights reserved.

---

## Credits

- **AISStream** — Real-time AIS vessel tracking data
- **Copernicus** — Free satellite imagery and data
- **Leaflet.js** — Interactive mapping library
- **FastAPI** — Modern Python web framework
- **SQLite** — Lightweight database for event logging

---

## Quick Reference

### Useful Commands

```bash
# Start (Docker)
docker build -t epic-archer:latest .
docker run -p 8000:8000 --env-file .env epic-archer:latest

# Start (Local)
uvicorn Epic_Archer:app --reload

# Access
http://localhost:8000

# Database
sqlite3 epic_archer_data/dark_ships.db

# Logs (Docker)
docker logs epic-archer -f

# Stop (Ctrl+C or docker stop epic-archer)
```

### API Examples

```bash
# Get dark ships
curl http://localhost:8000/api/dark-ships/current

# Get event history
curl http://localhost:8000/api/dark-ships/logs?hours=24

# Get tracking status
curl http://localhost:8000/api/dark-ships/status

# Update monitoring area
curl -X POST "http://localhost:8000/api/dark-ships/monitoring-area?lat=10.5&lon=-62.3"
```

---

**Last Updated**: June 21, 2026  
**Version**: 1.0.0  
**Status**: Production Ready
