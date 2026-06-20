# Epic Archer - Docker Deployment Guide

Epic Archer is containerized for easy deployment across Windows, Mac, and Linux. The Docker setup keeps your Copernicus API credentials external and editable.

---

## **Quick Start (TL;DR)**

```bash
# 1. Install Docker Desktop from https://www.docker.com/products/docker-desktop

# 2. Edit .env with your Copernicus credentials (see Step 1 below)

# 3. Build the image
docker build -t epic-archer:latest .
#OR
docker build --no-cache -t epic-archer:latest .

# 4. Run the container
docker run -p 8000:8000 --env-file .env epic-archer:latest

# 5. Open browser to http://localhost:8000
```

That's it! For detailed instructions, see below.

---

## **Prerequisites**

- **Docker Desktop** installed ([download here](https://www.docker.com/products/docker-desktop))
- **Epic Archer** repository cloned locally
- **.env file** with your Copernicus credentials (see below)

---

## **Step 1: Configure Your Credentials**

Edit the `.env` file in the Epic Archer directory:

```env
COPERNICUS_CLIENT_ID=your-client-id-here
COPERNICUS_CLIENT_SECRET=your-client-secret-here
EPIC_ARCHER_DATA_DIR=/app/epic_archer_data
RF_MODEL_PATH=/app/rf_model.pickle
```

**Where to get credentials:**
1. Visit [Copernicus Data Space Ecosystem](https://dataspace.copernicus.eu/)
2. Register a new account or log in
3. Create an OAuth2 application
4. Copy your **Client ID** and **Client Secret**
5. Paste into `.env`

---

## **Step 2: Build the Docker Image**

Open a terminal in the Epic Archer directory and run:

```bash
docker build -t epic-archer:latest .
```

**Expected output:**
```
Step 1/10 : FROM python:3.11-slim
Step 2/10 : WORKDIR /app
...
Successfully built abc12345def
Successfully tagged epic-archer:latest
```

*Building takes ~3-5 minutes on first run (subsequent builds are cached).*

---

## **Step 3: Run the Container**

```bash
docker run -p 8000:8000 --env-file .env epic-archer:latest
```

**What this does:**
- `-p 8000:8000`: Maps container port 8000 -> your machine's port 8000
- `--env-file .env`: Passes your credentials into the container
- `epic-archer:latest`: Uses the image you built

**Expected output:**
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete
```

---

## **Step 4: Access Epic Archer**

Open your browser and navigate to:

```
http://localhost:8000
```

You should see the **Epic Archer Dashboard** with 8 detector checkboxes.

---

## **Usage**

### **Select Detectors**
- Check boxes for detectors you want (Vehicles, Ships, Aircraft, Trains, Night Lights, SAR Vessels, Parking, Construction)

### **Draw Area of Interest (AOI)**
- Click the **rectangle tool** (top-left of map)
- Draw a bounding box over the region you want to analyze

### **Run Analysis**
- Click **"Analyze"**
- Monitor progress in the HUD
- Results stream in real-time

### **View Results**
- Detection badges appear on the map
- Click a badge -> see detector-specific telemetry (speed, RCS area, vehicle count, etc.)

---

## **Update Credentials (Without Rebuilding)**

You don't need to rebuild the Docker image to change credentials. Simply:

1. Edit `.env` with new credentials
2. Stop the running container: `Ctrl+C`
3. Run again:
   ```bash
   docker run -p 8000:8000 --env-file .env epic-archer:latest
   ```

---

## **Troubleshooting**

### **Container won't start**
```bash
docker run -p 8000:8000 --env-file .env epic-archer:latest
```
Check the error log. Common issues:
- Invalid `.env` path (use absolute path on Windows: `C:\path\to\.env`)
- Copernicus credentials invalid -> verify on [Copernicus Data Space](https://dataspace.copernicus.eu/)
- Port 8000 already in use -> use different port: `-p 9000:8000`

### **Port already in use**
```bash
docker run -p 9000:8000 --env-file .env epic-archer:latest
```
Then access at `http://localhost:9000`

### **View container logs**
```bash
docker logs <container-id>
```

### **Stop the container**
```bash
Ctrl+C
```

---

## **Advanced: Docker Compose**

For multi-container setups or production, create `docker-compose.yml`:

```yaml
version: '3.9'

services:
  epic-archer:
    build: .
    ports:
      - "8000:8000"
    env_file: .env
    volumes:
      - ./epic_archer_data:/app/epic_archer_data
    restart: unless-stopped
```

Then run:
```bash
docker-compose up
```

---

## **Production Deployment**

For cloud deployment (AWS, Google Cloud, Azure):

1. Push image to registry:
   ```bash
   docker tag epic-archer:latest your-registry/epic-archer:latest
   docker push your-registry/epic-archer:latest
   ```

2. Deploy from registry (instructions vary by platform)

3. Pass `.env` as environment variables or secrets (don't commit `.env` to version control)

---

## **Support**

For issues or questions:
- Check logs: `docker logs <container-id>`
- Verify Copernicus credentials: [Data Space OAuth](https://dataspace.copernicus.eu/)
- Ensure Docker is running (Docker Desktop must be open)

