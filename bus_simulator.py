# core backend of the entire prototype, one thing i have to admit is that this is assisted through AI (Claude) but had to manually tweak it myself (duration, ETAs, bus stops, etc.)
import math
import random
import time
import requests
import streamlit as st
# 1. route data (taken through davao city with its following stops)
ROUTES = {
    "R1": {
        "name": "R1 - Downtown to Airport (via J.P. Laurel Ave.)",
        "color": [230, 57, 70],  # red
        "stops": [
            {"name": "SM City Davao",        "lat": 7.0709, "lon": 125.6142},
            {"name": "Roxas Avenue",         "lat": 7.0736, "lon": 125.6129},
            {"name": "Davao City Hall",      "lat": 7.0682, "lon": 125.6122},
            {"name": "Bajada",               "lat": 7.0925, "lon": 125.6120},
            {"name": "SM Lanang Premier",    "lat": 7.1064, "lon": 125.6348},
            {"name": "Sasa",                 "lat": 7.1150, "lon": 125.6440},
            {"name": "Davao Airport",        "lat": 7.1255, "lon": 125.6458},
        ],
    },
    "R2": {
        "name": "R2 - Bajada to Matina (via Quimpo Blvd.)",
        "color": [42, 157, 143],  # teal
        "stops": [
            {"name": "Bajada",               "lat": 7.0925, "lon": 125.6120},
            {"name": "Victoria Plaza",       "lat": 7.0847, "lon": 125.6104},
            {"name": "Ateneo de Davao",      "lat": 7.0740, "lon": 125.6135},
            {"name": "Davao City Hall",      "lat": 7.0682, "lon": 125.6122},
            {"name": "Matina Town Square",   "lat": 7.0575, "lon": 125.5945},
            {"name": "Matina Crossing",      "lat": 7.0518, "lon": 125.5901},
        ],
    },
    "R3": {
        "name": "R3 - Agdao to Toril (via National Highway)",
        "color": [38, 70, 83],  # navy
        "stops": [
            {"name": "Agdao Public Market",  "lat": 7.0870, "lon": 125.6207},
            {"name": "Rizal Park",           "lat": 7.0700, "lon": 125.6122},
            {"name": "Bankerohan Terminal",  "lat": 7.0575, "lon": 125.6055},
            {"name": "Ulas Crossing",        "lat": 7.0326, "lon": 125.5788},
            {"name": "Toril Public Market",  "lat": 7.0084, "lon": 125.5327},
        ],
    },
}
BUS_STATUSES = ["On Time", "Delayed"]
CROWD_LEVELS = ["Low", "Moderate", "High"]
OSRM_URL = "http://router.project-osrm.org/route/v1/driving/"
# 2. geo helpers
def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance between two lat/lon points, in km."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
def _straight_line_path(stops):
    """Fallback path: just connect the stops directly. Used only if the
    live road-routing service can't be reached (e.g. no internet)."""
    dense = [(s["lat"], s["lon"]) for s in stops]
    cum = [0.0]
    for i in range(1, len(dense)):
        cum.append(cum[-1] + haversine_km(*dense[i - 1], *dense[i]))
    return {"dense": dense, "dense_cum": cum, "stop_cum": cum,
            "total_km": cum[-1], "road_snapped": False}
def fetch_road_geometry(stops):
    """Ask OSRM for the real road-following path between a list of stops.
    Returns a dict with:
      - dense: a dense list of (lat, lon) points that trace actual streets
      - dense_cum: cumulative km along `dense` (used to place a bus smoothly)
      - stop_cum: cumulative REAL ROAD km at each original stop (used for
        ETA / "next stop" logic)
      - total_km: total real road length of the route
      - road_snapped: True if this came from OSRM, False if we had to fall
        back to straight lines (e.g. no internet access)
    """
    coord_str = ";".join(f"{s['lon']},{s['lat']}" for s in stops)
    url = f"{OSRM_URL}{coord_str}?overview=full&geometries=geojson"
    try:
        resp = requests.get(url, timeout=6)
        resp.raise_for_status()
        data = resp.json()
        route = data["routes"][0]
        dense = [(lat, lon) for lon, lat in route["geometry"]["coordinates"]]
        dense_cum = [0.0]
        for i in range(1, len(dense)):
            dense_cum.append(dense_cum[-1] + haversine_km(*dense[i - 1], *dense[i]))
        stop_cum = [0.0]
        for leg in route["legs"]:
            stop_cum.append(stop_cum[-1] + leg["distance"] / 1000.0)
        return {
            "dense": dense, "dense_cum": dense_cum,
            "stop_cum": stop_cum, "total_km": dense_cum[-1],
            "road_snapped": True,
        }
    except Exception:
        return _straight_line_path(stops)
def point_at_distance(dense, dense_cum, dist_km):
    """Lat/lon of the point `dist_km` along a dense (lat, lon) path."""
    dist_km = max(0.0, min(dist_km, dense_cum[-1]))
    for i in range(1, len(dense)):
        if dist_km <= dense_cum[i]:
            seg_len = dense_cum[i] - dense_cum[i - 1]
            frac = 0.0 if seg_len == 0 else (dist_km - dense_cum[i - 1]) / seg_len
            lat = dense[i - 1][0] + frac * (dense[i][0] - dense[i - 1][0])
            lon = dense[i - 1][1] + frac * (dense[i][1] - dense[i - 1][1])
            return lat, lon
    return dense[-1]
def next_stop_index(stop_cum, dist_km):
    """Index of the next stop the bus hasn't reached yet."""
    for i, c in enumerate(stop_cum):
        if c >= dist_km:
            return i
    return len(stop_cum) - 1
# 3. route geometry cache
def init_route_geometry(force_route_id=None):
    """Fetch (or refresh) the real road geometry for each route. Cached in
    session_state so we only hit the routing service once per route, not
    on every 3-second refresh."""
    if "route_geo" not in st.session_state:
        st.session_state.route_geo = {}
    for route_id, route in ROUTES.items():
        if force_route_id == route_id or route_id not in st.session_state.route_geo:
            st.session_state.route_geo[route_id] = fetch_road_geometry(route["stops"])
def get_geo(route_id):
    init_route_geometry()
    return st.session_state.route_geo[route_id]
# 4. bus fleet initialization
def _new_bus(bus_id, route_id, total_km):
    return {
        "id": bus_id,
        "route_id": route_id,
        "dist_km": random.uniform(0, total_km),   # random starting position
        "speed_kmh": random.uniform(18, 28),       # base cruising speed
        "status": "On Time",
        "deviation": False,
        "crowd": random.choice(CROWD_LEVELS),
        "last_update": time.time(),
    }
def init_fleet():
    """Create the bus fleet once and store it in session_state."""
    init_route_geometry()
    if "buses" not in st.session_state:
        buses = {}
        bus_counter = 1
        for route_id in ROUTES:
            total_km = st.session_state.route_geo[route_id]["total_km"]
            for _ in range(2):  # 2 buses per route
                bid = f"Bus {bus_counter:02d}"
                buses[bid] = _new_bus(bid, route_id, total_km)
                bus_counter += 1
        st.session_state.buses = buses
        st.session_state.tick_count = 0
        st.session_state.history = []  # for the admin "active buses over time" chart
# 5. sim tick (the one that moves the buses a lil bit)
def simulate_tick(dt_seconds=3):
    """Advance the whole fleet's state. Call this on every refresh."""
    init_fleet()
    dt_hours = dt_seconds / 3600.0
    for bus in st.session_state.buses.values():
        total_km = st.session_state.route_geo[bus["route_id"]]["total_km"]
        # --- simulate traffic: occasionally slow down / speed up
        if random.random() < 0.15:
            bus["speed_kmh"] = max(5, min(35, bus["speed_kmh"] + random.uniform(-6, 6)))
        # --- simulate rare route deviation
        if random.random() < 0.02:
            bus["deviation"] = not bus["deviation"] if bus["deviation"] else True
        if bus["deviation"] and random.random() < 0.3:
            bus["deviation"] = False  # gets back on route eventually
        bus["status"] = "Delayed" if (bus["deviation"] or bus["speed_kmh"] < 15) else "On Time"
        # --- crowd level slow random walk
        if random.random() < 0.1:
            bus["crowd"] = random.choice(CROWD_LEVELS)
        # --- move the bus forward along the REAL ROAD path, loop at the end
        bus["dist_km"] = (bus["dist_km"] + bus["speed_kmh"] * dt_hours) % total_km
        bus["last_update"] = time.time()
    st.session_state.tick_count += 1
    st.session_state.history.append({
        "tick": st.session_state.tick_count,
        "on_time": sum(1 for b in st.session_state.buses.values() if b["status"] == "On Time"),
        "delayed": sum(1 for b in st.session_state.buses.values() if b["status"] == "Delayed"),
    })
    st.session_state.history = st.session_state.history[-40:]  # keep it short
# 6. query helpers
def get_bus_position(bus):
    geo = get_geo(bus["route_id"])
    return point_at_distance(geo["dense"], geo["dense_cum"], bus["dist_km"])
def get_buses_for_route(route_id):
    return {bid: b for bid, b in st.session_state.buses.items() if b["route_id"] == route_id}
def eta_to_stop_minutes(bus, stop_index):
    """Minutes until `bus` reaches the stop at `stop_index` on its route,
    using real road distance."""
    geo = get_geo(bus["route_id"])
    target_dist = geo["stop_cum"][stop_index]
    remaining = target_dist - bus["dist_km"]
    if remaining < 0:
        remaining += geo["total_km"]  # bus already passed it this loop, wraps around
    speed = max(bus["speed_kmh"], 1)
    return remaining, (remaining / speed) * 60
def next_stop_name(bus):
    geo = get_geo(bus["route_id"])
    stops = ROUTES[bus["route_id"]]["stops"]
    idx = next_stop_index(geo["stop_cum"], bus["dist_km"])
    return stops[idx]["name"], idx
def route_line_for_map(route_id):
    """[lon, lat] points tracing the ACTUAL road path, for drawing on the map."""
    geo = get_geo(route_id)
    return [[lon, lat] for lat, lon in geo["dense"]]