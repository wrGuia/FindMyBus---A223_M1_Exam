import pandas as pd
import pydeck as pdk
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from bus_simulator import (
    ROUTES, init_fleet, simulate_tick, get_bus_position,
    route_line_for_map, init_route_geometry,
)
st.set_page_config(page_title="FindMyBus · Admin", page_icon="🛠️", layout="wide")
init_fleet()
# tung tung sahur
if "admin_logged_in" not in st.session_state:
    st.session_state.admin_logged_in = False
if not st.session_state.admin_logged_in:
    st.title("🛠️ Admin Login")
    st.caption("Prototype login — use **admin / admin**")
    with st.form("login_form"):
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in")
    if submitted:
        if u == "admin" and p == "admin":
            st.session_state.admin_logged_in = True
            st.rerun()
        else:
            st.error("Invalid credentials. Try admin / admin.")
    st.stop()
# Auto-refresh to keep the fleet "live"
st_autorefresh(interval=3000, key="admin_refresh")
simulate_tick()
st.title("🛠️ Admin Dashboard")
top_l, top_r = st.columns([4, 1])
with top_r:
    if st.button("Log out"):
        st.session_state.admin_logged_in = False
        st.rerun()
buses = st.session_state.buses
# fleet wide summary
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Buses", len(buses))
c2.metric("On Time", sum(1 for b in buses.values() if b["status"] == "On Time"))
c3.metric("Delayed", sum(1 for b in buses.values() if b["status"] == "Delayed"))
c4.metric("Deviating", sum(1 for b in buses.values() if b["deviation"]))
# live map of the whole fleet
st.subheader("Live fleet map — all routes")
route_lines = [
    {"path": route_line_for_map(rid), "color": r["color"]}
    for rid, r in ROUTES.items()
]
all_stops = pd.DataFrame([s for r in ROUTES.values() for s in r["stops"]])
bus_rows = []
for bid, b in buses.items():
    lat, lon = get_bus_position(b)
    bus_rows.append({
        "bus_id": bid, "lat": lat, "lon": lon, "route": ROUTES[b["route_id"]]["name"],
        "status": b["status"],
        "color": [230, 57, 70] if b["status"] == "On Time" else [244, 162, 97],
    })
bus_df = pd.DataFrame(bus_rows)
layers = [
    pdk.Layer("PathLayer", data=route_lines, get_path="path", get_color="color",
              width_scale=1, width_min_pixels=3),
    pdk.Layer("ScatterplotLayer", data=all_stops, get_position=["lon", "lat"],
              get_radius=50, get_fill_color=[120, 120, 120], pickable=True),
    pdk.Layer("ScatterplotLayer", data=bus_df, get_position=["lon", "lat"],
              get_radius=100, get_fill_color="color", pickable=True),
]
view_state = pdk.ViewState(
    latitude=all_stops["lat"].mean(), longitude=all_stops["lon"].mean(), zoom=10.3
)
st.pydeck_chart(pdk.Deck(layers=layers, initial_view_state=view_state,
                          tooltip={"text": "{bus_id}\n{route}\n{status}"}, map_style=None))
st.divider()
# manages full fleet table with filters
st.subheader("Manage buses, routes & stops")
f1, f2 = st.columns(2)
with f1:
    route_filter = st.multiselect("Filter by route", options=list(ROUTES.keys()),
                                   default=list(ROUTES.keys()),
                                   format_func=lambda rid: ROUTES[rid]["name"])
with f2:
    status_filter = st.multiselect("Filter by status", options=["On Time", "Delayed"],
                                    default=["On Time", "Delayed"])
table_rows = []
for bid, b in buses.items():
    if b["route_id"] in route_filter and b["status"] in status_filter:
        table_rows.append({
            "Bus": bid,
            "Route": ROUTES[b["route_id"]]["name"],
            "Status": b["status"],
            "Speed (km/h)": round(b["speed_kmh"], 1),
            "Crowd Level": b["crowd"],
            "Deviation": "Yes" if b["deviation"] else "No",
        })
st.dataframe(pd.DataFrame(table_rows), hide_index=True, use_container_width=True)
with st.expander("➕ Add a stop to a route (prototype)"):
    add_route = st.selectbox("Route", options=list(ROUTES.keys()),
                              format_func=lambda rid: ROUTES[rid]["name"], key="add_stop_route")
    name = st.text_input("Stop name")
    lat = st.number_input("Latitude", value=7.07, format="%.5f")
    lon = st.number_input("Longitude", value=125.61, format="%.5f")
    if st.button("Add stop"):
        if name:
            ROUTES[add_route]["stops"].append({"name": name, "lat": lat, "lon": lon})
            init_route_geometry(force_route_id=add_route)  # re-snap to real roads
            st.success(f"Added '{name}' to {ROUTES[add_route]['name']} and re-routed on real roads.")
            st.rerun()
        else:
            st.warning("Please enter a stop name.")
st.divider()
# delays and deviations
st.subheader("Delays & route deviations")
flagged = [
    {"Bus": bid, "Route": ROUTES[b["route_id"]]["name"], "Issue":
        "Route deviation" if b["deviation"] else "Running slow / delayed",
     "Speed (km/h)": round(b["speed_kmh"], 1)}
    for bid, b in buses.items() if b["status"] == "Delayed" or b["deviation"]
]
if flagged:
    st.dataframe(pd.DataFrame(flagged), hide_index=True, use_container_width=True)
else:
    st.success("No delays or deviations right now — fleet running smoothly. ✅")
st.divider()
# historical trend
st.subheader("Fleet status over time")
if st.session_state.history:
    hist_df = pd.DataFrame(st.session_state.history).set_index("tick")
    st.line_chart(hist_df[["on_time", "delayed"]])
else:
    st.caption("Collecting data…")