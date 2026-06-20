# Epic Archer - Troubleshooting Guide

Common issues, diagnostics, and solutions for Epic Archer deployment and operation.

---

## Connection Issues

### AISStream Connection Failed

**Error Message**:
```
AISStream connection failed: timeout
AISStream request failed: [Errno -2] Name or service not known
```

**Causes**:
- No internet connection
- AIS API key invalid
- AISStream service down
- Firewall blocking WebSocket connections

**Solutions**:

1. **Check internet connection**:
   ```bash
   ping google.com
   ```

2. **Verify API key**:
   - Visit: https://www.aisstream.io/account/api-key
   - Copy correct key
   - Update `.env`: `AISSTREAM_API_KEY=your-key`
   - Restart application

3. **Check firewall**:
   - Allow port 443 (HTTPS/WSS)
   - Whitelist domain: `stream.aisstream.io`

4. **Test WebSocket connection**:
   ```bash
   # Using wscat (npm install -g wscat)
   wscat -c wss://stream.aisstream.io/v0/stream
   ```

5. **Check AISStream status**:
   - Visit: https://status.aisstream.io/

---

### Copernicus Authentication Failed

**Error Message**:
```
Copernicus authentication error: 401 Unauthorized
Copernicus token expired
```

**Causes**:
- Client ID/Secret incorrect
- Credentials expired
- Wrong environment variables
- Firewall blocking Copernicus

**Solutions**:

1. **Verify credentials**:
   - Visit: https://dataspace.copernicus.eu/user-settings/applications
   - Copy Client ID and Client Secret
   - Update `.env`:
     ```env
     COPERNICUS_CLIENT_ID=your-actual-id
     COPERNICUS_CLIENT_SECRET=your-actual-secret
     ```

2. **Check `.env` format**:
   ```bash
   # Correct
   COPERNICUS_CLIENT_ID=abc123
   
   # Wrong (no quotes needed)
   COPERNICUS_CLIENT_ID="abc123"  # ❌ Quotes included in value!
   ```

3. **Regenerate credentials**:
   - Log into Copernicus Data Space
   - Delete old application
   - Create new application
   - Copy new credentials

4. **Test authentication**:
   ```bash
   curl -X POST https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token \
     -d "grant_type=client_credentials" \
     -d "client_id=YOUR_ID" \
     -d "client_secret=YOUR_SECRET"
   ```

---

### OpenSky Network Unavailable

**Error Message**:
```
OpenSky API unreachable
Aircraft data unavailable: 429 Too Many Requests
```

**Causes**:
- Rate limit exceeded (4 req/min free tier)
- OpenSky service down
- Authentication token expired

**Solutions**:

1. **Check rate limits**:
   - OpenSky free tier: 4 requests/minute
   - Consider obtaining API key for higher limits

2. **Check service status**:
   - Visit: https://opensky-network.org/

3. **Implement backoff**:
   - Application already has retry logic
   - Increase `backoff_factor` in `Epic_Archer.py` if needed

---

## Docker Issues

### Container Won't Start

**Error Message**:
```
docker: Error response from daemon: ... exited with code 1
```

**Diagnosis**:
```bash
docker logs epic-archer
```

**Common Causes & Solutions**:

1. **Missing `.env` file**:
   ```bash
   # Create .env in same directory as docker run command
   cat > .env << EOF
   COPERNICUS_CLIENT_ID=your-id
   COPERNICUS_CLIENT_SECRET=your-secret
   AISSTREAM_API_KEY=your-key
   EOF
   
   docker run -p 8000:8000 --env-file .env epic-archer:latest
   ```

2. **Port already in use**:
   ```bash
   # Use different port
   docker run -p 9000:8000 --env-file .env epic-archer:latest
   # Access at http://localhost:9000
   ```

3. **Python dependencies missing**:
   ```bash
   # Rebuild without cache
   docker build --no-cache -t epic-archer:latest .
   ```

4. **Permissions issue**:
   ```bash
   # Run with elevated permissions
   sudo docker run -p 8000:8000 --env-file .env epic-archer:latest
   ```

---

### Container Exits Immediately

**Error Message**:
```
Container exited with code 1
```

**Solutions**:

1. **Check logs for specific error**:
   ```bash
   docker logs --tail 50 epic-archer
   ```

2. **Run interactively to see errors**:
   ```bash
   docker run -it -p 8000:8000 --env-file .env epic-archer:latest
   ```

3. **Verify Dockerfile**:
   ```bash
   docker build -t epic-archer:latest .
   docker inspect epic-archer:latest
   ```

---

### Docker Desktop Resources

**Error**: Container slow or crashing

**Solution**: Increase Docker Desktop resources

1. **Windows/Mac**: Docker Desktop → Settings → Resources
   - CPUs: Increase to 4+
   - Memory: Increase to 4GB+
   - Disk: Ensure 20GB+ available

2. **Linux**: No limit by default

---

## Application Issues

### No Ships Appearing on Map

**Possible Causes**:
- AISStream connection failed
- No ships in bounding box
- Data sampling issue

**Diagnosis**:

1. **Check API response**:
   ```bash
   curl http://localhost:8000/api/realtime/ships?min_lat=10&min_lon=-63&max_lat=11&max_lon=-62
   ```
   Should return `count > 0`

2. **Check logs**:
   ```
   INFO: 42 ships fetched from AISStream
   ```

3. **Expand search area**:
   - If no ships in your area, zoom out to larger region
   - Different maritime routes have varying traffic

4. **Wait for data**:
   - Application needs ~30 seconds to accumulate data
   - Check back after waiting

---

### Dark Ship Detection Not Working

**Symptom**: Ships stay online even when AIS should stop

**Diagnosis**:

1. **Check dark ships endpoint**:
   ```bash
   curl http://localhost:8000/api/dark-ships/current
   ```

2. **Check database**:
   ```bash
   sqlite3 epic_archer_data/dark_ships.db "SELECT COUNT(*) FROM dark_ship_events;"
   ```

3. **Check logs for errors**:
   ```
   ERROR: Dark ship tracking error for MMSI 123456789
   ```

**Solutions**:

1. **Verify ship is in monitoring area**:
   - Check distance from monitoring center
   - Should be < 200 NM

2. **Check dark timeout**:
   - Default: 1 hour without AIS = dark
   - Can be changed in `Epic_Archer.py`:
     ```python
     dark_timeout_seconds=1800  # 30 minutes
     ```

3. **Wait for timeout**:
   - If AIS just stopped, ship won't be marked dark for 1 hour
   - Monitoring is real-time only

4. **Reset database**:
   ```bash
   rm epic_archer_data/dark_ships.db
   # Restart application to create fresh database
   ```

---

### API Endpoints Returning 500 Errors

**Error Message**:
```json
{"detail": "Internal server error"}
```

**Diagnosis**:

1. **Check application logs**:
   ```bash
   # Local: Terminal output
   # Docker: docker logs epic-archer
   ```

2. **Check specific endpoint**:
   ```bash
   curl -v http://localhost:8000/api/dark-ships/logs
   ```

3. **Test with curl to see actual error**:
   ```bash
   curl -i http://localhost:8000/api/dark-ships/current
   ```

**Common Causes**:

1. **Database connection issue**:
   ```bash
   ls -la epic_archer_data/dark_ships.db
   # If not found, database needs initialization
   ```

2. **Missing environment variables**:
   ```bash
   echo $COPERNICUS_CLIENT_ID
   # Should print value, not empty
   ```

3. **Corrupted database**:
   ```bash
   rm epic_archer_data/dark_ships.db
   # Restart to recreate
   ```

---

## Database Issues

### "Database is Locked" Error

**Error Message**:
```
sqlite3.OperationalError: database is locked
```

**Causes**:
- Multiple processes accessing database
- Application not properly closed
- Long-running transaction

**Solutions**:

1. **Identify locking process**:
   ```bash
   # macOS/Linux
   lsof | grep dark_ships.db
   
   # Windows (PowerShell)
   Get-Process | Where-Object {$_.Name -like "*python*"}
   ```

2. **Kill process**:
   ```bash
   # macOS/Linux
   kill -9 <PID>
   
   # Windows (PowerShell)
   Stop-Process -Id <PID> -Force
   ```

3. **Restart application**:
   ```bash
   python Epic_Archer.py
   # or
   docker run -p 8000:8000 --env-file .env epic-archer:latest
   ```

4. **Increase timeout**:
   - Add to `dark_ships_db.py`:
     ```python
     conn = sqlite3.connect(self.db_path, timeout=30.0)  # 30 second timeout
     ```

---

### Database Corrupted

**Symptoms**:
- Database queries slow or failing
- "database disk image is malformed"
- Indices don't exist

**Solutions**:

1. **Backup database**:
   ```bash
   cp epic_archer_data/dark_ships.db epic_archer_data/dark_ships.db.corrupted
   ```

2. **Check integrity**:
   ```bash
   sqlite3 epic_archer_data/dark_ships.db "PRAGMA integrity_check;"
   ```

3. **Repair (if possible)**:
   ```bash
   sqlite3 epic_archer_data/dark_ships.db ".recover" | sqlite3 epic_archer_data/dark_ships_recovered.db
   ```

4. **Reset database** (last resort):
   ```bash
   rm epic_archer_data/dark_ships.db
   # Restart application to recreate
   ```

---

### Database Growing Too Large

**Symptom**: `dark_ships.db` exceeds 500 MB

**Solutions**:

1. **Check size**:
   ```bash
   ls -lh epic_archer_data/dark_ships.db
   ```

2. **Optimize database**:
   ```bash
   sqlite3 epic_archer_data/dark_ships.db "VACUUM;"
   ```

3. **Archive old events** (if storage critical):
   ```bash
   sqlite3 epic_archer_data/dark_ships.db ".mode csv" ".output events_backup.csv" "SELECT * FROM dark_ship_events WHERE event_time < datetime('now', '-30 days');"
   ```

4. **Delete old events**:
   ```sql
   DELETE FROM dark_ship_events WHERE event_time < datetime('now', '-90 days');
   VACUUM;
   ```

---

## Performance Issues

### High CPU Usage

**Symptoms**:
- Application slow
- System unresponsive
- "100% CPU" in Task Manager

**Diagnosis**:

1. **Profile application**:
   ```python
   import cProfile
   # See DEVELOPMENT.md for profiling guide
   ```

2. **Check query performance**:
   ```bash
   sqlite3 epic_archer_data/dark_ships.db "EXPLAIN QUERY PLAN SELECT * FROM dark_ship_events ORDER BY event_time DESC LIMIT 100;"
   ```

**Solutions**:

1. **Rebuild indices**:
   ```bash
   sqlite3 epic_archer_data/dark_ships.db "REINDEX;"
   ```

2. **Reduce AIS sample rate**:
   - In `Epic_Archer.py`, increase sample window:
     ```python
     sample_seconds=30  # From 8 to 30
     ```

3. **Upgrade hardware**:
   - Add more CPU cores
   - Increase RAM

---

### Slow API Responses

**Symptom**: API endpoints take > 5 seconds

**Diagnosis**:

1. **Measure response time**:
   ```bash
   curl -w "\nTotal time: %{time_total}\n" http://localhost:8000/api/dark-ships/logs
   ```

2. **Check database query time**:
   ```bash
   sqlite3 epic_archer_data/dark_ships.db
   .timer on
   SELECT * FROM dark_ship_events WHERE event_time > datetime('now', '-72 hours') LIMIT 100;
   ```

**Solutions**:

1. **Add database indices**:
   ```sql
   CREATE INDEX idx_event_time ON dark_ship_events(event_time);
   ```

2. **Reduce data range**:
   - Query fewer hours: `hours=24` instead of `hours=72`

3. **Implement caching** (advanced):
   - Cache API responses
   - Invalidate on database writes

4. **Upgrade database**:
   - Use PostgreSQL for better performance with large datasets

---

## Network Issues

### Firewall Blocking Connections

**Symptoms**:
- "Connection timeout"
- "No route to host"
- Services unavailable

**Solutions**:

1. **Check firewall status**:
   ```bash
   # Windows
   netsh advfirewall show allprofiles
   
   # macOS
   sudo launchctl list | grep firewall
   
   # Linux
   sudo iptables -L
   ```

2. **Allow application**:
   - Windows: Settings → Firewall → Allow app through firewall
   - macOS: System Preferences → Security → Firewall → Options
   - Linux: `sudo ufw allow 8000/tcp`

3. **Allow specific ports**:
   - 8000 (Epic Archer API)
   - 443 (HTTPS/WSS for external APIs)

---

### DNS Resolution Issues

**Symptom**: "Name or service not known"

**Solutions**:

1. **Test DNS**:
   ```bash
   nslookup stream.aisstream.io
   ```

2. **Use alternative DNS**:
   - Google: 8.8.8.8
   - Cloudflare: 1.1.1.1

3. **Check network**:
   ```bash
   ping google.com
   ```

---

## Memory Issues

### Out of Memory (OOM)

**Symptom**: Application crashes or freezes

**Diagnosis**:

1. **Check memory usage**:
   ```bash
   # macOS/Linux
   top
   
   # Windows
   tasklist /FI "IMAGENAME eq python.exe"
   ```

2. **Check available memory**:
   ```bash
   # macOS/Linux
   free -h
   
   # Windows (PowerShell)
   Get-ComputerInfo | Select-Object TotalPhysicalMemory, CsTotalPhysicalMemory
   ```

**Solutions**:

1. **Reduce ship tracking limit**:
   ```python
   max_items=100  # Track fewer ships
   ```

2. **Clear old data**:
   ```bash
   rm epic_archer_data/*.db
   ```

3. **Increase available memory**:
   - Close other applications
   - Docker: Increase memory allocation
   - System: Add RAM

---

## Frontend Issues

### Dashboard Not Loading

**Symptom**: Blank page, map doesn't appear

**Diagnosis**:

1. **Check browser console** (F12):
   - Look for red error messages
   - Check for CORS errors

2. **Check network tab** (F12):
   - See which requests fail
   - Note error status codes

3. **Verify server is running**:
   ```bash
   curl http://localhost:8000/
   ```

**Solutions**:

1. **Clear browser cache**:
   - Chrome: DevTools → Application → Clear storage
   - Firefox: Ctrl+Shift+Delete

2. **Check CORS configuration**:
   - In `Epic_Archer.py`, verify CORS middleware

3. **Verify static files exist**:
   ```bash
   ls -la frontend/
   # Should have index.html, app.js, styles.css
   ```

---

### Map Not Displaying

**Symptom**: Blank gray area where map should be

**Possible Causes**:
- Leaflet.js not loading
- Map container sizing issue
- Invalid coordinates

**Solutions**:

1. **Check browser console for errors**
2. **Verify map div exists** in `index.html`:
   ```html
   <div id="main-map"></div>
   ```

3. **Check CSS** - map needs height:
   ```css
   #main-map {
       width: 100%;
       height: 100%;
   }
   ```

---

### Dark Ships Table Empty

**Symptom**: "No dark ships currently" message

**Solutions**:

1. **Verify endpoint returns data**:
   ```bash
   curl http://localhost:8000/api/dark-ships/current
   ```

2. **Check database has events**:
   ```bash
   sqlite3 epic_archer_data/dark_ships.db "SELECT COUNT(*) FROM dark_ship_events;"
   ```

3. **Wait for dark timeout**:
   - Ships need 1 hour without AIS to be marked dark
   - Use test data to simulate faster

---

## Getting Help

### Collect Diagnostic Information

When reporting issues, gather:

```bash
# System info
uname -a                           # macOS/Linux
systeminfo                         # Windows

# Application version
cat README.md | grep -i version

# Error logs
docker logs epic-archer 2>&1       # If using Docker
# OR
python Epic_Archer.py 2>&1         # If running locally

# Database info
sqlite3 epic_archer_data/dark_ships.db "SELECT COUNT(*) FROM dark_ship_events;"

# Network test
curl -v http://localhost:8000/health

# API test
curl http://localhost:8000/api/dark-ships/current
```

### Support Resources

- **GitHub Issues**: https://github.com/blue44elephant/Epic-Archer-Counter-Narcotics-tool-/issues
- **Documentation**: See README.md, ARCHITECTURE.md, API_DOCUMENTATION.md
- **Database Guide**: See DATABASE.md
- **Development**: See DEVELOPMENT.md

---

**Troubleshooting Guide Version**: 1.0.0  
**Last Updated**: June 21, 2026
