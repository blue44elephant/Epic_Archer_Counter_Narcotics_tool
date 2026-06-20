

import os
import time
import json
import asyncio
import logging
import pickle
import importlib
import requests
import imageio.v3 as imageio
import numpy as np
import geopandas as gpd
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from shapely.geometry import LineString
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

import osmnx as ox
from sentinelhub import (
    SHConfig, SentinelHubRequest, DataCollection,
    BBox, CRS, MimeType, SentinelHubCatalog,
)
from dotenv import load_dotenv

# Dark ship tracking imports
try:
    from dark_ships_db import DarkShipsDatabase
    from ship_tracker import ShipTracker
    DARK_SHIPS_ENABLED = True
except ImportError:
    DARK_SHIPS_ENABLED = False
    logger_temp = logging.getLogger("EPIC_ARCHER")
    logger_temp.warning("Dark ships tracking module not available")

# -----------------------------------------------------------------------------
# Setup
# -----------------------------------------------------------------------------

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("EPIC_ARCHER")

SECONDS_OFFSET_B02_B04 = 1.01  # Sentinel-2 temporal sensing offset between B02 and B04

# Dynamic Storage Root (Expansion Drive or Local Fallback)
DATA_DIR = os.getenv("EPIC_ARCHER_DATA_DIR", os.path.join(os.getcwd(), "epic_archer_data"))
DETECTION_DIR = os.path.join(DATA_DIR, "sentinel_data/detections")
os.makedirs(DETECTION_DIR, exist_ok=True)

OVERPASS_MIRRORS = [
    "https://lz4.overpass-api.de/api/interpreter",
    "https://z.overpass-api.de/api/interpreter",
    "https://overpass.osm.ch/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]

OPENSKY_API_URL = "https://opensky-network.org/api/states/all"
OPENSKY_TOKEN_URL = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"
AISSTREAM_WS_URL = "wss://stream.aisstream.io/v0/stream"
_opensky_token = None
_opensky_token_expires_at = 0

# Network session with retries
_session = requests.Session()
_retry = Retry(
    total=2, backoff_factor=1.0,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET", "POST"],
)
_adapter = HTTPAdapter(max_retries=_retry)
_session.mount("http://", _adapter)
_session.mount("https://", _adapter)

ox.settings.requests_session = _session
ox.settings.requests_timeout = 30
ox.settings.overpass_rate_limit = False
ox.settings.max_query_area_size = 1_000_000_000_000
ox.settings.log_console = False
# OSMnx Cache Redirection
ox.settings.use_cache = True
ox.settings.cache_folder = os.path.join(DATA_DIR, "osm_cache")

# Copernicus Data Space config
CONFIG = SHConfig()
CONFIG.sh_client_id = os.getenv("COPERNICUS_CLIENT_ID")
CONFIG.sh_client_secret = os.getenv("COPERNICUS_CLIENT_SECRET")
CONFIG.sh_base_url = "https://sh.dataspace.copernicus.eu"
CONFIG.sh_token_url = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"

# SentinelHub Cache Redirection
CONFIG.cache_dir = os.path.join(DATA_DIR, "sh_cache")
os.makedirs(CONFIG.cache_dir, exist_ok=True)

# Note: We do NOT call CONFIG.save() here to avoid TOML serialization errors with NoneTypes
logger.info(f"Epic Archer Storage Link: {DATA_DIR}")
logger.info("Copernicus Data Space Authentication: CONFIGURED FOR CDSE")

FEATURED_SITES = [
    {"id": "v1", "name": "Braunschweig A7 (Research-Grade)", "bbox": [52.25, 10.45, 52.32, 10.55], "country": "Germany", "type": "high_volume"},
    {"id": "v2", "name": "Frankfurt A3 (High-Density)", "bbox": [50.05, 8.55, 50.12, 8.65], "country": "Germany", "type": "high_volume"},
    {"id": "v3", "name": "Karlsruhe A5 (Research-Standard)", "bbox": [48.95, 8.35, 49.05, 8.45], "country": "Germany", "type": "standard"},
]


# -----------------------------------------------------------------------------
# Helper math - mirrors S2TD.array_utils.math
# -----------------------------------------------------------------------------

def normalized_ratio(a, b):
    """(a - b) / (a + b), safe division."""
    denom = a + b
    with np.errstate(divide="ignore", invalid="ignore"):
        result = np.where(denom != 0, (a - b) / denom, 0.0)
    return result.astype(np.float32)


def rescale_s2(bands):
    """Rescale Sentinel-2 L2A reflectance values (typically 0-10000 int) to 0-1 float."""
    bands = bands.astype(np.float32)
    if np.nanmax(bands) > 10:  # likely DN scale
        bands /= 10000.0
    return bands


# -----------------------------------------------------------------------------
# Array subset - exact replica of S2TD.pick_arr_subset
# -----------------------------------------------------------------------------

def pick_arr_subset(arr, y, x, size):
    """Pick a sizexsize window centred on (y, x) from a 2D or 3D array."""
    size_low = size // 2
    size_up = size // 2
    if size_low + size_up < size:
        size_up += 1
    ymin = max(0, y - size_low)
    ymax = max(0, y + size_up)
    xmin = max(0, x - size_low)
    xmax = max(0, x + size_up)
    if arr.ndim == 2:
        return arr[ymin:ymax, xmin:xmax]
    elif arr.ndim == 3:
        return arr[:, ymin:ymax, xmin:xmax]
    return arr


# -----------------------------------------------------------------------------
# Feature stack - exact 7 features as in S2TD._build_feature_stack (Table 1)
# -----------------------------------------------------------------------------

def build_feature_stack(data):
    """
    Build the 7-feature stack from Sentinel-2 bands.

    Input `data` shape: (H, W, 5) with channels [B04(R), B03(G), B02(B), B08(NIR), CLM].

    Feature order (Table 1, Fisser et al. 2022):
        0: variance of (B04, B03, B02)
        1: normalized_ratio(B04, B02)  - red / blue
        2: normalized_ratio(B03, B02)  - green / blue
        3: B04 - mean(B04)
        4: B03 - mean(B03)
        5: B02 - mean(B02)
        6: B08 - mean(B08)
    """
    R = data[:, :, 0].astype(np.float32)    # B04
    G = data[:, :, 1].astype(np.float32)    # B03
    B = data[:, :, 2].astype(np.float32)    # B02
    NIR = data[:, :, 3].astype(np.float32)  # B08
    CLM = data[:, :, 4]

    # Rescale if needed
    bands = np.stack([R, G, B, NIR], axis=0)
    bands = rescale_s2(bands)
    R, G, B, NIR = bands[0], bands[1], bands[2], bands[3]

    # Cloud mask -> NaN
    cloud = CLM > 0
    R[cloud] = np.nan
    G[cloud] = np.nan
    B[cloud] = np.nan
    NIR[cloud] = np.nan

    H, W = R.shape
    fs = np.zeros((7, H, W), dtype=np.float32)

    # Check for any valid data to avoid "Mean of empty slice" warnings
    if np.any(~cloud):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            # Feature 0: variance of visible bands
            fs[0] = np.nanvar(np.stack([R, G, B], axis=0), axis=0, ddof=0)

            # Features 1-2: normalized ratios
            fs[1] = normalized_ratio(R, B)
            fs[2] = normalized_ratio(G, B)

            # Features 3-6: mean-centered bands
            fs[3] = R - np.nanmean(R)
            fs[4] = G - np.nanmean(G)
            fs[5] = B - np.nanmean(B)
            fs[6] = NIR - np.nanmean(NIR)
    else:
        # All pixels are cloud-masked
        fs.fill(np.nan)

    # Ensure NaN consistency
    nan_mask = np.isnan(fs[3])
    fs[:, nan_mask] = np.nan

    return {
        "feature_stack": fs,
        "bands": {"R": R, "G": G, "B": B, "NIR": NIR},
        "cloud_mask": cloud,
    }


# -----------------------------------------------------------------------------
# RF Model loading
# -----------------------------------------------------------------------------

# Path to the trained Random Forest model from S2TruckDetect
RF_MODEL_PATH = os.getenv("RF_MODEL_PATH", "rf_model.pickle")
_rf_model = None


def load_rf_model(path=None):
    """Load the trained RF model from pickle. Returns None if not found."""
    global _rf_model
    p = path or RF_MODEL_PATH
    if _rf_model is not None:
        return _rf_model
    if os.path.isfile(p):
        try:
            _rf_model = pickle.load(open(p, "rb"))
            logger.info(f"Loaded trained RF model from {p}")
            return _rf_model
        except Exception as e:
            logger.error(f"Failed to load RF model from {p}: {e}")
    else:
        logger.warning(f"RF model not found at {p} - will use proxy classifier (lower accuracy)")
    return None


# -----------------------------------------------------------------------------
# Classification - real RF (preferred) or proxy fallback
# -----------------------------------------------------------------------------

def rf_classify(feature_stack, road_mask, rf_model):
    """
    Classify pixels using the trained Random Forest model.
    Exact replica of S2TD._predict + _postprocess_prediction.

    :param feature_stack: (7, H, W) feature array
    :param road_mask: (H, W) binary road mask
    :param rf_model: trained sklearn RandomForestClassifier
    :return: (probabilities (4, H, W), prediction (H, W) int8)
    """
    H, W = feature_stack.shape[1], feature_stack.shape[2]

    # Reshape to (n_pixels, 7) for sklearn
    vars_reshaped = []
    for band_idx in range(feature_stack.shape[0]):
        vars_reshaped.append(feature_stack[band_idx].flatten())
    vars_reshaped = np.array(vars_reshaped).swapaxes(0, 1)  # (n_pixels, 7)

    # Build NaN mask - exclude NaN and Inf pixels
    nan_mask_flat = np.zeros_like(vars_reshaped)
    for var_idx in range(vars_reshaped.shape[1]):
        nan_mask_flat[:, var_idx] = ~np.isnan(vars_reshaped[:, var_idx])
    not_nan = (np.nanmin(nan_mask_flat, axis=1).astype(bool)
               & np.min(np.isfinite(vars_reshaped), axis=1).astype(bool))

    # Run RF predict_proba on valid pixels only
    if not np.any(not_nan):
        # Graceful return if no valid pixels found (e.g., all cloud masked)
        probabilities_shaped = np.zeros((4, H, W), dtype=np.float32)
        classification = np.zeros((H, W), dtype=np.int8)
        return probabilities_shaped, classification

    predictions_flat = rf_model.predict_proba(vars_reshaped[not_nan])

    # Map probabilities back to spatial grid
    n_classes = predictions_flat.shape[1] 
    probabilities_shaped = np.zeros((n_classes, H * W), dtype=np.float32)
    for idx in range(n_classes):
        probabilities_shaped[idx, not_nan] = predictions_flat[:, idx]

    probabilities_shaped = probabilities_shaped.reshape((n_classes, H, W))

    # Zero out NaN positions
    nan_2d = np.isnan(feature_stack[0])
    probabilities_shaped[:, nan_2d] = 0

    # Post-process: suppress low-confidence background (exact S2TD logic)
    probabilities_shaped[1][probabilities_shaped[1] < 0.75] = 0

    classification = np.nanargmax(probabilities_shaped, axis=0).astype(np.int8) + 1
    classification[np.max(probabilities_shaped, axis=0) == 0] = 0
    classification[nan_2d] = 0

    # Apply road mask
    rm = road_mask.astype(bool)
    classification[~rm] = 0

    return probabilities_shaped, classification


def proxy_classify(feature_stack, road_mask):
    """
    Heuristic proxy when RF model is unavailable. Lower accuracy.

    Produces:
        probabilities: (4, H, W) - class probs for [background, blue, green, red]
        prediction:    (H, W)    - int8 labels {0=nan, 1=background, 2=blue, 3=green, 4=red}
    """
    fs = feature_stack  # (7, H, W)
    H, W = fs.shape[1], fs.shape[2]
    probs = np.zeros((4, H, W), dtype=np.float32)

    centered_R = fs[3]
    centered_G = fs[4]
    centered_B = fs[5]
    var_feat = fs[0]
    nratio_rb = fs[1]
    nratio_gb = fs[2]

    rm = road_mask.astype(bool)
    nan_mask = np.isnan(centered_R)

    blue_score = np.clip(-nratio_rb * 2 + centered_B * 5 + var_feat * 10, 0, None)
    blue_score[~rm | nan_mask] = 0

    green_score = np.clip(nratio_gb * 2 + centered_G * 5 + var_feat * 10, 0, None)
    green_score[~rm | nan_mask] = 0

    red_score = np.clip(nratio_rb * 2 + centered_R * 5 + var_feat * 10, 0, None)
    red_score[~rm | nan_mask] = 0

    total = blue_score + green_score + red_score + 1e-8
    probs[1] = blue_score / total
    probs[2] = green_score / total
    probs[3] = red_score / total
    probs[0] = 1.0 - np.max(probs[1:], axis=0)

    probs[0][probs[0] < 0.75] = 0

    classification = np.nanargmax(probs, axis=0).astype(np.int8) + 1
    classification[np.max(probs, axis=0) == 0] = 0
    classification[nan_mask] = 0
    classification[~rm] = 0

    return probs, classification


def classify(feature_stack, road_mask, rf_model=None):
    """
    Unified classifier entry point.
    Uses trained RF if model is provided, otherwise falls back to proxy.
    """
    if rf_model is not None:
        logger.debug("Using trained RF model for classification")
        return rf_classify(feature_stack, road_mask, rf_model)
    else:
        logger.debug("Using proxy classifier (no RF model loaded)")
        return proxy_classify(feature_stack, road_mask)


# -----------------------------------------------------------------------------
# Object extraction - faithful port of S2TD ObjectExtractor
# -----------------------------------------------------------------------------

class ObjectExtractor:
    """
    Extracts truck objects from the RF prediction raster using recursive
    neighbourhood clustering, matching the S2TD reference implementation.
    """

    def __init__(self, probabilities, lat_arr, lon_arr):
        """
        :param probabilities: (4, H, W) class probabilities
        :param lat_arr: 1-D array of latitude per row
        :param lon_arr: 1-D array of longitude per column
        """
        self.probabilities = probabilities
        self.lat = lat_arr
        self.lon = lon_arr

    def extract(self, predictions_arr):
        """Main extraction loop over all blue (class 2) seed pixels."""
        preds = predictions_arr.copy()
        probs = self.probabilities.copy()

        preds[preds == 1] = 0  # zero out background
        blue_ys, blue_xs = np.where(preds == 2)
        detections = []
        sub_size = 9

        for i in range(len(blue_ys)):
            y_blue, x_blue = int(blue_ys[i]), int(blue_xs[i])
            if preds[y_blue, x_blue] == 0:
                continue

            subset_9 = pick_arr_subset(preds, y_blue, x_blue, sub_size).copy()
            subset_3 = pick_arr_subset(preds, y_blue, x_blue, 3).copy()
            subset_9_probs = pick_arr_subset(probs, y_blue, x_blue, sub_size).copy()

            half_idx_y = y_blue if subset_9.shape[0] < sub_size else subset_9.shape[0] // 2
            half_idx_x = x_blue if subset_9.shape[1] < sub_size else subset_9.shape[1] // 2
            try:
                current_value = subset_9[half_idx_y, half_idx_x]
            except IndexError:
                half_idx_y, half_idx_x = sub_size // 2, sub_size // 2
                current_value = subset_9[half_idx_y, half_idx_x]

            new_value = 100
            if not all(v in subset_9 for v in [2, 3, 4]):
                continue

            cluster, seen_idx, seen_vals, _ = self._cluster_array(
                arr=subset_9, probs=subset_9_probs,
                point=[half_idx_y, half_idx_x],
                new_value=new_value, current_value=current_value,
                yet_seen_indices=[], yet_seen_values=[],
                skipped_one=False,
            )

            if np.count_nonzero(cluster == new_value) < 3:
                continue

            det = self._postprocess_cluster(
                cluster, preds, probs, subset_3,
                y_blue, x_blue,
                half_idx_y, half_idx_x,
                new_value,
            )
            if det is not None:
                preds = det["updated_preds"]
                detections.append(det["detection"])

        return detections

    def _cluster_array(self, arr, probs, point, new_value, current_value,
                       yet_seen_indices, yet_seen_values, skipped_one):
        """Recursive neighbourhood clustering - matches S2TD._cluster_array."""
        if len(yet_seen_indices) == 0:
            yet_seen_indices.append(point)
            yet_seen_values.append(current_value)

        arr_mod = arr.copy()
        arr_mod[point[0], point[1]] = 0

        window_3x3 = pick_arr_subset(arr_mod, point[0], point[1], 3).copy()
        if window_3x3.shape[0] >= 2 and window_3x3.shape[1] >= 2:
            cy = min(1, window_3x3.shape[0] - 1)
            cx = min(1, window_3x3.shape[1] - 1)
            if window_3x3[cy, cx] == 2:
                window_3x3[window_3x3 == 4] = 1  # eliminate reds near blue

        y, x = point[0], point[1]
        window_3x3_probs = pick_arr_subset(probs, y, x, 3)

        windows = [window_3x3]
        windows_probs = [window_3x3_probs]
        if current_value == 4 or skipped_one:
            windows = windows[0:1]

        ys, xs = np.array([], dtype=int), np.array([], dtype=int)
        window_idx = 0
        offset_y, offset_x = 0, 0

        while len(ys) == 0 and window_idx < len(windows):
            window = windows[window_idx]
            window_p = windows_probs[window_idx]
            offset_y = window.shape[0] // 2
            offset_x = window.shape[1] // 2

            go_next = (current_value + 1) in window or current_value == 2
            target_value = current_value + 1 if go_next else current_value
            match = window == target_value
            if np.count_nonzero(match) == 0:
                target_value = current_value
                match = window == target_value

            ys_found, xs_found = np.where(match)

            # Probability-based tie-breaking
            if len(ys_found) > 1 and window_p.ndim == 3 and window_p.shape[0] > (target_value - 1):
                wp_target = window_p[target_value - 1] * match
                max_prob_mask = (wp_target == np.max(wp_target))
                ys_found, xs_found = np.where(max_prob_mask)

            ys, xs = ys_found, xs_found
            window_idx += 1

        ymin_w = max(0, point[0] - offset_y)
        xmin_w = max(0, point[1] - offset_x)

        for y_local, x_local in zip(ys, xs):
            ny, nx = ymin_w + int(y_local), xmin_w + int(x_local)
            if [ny, nx] in yet_seen_indices:
                continue
            if ny < 0 or ny >= arr.shape[0] or nx < 0 or nx >= arr.shape[1]:
                continue
            try:
                cv = arr[ny, nx]
            except IndexError:
                continue

            # Red already seen but this is green or blue -> skip
            if 4 in yet_seen_values and cv <= 3:
                continue

            arr_mod[ny, nx] = new_value
            yet_seen_indices.append([ny, nx])
            yet_seen_values.append(cv)

            # Guard: avoid picking many more reds than blues and greens
            n_blue = sum(1 for v in yet_seen_values if v == 2)
            n_green = sum(1 for v in yet_seen_values if v == 3)
            n_red = sum(1 for v in yet_seen_values if v == 4)
            if n_red > n_blue and n_red > n_green:
                break

            arr_mod, yet_seen_indices, yet_seen_values, skipped_one = self._cluster_array(
                arr_mod, probs, [ny, nx], new_value, cv,
                yet_seen_indices, yet_seen_values, skipped_one,
            )

        arr_mod[point[0], point[1]] = new_value
        return arr_mod, yet_seen_indices, yet_seen_values, skipped_one

    def _postprocess_cluster(self, cluster, preds_copy, probs, subset_3,
                             y_blue, x_blue, half_idx_y, half_idx_x,
                             new_value):
        """Validate cluster and produce a detection dict - mirrors S2TD._postprocess_cluster."""
        # Add neighbouring blues from the 3x3 window
        ys_ba, xs_ba = np.where(subset_3 == 2)
        ys_ba = ys_ba + half_idx_y - 1
        xs_ba = xs_ba + half_idx_x - 1
        for yb, xb in zip(ys_ba, xs_ba):
            yb_c = int(np.clip(yb, 0, cluster.shape[0] - 1))
            xb_c = int(np.clip(xb, 0, cluster.shape[1] - 1))
            cluster[yb_c, xb_c] = new_value

        cluster[cluster != new_value] = 0
        cys, cxs = np.where(cluster == new_value)
        if len(cys) == 0:
            return None

        # Map subset coords back to full array
        ymin_sub = int(np.clip(y_blue - half_idx_y, 0, np.inf))
        xmin_sub = int(np.clip(x_blue - half_idx_x, 0, np.inf))
        cys_full = cys + ymin_sub
        cxs_full = cxs + xmin_sub

        ymin = int(np.min(cys_full))
        xmin = int(np.min(cxs_full))
        ymax = int(np.max(cys_full)) + 1  # +1: box extends to upper bound of pixel
        xmax = int(np.max(cxs_full)) + 1

        H, W = preds_copy.shape
        ymin, ymax = max(0, ymin), min(H, ymax)
        xmin, xmax = max(0, xmin), min(W, xmax)

        box_preds = preds_copy[ymin:ymax, xmin:xmax].copy()
        box_probs = probs[1:, ymin:ymax, xmin:xmax].copy()  # classes 2,3,4 -> indices 0,1,2

        # Spectral probability scores (exact S2TD logic)
        max_probs = []
        for cls_offset, cls_val in enumerate([2, 3, 4]):
            mask = (box_preds == cls_val)
            vals = box_probs[cls_offset] * mask
            mp = float(np.nanmax(vals)) if np.any(mask) else 0.0
            max_probs.append(mp)

        mean_max_spectral_probability = float(np.nanmean(max_probs))
        mean_spectral_probability = float(np.nanmean(np.nanmax(box_probs, axis=0)))

        # Validation checks
        all_given = all(v in box_preds for v in [2, 3, 4])
        large_enough = box_preds.shape[0] > 2 or box_preds.shape[1] > 2
        too_large = box_preds.shape[0] > 5 or box_preds.shape[1] > 5

        if too_large or not all_given or not large_enough:
            return None

        # Score: TWO terms - matches reference
        score = mean_max_spectral_probability + mean_spectral_probability
        if score <= 1.2:
            return None

        # Direction (blue -> red vector)
        by, bx = np.where(box_preds == 2)
        ry, rx = np.where(box_preds == 4)
        blue_idx = np.array([by[0], bx[0]], dtype=np.int8)
        red_idx = np.array([ry[0], rx[0]], dtype=np.int8)
        vector = (blue_idx - red_idx) * np.array([1, -1], dtype=np.int8)
        heading = float(np.degrees(np.arctan2(vector[1], vector[0])) % 360)

        # Speed
        diameter = max(box_preds.shape) * 10 - 10
        speed_kmh = float(np.sqrt(diameter * 20) / SECONDS_OFFSET_B02_B04 * 3.6)

        # Geo-coordinates (centre of detection box)
        lat_centre = float((self.lat[ymin] + self.lat[min(ymax, len(self.lat) - 1)]) / 2)
        lon_centre = float((self.lon[xmin] + self.lon[min(xmax, len(self.lon) - 1)]) / 2)

        # Zero out detected pixels to prevent re-detection
        preds_copy[ymin:ymax, xmin:xmax] *= np.zeros_like(box_preds)
        # Also zero 3x3 around blue pixels
        blue_in_box = np.where(box_preds == 2)
        for yb, xb in zip(blue_in_box[0], blue_in_box[1]):
            y0, y1 = max(0, ymin + yb - 1), min(H, ymin + yb + 2)
            x0, x1 = max(0, xmin + xb - 1), min(W, xmin + xb + 2)
            preds_copy[y0:y1, x0:x1] *= (preds_copy[y0:y1, x0:x1] != 2).astype(np.int8)

        crop_id = f"truck_{int(time.time() * 1000)}_{ymin}_{xmin}.png"

        return {
            "updated_preds": preds_copy,
            "detection": {
                "lat": lat_centre,
                "lon": lon_centre,
                "confidence": float(min(score / 2.4, 1.0)),
                "s_score": round(score, 3),
                "speed_kmh": round(speed_kmh, 1),
                "heading": round(heading, 1),
                "heading_desc": self._direction_to_compass(heading),
                "id": crop_id,
                "image_url": f"/detections/{crop_id}",
                "box_shape": list(box_preds.shape),
                "max_probs": {"blue": max_probs[0], "green": max_probs[1], "red": max_probs[2]},
            },
        }

    @staticmethod
    def _direction_to_compass(deg):
        bins = np.arange(0, 359, 45, dtype=np.float32)
        labels = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
        return labels[int(np.argmin(np.abs(bins - deg)))]


# -----------------------------------------------------------------------------
# Detector Base Class & Multi-Sensor Framework
# -----------------------------------------------------------------------------

from abc import ABC, abstractmethod
from scipy import ndimage


class BaseDetector(ABC):
    """Abstract base for all orbital activity detectors."""

    def __init__(self, rf_model=None):
        self.rf_model = rf_model
        self.detector_type = "base"

    @abstractmethod
    def detect(self, data, bbox_coords, timestamp, road_mask=None):
        """
        Run detection on satellite data.

        :param data: sensor-specific array (H, W, C)
        :param bbox_coords: [min_lat, min_lon, max_lat, max_lon]
        :param timestamp: ISO timestamp
        :param road_mask: optional (H, W) binary mask
        :return: list of detection dicts
        """
        pass


class TruckDetector(BaseDetector):
    """Sentinel-2 RGB motion smear for vehicle detection (original)."""

    def __init__(self, rf_model=None):
        super().__init__(rf_model)
        self.detector_type = "truck"

    def detect(self, data, bbox_coords, timestamp, road_mask=None):
        """Detects vehicles on roads via S2 motion smear."""
        if road_mask is None:
            road_mask = np.ones(data.shape[:2], dtype=np.uint8)

        min_lat, min_lon, max_lat, max_lon = bbox_coords
        H, W = data.shape[:2]

        # Build feature stack
        feat = build_feature_stack(data)
        feature_stack = feat["feature_stack"]

        # Classify
        probs, prediction = classify(feature_stack, road_mask, self.rf_model)

        # Lat/lon arrays
        lat_arr = np.linspace(max_lat, min_lat, H)
        lon_arr = np.linspace(min_lon, max_lon, W)

        # Extract
        extractor = ObjectExtractor(probs, lat_arr, lon_arr)
        detections = extractor.extract(prediction)

        # Add timestamp and type
        for det in detections:
            det["timestamp"] = timestamp
            det["detector_type"] = "truck"
            try:
                self._save_crop(data, det, H, W, min_lat, min_lon, max_lat, max_lon)
            except Exception as e:
                logger.warning(f"Could not save crop for {det['id']}: {e}")

        return detections

    def _save_crop(self, data, det, H, W, min_lat, min_lon, max_lat, max_lon):
        """Save a 20x20 RGB crop centred on detection."""
        cy = int((max_lat - det["lat"]) / (max_lat - min_lat + 1e-9) * H)
        cx = int((det["lon"] - min_lon) / (max_lon - min_lon + 1e-9) * W)
        cy, cx = int(np.clip(cy, 0, H - 1)), int(np.clip(cx, 0, W - 1))

        y0, y1 = max(0, cy - 10), min(H, cy + 10)
        x0, x1 = max(0, cx - 10), min(W, cx + 10)

        rgb = data[y0:y1, x0:x1, :3].astype(np.float32)
        rgb = rescale_s2(rgb)
        rgb = (np.clip(rgb, 0, 0.3) / 0.3 * 255).astype(np.uint8)

        path = os.path.join(DETECTION_DIR, det["id"])
        imageio.imwrite(path, rgb)


class ShipWaveDetector(BaseDetector):
    """Sentinel-2 wave pattern detection for maritime vessels."""

    def __init__(self, rf_model=None):
        super().__init__(rf_model)
        self.detector_type = "ship_wave"

    def detect(self, data, bbox_coords, timestamp, road_mask=None):
        """Detects ships via wake patterns in S2 multispectral data."""
        min_lat, min_lon, max_lat, max_lon = bbox_coords
        H, W = data.shape[:2]

        # Extract RGB + NIR
        R = data[:, :, 0].astype(np.float32)
        G = data[:, :, 1].astype(np.float32)
        B = data[:, :, 2].astype(np.float32)
        NIR = data[:, :, 3].astype(np.float32)
        CLM = data[:, :, 4]

        bands = np.stack([R, G, B, NIR], axis=0)
        bands = rescale_s2(bands)
        R, G, B, NIR = bands[0], bands[1], bands[2], bands[3]

        # Wave signature: high variance in B channel (water scatter)
        # + chromaticity anomalies from motion
        cloud = CLM > 0
        R[cloud] = np.nan
        G[cloud] = np.nan
        B[cloud] = np.nan
        NIR[cloud] = np.nan

        # Local variance in blue channel (wake turbulence)
        from scipy.ndimage import uniform_filter
        B_mean = uniform_filter(np.nan_to_num(B, 0), size=5)
        B_var = uniform_filter(np.nan_to_num((B - B_mean)**2, 0), size=5)

        # Normalized water index (higher over water)
        nwi = normalized_ratio(NIR, G)
        nwi[cloud] = 0

        # Wave anomaly: high B variance + water presence
        wave_score = B_var * (nwi > 0).astype(np.float32)
        wave_score[cloud] = 0

        # Threshold & cluster
        threshold = np.nanpercentile(wave_score, 95)
        candidates = wave_score > threshold

        # Find connected components
        labeled, num_features = ndimage.label(candidates)

        detections = []
        lat_arr = np.linspace(max_lat, min_lat, H)
        lon_arr = np.linspace(min_lon, max_lon, W)

        for label_id in range(1, num_features + 1):
            ys, xs = np.where(labeled == label_id)
            if len(ys) < 5:  # minimum cluster size
                continue

            # Centroid
            cy, cx = int(np.mean(ys)), int(np.mean(xs))
            lat_c = lat_arr[cy]
            lon_c = lon_arr[cx]

            # Cluster extent (wake length estimate)
            y_span = np.max(ys) - np.min(ys)
            x_span = np.max(xs) - np.min(xs)
            wake_length_km = max(y_span, x_span) * 111 / H  # rough conversion

            # Direction: PCA on coordinates
            coords = np.column_stack([ys - cy, xs - cx])
            cov = np.cov(coords.T)
            eigvals, eigvecs = np.linalg.eigh(cov)
            heading = float(np.degrees(np.arctan2(eigvecs[1, 1], eigvecs[0, 1])) % 360)

            # Speed estimate (empirical for wake signature)
            speed_kmh = float(np.sqrt(wake_length_km * 15))

            confidence = float(np.clip(np.mean(wave_score[ys, xs]) / threshold, 0, 1))

            det = {
                "lat": float(lat_c),
                "lon": float(lon_c),
                "confidence": confidence,
                "speed_kmh": round(speed_kmh, 1),
                "heading": round(heading, 1),
                "heading_desc": self._direction_to_compass(heading),
                "id": f"ship_{int(time.time() * 1000)}_{cy}_{cx}.png",
                "image_url": f"/detections/ship_{int(time.time() * 1000)}_{cy}_{cx}.png",
                "timestamp": timestamp,
                "detector_type": "ship_wave",
                "wake_length_km": round(wake_length_km, 2),
            }
            detections.append(det)

        return detections

    @staticmethod
    def _direction_to_compass(deg):
        bins = np.arange(0, 359, 45, dtype=np.float32)
        labels = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
        return labels[int(np.argmin(np.abs(bins - deg)))]


class AircraftDetector(BaseDetector):
    """Sentinel-2 runway activity via motion smear on linear features."""

    def __init__(self, rf_model=None):
        super().__init__(rf_model)
        self.detector_type = "aircraft"

    def detect(self, data, bbox_coords, timestamp, road_mask=None):
        """Detects fast-moving aircraft on runways."""
        min_lat, min_lon, max_lat, max_lon = bbox_coords
        H, W = data.shape[:2]

        # Use same feature stack as trucks
        feat = build_feature_stack(data)
        feature_stack = feat["feature_stack"]
        CLM = data[:, :, 4]

        # Aircraft signatures: high motion smear (large magnitude in feature 1-2)
        motion_score = np.abs(feature_stack[1]) + np.abs(feature_stack[2])
        motion_score[CLM > 0] = 0

        # Runway constraint: elongated, linear features
        # Threshold high-motion pixels
        threshold = np.nanpercentile(motion_score, 98)
        candidates = motion_score > threshold

        # Morphological filter: favor linear structures
        from scipy.ndimage import binary_dilation, binary_erosion
        candidates = binary_erosion(candidates, iterations=1)
        candidates = binary_dilation(candidates, iterations=2)

        labeled, num_features = ndimage.label(candidates)

        detections = []
        lat_arr = np.linspace(max_lat, min_lat, H)
        lon_arr = np.linspace(min_lon, max_lon, W)

        for label_id in range(1, num_features + 1):
            ys, xs = np.where(labeled == label_id)
            if len(ys) < 10:  # aircraft tracks are longer than truck clusters
                continue

            # Check linearity: eigenvalue ratio
            coords = np.column_stack([ys, xs])
            if coords.shape[0] > 2:
                cov = np.cov(coords.T)
                eigvals = np.sort(np.linalg.eigvalsh(cov))[::-1]
                linearity = 1 - (eigvals[1] / (eigvals[0] + 1e-6))
                if linearity < 0.7:  # not linear enough
                    continue

            # Centroid
            cy, cx = int(np.mean(ys)), int(np.mean(xs))
            lat_c = lat_arr[cy]
            lon_c = lon_arr[cx]

            # Length (runway constraint: > 1 km)
            y_span = np.max(ys) - np.min(ys)
            x_span = np.max(xs) - np.min(xs)
            length_km = max(y_span, x_span) * 111 / H
            if length_km < 1.0:
                continue

            # Direction
            eigvecs = np.linalg.eigh(cov)[1]
            heading = float(np.degrees(np.arctan2(eigvecs[1, 1], eigvecs[0, 1])) % 360)

            # Speed: very high for aircraft
            speed_kmh = float(np.sqrt(length_km * 50))

            confidence = float(np.clip(np.mean(motion_score[ys, xs]) / threshold, 0, 1))

            det = {
                "lat": float(lat_c),
                "lon": float(lon_c),
                "confidence": confidence,
                "speed_kmh": round(speed_kmh, 1),
                "heading": round(heading, 1),
                "heading_desc": self._direction_to_compass(heading),
                "id": f"aircraft_{int(time.time() * 1000)}_{cy}_{cx}.png",
                "image_url": f"/detections/aircraft_{int(time.time() * 1000)}_{cy}_{cx}.png",
                "timestamp": timestamp,
                "detector_type": "aircraft",
                "track_length_km": round(length_km, 2),
            }
            detections.append(det)

        return detections

    @staticmethod
    def _direction_to_compass(deg):
        bins = np.arange(0, 359, 45, dtype=np.float32)
        labels = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
        return labels[int(np.argmin(np.abs(bins - deg)))]


class TrainDetector(BaseDetector):
    """Sentinel-2 train detection via straight-line motion on rail geometry."""

    def __init__(self, rf_model=None):
        super().__init__(rf_model)
        self.detector_type = "train"

    def detect(self, data, bbox_coords, timestamp, road_mask=None):
        """Detects trains on tracks via motion smear and rail geometry."""
        min_lat, min_lon, max_lat, max_lon = bbox_coords
        H, W = data.shape[:2]

        feat = build_feature_stack(data)
        feature_stack = feat["feature_stack"]
        CLM = data[:, :, 4]

        # Motion metric (similar to aircraft but stricter geometry)
        motion_score = np.abs(feature_stack[1]) + np.abs(feature_stack[2])
        motion_score[CLM > 0] = 0

        threshold = np.nanpercentile(motion_score, 97)
        candidates = motion_score > threshold

        labeled, num_features = ndimage.label(candidates)

        detections = []
        lat_arr = np.linspace(max_lat, min_lat, H)
        lon_arr = np.linspace(min_lon, max_lon, W)

        for label_id in range(1, num_features + 1):
            ys, xs = np.where(labeled == label_id)
            if len(ys) < 15:  # trains: medium-long tracks
                continue

            coords = np.column_stack([ys, xs])
            if coords.shape[0] > 2:
                cov = np.cov(coords.T)
                eigvals = np.sort(np.linalg.eigvalsh(cov))[::-1]
                linearity = 1 - (eigvals[1] / (eigvals[0] + 1e-6))
                if linearity < 0.8:  # very linear (rail constraint)
                    continue

            cy, cx = int(np.mean(ys)), int(np.mean(xs))
            lat_c = lat_arr[cy]
            lon_c = lon_arr[cx]

            y_span = np.max(ys) - np.min(ys)
            x_span = np.max(xs) - np.min(xs)
            length_km = max(y_span, x_span) * 111 / H

            # Speed: trains are slower than aircraft but faster than trucks
            speed_kmh = float(np.clip(np.sqrt(length_km * 30), 20, 150))

            eigvecs = np.linalg.eigh(cov)[1]
            heading = float(np.degrees(np.arctan2(eigvecs[1, 1], eigvecs[0, 1])) % 360)

            confidence = float(np.clip(np.mean(motion_score[ys, xs]) / threshold, 0, 1))

            det = {
                "lat": float(lat_c),
                "lon": float(lon_c),
                "confidence": confidence,
                "speed_kmh": round(speed_kmh, 1),
                "heading": round(heading, 1),
                "heading_desc": self._direction_to_compass(heading),
                "id": f"train_{int(time.time() * 1000)}_{cy}_{cx}.png",
                "image_url": f"/detections/train_{int(time.time() * 1000)}_{cy}_{cx}.png",
                "timestamp": timestamp,
                "detector_type": "train",
                "track_length_km": round(length_km, 2),
            }
            detections.append(det)

        return detections

    @staticmethod
    def _direction_to_compass(deg):
        bins = np.arange(0, 359, 45, dtype=np.float32)
        labels = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
        return labels[int(np.argmin(np.abs(bins - deg)))]


class NightLightsDetector(BaseDetector):
    """VIIRS night-light activity detection."""

    def __init__(self, rf_model=None):
        super().__init__(rf_model)
        self.detector_type = "night_lights"

    def detect(self, data, bbox_coords, timestamp, road_mask=None):
        """Detects economic/military activity via night-light clustering."""
        min_lat, min_lon, max_lat, max_lon = bbox_coords

        # NOAA VIIRS DNB tile URL
        date_str = timestamp[:10].replace("-", "")
        url_template = f"https://map1.vis.earthdata.nasa.gov/wmts-webmerc/VIIRS_CityLights_2012/default//GoogleMapsCompatible_Level8/{date_str}/GoogleMapsCompatible_Level8_VIIRS_CityLights_2012{date_str}_v1.0.0.tif"

        try:
            import rasterio
            from rasterio.windows import Window
            from rasterio.vrt import WarpedVRT

            # Simple grid-based detection: fetch VIIRS tile and threshold
            # This is a simplified approach; full implementation would use NOAA direct download
            logger.debug(f"Fetching VIIRS night-lights for {date_str}")

            # For now, return a placeholder (full implementation requires NOAA API)
            # In production: use https://ladsweb.modaps.eosdis.nasa.gov
            detections = []

            # Simulate detection for demo
            det = {
                "lat": (min_lat + max_lat) / 2,
                "lon": (min_lon + max_lon) / 2,
                "confidence": 0.6,
                "light_intensity": 45.3,
                "id": f"nightlights_{int(time.time() * 1000)}.png",
                "image_url": f"/detections/nightlights_{int(time.time() * 1000)}.png",
                "timestamp": timestamp,
                "detector_type": "night_lights",
                "note": "Integration with NOAA VIIRS requires API key. Demo mode.",
            }
            detections.append(det)

            return detections

        except Exception as e:
            logger.warning(f"Night-lights detector error: {e}")
            return []


class SARVesselDetector(BaseDetector):
    """Sentinel-1 SAR for vessel detection via radar backscatter."""

    def __init__(self, rf_model=None):
        super().__init__(rf_model)
        self.detector_type = "sar_vessel"

    def detect(self, data, bbox_coords, timestamp, road_mask=None):
        """Detects vessels using Sentinel-1 SAR backscatter (VV/VH ratio)."""
        min_lat, min_lon, max_lat, max_lon = bbox_coords

        try:
            # Query Sentinel-1 GRD
            sh_bbox = BBox(bbox=[min_lon, min_lat, max_lon, max_lat], crs=CRS.WGS84)
            
            s1_collection = DataCollection.SENTINEL1_IW.define_from(
                "s1", service_url=CONFIG.sh_base_url,
            )

            end_date_str = timestamp[:10]
            start_date_str = (pd.to_datetime(timestamp[:10]) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")

            catalog = SentinelHubCatalog(config=CONFIG)
            search_results = list(catalog.search(
                s1_collection, bbox=sh_bbox,
                datetime=f"{start_date_str}T00:00:00Z/{end_date_str}T23:59:59Z",
                fields={"include": ["properties.datetime", "id"], "exclude": []}
            ))

            detections = []

            if not search_results:
                logger.debug("No Sentinel-1 data in timeframe")
                return detections

            # Use first available SAR image
            sar_obs = search_results[0]

            # Evalscript: output VV and VH polarization
            evalscript = """//VERSION=3
function setup() {
  return {
    input: ["VV", "VH"],
    output: { id: "default", bands: 2, sampleType: "FLOAT32" }
  };
}
function evaluatePixel(s) {
  return [s.VV, s.VH];
}"""

            req_sar = SentinelHubRequest(
                evalscript=evalscript,
                input_data=[SentinelHubRequest.input_data(
                    data_collection=s1_collection,
                    time_interval=(sar_obs["properties"]["datetime"], sar_obs["properties"]["datetime"]),
                )],
                responses=[SentinelHubRequest.output_response("default", MimeType.TIFF)],
                bbox=sh_bbox, config=CONFIG,
            )

            sar_data_list = req_sar.get_data()
            if not sar_data_list:
                logger.debug("Failed to fetch SAR data")
                return detections

            sar_data = sar_data_list[0]
            H, W = sar_data.shape[:2]

            # Extract VV and VH
            vv = sar_data[:, :, 0].astype(np.float32)
            vh = sar_data[:, :, 1].astype(np.float32)

            # Convert to dB
            vv_db = 10 * np.log10(np.maximum(vv, 1e-6))
            vh_db = 10 * np.log10(np.maximum(vh, 1e-6))

            # Vessel signature: high VV + high VV/VH ratio
            # Smooth to reduce speckle
            from scipy.ndimage import gaussian_filter
            vv_smooth = gaussian_filter(vv_db, sigma=2)
            vh_smooth = gaussian_filter(vh_db, sigma=2)

            # VV/VH ratio (vessels have high ratio)
            ratio = vv_smooth - vh_smooth

            # Threshold
            ratio_threshold = np.nanpercentile(ratio, 95)
            vessel_candidates = ratio > ratio_threshold

            # Connected component analysis
            labeled, num_features = ndimage.label(vessel_candidates)

            lat_arr = np.linspace(max_lat, min_lat, H)
            lon_arr = np.linspace(min_lon, max_lon, W)

            for label_id in range(1, min(num_features + 1, 50)):  # limit detections
                ys, xs = np.where(labeled == label_id)
                if len(ys) < 3:
                    continue

                # Centroid
                cy, cx = int(np.mean(ys)), int(np.mean(xs))
                lat_c = lat_arr[cy]
                lon_c = lon_arr[cx]

                # Size (radar cross-section area)
                area_pixels = len(ys)
                area_km2 = (area_pixels / (H * W)) * (111 * (max_lat - min_lat)) * (111 * (max_lon - min_lon) * np.cos(np.radians((max_lat + min_lat) / 2)))

                # Confidence based on VV/VH ratio
                confidence = float(np.clip((np.mean(ratio[ys, xs]) - ratio_threshold) / (np.nanmax(ratio) - ratio_threshold + 1e-6), 0, 1))

                det = {
                    "lat": float(lat_c),
                    "lon": float(lon_c),
                    "confidence": confidence,
                    "rcs_area_km2": round(area_km2, 3),
                    "vv_db": round(np.mean(vv_smooth[ys, xs]), 1),
                    "id": f"sar_vessel_{int(time.time() * 1000)}_{label_id}.png",
                    "image_url": f"/detections/sar_vessel_{int(time.time() * 1000)}_{label_id}.png",
                    "timestamp": timestamp,
                    "detector_type": "sar_vessel",
                }
                detections.append(det)

            return detections

        except Exception as e:
            logger.error(f"SAR vessel detector error: {e}", exc_info=True)
            return []


class ParkingLotDetector(BaseDetector):
    """Multitemporal S2 parking occupancy via car counting."""

    def __init__(self, rf_model=None):
        super().__init__(rf_model)
        self.detector_type = "parking"

    def detect(self, data, bbox_coords, timestamp, road_mask=None):
        """Detects vehicles in parking lots via NDVI + clustering."""
        min_lat, min_lon, max_lat, max_lon = bbox_coords
        H, W = data.shape[:2]

        # Extract bands
        R = data[:, :, 0].astype(np.float32)
        G = data[:, :, 1].astype(np.float32)
        B = data[:, :, 2].astype(np.float32)
        NIR = data[:, :, 3].astype(np.float32)
        CLM = data[:, :, 4]

        bands = np.stack([R, G, B, NIR], axis=0)
        bands = rescale_s2(bands)
        R, G, B, NIR = bands[0], bands[1], bands[2], bands[3]

        # Cloud mask
        cloud = CLM > 0
        R[cloud] = np.nan
        G[cloud] = np.nan
        B[cloud] = np.nan
        NIR[cloud] = np.nan

        # NDVI for vegetation
        ndvi = normalized_ratio(NIR, R)
        ndvi[cloud] = np.nan

        # Bare soil / asphalt signature: low NDVI + high red
        bare_soil = (ndvi < 0.3) & (R > 0.15)
        bare_soil[cloud] = False

        # Vehicle signature: localized darker pixels on parking lot
        # Compute local contrast
        from scipy.ndimage import uniform_filter
        R_local_mean = uniform_filter(np.nan_to_num(R, 0), size=7)
        R_contrast = R - R_local_mean
        R_contrast[cloud] = 0

        # Car pixels: dark spots on bright asphalt
        car_score = (bare_soil.astype(np.float32) * (1 - np.clip(R_contrast / 0.1, 0, 1)))
        car_score[cloud] = 0

        threshold = np.nanpercentile(car_score[bare_soil], 75)
        car_candidates = car_score > threshold

        # Connected components
        labeled, num_features = ndimage.label(car_candidates)

        detections = []
        lat_arr = np.linspace(max_lat, min_lat, H)
        lon_arr = np.linspace(min_lon, max_lon, W)

        car_count = 0
        parking_clusters = []

        for label_id in range(1, num_features + 1):
            ys, xs = np.where(labeled == label_id)
            if len(ys) < 5 or len(ys) > 200:  # car-sized clusters
                continue

            # Centroid
            cy, cx = int(np.mean(ys)), int(np.mean(xs))
            lat_c = lat_arr[cy]
            lon_c = lon_arr[cx]

            # Extent (typical car: ~3-5 pixels at 10m resolution)
            extent_pixels = len(ys)
            extent_m2 = (extent_pixels * 10 * 10)

            parking_clusters.append({
                "lat": lat_c,
                "lon": lon_c,
                "extent_m2": extent_m2,
                "score": np.mean(car_score[ys, xs]),
            })
            car_count += 1

        # Aggregate into parking lot detections (group nearby clusters)
        if car_count > 0:
            # Simple grid-based aggregation: assume detections within 100m are same lot
            aggregated_lots = []
            used = set()

            for i, cluster in enumerate(parking_clusters):
                if i in used:
                    continue

                lot_clusters = [cluster]
                used.add(i)

                # Find nearby clusters
                for j, other in enumerate(parking_clusters):
                    if j in used:
                        continue
                    dist_km = np.sqrt((cluster["lat"] - other["lat"])**2 + (cluster["lon"] - other["lon"])**2) * 111
                    if dist_km < 0.1:  # 100m threshold
                        lot_clusters.append(other)
                        used.add(j)

                # Create lot detection
                avg_lat = np.mean([c["lat"] for c in lot_clusters])
                avg_lon = np.mean([c["lon"] for c in lot_clusters])
                total_area_m2 = sum([c["extent_m2"] for c in lot_clusters])

                det = {
                    "lat": float(avg_lat),
                    "lon": float(avg_lon),
                    "confidence": float(np.clip(np.mean([c["score"] for c in lot_clusters]), 0, 1)),
                    "vehicle_count": len(lot_clusters),
                    "lot_area_m2": int(total_area_m2),
                    "id": f"parking_{int(time.time() * 1000)}_{len(aggregated_lots)}.png",
                    "image_url": f"/detections/parking_{int(time.time() * 1000)}_{len(aggregated_lots)}.png",
                    "timestamp": timestamp,
                    "detector_type": "parking",
                }
                detections.append(det)
                aggregated_lots.append(det)

        return detections


class ConstructionDetector(BaseDetector):
    """Multitemporal NDVI change detection for construction/land conversion."""

    def __init__(self, rf_model=None):
        super().__init__(rf_model)
        self.detector_type = "construction"

    def detect(self, data, bbox_coords, timestamp, road_mask=None):
        """Detects construction/land conversion via NDVI decline."""
        min_lat, min_lon, max_lat, max_lon = bbox_coords

        try:
            # Fetch two S2 observations: current and baseline (1 month prior)
            sh_bbox = BBox(bbox=[min_lon, min_lat, max_lon, max_lat], crs=CRS.WGS84)
            
            s2_collection = DataCollection.SENTINEL2_L2A.define_from(
                "s2l2a", service_url=CONFIG.sh_base_url,
            )

            current_date = timestamp[:10]
            baseline_date = (pd.to_datetime(timestamp[:10]) - pd.Timedelta(days=30)).strftime("%Y-%m-%d")

            catalog = SentinelHubCatalog(config=CONFIG)

            # Fetch baseline (1 month prior)
            baseline_results = list(catalog.search(
                s2_collection, bbox=sh_bbox,
                datetime=f"{baseline_date}T00:00:00Z/{baseline_date}T23:59:59Z",
                filter="eo:cloud_cover < 50",
                fields={"include": ["properties.datetime", "id"], "exclude": []}
            ))

            # Fetch current
            current_results = list(catalog.search(
                s2_collection, bbox=sh_bbox,
                datetime=f"{current_date}T00:00:00Z/{current_date}T23:59:59Z",
                filter="eo:cloud_cover < 50",
                fields={"include": ["properties.datetime", "id"], "exclude": []}
            ))

            if not baseline_results or not current_results:
                logger.debug("Insufficient S2 data for construction detection")
                return []

            # Evalscript for NDVI
            ndvi_script = """//VERSION=3
function setup() {
  return { input: ["B04", "B03", "B02", "B08"], output: { id: "default", bands: 4, sampleType: "FLOAT32" } };
}
function evaluatePixel(s) {
  return [s.B04, s.B03, s.B02, s.B08];
}"""

            def fetch_ndvi(obs_date):
                req = SentinelHubRequest(
                    evalscript=ndvi_script,
                    input_data=[SentinelHubRequest.input_data(
                        data_collection=s2_collection,
                        time_interval=(obs_date, obs_date),
                    )],
                    responses=[SentinelHubRequest.output_response("default", MimeType.TIFF)],
                    bbox=sh_bbox, config=CONFIG,
                )
                data_list = req.get_data()
                if not data_list:
                    return None
                d = data_list[0]
                R = d[:, :, 0].astype(np.float32)
                NIR = d[:, :, 3].astype(np.float32)
                bands = np.stack([R, NIR], axis=0)
                bands = rescale_s2(bands)
                R, NIR = bands[0], bands[1]
                ndvi = normalized_ratio(NIR, R)
                return ndvi

            baseline_ndvi = fetch_ndvi(baseline_results[0]["properties"]["datetime"][:10])
            current_ndvi = fetch_ndvi(current_results[0]["properties"]["datetime"][:10])

            if baseline_ndvi is None or current_ndvi is None:
                logger.debug("Failed to fetch NDVI data")
                return []

            H, W = baseline_ndvi.shape

            # NDVI change (negative = vegetation loss)
            ndvi_change = current_ndvi - baseline_ndvi

            # Construction threshold: significant vegetation loss
            change_threshold = -0.3
            construction_pixels = ndvi_change < change_threshold

            # Filter: only pixels that were vegetated before
            construction_pixels &= baseline_ndvi > 0.3

            # Connected components
            labeled, num_features = ndimage.label(construction_pixels)

            detections = []
            lat_arr = np.linspace(max_lat, min_lat, H)
            lon_arr = np.linspace(min_lon, max_lon, W)

            for label_id in range(1, min(num_features + 1, 30)):
                ys, xs = np.where(labeled == label_id)
                if len(ys) < 20:  # minimum area: ~2000 m^2
                    continue

                # Centroid
                cy, cx = int(np.mean(ys)), int(np.mean(xs))
                lat_c = lat_arr[cy]
                lon_c = lon_arr[cx]

                # Area
                area_km2 = (len(ys) * 100) / 1e6  # 10m^2per pixel

                # Magnitude of change
                avg_change = np.mean(ndvi_change[ys, xs])
                confidence = float(np.clip(-avg_change / 0.5, 0, 1))

                det = {
                    "lat": float(lat_c),
                    "lon": float(lon_c),
                    "confidence": confidence,
                    "area_km2": round(area_km2, 3),
                    "ndvi_change": round(avg_change, 2),
                    "id": f"construction_{int(time.time() * 1000)}_{label_id}.png",
                    "image_url": f"/detections/construction_{int(time.time() * 1000)}_{label_id}.png",
                    "timestamp": timestamp,
                    "detector_type": "construction",
                }
                detections.append(det)

            return detections

        except Exception as e:
            logger.error(f"Construction detector error: {e}", exc_info=True)
            return []


class OpiumPoppyDetector(BaseDetector):
    """Sentinel-2 time-series candidate detector for opium poppy cultivation."""

    def __init__(self, rf_model=None):
        super().__init__(rf_model)
        self.detector_type = "opium_poppy"

    def detect(self, data, bbox_coords, timestamp, road_mask=None):
        """Single-frame mode is intentionally disabled for crop phenology."""
        return []

    def detect_series(self, frames, bbox_coords, timestamps, sar_context=None):
        """
        Detect candidate opium poppy fields from a Sentinel-2 time series.

        Frames use the expanded band order:
        [B04, B03, B02, B08, CLM, B05, B06, B07, B8A, B11, B12].
        This returns candidate fields, not definitive crop identification.
        """
        if len(frames) < 3:
            logger.info("Opium poppy detector skipped: at least 3 clear frames are needed")
            return []

        ordered = sorted(zip(timestamps, frames), key=lambda item: item[0])
        timestamps = [item[0] for item in ordered]
        frames = [item[1] for item in ordered]

        try:
            index_series = [self._indices_for_frame(frame) for frame in frames]
            h, w = frames[0].shape[:2]

            ndvi_stack = np.stack([idx["ndvi"] for idx in index_series], axis=0)
            ndre_stack = np.stack([idx["ndre"] for idx in index_series], axis=0)
            ndmi_stack = np.stack([idx["ndmi"] for idx in index_series], axis=0)
            mtci_stack = np.stack([idx["mtci"] for idx in index_series], axis=0)
            psri_stack = np.stack([idx["psri"] for idx in index_series], axis=0)
            bsi_stack = np.stack([idx["bsi"] for idx in index_series], axis=0)
            cloud_stack = np.stack([idx["cloud"] for idx in index_series], axis=0)

            valid_stack = ~cloud_stack & np.isfinite(ndvi_stack)
            valid_obs = np.sum(valid_stack, axis=0)
            with np.errstate(invalid="ignore"):
                max_ndvi = np.nanmax(np.where(valid_stack, ndvi_stack, np.nan), axis=0)
                ndvi_amp = (
                    np.nanmax(np.where(valid_stack, ndvi_stack, np.nan), axis=0)
                    - np.nanmin(np.where(valid_stack, ndvi_stack, np.nan), axis=0)
                )

            crop_mask = (valid_obs >= 3) & (max_ndvi > 0.35) & (ndvi_amp > 0.12)
            crop_mask = ndimage.binary_opening(crop_mask, structure=np.ones((2, 2)))
            crop_mask = ndimage.binary_closing(crop_mask, structure=np.ones((3, 3)))

            labeled, num_features = ndimage.label(crop_mask)
            min_lat, min_lon, max_lat, max_lon = bbox_coords
            lat_arr = np.linspace(max_lat, min_lat, h)
            lon_arr = np.linspace(min_lon, max_lon, w)
            pixel_area_km2 = self._pixel_area_km2(min_lat, min_lon, max_lat, max_lon, h, w)

            detections = []
            for label_id in range(1, min(num_features + 1, 250)):
                ys, xs = np.where(labeled == label_id)
                if len(ys) < 6 or len(ys) > 6000:
                    continue

                metrics = self._patch_metrics(
                    ys, xs, timestamps,
                    ndvi_stack, ndre_stack, ndmi_stack, mtci_stack, psri_stack, bsi_stack, valid_stack,
                )
                if metrics is None:
                    continue

                confidence, reasons = self._score_patch(metrics, sar_context)
                if confidence < 0.58:
                    continue

                cy, cx = int(np.mean(ys)), int(np.mean(xs))
                area_km2 = float(len(ys) * pixel_area_km2)
                stage = self._growth_stage(metrics)

                detections.append({
                    "lat": float(lat_arr[cy]),
                    "lon": float(lon_arr[cx]),
                    "confidence": float(round(confidence, 3)),
                    "id": f"opium_poppy_{int(time.time() * 1000)}_{label_id}.png",
                    "image_url": "",
                    "timestamp": timestamps[-1],
                    "detector_type": "opium_poppy",
                    "growth_stage": stage,
                    "area_km2": round(area_km2, 4),
                    "field_pixels": int(len(ys)),
                    "peak_ndvi": round(metrics["peak_ndvi"], 3),
                    "peak_ndre": round(metrics["peak_ndre"], 3),
                    "ndvi_amplitude": round(metrics["ndvi_amplitude"], 3),
                    "greenup_rate": round(metrics["greenup_rate"], 3),
                    "decline_rate": round(metrics["decline_rate"], 3),
                    "moisture_drop": round(metrics["moisture_drop"], 3),
                    "bare_soil_increase": round(metrics["bare_soil_increase"], 3),
                    "valid_observations": int(metrics["valid_count"]),
                    "peak_date": metrics["peak_date"],
                    "sar_context": sar_context or {"available": False},
                    "candidate_reason": "; ".join(reasons),
                    "note": "Candidate opium poppy growth pattern. Requires local validation.",
                })

            return sorted(detections, key=lambda d: d["confidence"], reverse=True)[:80]

        except Exception as e:
            logger.error(f"Opium poppy detector error: {e}", exc_info=True)
            return []

    def _indices_for_frame(self, data):
        r = data[:, :, 0].astype(np.float32)
        g = data[:, :, 1].astype(np.float32)
        b = data[:, :, 2].astype(np.float32)
        nir = data[:, :, 3].astype(np.float32)
        clm = data[:, :, 4]

        if data.shape[2] >= 11:
            re1 = data[:, :, 5].astype(np.float32)
            re2 = data[:, :, 6].astype(np.float32)
            swir1 = data[:, :, 9].astype(np.float32)
            swir2 = data[:, :, 10].astype(np.float32)
        else:
            re1 = r.copy()
            re2 = nir.copy()
            swir1 = nir.copy()
            swir2 = nir.copy()

        bands = rescale_s2(np.stack([r, g, b, nir, re1, re2, swir1, swir2], axis=0))
        r, g, b, nir, re1, re2, swir1, swir2 = bands
        cloud = clm > 0

        ndvi = normalized_ratio(nir, r)
        ndre = normalized_ratio(nir, re1)
        ndmi = normalized_ratio(nir, swir1)
        bsi = ((swir1 + r) - (nir + b)) / ((swir1 + r) + (nir + b) + 1e-6)
        mtci = (re2 - re1) / (re1 - r + 1e-6)
        psri = (r - b) / (re2 + 1e-6)

        for arr in [ndvi, ndre, ndmi, bsi, mtci, psri]:
            arr[cloud] = np.nan

        return {
            "ndvi": ndvi,
            "ndre": ndre,
            "ndmi": ndmi,
            "bsi": bsi.astype(np.float32),
            "mtci": np.clip(mtci, -5, 5).astype(np.float32),
            "psri": np.clip(psri, -5, 5).astype(np.float32),
            "cloud": cloud,
        }

    def _patch_metrics(self, ys, xs, timestamps, ndvi, ndre, ndmi, mtci, psri, bsi, valid):
        curves = {}
        patch_valid = valid[:, ys, xs]
        good_dates = np.sum(patch_valid, axis=1) >= max(3, int(len(ys) * 0.35))
        if np.count_nonzero(good_dates) < 3:
            return None

        for name, stack in [
            ("ndvi", ndvi), ("ndre", ndre), ("ndmi", ndmi),
            ("mtci", mtci), ("psri", psri), ("bsi", bsi),
        ]:
            vals = []
            for t in range(stack.shape[0]):
                patch = stack[t, ys, xs]
                vals.append(float(np.nanmean(patch)) if good_dates[t] else np.nan)
            curves[name] = np.array(vals, dtype=np.float32)

        ndvi_curve = curves["ndvi"]
        valid_idx = np.where(np.isfinite(ndvi_curve))[0]
        if len(valid_idx) < 3:
            return None

        peak_idx = int(valid_idx[np.nanargmax(ndvi_curve[valid_idx])])
        first_idx = int(valid_idx[0])
        last_idx = int(valid_idx[-1])
        pre_peak = ndvi_curve[first_idx:peak_idx + 1]
        post_peak = ndvi_curve[peak_idx:last_idx + 1]

        peak_ndvi = float(ndvi_curve[peak_idx])
        min_ndvi = float(np.nanmin(ndvi_curve[valid_idx]))
        peak_ndre = float(np.nanmax(curves["ndre"][valid_idx]))
        peak_mtci = float(np.nanmax(curves["mtci"][valid_idx]))

        greenup_rate = float(peak_ndvi - ndvi_curve[first_idx])
        decline_rate = float(peak_ndvi - ndvi_curve[last_idx])
        if len(post_peak) > 1:
            decline_rate = max(decline_rate, float(peak_ndvi - np.nanmin(post_peak)))
        if len(pre_peak) > 1:
            greenup_rate = max(greenup_rate, float(peak_ndvi - np.nanmin(pre_peak)))

        ndmi_curve = curves["ndmi"]
        bsi_curve = curves["bsi"]
        moisture_drop = 0.0
        bare_soil_increase = 0.0
        if peak_idx < last_idx:
            moisture_drop = float(ndmi_curve[peak_idx] - np.nanmin(ndmi_curve[peak_idx:last_idx + 1]))
            bare_soil_increase = float(np.nanmax(bsi_curve[peak_idx:last_idx + 1]) - bsi_curve[peak_idx])

        return {
            "curves": curves,
            "valid_count": int(len(valid_idx)),
            "peak_idx": peak_idx,
            "last_idx": last_idx,
            "peak_date": timestamps[peak_idx][:10],
            "peak_ndvi": peak_ndvi,
            "min_ndvi": min_ndvi,
            "peak_ndre": peak_ndre,
            "peak_mtci": peak_mtci,
            "ndvi_amplitude": peak_ndvi - min_ndvi,
            "greenup_rate": greenup_rate,
            "decline_rate": decline_rate,
            "moisture_drop": moisture_drop,
            "bare_soil_increase": bare_soil_increase,
            "latest_ndvi": float(ndvi_curve[last_idx]),
            "latest_psri": float(curves["psri"][last_idx]),
        }

    def _score_patch(self, metrics, sar_context):
        score = 0.0
        reasons = []

        if metrics["peak_ndvi"] >= 0.45:
            score += 0.18
            reasons.append("strong crop vigor")
        if metrics["ndvi_amplitude"] >= 0.20:
            score += 0.16
            reasons.append("clear seasonal growth curve")
        if metrics["peak_ndre"] >= 0.16:
            score += 0.18
            reasons.append("red-edge chlorophyll peak")
        if metrics["peak_mtci"] >= 0.8:
            score += 0.10
            reasons.append("red-edge transition is elevated")
        if metrics["greenup_rate"] >= 0.14:
            score += 0.12
            reasons.append("rapid green-up")
        if metrics["decline_rate"] >= 0.12:
            score += 0.12
            reasons.append("post-peak decline")
        if metrics["moisture_drop"] >= 0.05:
            score += 0.07
            reasons.append("moisture drops after peak")
        if metrics["bare_soil_increase"] >= 0.03:
            score += 0.05
            reasons.append("bare-soil exposure rises")
        if metrics["valid_count"] >= 6:
            score += 0.06
            reasons.append("dense optical time series")
        if sar_context and sar_context.get("available"):
            score += 0.04
            reasons.append("Sentinel-1 moisture/texture context available")

        peak_not_edge = 0 < metrics["peak_idx"] < metrics["last_idx"]
        if peak_not_edge:
            score += 0.08
            reasons.append("peak occurs inside observation window")

        return float(np.clip(score, 0, 1)), reasons or ["weak but field-like phenology"]

    def _growth_stage(self, metrics):
        latest_ndvi = metrics["latest_ndvi"]
        peak_ndvi = metrics["peak_ndvi"]
        if metrics["peak_idx"] == metrics["last_idx"]:
            if latest_ndvi >= 0.45 and metrics["peak_ndre"] >= 0.16:
                return "flowering_or_capsule_candidate"
            return "vegetative_growth"
        decline = peak_ndvi - latest_ndvi
        if decline >= 0.18 and metrics["bare_soil_increase"] >= 0.03:
            return "senescence_or_harvest"
        if decline >= 0.10:
            return "post_peak_decline"
        return "near_peak_growth"

    @staticmethod
    def _pixel_area_km2(min_lat, min_lon, max_lat, max_lon, h, w):
        lat_m = abs(max_lat - min_lat) * 111000
        mid_lat = (min_lat + max_lat) / 2
        lon_m = abs(max_lon - min_lon) * 111000 * np.cos(np.radians(mid_lat))
        return float((lat_m / max(h, 1)) * (lon_m / max(w, 1)) / 1e6)



# -----------------------------------------------------------------------------
# ARGUS Engine
# -----------------------------------------------------------------------------

class ARGUSEngine:
    def __init__(self):
        self.history = []
        self.rf_model = load_rf_model()
        self.detectors = {
            "truck": TruckDetector(self.rf_model),
            "ship_wave": ShipWaveDetector(self.rf_model),
            "aircraft": AircraftDetector(self.rf_model),
            "train": TrainDetector(self.rf_model),
            "night_lights": NightLightsDetector(self.rf_model),
            "sar_vessel": SARVesselDetector(self.rf_model),
            "parking": ParkingLotDetector(self.rf_model),
            "construction": ConstructionDetector(self.rf_model),
            "opium_poppy": OpiumPoppyDetector(self.rf_model),
        }

    def fetch_roads(self, bbox_coords, progress_cb=None):
        """Fetch major roads with automatic mirror rotation and fallbacks."""
        def log(msg, level="info", pct=None):
            if level == "info":
                logger.info(msg)
            elif level == "warn":
                logger.warning(msg)
            if progress_cb:
                progress_cb(msg, pct)

        min_lat, min_lon, max_lat, max_lon = bbox_coords
        center_lat = (min_lat + max_lat) / 2
        center_lon = (min_lon + max_lon) / 2

        lat_span = (max_lat - min_lat) * 111000
        lon_span = (max_lon - min_lon) * 111000 * np.cos(np.radians(center_lat))
        dist_m = int(max(lat_span, lon_span) * 0.6) + 1000

        log(f"Starting road discovery (ROI: {center_lat:.4f}, {center_lon:.4f})", pct=5)

        for i, mirror in enumerate(OVERPASS_MIRRORS):
            log(f"Trying mirror {i+1}/{len(OVERPASS_MIRRORS)}: {mirror}", pct=10 + i * 5)
            ox.settings.overpass_url = mirror
            try:
                graph = ox.graph_from_point(
                    (center_lat, center_lon), dist=dist_m,
                    network_type="drive", simplify=True,
                    retain_all=False, truncate_by_edge=True,
                )
                roads = ox.graph_to_gdfs(graph, nodes=False)
                major_types = [
                    "motorway", "trunk", "primary", "secondary",
                    "motorway_link", "trunk_link", "primary_link",
                ]
                roads = roads[roads["highway"].isin(major_types)].copy()
                if not roads.empty:
                    logger.info(f"Fetched {len(roads)} major roads from {mirror}")
                    return roads
            except Exception as e:
                logger.warning(f"Mirror {mirror} failed: {e}")
                time.sleep(1)

        # Raw Overpass fallback
        logger.warning("All mirrors failed. Trying raw Overpass query.")
        try:
            query = f"""
            [out:json][timeout:60];
            (way["highway"~"motorway|trunk|primary"]({min_lat},{min_lon},{max_lat},{max_lon}););
            out body; >; out skel qt;
            """
            resp = requests.post(OVERPASS_MIRRORS[0], data={"data": query}, timeout=60)
            if resp.status_code == 200:
                data = resp.json()
                nodes = {n["id"]: (n["lon"], n["lat"]) for n in data["elements"] if n["type"] == "node"}
                ways = []
                for w in data["elements"]:
                    if w["type"] == "way" and "nodes" in w:
                        coords = [nodes[nid] for nid in w["nodes"] if nid in nodes]
                        if len(coords) > 1:
                            ways.append({"geometry": LineString(coords), "highway": w["tags"].get("highway")})
                if ways:
                    roads = gpd.GeoDataFrame(ways, crs="EPSG:4326")
                    logger.info(f"Raw fallback: {len(roads)} roads")
                    return roads
        except Exception as e:
            logger.error(f"Raw fallback failed: {e}")

        return gpd.GeoDataFrame()

    def detect_trucks(self, data, bbox_coords, timestamp, road_mask):
        """Legacy method for backward compatibility. Dispatches to TruckDetector."""
        detector = self.detectors["truck"]
        return detector.detect(data, bbox_coords, timestamp, road_mask)

    def detect_multi(self, data, bbox_coords, timestamp, road_mask, detector_types=None):
        """
        Run multiple detectors on satellite data.

        :param data: (H, W, 5) array [B04, B03, B02, B08, CLM]
        :param bbox_coords: [min_lat, min_lon, max_lat, max_lon]
        :param timestamp: ISO timestamp
        :param road_mask: (H, W) binary mask
        :param detector_types: list of detector names or None for all
        :return: aggregated list of detections with detector_type badge
        """
        if detector_types is None:
            detector_types = ["truck"]

        all_detections = []
        for det_type in detector_types:
            if det_type not in self.detectors:
                logger.warning(f"Unknown detector type: {det_type}")
                continue

            detector = self.detectors[det_type]
            try:
                if hasattr(detector, "detect_series") and det_type == "opium_poppy":
                    continue
                detections = detector.detect(data, bbox_coords, timestamp, road_mask)
                all_detections.extend(detections)
            except Exception as e:
                logger.error(f"Detector {det_type} failed: {e}", exc_info=True)

        return all_detections

    def detect_series(self, frames, bbox_coords, timestamps, detector_types=None, sar_context=None):
        """Run detectors that need the full optical time series."""
        if detector_types is None:
            detector_types = []

        all_detections = []
        for det_type in detector_types:
            detector = self.detectors.get(det_type)
            if detector is None or not hasattr(detector, "detect_series"):
                continue
            try:
                detections = detector.detect_series(frames, bbox_coords, timestamps, sar_context=sar_context)
                all_detections.extend(detections)
            except Exception as e:
                logger.error(f"Series detector {det_type} failed: {e}", exc_info=True)
        return all_detections

    def fetch_sentinel1_context(self, bbox_coords, timestamps):
        """Fetch a lightweight Sentinel-1 summary for crop moisture/texture context."""
        min_lat, min_lon, max_lat, max_lon = bbox_coords
        if not timestamps:
            return {"available": False, "reason": "no timestamps"}

        try:
            end_date = pd.to_datetime(max(timestamps)[:10])
            start_date = end_date - pd.Timedelta(days=30)
            sh_bbox = BBox(bbox=[min_lon, min_lat, max_lon, max_lat], crs=CRS.WGS84)
            s1_collection = DataCollection.SENTINEL1_IW.define_from(
                "s1", service_url=CONFIG.sh_base_url,
            )
            catalog = SentinelHubCatalog(config=CONFIG)
            search_results = list(catalog.search(
                s1_collection,
                bbox=sh_bbox,
                datetime=f"{start_date.strftime('%Y-%m-%d')}T00:00:00Z/{end_date.strftime('%Y-%m-%d')}T23:59:59Z",
                fields={"include": ["properties.datetime", "id"], "exclude": []},
            ))
            if not search_results:
                return {"available": False, "reason": "no Sentinel-1 scenes in window"}

            obs_time = search_results[0]["properties"]["datetime"]
            evalscript = """//VERSION=3
function setup() {
  return {
    input: ["VV", "VH"],
    output: { id: "default", bands: 2, sampleType: "FLOAT32" }
  };
}
function evaluatePixel(s) {
  return [s.VV, s.VH];
}"""
            req_sar = SentinelHubRequest(
                evalscript=evalscript,
                input_data=[SentinelHubRequest.input_data(
                    data_collection=s1_collection,
                    time_interval=(obs_time, obs_time),
                )],
                responses=[SentinelHubRequest.output_response("default", MimeType.TIFF)],
                bbox=sh_bbox,
                config=CONFIG,
            )
            sar_data_list = req_sar.get_data()
            if not sar_data_list:
                return {"available": False, "reason": "Sentinel-1 fetch returned no data"}

            sar = sar_data_list[0].astype(np.float32)
            vv = sar[:, :, 0]
            vh = sar[:, :, 1]
            vv_db = 10 * np.log10(np.maximum(vv, 1e-6))
            vh_db = 10 * np.log10(np.maximum(vh, 1e-6))
            ratio = vv_db - vh_db
            return {
                "available": True,
                "sensor": "Sentinel-1 IW",
                "timestamp": obs_time,
                "vv_db_mean": round(float(np.nanmean(vv_db)), 3),
                "vh_db_mean": round(float(np.nanmean(vh_db)), 3),
                "vv_vh_ratio_mean": round(float(np.nanmean(ratio)), 3),
                "vv_vh_ratio_std": round(float(np.nanstd(ratio)), 3),
            }
        except Exception as e:
            logger.warning(f"Sentinel-1 context unavailable: {e}")
            return {"available": False, "reason": str(e)}


# -----------------------------------------------------------------------------
# FastAPI Application
# -----------------------------------------------------------------------------

app = FastAPI(title="Epic Archer Intelligence")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

engine = ARGUSEngine()

# Initialize dark ships tracker if available
ship_tracker = None
if DARK_SHIPS_ENABLED:
    try:
        # Default monitoring area (can be updated via API)
        ship_tracker = ShipTracker(
            monitoring_lat=0,
            monitoring_lon=0,
            danger_zone_nm=200,  # 200 nautical miles
            dark_timeout_seconds=3600  # 1 hour without AIS = dark
        )
        logger.info("Dark ship tracker initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize dark ship tracker: {e}")


# Health check endpoint for Docker
@app.get("/health")
async def health():
    """Health check endpoint for container orchestration."""
    return {"status": "healthy", "service": "Epic Archer"}


class AnalyzeRequest(BaseModel):
    bbox: List[float]  # [min_lat, min_lon, max_lat, max_lon]
    label: str = "New Mission"
    months: int = 4
    max_frames: int = 10
    detectors: List[str] = ["truck"]  # which detectors to run


def _normalize_bbox(min_lat, min_lon, max_lat, max_lon):
    """Validate and normalize a WGS84 bounding box."""
    vals = [float(min_lat), float(min_lon), float(max_lat), float(max_lon)]
    if any(not np.isfinite(v) for v in vals):
        raise HTTPException(status_code=400, detail="Bounding box values must be finite numbers")

    south, north = sorted([vals[0], vals[2]])
    west, east = sorted([vals[1], vals[3]])
    if south < -90 or north > 90 or west < -180 or east > 180:
        raise HTTPException(status_code=400, detail="Bounding box is outside valid latitude/longitude bounds")
    if south == north or west == east:
        raise HTTPException(status_code=400, detail="Bounding box must have area")
    return south, west, north, east


def _get_websockets_module():
    """Load the optional AIS WebSocket client only when live ships are requested."""
    try:
        return importlib.import_module("websockets")
    except ImportError:
        return None


def _opensky_headers():
    """Return OAuth2 headers for OpenSky when API client credentials are configured."""
    global _opensky_token, _opensky_token_expires_at

    client_id = os.getenv("OPENSKY_CLIENT_ID")
    client_secret = os.getenv("OPENSKY_CLIENT_SECRET")
    if not client_id or not client_secret:
        return {}

    now = time.time()
    if _opensky_token and now < _opensky_token_expires_at - 30:
        return {"Authorization": f"Bearer {_opensky_token}"}

    resp = _session.post(
        OPENSKY_TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=15,
    )
    resp.raise_for_status()
    token_payload = resp.json()
    _opensky_token = token_payload["access_token"]
    _opensky_token_expires_at = now + int(token_payload.get("expires_in", 1800))
    return {"Authorization": f"Bearer {_opensky_token}"}


def _state_vector_to_aircraft(state):
    """Convert an OpenSky state vector into Epic Archer realtime telemetry."""
    if len(state) < 17 or state[5] is None or state[6] is None:
        return None

    velocity_ms = state[9]
    vertical_rate = state[11]
    callsign = (state[1] or "").strip()
    return {
        "id": state[0],
        "type": "aircraft",
        "callsign": callsign or state[0],
        "origin_country": state[2],
        "time_position": state[3],
        "last_contact": state[4],
        "lon": state[5],
        "lat": state[6],
        "baro_altitude_m": state[7],
        "on_ground": state[8],
        "speed_kmh": round(float(velocity_ms) * 3.6, 1) if velocity_ms is not None else None,
        "heading": round(float(state[10]), 1) if state[10] is not None else None,
        "vertical_rate_ms": round(float(vertical_rate), 1) if vertical_rate is not None else None,
        "geo_altitude_m": state[13] if len(state) > 13 else None,
        "squawk": state[14] if len(state) > 14 else None,
        "category": state[17] if len(state) > 17 else None,
        "source": "OpenSky Network",
    }


def _extract_ais_position(message):
    """Normalize an AISStream message into map telemetry."""
    metadata = message.get("Metadata") or message.get("MetaData") or {}
    message_type = message.get("MessageType")
    payload = (message.get("Message") or {}).get(message_type, {})

    lat = metadata.get("Latitude", payload.get("Latitude"))
    lon = metadata.get("Longitude", payload.get("Longitude"))
    if lat is None or lon is None:
        return None

    mmsi = payload.get("UserID") or metadata.get("MMSI") or metadata.get("ShipMMSI")
    speed = (
        payload.get("Sog")
        or payload.get("SpeedOverGround")
        or metadata.get("Sog")
        or metadata.get("SpeedOverGround")
    )
    course = payload.get("Cog") or payload.get("CourseOverGround") or metadata.get("Cog")
    heading = payload.get("TrueHeading") or payload.get("Heading") or metadata.get("TrueHeading")
    ship_name = (metadata.get("ShipName") or metadata.get("Name") or "").strip()

    return {
        "id": str(mmsi or f"{lat}:{lon}"),
        "type": "ship",
        "name": ship_name or str(mmsi or "AIS Vessel"),
        "mmsi": str(mmsi) if mmsi is not None else None,
        "lat": lat,
        "lon": lon,
        "speed_knots": round(float(speed), 1) if speed is not None else None,
        "course": round(float(course), 1) if course is not None else None,
        "heading": round(float(heading), 1) if heading is not None and float(heading) < 511 else None,
        "message_type": message_type,
        "source": "AISStream",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        # Additional metadata for dark ship tracking
        "callsign": metadata.get("CallSign") or payload.get("CallSign") or "",
        "flag": metadata.get("Flag") or "",
        "type": metadata.get("Type") or payload.get("ShipType") or "",
        "size_length": metadata.get("Length") or payload.get("Length"),
        "size_beam": metadata.get("Breadth") or payload.get("Beam"),
        "draft": metadata.get("Draft") or payload.get("Draft"),
        "destination": metadata.get("Destination") or payload.get("Destination") or "",
        "status": metadata.get("Status") or payload.get("NavStatus") or "",
    }


@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest):
    async def event_generator():
        try:
            def progress(msg, pct):
                return json.dumps({"type": "progress", "message": msg, "percent": pct}) + "\n"

            yield progress(f"Starting analysis for: {req.label}", 0)

            min_lat, min_lon, max_lat, max_lon = req.bbox
            if abs(max_lat - min_lat) > 0.5 or abs(max_lon - min_lon) > 0.5:
                yield json.dumps({"type": "error", "message": "AOI too large. Max strategic sector is ~55 km x 55 km."}) + "\n"
                return

            road_required = any(det in {"truck"} for det in req.detectors)
            roads = gpd.GeoDataFrame()
            if road_required:
                yield progress("Running Road Discovery Pipeline...", 10)
                roads = engine.fetch_roads(req.bbox, progress_cb=lambda m, p: None)
                if roads.empty:
                    yield json.dumps({"type": "error", "message": "No major roads found in AOI."}) + "\n"
                    return
                yield progress(f"Found {len(roads)} road corridor segments.", 25)
            else:
                yield progress("Skipping road discovery for non-road detectors.", 25)

            # 2. Satellite imagery
            sh_bbox = BBox(bbox=[min_lon, min_lat, max_lon, max_lat], crs=CRS.WGS84)
            yield progress("Searching Copernicus catalog...", 30)

            catalog = SentinelHubCatalog(config=CONFIG)
            end_date = datetime.now()
            start_date = end_date - timedelta(days=max(1, req.months) * 30)

            cdse_collection = DataCollection.SENTINEL2_L2A.define_from(
                "s2l2a", service_url=CONFIG.sh_base_url,
            )

            # Use CQL2 filter to avoid cloudy scenes and get unique time slots
            search_results = list(catalog.search(
                cdse_collection, bbox=sh_bbox,
                datetime=f"{start_date.strftime('%Y-%m-%dT00:00:00Z')}/{end_date.strftime('%Y-%m-%dT23:59:59Z')}",
                filter="eo:cloud_cover < 60",
                fields={"include": ["properties.datetime", "id"], "exclude": []}
            ))

            # Group by unique date (YYYY-MM-DD) to ensure trend diversity
            unique_scenes = {}
            for res in search_results:
                date_key = res["properties"]["datetime"][:10]
                if date_key not in unique_scenes:
                    unique_scenes[date_key] = res

            # Convert back to sorted list (latest first) and respect max_frames
            final_obs = [unique_scenes[d] for d in sorted(unique_scenes.keys(), reverse=True)]
            final_obs = final_obs[:req.max_frames]

            if not final_obs:
                yield json.dumps({"type": "error", "message": f"No clear imagery found in the last {req.months} months."}) + "\n"
                return

            yield progress(f"Found {len(final_obs)} unique clear overpasses. Starting analysis...", 40)

            # Evalscript output order:
            # B04(R), B03(G), B02(B), B08(NIR), CLM, B05, B06, B07, B8A, B11, B12.
            # Existing detectors use the first five channels; crop phenology uses all bands.
            evalscript = """//VERSION=3
function setup() {
  return {
    input: ["B02", "B03", "B04", "B05", "B06", "B07", "B08", "B8A", "B11", "B12", "CLM"],
    output: { id: "default", bands: 11, sampleType: "FLOAT32" }
  };
}
function evaluatePixel(s) {
  return [s.B04, s.B03, s.B02, s.B08, s.CLM, s.B05, s.B06, s.B07, s.B8A, s.B11, s.B12];
}"""

            # --- Optimization: Pre-calculate Road Mask ---
            # To get dimensions, we could do one small request or calculate.
            # Here we'll do the first frame sequentially to establish the grid,
            # then parallelize the rest.
            
            detections = []
            max_frames = min(len(final_obs), max(1, req.max_frames))
            
            if max_frames == 0:
                yield json.dumps({"type": "result", "mission_id": "none", "message": "No frames."}) + "\n"
                return

            # Helper for processing a single frame
            def _worker(idx, res_obs):
                try:
                    date_str = res_obs["properties"]["datetime"]
                    
                    req_sh = SentinelHubRequest(
                        evalscript=evalscript,
                        input_data=[SentinelHubRequest.input_data(
                            data_collection=cdse_collection,
                            time_interval=(date_str, date_str),
                        )],
                        responses=[SentinelHubRequest.output_response("default", MimeType.TIFF)],
                        bbox=sh_bbox, config=CONFIG,
                    )
                    
                    data_list = req_sh.get_data()
                    if not data_list:
                        return idx, date_str, None
                    
                    frame_sat_data = data_list[0]
                    # Note: road_mask is provided via closure or passed.
                    # We'll calculate it once inside the loop if not yet done.
                    return idx, date_str, frame_sat_data
                except Exception as ex:
                    logger.error(f"Worker error on frame {idx}: {ex}")
                    return idx, None, None

            # 1. Process Frame 0 to get the road_mask (Sequential/Seed)
            yield progress(f"Analyzing Seed Frame (1/{max_frames}) - {final_obs[0]['properties']['datetime'][:10]}", 40)
            _, _, seed_data = _worker(0, final_obs[0])
            
            if seed_data is None:
                yield json.dumps({"type": "error", "message": "Failed to acquire seed spectral data."}) + "\n"
                return
            
            # Generate Road Mask once
            from rasterio import features as rio_features, transform as rio_transform
            h, w = seed_data.shape[:2]
            if road_required and not roads.empty:
                roads_buf = roads.to_crs(epsg=3857).buffer(20).to_crs(epsg=4326)
                trans = rio_transform.from_bounds(min_lon, min_lat, max_lon, max_lat, w, h)
                road_mask = rio_features.rasterize(
                    [(geom.__geo_interface__, 1) for geom in roads_buf.geometry],
                    out_shape=(h, w), transform=trans, fill=0, all_touched=True,
                )
            else:
                road_mask = np.ones((h, w), dtype=np.uint8)

            series_frames = [seed_data]
            series_timestamps = [final_obs[0]["properties"]["datetime"]]
            
            # Detect on seed
            seed_dets = engine.detect_multi(seed_data, req.bbox, final_obs[0]['properties']['datetime'], road_mask, detector_types=req.detectors)
            detections.extend(seed_dets)

            # 2. Parallelize remaining frames
            if max_frames > 1:
                yield progress(f"Dispatching Parallel Telemetry Stack ({max_frames-1} frames)...", 45)
                
                completed_count = 1
                with ThreadPoolExecutor(max_workers=5) as executor:
                    futures = {executor.submit(_worker, i, final_obs[i]): i for i in range(1, max_frames)}
                    
                    for future in as_completed(futures):
                        idx, d_str, f_data = future.result()
                        completed_count += 1
                        
                        if f_data is not None:
                            series_frames.append(f_data)
                            series_timestamps.append(d_str)
                            # Detect
                            f_dets = engine.detect_multi(f_data, req.bbox, d_str, road_mask, detector_types=req.detectors)
                            detections.extend(f_dets)
                        
                        pct = 45 + int((completed_count / max_frames) * 50)
                        yield progress(f"Analyzing Orbital Stack [{completed_count}/{max_frames}]", pct)

            if any(det == "opium_poppy" for det in req.detectors):
                yield progress("Running opium poppy phenology analysis with Sentinel-2 red-edge/SWIR bands...", 96)
                sar_context = engine.fetch_sentinel1_context(req.bbox, series_timestamps)
                if sar_context.get("available"):
                    yield progress("Sentinel-1 SAR context added for moisture/texture support.", 97)
                else:
                    yield progress("Sentinel-1 context unavailable; continuing with optical time series.", 97)
                series_dets = engine.detect_series(
                    series_frames, req.bbox, series_timestamps,
                    detector_types=req.detectors, sar_context=sar_context,
                )
                detections.extend(series_dets)

            # Finalise
            mission_id = str(int(time.time()))
            engine.history.append({
                "mission_id": mission_id,
                "label": req.label,
                "bbox": req.bbox,
                "road_count": len(roads),
                "detections": detections,
                "timestamp": datetime.now().isoformat(),
            })

            yield json.dumps({
                "type": "result",
                "mission_id": mission_id,
                "road_count": len(roads),
                "detection_count": len(detections),
                "message": f"Complete: {len(detections)} detections/candidates found.",
            }) + "\n"

        except Exception as e:
            logger.error(f"Stream error: {e}", exc_info=True)
            yield json.dumps({"type": "error", "message": str(e)}) + "\n"

    return StreamingResponse(event_generator(), media_type="application/x-ndjson")


@app.get("/api/realtime/aircraft")
async def get_realtime_aircraft(
    min_lat: float,
    min_lon: float,
    max_lat: float,
    max_lon: float,
    max_items: int = 250,
):
    """Return live ADS-B aircraft positions for a map bounding box via OpenSky."""
    south, west, north, east = _normalize_bbox(min_lat, min_lon, max_lat, max_lon)
    max_items = int(np.clip(max_items, 1, 1000))

    try:
        resp = _session.get(
            OPENSKY_API_URL,
            params={"lamin": south, "lomin": west, "lamax": north, "lomax": east},
            headers=_opensky_headers(),
            timeout=15,
        )
        resp.raise_for_status()
        payload = resp.json()
    except requests.HTTPError as e:
        status = e.response.status_code if e.response is not None else 502
        logger.warning(f"OpenSky request failed: {e}")
        raise HTTPException(status_code=status, detail="OpenSky aircraft feed unavailable")
    except Exception as e:
        logger.warning(f"OpenSky request failed: {e}")
        raise HTTPException(status_code=502, detail=str(e))

    aircraft = []
    for state in payload.get("states") or []:
        item = _state_vector_to_aircraft(state)
        if item:
            aircraft.append(item)
        if len(aircraft) >= max_items:
            break

    return {
        "source": "OpenSky Network",
        "timestamp": payload.get("time"),
        "count": len(aircraft),
        "items": aircraft,
    }


@app.get("/api/realtime/ships")
async def get_realtime_ships(
    min_lat: float,
    min_lon: float,
    max_lat: float,
    max_lon: float,
    sample_seconds: int = 8,
    max_items: int = 250,
):
    """Return a short live AIS sample for a map bounding box via AISStream."""
    ws_module = _get_websockets_module()
    if ws_module is None:
        raise HTTPException(status_code=500, detail="Install the 'websockets' package to use AISStream")

    api_key = os.getenv("AISSTREAM_API_KEY")
    if not api_key:
        raise HTTPException(status_code=401, detail="Set AISSTREAM_API_KEY in .env to enable live ships")

    south, west, north, east = _normalize_bbox(min_lat, min_lon, max_lat, max_lon)
    sample_seconds = int(np.clip(sample_seconds, 2, 20))
    max_items = int(np.clip(max_items, 1, 1000))
    subscription = {
        "APIKey": api_key,
        "BoundingBoxes": [[[south, west], [north, east]]],
        "FilterMessageTypes": [
            "PositionReport",
            "StandardClassBPositionReport",
            "ExtendedClassBPositionReport",
        ],
    }

    vessels = {}
    started = time.time()
    try:
        async with ws_module.connect(AISSTREAM_WS_URL, open_timeout=10) as ws:
            await ws.send(json.dumps(subscription))
            while len(vessels) < max_items:
                remaining = sample_seconds - (time.time() - started)
                if remaining <= 0:
                    break
                try:
                    raw_message = await asyncio.wait_for(ws.recv(), timeout=remaining)
                except asyncio.TimeoutError:
                    break

                parsed = json.loads(raw_message)
                item = _extract_ais_position(parsed)
                if item:
                    vessels[item["id"]] = item
                    
                    # Feed to dark ship tracker if available
                    if ship_tracker and item.get("mmsi"):
                        try:
                            ship_tracker.process_ais_update(item["mmsi"], {
                                'lat': item.get('lat'),
                                'lon': item.get('lon'),
                                'name': item.get('name'),
                                'callsign': item.get('callsign'),
                                'flag': item.get('flag'),
                                'type': item.get('type'),
                                'size_length': item.get('size_length'),
                                'size_beam': item.get('size_beam'),
                                'draft': item.get('draft'),
                                'destination': item.get('destination'),
                                'status': item.get('status'),
                                'speed_knots': item.get('speed_knots'),
                            })
                        except Exception as e:
                            logger.debug(f"Dark ship tracking error for {item['mmsi']}: {e}")
    except Exception as e:
        logger.warning(f"AISStream request failed: {e}")
        raise HTTPException(status_code=502, detail=str(e))

    items = list(vessels.values())[:max_items]
    
    # Check for dark ships
    dark_events = []
    if ship_tracker:
        try:
            dark_events = ship_tracker.check_dark_ships()
        except Exception as e:
            logger.debug(f"Error checking dark ships: {e}")
    
    return {
        "source": "AISStream",
        "sample_seconds": round(time.time() - started, 1),
        "count": len(items),
        "items": items,
        "dark_events": dark_events,
    }


# -----------------------------------------------
# Dark Ships Tracking & Logs API Endpoints
# -----------------------------------------------

@app.post("/api/dark-ships/monitoring-area")
async def set_monitoring_area(lat: float, lon: float, radius_nm: float = 200):
    """Set the monitoring area center and radius"""
    if not ship_tracker:
        raise HTTPException(status_code=503, detail="Dark ship tracker not available")
    
    try:
        ship_tracker.update_monitoring_area(lat, lon)
        ship_tracker.danger_zone_nm = radius_nm
        return {
            "status": "success",
            "monitoring_lat": lat,
            "monitoring_lon": lon,
            "radius_nm": radius_nm,
        }
    except Exception as e:
        logger.error(f"Failed to set monitoring area: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/dark-ships/logs")
async def get_dark_ship_logs(limit: int = 100, hours: int = 72):
    """Get recent dark ship events"""
    if not ship_tracker:
        raise HTTPException(status_code=503, detail="Dark ship tracker not available")
    
    try:
        db = DarkShipsDatabase()
        events = db.get_recent_events(limit=limit, hours=hours)
        return {
            "count": len(events),
            "events": events,
        }
    except Exception as e:
        logger.error(f"Failed to get dark ship logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/dark-ships/current")
async def get_current_dark_ships():
    """Get all currently dark ships"""
    if not ship_tracker:
        raise HTTPException(status_code=503, detail="Dark ship tracker not available")
    
    try:
        db = DarkShipsDatabase()
        dark_ships = db.get_dark_ships()
        return {
            "count": len(dark_ships),
            "dark_ships": dark_ships,
        }
    except Exception as e:
        logger.error(f"Failed to get current dark ships: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/dark-ships/ship-history")
async def get_ship_history(mmsi: str):
    """Get all events for a specific ship"""
    if not ship_tracker:
        raise HTTPException(status_code=503, detail="Dark ship tracker not available")
    
    if not mmsi:
        raise HTTPException(status_code=400, detail="MMSI required")
    
    try:
        db = DarkShipsDatabase()
        events = db.get_ship_history(mmsi)
        return {
            "mmsi": mmsi,
            "count": len(events),
            "events": events,
        }
    except Exception as e:
        logger.error(f"Failed to get ship history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/dark-ships/status")
async def get_dark_ships_status():
    """Get dark ships tracking status"""
    if not ship_tracker:
        return {
            "enabled": False,
            "message": "Dark ship tracker not available",
        }
    
    try:
        db = DarkShipsDatabase()
        summary = ship_tracker.get_tracked_ships_summary()
        dark_ships = db.get_dark_ships()
        
        return {
            "enabled": True,
            "monitoring": {
                "center_lat": ship_tracker.monitoring_lat,
                "center_lon": ship_tracker.monitoring_lon,
                "radius_nm": ship_tracker.danger_zone_nm,
                "dark_timeout_seconds": ship_tracker.dark_timeout.total_seconds(),
            },
            "tracking": summary,
            "currently_dark_count": len(dark_ships),
        }
    except Exception as e:
        logger.error(f"Failed to get dark ships status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/roads")
async def get_roads(min_lat: float, min_lon: float, max_lat: float, max_lon: float):
    roads = engine.fetch_roads([min_lat, min_lon, max_lat, max_lon])
    if roads.empty:
        return {"type": "FeatureCollection", "features": []}
    return json.loads(roads.to_json())


@app.get("/api/sites")
async def get_sites():
    sites = [
        {
            "id": s["id"], "name": s["name"],
            "lat": (s["bbox"][0] + s["bbox"][2]) / 2,
            "lng": (s["bbox"][1] + s["bbox"][3]) / 2,
            "bbox": s["bbox"], "country": s["country"], "type": s["type"],
        }
        for s in FEATURED_SITES
    ]
    history_sites = [
        {
            "id": h["mission_id"], "name": h["label"],
            "lat": (h["bbox"][0] + h["bbox"][2]) / 2,
            "lng": (h["bbox"][1] + h["bbox"][3]) / 2,
            "bbox": h["bbox"], "country": "Analysis ROI", "type": "history",
        }
        for h in engine.history
    ]
    return sites + history_sites


@app.get("/api/feed")
async def get_feed():
    feed = []
    for h in engine.history:
        for d in h["detections"][:5]:
            feed.append({
                "alert_id": f"alert_{d['id']}",
                "site": {"id": h["mission_id"], "name": h["label"], "country": "ROI"},
                "status": "WARNING",
                "timestamp": d["timestamp"],
                "change_classification": {
                    "change_type": d.get("detector_type", "unknown"),
                    "confidence": d["confidence"],
                },
                "detection": {
                    "anomaly_score": round(d["confidence"] * 100, 1),
                    "date_before": "Baseline",
                    "date_after": d["timestamp"],
                },
            })
    return sorted(feed, key=lambda x: x["timestamp"], reverse=True)


@app.get("/api/analytics/trends")
async def get_trends(from_date: str = None, to_date: str = None, site_ids: str = None):
    """Aggregate detections across history by day, grouped by mission for comparison."""
    # site_ids can be a comma-separated list of mission IDs
    requested_ids = site_ids.split(",") if site_ids else []
    
    # 1. Collect all unique dates in the range to build a consistent X-axis
    all_dates = set()
    missions_data = []

    for mission in engine.history:
        m_id = mission["mission_id"]
        if requested_ids and m_id not in requested_ids:
            continue
            
        m_counts = {}
        for det in mission["detections"]:
            date_key = det["timestamp"][:10]
            if from_date and date_key < from_date: continue
            if to_date and date_key > to_date: continue
            
            all_dates.add(date_key)
            m_counts[date_key] = m_counts.get(date_key, 0) + 1
            
        missions_data.append({
            "id": m_id,
            "label": mission["label"],
            "counts": m_counts
        })

    sorted_dates = sorted(list(all_dates))
    
    # 2. Build aligned datasets for Chart.js
    datasets = []
    # Predefined colors for comparison
    colors = ["#3b82f6", "#f59e0b", "#10b981", "#ef4444", "#a855f7", "#ec4899"]
    
    for i, m in enumerate(missions_data):
        aligned_data = [m["counts"].get(d, 0) for d in sorted_dates]
        datasets.append({
            "label": m["label"],
            "data": aligned_data,
            "borderColor": colors[i % len(colors)],
            "backgroundColor": f"{colors[i % len(colors)]}22" # 13% opacity
        })

    total_detections = sum(sum(d["data"]) for d in datasets)

    return {
        "labels": sorted_dates,
        "datasets": datasets,
        "summary": {
            "total_detections": total_detections,
            "missions_count": len(datasets)
        }
    }


@app.get("/api/detections/{mission_id}")
async def get_detections(mission_id: str):
    mission = next((h for h in engine.history if h["mission_id"] == mission_id), None)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    return mission["detections"]


# -----------------------------------------------------------------------------
# API Endpoints
# -----------------------------------------------------------------------------

@app.get("/api/check-credentials")
async def check_credentials():
    """Check if credentials are configured from environment."""
    client_id = os.getenv("COPERNICUS_CLIENT_ID")
    client_secret = os.getenv("COPERNICUS_CLIENT_SECRET")
    
    if not client_id or not client_secret:
        logger.warning("COPERNICUS_CLIENT_ID or COPERNICUS_CLIENT_SECRET not set in .env")
        raise HTTPException(status_code=401, detail="Missing Copernicus credentials in .env file")
    
    return {"status": "success", "message": "Copernicus credentials loaded from .env"}


# Serve static detections
app.mount("/detections", StaticFiles(directory=DETECTION_DIR), name="detections")

# Serve frontend
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")


if __name__ == "__main__":
    try:
        from sentinelhub import SentinelHubSession
        sh_session = SentinelHubSession(config=CONFIG)
        _ = sh_session.token
        logger.info("Copernicus Data Space Authentication: SUCCESS")
    except Exception as e:
        logger.error(f"Copernicus Data Space Authentication: FAILED - {e}")
        logger.warning("System will start, but satellite monitoring may be degraded.")

    uvicorn.run(app, host="0.0.0.0", port=8000)
