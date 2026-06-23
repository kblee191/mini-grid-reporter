import streamlit as st
import pandas as pd
import re
import calendar
import plotly.express as px
from sqlalchemy import text

# Connect to our cloud database automatically using secrets config
conn = st.connection("postgresql", type="sql")

# Page Configuration
st.set_page_config(page_title="Mini-Grid Reporter", layout="wide", page_icon="⚡")

# Initialize session state memory keys if they don't exist
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False
if "uploader_key" not in st.session_state:
    st.session_state["uploader_key"] = 0
if "processed_report" not in st.session_state:
    st.session_state["processed_report"] = None

# =========================================================
# 🔒 Authentication System
# =========================================================
def check_credentials(username, password):
    try:
        user_passwords = st.secrets["passwords"]
        return username in user_passwords and user_passwords[username] == password
    except KeyError:
        fallback_creds = {"admin": "password123", "team": "grid2026"}
        return username in fallback_creds and fallback_creds[username] == password

# Show login screen if not authenticated
if not st.session_state["authenticated"]:
    st.markdown("<h2 style='text-align: center;'>⚡ Mini-Grid Reporter Portal</h2>", unsafe_allow_html=True)
    
    _, login_col, _ = st.columns([1, 1, 1])
    with login_col:
        with st.form("login_form"):
            st.subheader("Team Authorization Required")
            username = st.text_input("Username").strip()
            password = st.text_input("Password", type="password")
            submit = st.form_submit_button("Log In", type="primary", use_container_width=True)
            
            if submit:
                if check_credentials(username, password):
                    st.session_state["authenticated"] = True
                    st.session_state["user"] = username
                    st.success("Access Granted!")
                    st.rerun()
                else:
                    st.error("Invalid username or password.")
                    
    st.stop()

# =========================================================
# 🔓 Authorized Session Area
# =========================================================
with st.sidebar:
    st.markdown(f"👤 **User:** `{st.session_state['user']}`")
    if st.button("Logout", type="secondary", use_container_width=True):
        st.session_state["authenticated"] = False
        st.session_state["user"] = None
        st.session_state["processed_report"] = None
        st.rerun()
    st.divider()

st.title("⚡ Mini-Grid Monthly Performance Reporter")
st.markdown("Analyze raw system logs and maintain a central historical archive for your mini-grid operations.")

# =========================================================
# 0. User Input for Mini-Grid Parameters
# =========================================================
st.header("1. Mini-Grid Configuration")
col1, col2, col3, col4 = st.columns(4)

with col1:
    grid_name = st.text_input("Mini-grid Name", value="My Mini-Grid")
with col2:
    grid_capacity_kwp = st.number_input("Capacity (kWp)", min_value=0.1, value=10.0, step=0.1)
with col3:
    peak_sun_hours = st.number_input("Peak Sun Hours", min_value=0.1, value=4.5, step=0.1)
with col4:
    derate_factor = st.number_input("Derate Factor (e.g., 0.75)", min_value=0.01, max_value=1.0, value=0.75, step=0.05)

# =========================================================
# 1. Choose Dashboard Mode
# =========================================================
st.header("2. Choose Dashboard Mode")
app_mode = st.radio("What operational task would you like to run?", ["Upload New CSV Logs", "📜 View Historical Archive Dashboard"], horizontal=True)

# --- MODE A: FILE UPLOADER & PROCESSING ---
if app_mode == "Upload New CSV Logs":
    uploaded_files = st.file_uploader(
        f"Select CSV Log Files for {grid_name}", 
        type=["csv", "CSV"], 
        accept_multiple_files=True,
        key=f"file_uploader_{st.session_state['uploader_key']}"
    )

    generate_report = False
    if uploaded_files:
        btn_col1, btn_col2, _ = st.columns([1.5, 1, 6])
        with btn_col1:
            if st.button("🚀 Generate Report", type="primary", use_container_width=True):
                generate_report = True
        with btn_col2:
            if st.button("❌ Clear Files", type="secondary", use_container_width=True):
                st.session_state["uploader_key"] += 1
                st.session_state["processed_report"] = None
                st.rerun()

    # =========================================================
    # 2. Report Generation Logic (Runs only on click)
    # =========================================================
    if uploaded_files and generate_report:
        with st.spinner("Processing files..."):
            data_records = []
            event_records = []

            for file in uploaded_files:
                content = file.read().decode('latin1')
                lines = content.splitlines()
                
                if len(lines) < 4: 
                    continue 
                    
                r0 = [x.strip('"\n\r ') for x in lines[0].split(',')]
                r2 = [x.strip('"\n\r ') for x in lines[2].split(',')]
                
                cols = ["Time"]
                last_r0 = ""
                for i in range(1, len(r0)):
                    if r0[i] != "":
                        last_r0 = r0[i]
                        
                    phase = r2[i] if i < len(r2) and r2[i] != "" else ""
                    col_name = f"{last_r0} {phase}".strip()
                    cols.append(col_name)

                for line in lines[3:]:
                    row = [x.strip('"\n\r ') for x in line.split(',')]
                    if not row or not row[0]: continue
                    
                    timestamp = row[0]
                    
                    if re.match(r'\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}', timestamp):
                        row_data = {}
                        for i in range(1, len(cols)):
                            try:
                                row_data[cols[i]] = float(row[i]) if i < len(row) and row[i] != '' else None
                            except ValueError:
                                row_data[cols[i]] = None
                                
                        row_data['Time'] = timestamp
                        data_records.append(row_data)
                        
                    elif re.match(r'\d{1,2}:\d{2}:\d{2}', timestamp):
                        msg = row[1] if len(row) > 1 else ""
                        event_records.append({
                            'Time': timestamp, 
                            'Message': msg
                        })

            if not data_records:
                st.error("Error: No valid system data was found in the selected files.")
                st.stop()

            df_data = pd.DataFrame(data_records)
            df_data['Time'] = pd.to_datetime(df_data['Time'], format='%d.%m.%Y %H:%M')
            df_data.set_index('Time', inplace=True)
            df_data = df_data.sort_index()

            df_events = pd.DataFrame(event_records)
            review_period = df_data.index[0].strftime('%B %Y')

            if 'Solar power (ALL) [kW] ALL' in df_data.columns:
                daily_solar_kwh = df_data['Solar power (ALL) [kW] ALL'].resample('D').sum() / 60
            else:
                daily_solar_kwh = pd.Series(dtype=float)

            pout_cols = [c for c in df_data.columns if c.startswith('XT-Pout a [kW]')]

            if pout_cols:
                df_data['Total_AC_Output_kW'] = df_data[pout_cols].sum(axis=1, skipna=True)
                daily_ac_output_kwh = df_data['Total_AC_Output_kW'].resample('D').sum() / 60
                daily_online_hours = (df_data['Total_AC_Output_kW'] > 0).resample('D').sum() / 60
                peak_ac_power_kw = df_data['Total_AC_Output_kW'].max() 
            else:
                daily_ac_output_kwh = pd.Series(dtype=float)
                daily_online_hours = pd.Series(dtype=float)
                peak_ac_power_kw = 0.0

            if 'BSP-SOC [%] 1' in df_data.columns:
                daily_min_soc = df_data['BSP-SOC [%] 1'].resample('D').min()
                daily_max_soc = df_data['BSP-SOC [%] 1'].resample('D').max()
                min_soc_timestamp = df_data['BSP-SOC [%] 1'].resample('D').apply(lambda x: x.idxmin() if x.notna().any() else pd.NaT)
                daily_min_soc_time = min_soc_timestamp.dt.strftime('%H:%M')
                soc_6am = df_data['BSP-SOC [%] 1'].between_time('05:55', '06:05').resample('D').mean()
                soc_6pm = df_data['BSP-SOC [%] 1'].between_time('17:55', '18:05').resample('D').mean()
            else:
                daily_min_soc = pd.Series(dtype=float)
                daily_max_soc = pd.Series(dtype=float)
                daily_min_soc_time = pd.Series(dtype=str)
                soc_6am = pd.Series(dtype=float)
                soc_6pm = pd.Series(dtype=float)

            report_df = pd.DataFrame({
                'Solar_Yield_kWh': daily_solar_kwh.round(2) if not daily_solar_kwh.empty else None,
                'AC_Energy_Output_kWh': daily_ac_output_kwh.round(2) if not daily_ac_output_kwh.empty else None,
                'System_Online_Hours': daily_online_hours.round(2) if not daily_online_hours.empty else None,
                'SOC_6AM_%': soc_6am.round(1) if not soc_6am.empty else None,
                'SOC_6PM_%': soc_6pm.round(1) if not soc_6pm.empty else None,
                'Max_SOC_%': daily_max_soc, 
                'Min_SOC_%': daily_min_soc,
                'Time_of_Min_SOC': daily_min_soc_time
            })

            # Save compiled datasets to continuous background session memory
            st.session_state["processed_report"] = {
                "report_df": report_df,
                "df_data": df_data,
                "df_events": df_events,
                "review_period": review_period,
                "grid_name": grid_name,
                "grid_capacity_kwp": grid_capacity_kwp,
                "peak_sun_hours": peak_sun_hours,
                "derate_factor": derate_factor,
                "peak_ac_power_kw": peak_ac_power_kw
            }

    # =========================================================
    # 3. Render Dashboard from Memory (Keeps UI locked on screen)
    # =========================================================
    if st.session_state["processed_report"] is not None:
        # Unpack stored variables safely
        rep = st.session_state["processed_report"]
        report_df = rep["report_df"]
        df_data = rep["df_data"]
        df_events = rep["df_events"]
        review_period = rep["review_period"]
        active_grid = rep["grid_name"]
        capacity = rep["grid_capacity_kwp"]
        sun_hours = rep["peak_sun_hours"]
        derate = rep["derate_factor"]
        peak_ac_power_kw = rep["peak_ac_power_kw"]

        st.success(f"Successfully loaded processing summary for {review_period}.")
        st.header(f"📊 {active_grid.upper()} REPORT - {review_period.upper()}")

        # =========================================================
        # 🚨 System Anomaly Detection
        # =========================================================
        st.subheader("🚨 System Anomaly Detection")
        with st.expander("🛠️ View Detected System Anomalies & Warnings", expanded=True):
            anomaly_found = False
            
            critical_soc_days = report_df[report_df['Min_SOC_%'] < 20.0]
            if not critical_soc_days.empty:
                anomaly_found = True
                dates_str = ", ".join(critical_soc_days.index.strftime('%b %d'))
                st.error(f"**Critical Deep Discharge Detected (< 20%):** Happened on **{dates_str}**. "
                         f"The Lithium-ion bank hit a minimum low of {critical_soc_days['Min_SOC_%'].min():.1f}%.")
            
            poor_recharge_days = report_df[report_df['Max_SOC_%'] < 85.0]
            if not poor_recharge_days.empty:
                anomaly_found = True
                dates_str = ", ".join(poor_recharge_days.index.strftime('%b %d'))
                st.warning(f"**Incomplete Daytime Recharge (< 85%):** Batteries failed to fully charge on **{dates_str}**.")

            if 'Solar power (ALL) [kW] ALL' in df_data.columns:
                midday_solar = df_data.between_time('11:00', '13:00')
                daily_midday_avg = midday_solar['Solar power (ALL) [kW] ALL'].resample('D').mean()
                zero_solar_days = daily_midday_avg[daily_midday_avg < 0.1]
                if not zero_solar_days.empty:
                    anomaly_found = True
                    dates_str = ", ".join(zero_solar_days.index.strftime('%b %d'))
                    st.error(f"**Zero Midday Solar Output Trip:** Solar generation cut out between 11 AM - 1 PM on **{dates_str}**.")

            outage_days = report_df[report_df['System_Online_Hours'] < 23.5]
            if not outage_days.empty:
                anomaly_found = True
                for idx, row in outage_days.iterrows():
                    st.error(f"**System Blackout Event:** Grid went offline on **{idx.strftime('%b %d')}** for ~{24.0 - row['System_Online_Hours']:.2f} hours.")

            if not anomaly_found:
                st.success("✅ No operational anomalies detected. System parameters running within target tolerances.")

        st.divider()

        # =========================================================
        # 4. Monthly Totals & KPI Calculations
        # =========================================================
        total_solar = report_df['Solar_Yield_kWh'].sum()
        total_ac = report_df['AC_Energy_Output_kWh'].sum()
        total_hours = report_df['System_Online_Hours'].sum()
        avg_soc_6am = report_df['SOC_6AM_%'].mean()
        avg_soc_6pm = report_df['SOC_6PM_%'].mean()

        log_year = df_data.index[0].year
        log_month = df_data.index[0].month
        num_days_in_month = calendar.monthrange(log_year, log_month)[1]
        planned_operational_hours = num_days_in_month * 24

        specific_yield = total_ac / capacity if capacity > 0 else 0
        pr_denominator = num_days_in_month * sun_hours
        performance_ratio = (specific_yield / pr_denominator) * 100 if pr_denominator > 0 else 0
        cf_denominator = capacity * planned_operational_hours
        capacity_factor = (total_ac / cf_denominator) * 100 if cf_denominator > 0 else 0
        availability_factor = (total_hours / planned_operational_hours) * 100 if planned_operational_hours > 0 else 0
        target_generation = sun_hours * capacity * num_days_in_month * derate

        st.subheader("Monthly Totals")
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Total Solar Yield", f"{total_solar:,.2f} kWh")
        m2.metric("Total AC Energy Output", f"{total_ac:,.2f} kWh")
        m3.metric("System Online Time", f"{total_hours:,.2f} hrs")
        m4.metric("Avg SOC (6 AM / 6 PM)", f"{avg_soc_6am:.1f}% / {avg_soc_6pm:.1f}%")
        m5.metric("Peak AC Power", f"{peak_ac_power_kw:,.2f} kW")

        st.divider()

        st.subheader("Key Performance Indicators (KPIs)")
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Specific Yield", f"{specific_yield:,.2f} kWh/kWp")
        k2.metric("Performance Ratio", f"{performance_ratio:.2f}%")
        k3.metric("Capacity Factor", f"{capacity_factor:.2f}%")
        k4.metric("Availability Factor", f"{availability_factor:.2f}%")
        st.info(f"**Target Solar Generation:** {target_generation:,.2f} kWh")

        # ==========================================
        # --- Visualizations & Dataframes ---
        # ==========================================
        st.divider()
        st.subheader("📈 High-Resolution Performance Visualizations")
        tab1, tab2, tab3 = st.tabs(["⚡ Power Profile (kW)", "🔋 Battery SOC (%)", "⏱️ Daily Online Hours"])
        
        with tab1:
            power_df = df_data[['Solar power (ALL) [kW] ALL', 'Total_AC_Output_kW']].copy()
            power_df.columns = ['Solar Power (kW)', 'AC Output (kW)'] 
            fig_power = px.line(power_df, y=['Solar Power (kW)', 'AC Output (kW)'], labels={'value': 'Power (kW)', 'Time': 'Date & Time'})
            st.plotly_chart(fig_power, use_container_width=True)
            
        with tab2:
            if 'BSP-SOC [%] 1' in df_data.columns:
                fig_soc = px.line(df_data, y='BSP-SOC [%] 1', labels={'BSP-SOC [%] 1': 'Battery SOC (%)'})
                st.plotly_chart(fig_soc, use_container_width=True)
            else:
                st.warning("SOC data not available in these logs.")
            
        with tab3:
            st.area_chart(report_df['System_Online_Hours'])
            
        st.divider()
        st.subheader("Daily Performance Summary Table")
        st.dataframe(report_df, use_container_width=True)

        # ==========================================
        # --- Action Buttons (Download & Save) ---
        # ==========================================
        clean_grid_name = "".join(x for x in active_grid if x.isalnum() or x in " -_")
        output_filename = f'{clean_grid_name}_{review_period.replace(" ", "_")}_Report.csv'
        csv_data = report_df.to_csv().encode('utf-8')
        
        action_col1, action_col2, _ = st.columns([2, 2.5, 4])
        with action_col1:
            st.download_button(label="⬇️ Download Daily Report (CSV)", data=csv_data, file_name=output_filename, mime='text/csv', use_container_width=True)
        
        with action_col2:
            if st.button("💾 Save Report to Historical Database", type="primary", use_container_width=True):
                with st.spinner("Archiving data rows directly to Supabase..."):
                    try:
                        with conn.session as session:
                            session.execute(text("""
                                CREATE TABLE IF NOT EXISTS minigrid_daily_reports (
                                    id SERIAL PRIMARY KEY,
                                    grid_name VARCHAR(100) NOT NULL,
                                    report_date DATE NOT NULL,
                                    solar_yield_kwh FLOAT,
                                    ac_energy_output_kwh FLOAT,
                                    system_online_hours FLOAT,
                                    soc_6am FLOAT,
                                    soc_6pm FLOAT,
                                    max_soc FLOAT,
                                    min_soc FLOAT,
                                    time_of_min_soc VARCHAR(10),
                                    UNIQUE(grid_name, report_date)
                                );
                            """))
                            
                            for idx, row in report_df.iterrows():
                                session.execute(
                                    text("""
                                    INSERT INTO minigrid_daily_reports 
                                    (grid_name, report_date, solar_yield_kwh, ac_energy_output_kwh, system_online_hours, soc_6am, soc_6pm, max_soc, min_soc, time_of_min_soc)
                                    VALUES (:grid_name, :report_date, :solar, :ac, :online, :soc6am, :soc6pm, :max_soc, :min_soc, :time_min)
                                    ON CONFLICT (grid_name, report_date) 
                                    DO UPDATE SET 
                                        solar_yield_kwh = EXCLUDED.solar_yield_kwh,
                                        ac_energy_output_kwh = EXCLUDED.ac_energy_output_kwh,
                                        system_online_hours = EXCLUDED.system_online_hours,
                                        soc_6am = EXCLUDED.soc_6am,
                                        soc_6pm = EXCLUDED.soc_6pm,
                                        max_soc = EXCLUDED.max_soc,
                                        min_soc = EXCLUDED.min_soc,
                                        time_of_min_soc = EXCLUDED.time_of_min_soc;
                                    """),
                                    {
                                        "grid_name": active_grid,
                                        "report_date": idx.date(),
                                        "solar": None if pd.isna(row['Solar_Yield_kWh']) else float(row['Solar_Yield_kWh']),
                                        "ac": None if pd.isna(row['AC_Energy_Output_kWh']) else float(row['AC_Energy_Output_kWh']),
                                        "online": None if pd.isna(row['System_Online_Hours']) else float(row['System_Online_Hours']),
                                        "soc6am": None if pd.isna(row['SOC_6AM_%']) else float(row['SOC_6AM_%']),
                                        "soc6pm": None if pd.isna(row['SOC_6PM_%']) else float(row['SOC_6PM_%']),
                                        "max_soc": None if pd.isna(row['Max_SOC_%']) else float(row['Max_SOC_%']),
                                        "min_soc": None if pd.isna(row['Min_SOC_%']) else float(row['Min_SOC_%']),
                                        "time_min": str(row['Time_of_Min_SOC']) if pd.notna(row['Time_of_Min_SOC']) else None
                                    }
                                )
                            session.commit()
                        st.success("🎉 Monthly data compiled and safely archived in Supabase cloud!")
                    except Exception as e:
                        st.error(f"Failed to communicate with Supabase: {e}")

        if not df_events.empty:
            st.divider()
            st.subheader("Top System Events / Faults")
            top_events = df_events['Message'].value_counts().head(5).reset_index()
            top_events.columns = ['Event Message', 'Count']
            st.dataframe(top_events, hide_index=True)

# --- MODE B: HISTORICAL DATABASE EXPLORER ---
elif app_mode == "📜 View Historical Archive Dashboard":
    st.subheader("📜 Historical Mini-Grid Data Explorer")
    
    try:
        # Using ttl=0 to bypass cache and fetch fresh databases automatically
        available_grids_df = conn.query("SELECT DISTINCT grid_name FROM minigrid_daily_reports;", ttl=0)
        
        if not available_grids_df.empty:
            selected_grid = st.selectbox("Select Mini-Grid Portfolio:", available_grids_df['grid_name'])
            
            # Using ttl=0 to ensure immediate view of recently saved metrics
            hist_df = conn.query(
                "SELECT * FROM minigrid_daily_reports WHERE grid_name = :name ORDER BY report_date ASC;",
                params={"name": selected_grid},
                ttl=0
            )
            
            hist_df['report_date'] = pd.to_datetime(hist_df['report_date'])
            
            h_col1, h_col2, h_col3 = st.columns(3)
            h_col1.metric("Total Logged History", f"{len(hist_df)} days")
            h_col2.metric("Cumulative Generation Archive", f"{hist_df['solar_yield_kwh'].sum():,.1f} kWh")
            h_col3.metric("Cumulative Energy Served", f"{hist_df['ac_energy_output_kwh'].sum():,.1f} kWh")
            
            st.write("### 📈 Long-term Energy Metrics Analysis")
            fig_hist = px.line(hist_df, x="report_date", y=["solar_yield_kwh", "ac_energy_output_kwh"], 
                               labels={"value": "Energy Metrics (kWh)", "report_date": "Observation Date"},
                               title=f"Archived Asset Yield Analysis for {selected_grid}")
            fig_hist.update_layout(hovermode="x unified", legend_title_text="")
            st.plotly_chart(fig_hist, use_container_width=True)
            
            st.write("### 🔋 Battery Health Trend Tracking")
            fig_soc_hist = px.scatter(hist_df, x="report_date", y="min_soc", color="min_soc",
                                      color_continuous_scale=["red", "orange", "green"],
                                      range_color=[15, 45],
                                      labels={"min_soc": "Minimum Daily SOC (%)", "report_date": "Observation Date"},
                                      title="Historical Low Voltage/Discharge Index Progression")
            st.plotly_chart(fig_soc_hist, use_container_width=True)
            
            st.write("### Raw Historical Database Records")
            st.dataframe(hist_df.set_index("report_date"), use_container_width=True)
            
        else:
            st.info("The database structure is active but empty. Upload metrics in 'Upload New CSV Logs' mode and hit save.")
    except Exception as e:
        st.info("The historical tables are not yet initialized. Upload your first month of metrics to activate the cloud tables automatically.")
