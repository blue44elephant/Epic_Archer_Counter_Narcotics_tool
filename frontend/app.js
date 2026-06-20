/**
 * DrishX Tactical Command Terminal v1.0.0
 */

class EpicArcherDashboard {
    constructor() {
        this.map = null;
        this.chart = null;
        this.markers = {};
        this.roadLayer = null;
        this.sites = [];
        this.currentView = 'dashboard';
        this.isSatellite = false;
        this.selectedMissionIds = new Set();
        this.allMissions = [];
        this.allMissionsFetched = false;
        this.selectedDetectors = new Set(['truck']); // Default: truck detection
        this.realtimeLayers = {
            aircraft: L.layerGroup(),
            ships: L.layerGroup()
        };
        this.liveAircraftEnabled = false;
        this.liveShipsEnabled = false;
        this.realtimeRefreshTimer = null;

        this.init();
    }

    async init() {
        console.log("Initializing Epic Archer dashboard...");
        this.setupMap();
        this.setupEventListeners();

        // Initial data fetch
        await this.fetchSites();

        // Boot Auth (BYOK check)
        this.checkStoredCredentials();
    }

    setupMap() {
        // Use the German A2 (Fisser et al. Validation Site) as default view
        const testArea = [52.345, 10.550];
        this.map = L.map('main-map', {
            center: testArea,
            zoom: 14,
            zoomControl: false,
            attributionControl: false
        });

        this.updateBasemap();
        this.realtimeLayers.aircraft.addTo(this.map);
        this.realtimeLayers.ships.addTo(this.map);

        L.control.zoom({ position: 'bottomright' }).addTo(this.map);

        // Initialize drawing layer
        this.drawnItems = new L.FeatureGroup();
        this.map.addLayer(this.drawnItems);

        this.drawControl = new L.Control.Draw({
            draw: {
                polygon: false,
                marker: false,
                circle: false,
                circlemarker: false,
                polyline: false,
                rectangle: {
                    shapeOptions: {
                        color: 'var(--accent-blue)',
                        weight: 2
                    }
                }
            },
            edit: {
                featureGroup: this.drawnItems,
                remove: true
            }
        });

        this.map.on(L.Draw.Event.CREATED, (e) => {
            const layer = e.layer;
            this.drawnItems.clearLayers();
            this.drawnItems.addLayer(layer);
            const bbox = layer.getBounds();
            this.handleAOISelection(bbox);
        });
    }

    updateBasemap() {
        if (this.currentBasemap) this.map.removeLayer(this.currentBasemap);

        const url = this.isSatellite
            ? 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
            : 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png';

        this.currentBasemap = L.tileLayer(url, {
            subdomains: 'abcd',
            maxZoom: 20
        }).addTo(this.map);
    }

    setupEventListeners() {
        // AOI Selector
        document.getElementById('draw-aoi')?.addEventListener('click', () => {
            const rectDrawer = new L.Draw.Rectangle(this.map, this.drawControl.options.draw.rectangle);
            rectDrawer.enable();
            this.notify("Select an area on the map to analyze.", "info");
        });

        // Satellite Toggle
        document.getElementById('toggle-satellite')?.addEventListener('click', () => {
            this.isSatellite = !this.isSatellite;
            this.updateBasemap();
            this.notify(`Basemap switched to ${this.isSatellite ? 'Satellite' : 'Standard'}`, "info");
        });

        // Navigation
        document.querySelectorAll('.nav-item').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const view = e.currentTarget.dataset.view;
                this.switchView(view);
            });
        });

        // Trends Controls
        document.getElementById('refresh-trends')?.addEventListener('click', () => this.updateTrends());

        // Initialize Flatpickr for better calendar experience
        const fpConfig = {
            theme: "dark",
            dateFormat: "Y-m-d",
            onChange: () => this.updateTrends()
        };

        flatpickr("#trend-from", fpConfig);
        flatpickr("#trend-to", fpConfig);

        // Search Bar
        const searchBtn = document.getElementById('execute-search');
        const searchInput = document.getElementById('map-search-input');

        searchBtn?.addEventListener('click', () => this.handleLocationSearch());
        searchInput?.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.handleLocationSearch();
        });

        // Close Overlays
        document.querySelector('.close-overlay')?.addEventListener('click', () => {
            document.getElementById('site-overlay').classList.add('hidden');
        });

        document.getElementById('close-intel')?.addEventListener('click', () => {
            document.getElementById('intel-drawer').classList.add('hidden');
        });

        // Copernicus Auth: .env only - no UI input
        // Removed save-auth listener (credentials from .env only)

        // Detector selection
        document.querySelectorAll('.detector-checkbox').forEach(chk => {
            chk.addEventListener('change', (e) => this.toggleDetector(e.target.value, e.target.checked));
        });

        document.getElementById('toggle-live-aircraft')?.addEventListener('change', (e) => {
            this.liveAircraftEnabled = e.target.checked;
            this.handleRealtimeToggle();
        });

        document.getElementById('toggle-live-ships')?.addEventListener('change', (e) => {
            this.liveShipsEnabled = e.target.checked;
            this.handleRealtimeToggle();
        });

        document.getElementById('refresh-realtime')?.addEventListener('click', () => this.refreshRealtime());

        // Dark Ships Logs
        document.getElementById('refresh-logs')?.addEventListener('click', () => this.loadDarkShipsLogs());
        document.getElementById('view-status')?.addEventListener('click', () => this.showTrackingStatus());
        document.querySelector('#tracking-status-modal .modal-close')?.addEventListener('click', () => {
            document.getElementById('tracking-status-modal').classList.add('hidden');
        });
    }

    handleRealtimeToggle() {
        if (!this.liveAircraftEnabled) this.realtimeLayers.aircraft.clearLayers();
        if (!this.liveShipsEnabled) this.realtimeLayers.ships.clearLayers();

        if (this.liveAircraftEnabled || this.liveShipsEnabled) {
            this.refreshRealtime();
            if (this.realtimeRefreshTimer) clearInterval(this.realtimeRefreshTimer);
            this.realtimeRefreshTimer = setInterval(() => this.refreshRealtime(), 30000);
        } else if (this.realtimeRefreshTimer) {
            clearInterval(this.realtimeRefreshTimer);
            this.realtimeRefreshTimer = null;
            this.setRealtimeStatus('Realtime overlay off.');
        }
    }

    currentMapBbox() {
        const bounds = this.map.getBounds();
        return {
            minLat: bounds.getSouth(),
            minLon: bounds.getWest(),
            maxLat: bounds.getNorth(),
            maxLon: bounds.getEast()
        };
    }

    async refreshRealtime() {
        if (!this.liveAircraftEnabled && !this.liveShipsEnabled) {
            this.setRealtimeStatus('Select live aircraft or ships first.');
            return;
        }

        const bbox = this.currentMapBbox();
        const params = new URLSearchParams({
            min_lat: bbox.minLat,
            min_lon: bbox.minLon,
            max_lat: bbox.maxLat,
            max_lon: bbox.maxLon
        });

        this.setRealtimeStatus('Refreshing live transponder data...');
        const tasks = [];
        if (this.liveAircraftEnabled) {
            tasks.push(this.fetchRealtimeFeed(`/api/realtime/aircraft?${params.toString()}`, 'aircraft'));
        }
        if (this.liveShipsEnabled) {
            const shipParams = new URLSearchParams(params);
            shipParams.set('sample_seconds', '8');
            tasks.push(this.fetchRealtimeFeed(`/api/realtime/ships?${shipParams.toString()}`, 'ships'));
        }

        const results = await Promise.allSettled(tasks);
        const ok = results
            .filter(r => r.status === 'fulfilled')
            .map(r => r.value)
            .filter(Boolean);
        const failed = results.length - ok.length;
        const total = ok.reduce((sum, item) => sum + item.count, 0);
        const suffix = failed ? ` (${failed} source unavailable)` : '';
        this.setRealtimeStatus(`Mapped ${total} live contacts${suffix}.`);
    }

    async fetchRealtimeFeed(url, layerName) {
        try {
            const resp = await fetch(url);
            const data = await resp.json();
            if (!resp.ok) throw new Error(data.detail || 'Realtime source unavailable');
            this.renderRealtimeMarkers(data.items || [], layerName);
            return { layerName, count: data.count || 0 };
        } catch (e) {
            console.error(`Realtime ${layerName} error:`, e);
            this.setRealtimeStatus(`${layerName === 'aircraft' ? 'Aircraft' : 'Ships'} unavailable: ${e.message}`);
            return null;
        }
    }

    renderRealtimeMarkers(items, layerName) {
        const layer = this.realtimeLayers[layerName];
        layer.clearLayers();

        items.forEach(item => {
            if (item.lat === null || item.lon === null) return;
            const isAircraft = layerName === 'aircraft';
            const marker = L.marker([item.lat, item.lon], {
                icon: L.divIcon({
                    className: `realtime-marker ${isAircraft ? 'aircraft-marker' : 'ship-marker'}`,
                    html: `<div class="realtime-icon"><i class="fas ${isAircraft ? 'fa-plane' : 'fa-ship'}"></i></div>`,
                    iconSize: [28, 28],
                    iconAnchor: [14, 14]
                })
            }).addTo(layer);

            marker.bindPopup(this.realtimePopupHtml(item, isAircraft));
        });
    }

    realtimePopupHtml(item, isAircraft) {
        if (isAircraft) {
            return `
                <div class="marker-popup realtime-popup">
                    <div class="popup-title">${item.callsign || item.id}</div>
                    <div class="popup-meta">OpenSky - ${item.origin_country || 'Unknown origin'}</div>
                    <div class="popup-line">Speed: ${item.speed_kmh ?? '--'} km/h</div>
                    <div class="popup-line">Altitude: ${item.geo_altitude_m ?? item.baro_altitude_m ?? '--'} m</div>
                    <div class="popup-line">Heading: ${item.heading ?? '--'} deg</div>
                    <div class="popup-line">ICAO24: ${item.id}</div>
                </div>
            `;
        }

        return `
            <div class="marker-popup realtime-popup">
                <div class="popup-title">${item.name || item.mmsi || 'AIS Vessel'}</div>
                <div class="popup-meta">AISStream - ${item.message_type || 'Position'}</div>
                <div class="popup-line">MMSI: ${item.mmsi || '--'}</div>
                <div class="popup-line">Speed: ${item.speed_knots ?? '--'} kt</div>
                <div class="popup-line">Course: ${item.course ?? item.heading ?? '--'} deg</div>
                <div class="popup-line">Updated: ${item.timestamp ? new Date(item.timestamp).toLocaleTimeString() : '--'}</div>
            </div>
        `;
    }

    setRealtimeStatus(message) {
        const status = document.getElementById('realtime-status');
        if (status) status.textContent = message;
    }

    async handleLocationSearch() {
        const query = document.getElementById('map-search-input').value;
        if (!query) return;

        const dropdown = document.getElementById('search-results-dropdown');
        dropdown.innerHTML = '<div class="search-result"><span class="main-text">Querying satellites...</span></div>';
        dropdown.classList.remove('hidden');

        try {
            const resp = await fetch(`https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(query)}&limit=5`);
            const results = await resp.json();

            if (results.length === 0) {
                dropdown.innerHTML = '<div class="search-result"><span class="main-text">No sectors found.</span></div>';
                return;
            }

            dropdown.innerHTML = results.map(res => `
                <div class="search-result" onclick="window.dashboard.jumpToLocation(${res.lat}, ${res.lon}, '${res.display_name.split(',')[0]}')">
                    <span class="main-text">${res.display_name.split(',')[0]}</span>
                    <span class="sub-text">${res.display_name.split(',').slice(1).join(',')}</span>
                </div>
            `).join('');

        } catch (e) {
            this.notify("Search engine offline.", "error");
            dropdown.classList.add('hidden');
        }
    }

    jumpToLocation(lat, lon, label) {
        this.map.flyTo([lat, lon], 15, { duration: 1.5 });
        document.getElementById('search-results-dropdown').classList.add('hidden');
        this.notify(`Navigating to sector: ${label}`, "info");

        // Brief highlight
        const circle = L.circle([lat, lon], {
            radius: 500,
            color: 'var(--accent-blue)',
            fillColor: 'var(--accent-blue)',
            fillOpacity: 0.1,
            dashArray: '5, 10'
        }).addTo(this.map);

        setTimeout(() => this.map.removeLayer(circle), 3000);
    }

    switchView(view) {
        this.currentView = view;
        document.querySelectorAll('.view').forEach(v => v.classList.add('hidden'));
        document.getElementById(`${view}-view`)?.classList.remove('hidden');

        // Update tabs
        document.querySelectorAll('.nav-item').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.view === view);
        });

        if (view === 'trends') {
            this.updateTrends();
        } else if (view === 'logs') {
            this.loadDarkShipsLogs();
        }

        // Update header
        const titles = {
            dashboard: 'Operations',
            trends: 'Tactical Trends',
            settings: 'Copernicus Link',
            logs: 'Dark Ships Event Log'
        };
        const titleEl = document.querySelector('.top-header h1');
        const subtitleEl = document.querySelector('.top-header p');
        if (titleEl && titles[view]) {
            titleEl.textContent = titles[view];
            if (subtitleEl) {
                const subtitles = {
                    dashboard: 'Operational monitoring and site analysis',
                    trends: 'Historical detection analysis and trends',
                    settings: 'Configure Copernicus Data Space credentials',
                    logs: 'Track ships that go dark (AIS offline) near monitoring areas'
                };
                subtitleEl.textContent = subtitles[view] || '';
            }
        }
    }

    async updateTrends() {
        const fromDate = document.getElementById('trend-from').value;
        const toDate = document.getElementById('trend-to').value;
        const siteIdsArray = Array.from(this.selectedMissionIds || []);
        const siteIds = siteIdsArray.join(',');

        try {
            const resp = await fetch(`/api/analytics/trends?from_date=${fromDate}&to_date=${toDate}${siteIds ? `&site_ids=${siteIds}` : ''}`);
            const data = await resp.json();

            // Update stats
            document.getElementById('stat-total').textContent = data.summary.total_detections;
            document.getElementById('stat-peak').textContent = data.summary.missions_count + " Sectors";
            document.getElementById('stat-avg').textContent = data.datasets.length;

            this.renderTrendChart(data);
            this.updateMissionSelector();
        } catch (e) {
            console.error("Trends fetch error:", e);
            this.notify("Failed to sync historical trends.", "error");
        }
    }

    updateMissionSelector() {
        const container = document.getElementById('mission-comparison-selector');
        if (!container) return;

        if (this.allMissionsFetched) {
            this.renderMissionChecklist(container);
            return;
        }

        fetch('/api/sites').then(r => r.json()).then(sites => {
            this.allMissions = sites.filter(s => s.type === 'history');
            this.allMissionsFetched = true;
            this.renderMissionChecklist(container);
        });
    }

    renderMissionChecklist(container) {
        if (!this.selectedMissionIds) this.selectedMissionIds = new Set();

        container.innerHTML = this.allMissions.map((m, i) => {
            const isActive = this.selectedMissionIds.has(m.id);
            const colors = ["#3b82f6", "#f59e0b", "#10b981", "#ef4444", "#a855f7", "#ec4899"];
            const color = colors[i % colors.length];

            return `
                <div class="comparison-item ${isActive ? 'active' : ''}" onclick="window.dashboard.toggleMissionComparison('${m.id}')">
                    <span class="color-dot" style="background: ${color}"></span>
                    <span>${m.name}</span>
                </div>
            `;
        }).join('');
    }

    toggleMissionComparison(id) {
        if (!this.selectedMissionIds) this.selectedMissionIds = new Set();
        if (this.selectedMissionIds.has(id)) {
            this.selectedMissionIds.delete(id);
        } else {
            this.selectedMissionIds.add(id);
        }
        this.updateTrends();
    }

    toggleDetector(detectorType, isSelected) {
        if (isSelected) {
            this.selectedDetectors.add(detectorType);
        } else {
            this.selectedDetectors.delete(detectorType);
        }
        if (this.selectedDetectors.size === 0) {
            this.selectedDetectors.add('truck'); // ensure at least one
        }
        console.log("Selected detectors:", Array.from(this.selectedDetectors));
    }

    renderTrendChart(data) {
        const ctx = document.getElementById('trend-chart')?.getContext('2d');
        if (!ctx) return;

        if (this.trendChartInstance) {
            this.trendChartInstance.destroy();
        }

        this.trendChartInstance = new Chart(ctx, {
            type: 'line',
            data: {
                labels: data.labels,
                datasets: data.datasets.map(ds => ({
                    ...ds,
                    borderWidth: 3,
                    fill: true,
                    tension: 0.4,
                    pointRadius: 4,
                    pointBackgroundColor: ds.borderColor
                }))
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: true,
                        labels: { color: '#94a3b8', boxWidth: 12, padding: 20 }
                    },
                    tooltip: {
                        mode: 'index',
                        intersect: false,
                        backgroundColor: '#1e293b',
                        titleColor: '#94a3b8',
                        bodyColor: '#fff',
                        borderColor: 'rgba(255,255,255,0.1)',
                        borderWidth: 1
                    }
                },
                scales: {
                    y: {
                        grid: { color: 'rgba(255,255,255,0.05)', drawBorder: false },
                        ticks: { color: '#94a3b8', font: { size: 10 } }
                    },
                    x: {
                        grid: { display: false },
                        ticks: { color: '#94a3b8', font: { size: 10 } }
                    }
                }
            }
        });
    }

    async handleAOISelection(bounds, siteId = 'custom', siteName = null) {
        const sw = bounds instanceof L.LatLngBounds ? bounds.getSouthWest() : { lat: bounds[0], lng: bounds[1] };
        const ne = bounds instanceof L.LatLngBounds ? bounds.getNorthEast() : { lat: bounds[2], lng: bounds[3] };
        const bbox = bounds instanceof L.LatLngBounds ? [sw.lat, sw.lng, ne.lat, ne.lng] : bounds;

        // Prepare HUD
        const hud = document.getElementById('progress-hud');
        const progressBar = document.getElementById('hud-progress-bar');
        const stepText = document.getElementById('hud-step-text');
        const percentText = document.getElementById('hud-percent-text');
        const logConsole = document.getElementById('hud-log');

        hud.classList.remove('hidden');
        progressBar.style.width = '0%';
        stepText.innerText = "Initializing mission...";
        percentText.innerText = "0%";
        logConsole.innerHTML = '';

        const appendLog = (msg) => {
            const entry = document.createElement('div');
            entry.className = 'log-entry';
            entry.innerHTML = `
                <span class="time">[${new Date().toLocaleTimeString()}]</span>
                <span class="indicator">>></span>
                <span class="msg">${msg}</span>
            `;
            logConsole.appendChild(entry);
            logConsole.scrollTop = logConsole.scrollHeight;
        };

        const months = parseInt(document.getElementById('mission-months')?.value || 4);
        const frames = parseInt(document.getElementById('mission-frames')?.value || 10);
        const label = siteName ? `Mission: ${siteName}` : `Analysis Area ${new Date().toLocaleTimeString()} (${months}mo, ${frames}fr)`;

        try {
            const resp = await fetch('/api/analyze', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    bbox: bbox,
                    label: label,
                    months: months,
                    max_frames: frames,
                    site_id: siteId,
                    detectors: Array.from(this.selectedDetectors)
                })
            });

            const reader = resp.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop(); // Keep partial line in buffer

                for (const line of lines) {
                    if (!line.trim()) continue;
                    try {
                        const evt = JSON.parse(line);

                        if (evt.type === 'progress') {
                            progressBar.style.width = `${evt.percent}%`;
                            percentText.innerText = `${evt.percent}%`;
                            stepText.innerText = evt.message;
                            appendLog(evt.message);
                        } else if (evt.type === 'result') {
                            appendLog("Mission complete. Synchronizing results...");
                            this.notify(evt.message, "success");

                            // Successful finish
                            setTimeout(() => {
                                hud.classList.add('hidden');
                                this.fetchRoads(bbox);
                                this.fetchSites();

                                // Show observation markers if available
                                if (evt.mission_id) {
                                    this.loadMissionMarkers(evt.mission_id);
                                }
                            }, 1500);
                        } else if (evt.type === 'error') {
                            this.notify(evt.status === 'error' ? evt.message : "Analysis failed.", "error");
                            appendLog(`ERROR: ${evt.message}`);
                            setTimeout(() => hud.classList.add('hidden'), 3000);
                        }
                    } catch (err) {
                        console.error("Parse error in stream:", err);
                    }
                }
            }
        } catch (e) {
            this.notify("Network error in satellite link.", "error");
            appendLog("CRITICAL: Connection timed out.");
            setTimeout(() => hud.classList.add('hidden'), 3000);
        }
    }

    async fetchRoads(bbox) {
        try {
            const [minLat, minLon, maxLat, maxLon] = bbox;
            const resp = await fetch(`/api/roads?min_lat=${minLat}&min_lon=${minLon}&max_lat=${maxLat}&max_lon=${maxLon}`);
            const geojson = await resp.json();
            this.renderRoads(geojson);
        } catch (e) {
            console.error("Failed to fetch roads:", e);
        }
    }

    renderRoads(geojson) {
        if (this.roadLayer) this.map.removeLayer(this.roadLayer);

        this.roadLayer = L.geoJSON(geojson, {
            style: {
                color: 'var(--accent-amber)',
                weight: 3,
                opacity: 0.6,
                dashArray: '5, 5'
            }
        }).addTo(this.map);

        this.notify("Road corridors identified and highlighted.", "info");
    }

    async loadMissionMarkers(missionId) {
        try {
            const resp = await fetch(`/api/detections/${missionId}`);
            const detections = await resp.json();
            this.renderObservationMarkers(detections);
        } catch (e) {
            console.error("Failed to load mission markers:", e);
        }
    }

    renderObservationMarkers(detections) {
        // Clear existing observation markers
        if (this.obsMarkers) {
            this.obsMarkers.forEach(m => this.map.removeLayer(m));
        }
        this.obsMarkers = [];

        detections.forEach(d => {
            const marker = L.marker([d.lat, d.lon], {
                icon: L.divIcon({
                    className: 'observation-pip',
                    html: '<div class="pip-core"></div>',
                    iconSize: [12, 12],
                    iconAnchor: [6, 6]
                })
            }).addTo(this.map);

            marker.on('click', () => {
                this.showDetectionIntel(d);
                this.map.setView([d.lat, d.lon], 18);
            });

            this.obsMarkers.push(marker);
        });

        if (detections.length > 0) {
            this.notify(`Mapped ${detections.length} tactical detections.`, "success");
        }
    }

    showDetectionIntel(d) {
        const drawer = document.getElementById('intel-drawer');
        const content = document.getElementById('intel-content');
        if (!drawer || !content) return;

        drawer.classList.remove('hidden');
        const detectorLabel = (d.detector_type || 'truck').toUpperCase().replace('_', ' ');
        
        // Build dynamic telemetry grid based on detector type
        let telemetryHtml = `
                    <div class="tel-item">
                        <span class="hud-label">Sensed Domain</span>
                        <span class="tel-value">${new Date(d.timestamp).toLocaleDateString()}</span>
                    </div>
                    <div class="tel-item">
                        <span class="hud-label">Time (UTC)</span>
                        <span class="tel-value">${new Date(d.timestamp).toLocaleTimeString()}</span>
                    </div>
        `;

        // Detector-specific fields
        if (d.speed_kmh !== undefined) {
            telemetryHtml += `<div class="tel-item accent-blue">
                        <span class="hud-label">Logistics Speed</span>
                        <span class="tel-value">${d.speed_kmh} KM/H</span>
                    </div>`;
        }
        if (d.heading !== undefined) {
            telemetryHtml += `<div class="tel-item">
                        <span class="hud-label">Heading Vector</span>
                        <span class="tel-value">${d.heading}&deg;</span>
                    </div>`;
        }
        if (d.wake_length_km !== undefined) {
            telemetryHtml += `<div class="tel-item">
                        <span class="hud-label">Wake Length</span>
                        <span class="tel-value">${d.wake_length_km} KM</span>
                    </div>`;
        }
        if (d.track_length_km !== undefined) {
            telemetryHtml += `<div class="tel-item">
                        <span class="hud-label">Track Length</span>
                        <span class="tel-value">${d.track_length_km} KM</span>
                    </div>`;
        }
        if (d.rcs_area_km2 !== undefined) {
            telemetryHtml += `<div class="tel-item accent-blue">
                        <span class="hud-label">Radar Cross Section</span>
                        <span class="tel-value">${d.rcs_area_km2} KM^2</span>
                    </div>`;
        }
        if (d.vv_db !== undefined) {
            telemetryHtml += `<div class="tel-item">
                        <span class="hud-label">VV Intensity</span>
                        <span class="tel-value">${d.vv_db} dB</span>
                    </div>`;
        }
        if (d.vehicle_count !== undefined) {
            telemetryHtml += `<div class="tel-item accent-blue">
                        <span class="hud-label">Vehicle Count</span>
                        <span class="tel-value">${d.vehicle_count}</span>
                    </div>`;
        }
        if (d.lot_area_m2 !== undefined) {
            telemetryHtml += `<div class="tel-item">
                        <span class="hud-label">Lot Area</span>
                        <span class="tel-value">${(d.lot_area_m2 / 1000).toFixed(1)} KM^2</span>
                    </div>`;
        }
        if (d.area_km2 !== undefined) {
            telemetryHtml += `<div class="tel-item accent-blue">
                        <span class="hud-label">Change Area</span>
                        <span class="tel-value">${d.area_km2} KM^2</span>
                    </div>`;
        }
        if (d.ndvi_change !== undefined) {
            telemetryHtml += `<div class="tel-item">
                        <span class="hud-label">NDVI Delta</span>
                        <span class="tel-value">${d.ndvi_change}</span>
                    </div>`;
        }
        if (d.light_intensity !== undefined) {
            telemetryHtml += `<div class="tel-item accent-blue">
                        <span class="hud-label">Light Intensity</span>
                        <span class="tel-value">${d.light_intensity}</span>
                    </div>`;
        }
        if (d.growth_stage !== undefined) {
            telemetryHtml += `<div class="tel-item accent-blue">
                        <span class="hud-label">Growth Stage</span>
                        <span class="tel-value">${String(d.growth_stage).replace(/_/g, ' ')}</span>
                    </div>`;
        }
        if (d.peak_ndvi !== undefined) {
            telemetryHtml += `<div class="tel-item">
                        <span class="hud-label">Peak NDVI</span>
                        <span class="tel-value">${d.peak_ndvi}</span>
                    </div>`;
        }
        if (d.peak_ndre !== undefined) {
            telemetryHtml += `<div class="tel-item">
                        <span class="hud-label">Peak NDRE</span>
                        <span class="tel-value">${d.peak_ndre}</span>
                    </div>`;
        }
        if (d.ndvi_amplitude !== undefined) {
            telemetryHtml += `<div class="tel-item">
                        <span class="hud-label">NDVI Amp.</span>
                        <span class="tel-value">${d.ndvi_amplitude}</span>
                    </div>`;
        }
        if (d.valid_observations !== undefined) {
            telemetryHtml += `<div class="tel-item">
                        <span class="hud-label">Clear Frames</span>
                        <span class="tel-value">${d.valid_observations}</span>
                    </div>`;
        }
        if (d.peak_date !== undefined) {
            telemetryHtml += `<div class="tel-item">
                        <span class="hud-label">Peak Date</span>
                        <span class="tel-value">${d.peak_date}</span>
                    </div>`;
        }
        if (d.candidate_reason !== undefined) {
            telemetryHtml += `<div class="tel-item full-width">
                        <span class="hud-label">Candidate Reason</span>
                        <span class="tel-value">${d.candidate_reason}</span>
                    </div>`;
        }

        // Common fields
        telemetryHtml += `
                    <div class="tel-item">
                        <span class="hud-label">Coords</span>
                        <span class="tel-value">${d.lat.toFixed(4)}, ${d.lon.toFixed(4)}</span>
                    </div>
                    <div class="tel-item highlight-amber">
                        <span class="hud-label">Spectral Conf.</span>
                        <span class="tel-value">${(d.confidence * 100).toFixed(1)}%</span>
                    </div>
        `;

        content.innerHTML = `
            <div class="intel-profile">
                <div class="detector-badge">${detectorLabel}</div>
                ${d.image_url ? `
                    <div class="multispectral-view">
                        <img src="${d.image_url}" alt="Target Signature">
                    </div>
                ` : `
                    <div class="multispectral-view no-preview">
                        <span>NO PREVIEW AVAILABLE</span>
                    </div>
                `}
                <div class="telemetry-grid">
                    ${telemetryHtml}
                </div>
            </div>
        `;
    }

    async fetchSites() {
        try {
            const resp = await fetch('/api/sites');
            this.sites = await resp.json();
            this.updateMarkers();
        } catch (e) {
            console.error("Failed to fetch sites:", e);
        }
    }

    updateMarkers() {
        Object.values(this.markers).forEach(m => this.map.removeLayer(m));
        this.markers = {};

        const icon = L.divIcon({
            className: 'custom-marker',
            html: '<div class="marker-pin"></div>',
            iconSize: [20, 20],
            iconAnchor: [10, 10]
        });

        this.sites.forEach(site => {
            const marker = L.marker([site.lat, site.lng], { icon })
                .addTo(this.map);

            const popupContent = document.createElement('div');
            popupContent.className = 'marker-popup';
            popupContent.innerHTML = `
                <div class="popup-title">${site.name}</div>
                <div class="popup-meta">${site.country} - ${site.type.toUpperCase()}</div>
                <div class="popup-actions">
                    <button class="btn btn-hud-primary btn-sm analyze-site-btn">Analyze Node</button>
                </div>
            `;

            popupContent.querySelector('.analyze-site-btn').onclick = () => {
                this.handleAOISelection(site.bbox, site.id, site.name);
                marker.closePopup();
            };

            marker.bindPopup(popupContent);
            marker.bindTooltip(`<b>${site.name}</b>`, { direction: 'top' });

            this.markers[site.id] = marker;
        });
    }

    // Dark Ships Logging Functions
    async loadDarkShipsLogs() {
        try {
            // Fetch dark ships logs
            const logsResp = await fetch('/api/dark-ships/logs?limit=100&hours=72');
            const logsData = await logsResp.json();

            // Fetch currently dark ships
            const darkResp = await fetch('/api/dark-ships/current');
            const darkData = await darkResp.json();

            // Update counts
            document.getElementById('dark-ships-count').textContent = darkData.count || 0;
            document.getElementById('recent-events-count').textContent = logsData.count || 0;

            // Render dark ships table
            this.renderDarkShipsTable(darkData.dark_ships || []);

            // Render events log
            this.renderEventsLog(logsData.events || []);

            this.notify('Dark ships logs updated', 'info');
        } catch (e) {
            console.error('Failed to load dark ships logs:', e);
            this.notify('Failed to load dark ships logs: ' + e.message, 'error');
        }
    }

    renderDarkShipsTable(darkShips) {
        const tbody = document.getElementById('dark-ships-list');
        if (!tbody) return;

        if (darkShips.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="text-center">No dark ships currently</td></tr>';
            return;
        }

        tbody.innerHTML = darkShips.map(ship => {
            const darkSince = new Date(ship.dark_start_time);
            const now = new Date();
            const durationMs = now - darkSince;
            const hours = Math.floor(durationMs / (1000 * 60 * 60));
            const minutes = Math.floor((durationMs % (1000 * 60 * 60)) / (1000 * 60));
            const durationStr = hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m`;

            const position = ship.last_lat && ship.last_lon ? 
                `${ship.last_lat.toFixed(4)}, ${ship.last_lon.toFixed(4)}` : 'Unknown';

            return `
                <tr>
                    <td><strong>${ship.ship_name || 'Unknown'}</strong></td>
                    <td>${ship.mmsi}</td>
                    <td>${ship.distance_nm ? ship.distance_nm.toFixed(1) : '--'}</td>
                    <td>${darkSince.toLocaleString()}</td>
                    <td><span class="duration-badge">${durationStr}</span></td>
                    <td>${position}</td>
                </tr>
            `;
        }).join('');
    }

    renderEventsLog(events) {
        const logContainer = document.getElementById('events-log');
        if (!logContainer) return;

        if (events.length === 0) {
            logContainer.innerHTML = '<div class="empty-state">No events in the last 72 hours</div>';
            return;
        }

        logContainer.innerHTML = events.map(event => {
            const eventTime = new Date(event.event_time);
            const eventClass = event.event_type === 'WENT_DARK' ? 'event-dark' : 'event-online';
            const icon = event.event_type === 'WENT_DARK' ? 
                '<i class="fas fa-exclamation-triangle"></i>' : 
                '<i class="fas fa-check-circle"></i>';

            const details = event.ship_details ? event.ship_details : {};
            const detailsStr = Object.entries({
                'Callsign': details.callsign,
                'Flag': details.flag,
                'Type': details.type,
                'Destination': details.destination
            })
            .filter(([_, v]) => v)
            .map(([k, v]) => `${k}: ${v}`)
            .join(' | ');

            return `
                <div class="event-entry ${eventClass}">
                    <div class="event-header">
                        <span class="event-icon">${icon}</span>
                        <span class="event-type">${event.event_type === 'WENT_DARK' ? 'WENT DARK' : 'CAME ONLINE'}</span>
                        <span class="event-time">${eventTime.toLocaleString()}</span>
                    </div>
                    <div class="event-body">
                        <p><strong>Ship:</strong> ${event.ship_name || 'Unknown'} (MMSI: ${event.mmsi})</p>
                        <p><strong>Position:</strong> ${event.latitude.toFixed(4)}, ${event.longitude.toFixed(4)}</p>
                        <p><strong>Distance:</strong> ${event.distance_nm ? event.distance_nm.toFixed(1) : '--'} NM</p>
                        ${detailsStr ? `<p><strong>Details:</strong> ${detailsStr}</p>` : ''}
                    </div>
                </div>
            `;
        }).join('');
    }

    async showTrackingStatus() {
        try {
            const resp = await fetch('/api/dark-ships/status');
            const data = await resp.json();

            if (!data.enabled) {
                this.notify('Dark ship tracking is not available', 'warning');
                return;
            }

            const tracking = data.tracking || {};
            const monitoring = data.monitoring || {};

            const statusHtml = `
                <div class="status-card">
                    <h4>Monitoring Configuration</h4>
                    <p>Center: ${monitoring.center_lat?.toFixed(4)}, ${monitoring.center_lon?.toFixed(4)}</p>
                    <p>Radius: ${monitoring.radius_nm} nautical miles</p>
                    <p>Dark Timeout: ${monitoring.dark_timeout_seconds} seconds</p>
                </div>
                <div class="status-card">
                    <h4>Current Tracking</h4>
                    <p>Total Ships Being Tracked: ${tracking.total_tracked || 0}</p>
                    <p>Currently Dark: ${tracking.currently_dark || 0}</p>
                </div>
            `;

            const modal = document.getElementById('tracking-status-modal');
            const content = document.getElementById('status-content');
            if (modal && content) {
                content.innerHTML = statusHtml;
                modal.classList.remove('hidden');
            }
        } catch (e) {
            console.error('Failed to get tracking status:', e);
            this.notify('Failed to get tracking status: ' + e.message, 'error');
        }
    }

    notify(msg, type = 'info') {
        console.log(`[${type.toUpperCase()}] ${msg}`);
        // Simple UI notification
        const statusEl = document.querySelector('.status-indicator span:last-child');
        if (statusEl) {
            statusEl.textContent = msg;
            setTimeout(() => { statusEl.textContent = 'System Online'; }, 5000);
        }
    }

    async checkStoredCredentials() {
        // Check if server has credentials configured in .env
        try {
            const checkRes = await fetch('/api/check-credentials');
            const checkData = await checkRes.json();
            
            console.log("Epic Archer: .env credentials validated. Link active.");
            const statusEl = document.getElementById('auth-status');
            if (statusEl) {
                statusEl.innerHTML = '<i class="fas fa-check-circle" style="color: #00ff00;"></i> .ENV CONFIGURED';
                statusEl.className = 'portal-status-msg text-success';
            }
            
            // Hide credential inputs - .env is the only source
            const credForm = document.querySelector('.auth-portal-content');
            if (credForm) {
                credForm.innerHTML = `
                    <div style="text-align: center; padding: 20px;">
                        <p style="color: #00ff00; font-size: 14px; margin-bottom: 10px;">OK Credentials loaded from .env</p>
                        <p style="color: #999; font-size: 12px;">To change credentials, edit .env and restart the container.</p>
                    </div>
                `;
            }
            
        } catch (err) {
            console.error("Epic Archer: .env credentials missing or invalid!", err);
            const statusEl = document.getElementById('auth-status');
            if (statusEl) {
                statusEl.innerHTML = '<i class="fas fa-exclamation-triangle text-error"></i> NO .ENV CREDENTIALS';
                statusEl.className = 'portal-status-msg text-error';
            }
            this.notify("WARNING: CRITICAL: Copernicus credentials not found in .env file. Analysis unavailable.", "error");
        }
    }

    async handleAuthSave(silent = false) {
        // .ENV-ONLY MODE: Credentials cannot be changed via UI
        // To update credentials, edit .env and restart the container
        if (!silent) {
            this.notify("Credentials are configured via .env only. Restart container to update.", "info");
        }
    }
}

window.addEventListener('DOMContentLoaded', () => {
    window.dashboard = new EpicArcherDashboard();
});
