import streamlit as st
from bus_simulator import init_fleet, simulate_tick
st.set_page_config(page_title="FindMyBus", page_icon="🚌", layout="wide")
init_fleet()
simulate_tick()  # keep the simulated fleet moving even on the home page
st.title("🚌 FindMyBus")
st.caption("Real-Time Smart Bus Tracking and Route Assistance System — Prototype")
col1, col2 = st.columns(2)
with col1:
    st.subheader("🧍 Passenger")
    st.write("Search a route, see live bus locations, check ETA, and get an alert when your bus is close.")
    st.page_link("pages/1_🚌_Passenger_View.py", label="Open Passenger View", icon="🚌")
with col2:
    st.subheader("🛠️ Administrator")
    st.write("Monitor the whole fleet on one map, manage routes/stops, and review delays.")
    st.page_link("pages/2_🛠️_Admin_Dashboard.py", label="Open Admin Dashboard", icon="🛠️")
st.divider()
c1, c2, c3 = st.columns(3)
c1.metric("Active Routes", len(set(b["route_id"] for b in st.session_state.buses.values())))
c2.metric("Buses in Fleet", len(st.session_state.buses))
c3.metric(
    "Buses On Time",
    sum(1 for b in st.session_state.buses.values() if b["status"] == "On Time"),
)
st.info(
    "💡 Prototype note: bus positions update every few seconds using a simulated "
    "GPS feed. In a production version, each bus would send real GPS coordinates "
    "to the server instead."
)
