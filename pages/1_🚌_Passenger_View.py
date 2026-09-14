import pandas as pd
import pydeck as pdk
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from bus_simulator import (
    ROUTES, init_fleet, simulate_tick, get_bus_position,
    get_buses_for_route, eta_to_stop_minutes, next_stop_name,
    get_geo, route_line_for_map,
)
st.set_page_config(page_title="FindMyBus · Passenger", page_icon="🚌", layout="wide")
init_fleet()
# auto-refresh every 3 seconds to simulate a 'live' GPS feed
st_autorefresh(interval=3000, key="passenger_refresh")
simulate_tick()
st.title("🧍 Passenger View")
# 3. search / choose a route
route_id = st.selectbox(
    "Where are you headed? Choose a route",
    options=list(ROUTES.keys()),
    format_func=lambda rid: ROUTES[rid]["name"],
)
route = ROUTES[route_id]
buses = get_buses_for_route(route_id)
st.subheader(f"Live map — {route['name']}")
# 2. build map data
stop_df = pd.DataFrame(route["stops"])
bus_rows = []
for bid, b in buses.items():
    lat, lon = get_bus_position(b)
    bus_rows.append({
        "bus_id": bid, "lat": lat, "lon": lon,
        "status": b["status"], "crowd": b["crowd"],
    })
bus_df = pd.DataFrame(bus_rows)
geo = get_geo(route_id)
route_line = [{"path": route_line_for_map(route_id), "color": route["color"]}]
if not geo["road_snapped"]:
    st.warning(
        "⚠️ Couldn't reach the live road-routing service right now, so this route "
        "is shown as a straight line between stops instead of following real streets."
    )
layers = [
    pdk.Layer("PathLayer", data=route_line, get_path="path", get_color="color",
              width_scale=1, width_min_pixels=4),
    pdk.Layer("ScatterplotLayer", data=stop_df, get_position=["lon", "lat"],
              get_radius=60, get_fill_color=[100, 100, 100], pickable=True),
    pdk.Layer("ScatterplotLayer", data=bus_df, get_position=["lon", "lat"],
              get_radius=90, get_fill_color=[230, 57, 70], pickable=True),
]
view_state = pdk.ViewState(
    latitude=stop_df["lat"].mean(), longitude=stop_df["lon"].mean(), zoom=11.5
)
st.pydeck_chart(pdk.Deck(
    layers=layers, initial_view_state=view_state,
    tooltip={"text": "{name}{bus_id}"},
    map_style=None,
))
st.caption("🔴 Buses · ⚪ Stops · colored line = route path")
# 3. buses w/ live status
st.subheader("Buses on this route")
list_rows = []
for bid, b in buses.items():
    stop_name, _ = next_stop_name(b)
    list_rows.append({
        "Bus": bid,
        "Status": ("✅ " + b["status"]) if b["status"] == "On Time" else ("⚠️ " + b["status"]),
        "Speed (km/h)": round(b["speed_kmh"], 1),
        "Crowd Level": b["crowd"],
        "Next Stop": stop_name,
        "Deviation": "🚧 Yes" if b["deviation"] else "No",
    })
st.dataframe(pd.DataFrame(list_rows), hide_index=True, use_container_width=True)
st.divider()
# 4. select a bus and destination route
st.subheader("Track a specific bus")
col_a, col_b = st.columns(2)
with col_a:
    chosen_bus_id = st.selectbox("Select your bus", options=list(buses.keys()))
with col_b:
    stop_names = [s["name"] for s in route["stops"]]
    dest_name = st.selectbox("Select your destination stop", options=stop_names, index=len(stop_names) - 1)
chosen_bus = buses[chosen_bus_id]
dest_index = stop_names.index(dest_name)
remaining_km, eta_min = eta_to_stop_minutes(chosen_bus, dest_index)
total_km = geo["total_km"]
progress = 1 - (remaining_km / total_km) if total_km else 0
progress = min(max(progress, 0.0), 1.0)
m1, m2, m3 = st.columns(3)
m1.metric("Distance remaining", f"{remaining_km:.2f} km")
m2.metric("Estimated arrival", f"{eta_min:.1f} min")
m3.metric("Bus status", chosen_bus["status"])
st.progress(progress, text=f"{chosen_bus_id} progress toward {dest_name}")
ALERT_THRESHOLD_KM = 0.4
if remaining_km <= ALERT_THRESHOLD_KM:
    st.toast(f"🔔 {chosen_bus_id} is approaching {dest_name}!", icon="🚌")
    st.success(f"🔔 **Alert:** {chosen_bus_id} is about **{remaining_km*1000:.0f} m** from "
               f"**{dest_name}** — get ready to board/alight!")
else:
    st.caption(f"You'll be notified automatically once {chosen_bus_id} is within "
               f"{ALERT_THRESHOLD_KM*1000:.0f} m of {dest_name}.")
if chosen_bus["deviation"]:
    st.warning(f"⚠️ {chosen_bus_id} has deviated from its usual route — ETA may be less accurate.")