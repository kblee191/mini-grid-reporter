import streamlit as st
import pandas as pd
import re
import calendar
import plotly.express as px

# Page Configuration
st.set_page_config(page_title="Mini-Grid Reporter", layout="wide", page_icon="⚡")

# =========================================================
# 🔒 Authentication System
# =========================================================
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

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
        st.rerun()
    st.divider()

st.title("⚡ Mini-Grid Monthly Performance Reporter")
st.markdown("Upload your CSV log files to automatically generate a monthly performance report.")

if "uploader_key" not in st.session_state:
    st.session_state["uploader_key"] = 0

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
# 1. File Uploading & Action Buttons
# =========================================================
st.header("2. Upload Log Files")

uploaded_files = st.file_uploader(
    f"Select CSV Log Files for {grid_name}", 
    type=["csv", "CSV"], 
    accept_multiple_files=True,
    key=f"file_uploader_{st.session_state['uploader_key']}"
)

if uploaded_files:
    btn_col1, btn_col2, _ = st.columns([1.5, 1, 6])
    with btn_col1:
        generate_report = st.button("🚀 Generate Report", type="primary", use_container_width=True)
    with btn_col2:
        if st.button("❌ Clear Files", type="secondary", use_container_width=True):
            st.session_state["uploader_key"] += 1
            st.rerun()
else:
    generate_report = False

# =========================================================
# 2. Report Generation Logic
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

        st.success(f"Successfully processed {len(uploaded_files)} files for {review_period}.")

        # =========================================================
        # 3. Extract Metrics & Setup Summary DataFrame
        # =========================================================
        st.header(f"📊 {grid_name.upper()} REPORT - {review_period.upper()}")

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

        # =========================================================
        # 🚨 NEW FEATURE: Field Engineer Automated Diagnostics
        # =========================================================
        st.subheader("🚨 System Anomaly Detection")
        
        with st.expander("🛠️ View Detected System Anomalies & Warnings", expanded=True):
            anomaly_found = False
            
            # 1. Lithium Deep Discharge Check (< 20%)
            critical_soc_days = report_df[report_df['Min_SOC_%'] < 15.0]
            if not critical_soc_days.empty:
                anomaly_found = True
                dates_str = ", ".join(critical_soc_days.index.strftime('%b %d'))
                st.error(f"**Critical Deep Discharge Deteted (< 15%):** Happened on **{dates_str}**. "
                         f"The Lithium-ion bank hit a minimum low of {critical_soc_days['Min_SOC_%'].min():.1f}%. "
                         f"Possible load overload or undersized array.")
            
            # 2. Deficit Daytime Recharge Check (Max SOC < 85% during the day)
            poor_recharge_days = report_df[report_df['Max_SOC_%'] < 85.0]
            if not poor_recharge_days.empty:
                anomaly_found = True
                dates_str = ", ".join(poor_recharge_days.index.strftime('%b %d'))
                st.warning(f"**Incomplete Daytime Recharge (< 85%):** Batteries failed to fully charge on **{dates_str}**. "
                           f"Check if panels are heavily soiled/shaded or daytime load was abnormally high.")

            # 3. Peak Midday Solar Dropped to Zero (Inverter/Breaker Trip Check)
            if 'Solar power (ALL) [kW] ALL' in df_data.columns:
                midday_solar = df_data.between_time('11:00', '13:00')
                daily_midday_avg = midday_solar['Solar power (ALL) [kW] ALL'].resample('D').mean()
                zero_solar_days = daily_midday_avg[daily_midday_avg < 0.1] # effectively 0 kW during peak sun
                
                if not zero_solar_days.empty:
                    anomaly_found = True
                    dates_str = ", ".join(zero_solar_days.index.strftime('%b %d'))
                    st.error(f"**Zero Midday Solar Output Trip:** Solar generation completely cut out between 11 AM - 1 PM on **{dates_str}**. "
                             f"This indicates a severe local hardware event (e.g., Tripped DC breaker, blown string fuses, or inverter error).")

            # 4. System Outage / Micro-blackout Check (Online Hours < 23.5 hours)
            outage_days = report_df[report_df['System_Online_Hours'] < 23.5]
            if not outage_days.empty:
                anomaly_found = True
                for idx, row in outage_days.iterrows():
                    st.error(f"**System Blackout Event:** Grid went offline on **{idx.strftime('%b %d')}** for approximately "
                             f"{24.0 - row['System_Online_Hours']:.2f} hours. Cross-reference the fault log below for exact timing.")

            if not anomaly_found:
                st.success("✅ No operational anomalies detected. Lithium-ion health parameters and PV strings running within target tolerances.")

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

        specific_yield = total_ac / grid_capacity_kwp if grid_capacity_kwp > 0 else 0
        pr_denominator = num_days_in_month * peak_sun_hours
        performance_ratio = (specific_yield / pr_denominator) * 100 if pr_denominator > 0 else 0
        cf_denominator = grid_capacity_kwp * planned_operational_hours
        capacity_factor = (total_ac / cf_denominator) * 100 if cf_denominator > 0 else 0
        availability_factor = (total_hours / planned_operational_hours) * 100 if planned_operational_hours > 0 else 0
        target_generation = peak_sun_hours * grid_capacity_kwp * num_days_in_month * derate_factor

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
            st.markdown("**Minute-by-Minute Solar Power vs. AC Output**")
            power_df = df_data[['Solar power (ALL) [kW] ALL', 'Total_AC_Output_kW']].copy()
            power_df.columns = ['Solar Power (kW)', 'AC Output (kW)'] 
            fig_power = px.line(power_df, y=['Solar Power (kW)', 'AC Output (kW)'], labels={'value': 'Power (kW)', 'Time': 'Date & Time'})
            fig_power.update_layout(legend_title_text='', hovermode="x unified")
            st.plotly_chart(fig_power, use_container_width=True)
            
        with tab2:
            st.markdown("**Continuous State of Charge (SOC) Profile**")
            if 'BSP-SOC [%] 1' in df_data.columns:
                fig_soc = px.line(df_data, y='BSP-SOC [%] 1', labels={'BSP-SOC [%] 1': 'Battery SOC (%)'})
                fig_soc.update_layout(hovermode="x unified")
                st.plotly_chart(fig_soc, use_container_width=True)
            else:
                st.warning("SOC data not available in these logs.")
            
        with tab3:
            st.markdown("**System Online Hours per Day**")
            st.area_chart(report_df['System_Online_Hours'])
            
        st.divider()

        st.subheader("Daily Performance Summary Table")
        st.dataframe(report_df, use_container_width=True)

        clean_grid_name = "".join(x for x in grid_name if x.isalnum() or x in " -_")
        output_filename = f'{clean_grid_name}_{review_period.replace(" ", "_")}_Report.csv'
        csv_data = report_df.to_csv().encode('utf-8')
        st.download_button(label="⬇️ Download Daily Report (CSV)", data=csv_data, file_name=output_filename, mime='text/csv')

        if not df_events.empty:
            st.divider()
            st.subheader("Top System Events / Faults")
            top_events = df_events['Message'].value_counts().head(5).reset_index()
            top_events.columns = ['Event Message', 'Count']
            st.dataframe(top_events, hide_index=True)
