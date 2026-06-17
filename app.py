import streamlit as st
import pandas as pd
import re
import calendar

# Page Configuration
st.set_page_config(page_title="Mini-Grid Reporter", layout="wide", page_icon="⚡")

st.title("⚡ Mini-Grid Monthly Performance Reporter")
st.markdown("Upload your CSV log files to automatically generate a monthly performance report.")

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
# 1. File Uploading
# =========================================================
st.header("2. Upload Log Files")
uploaded_files = st.file_uploader(
    f"Select CSV Log Files for {grid_name}", 
    type=["csv"], 
    accept_multiple_files=True
)

if uploaded_files and st.button("Generate Report", type="primary"):
    with st.spinner("Processing files..."):
        data_records = []
        event_records = []

        # 2. Process each selected file
        for file in uploaded_files:
            # Read and decode the file content
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

            # Parse Rows
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

        # 3. Create Pandas DataFrames
        df_data = pd.DataFrame(data_records)
        df_data['Time'] = pd.to_datetime(df_data['Time'], format='%d.%m.%Y %H:%M')
        df_data.set_index('Time', inplace=True)
        df_data = df_data.sort_index()

        df_events = pd.DataFrame(event_records)

        # Extract Review Month and Year automatically
        review_period = df_data.index[0].strftime('%B %Y')

        st.success(f"Successfully processed {len(uploaded_files)} files for {review_period}.")

        # =========================================================
        # 4. Extract Key Operation and Maintenance (O&M) Metrics
        # =========================================================
        st.header(f"📊 {grid_name.upper()} REPORT - {review_period.upper()}")

        # A. Daily Solar Generation (kWh) 
        if 'Solar power (ALL) [kW] ALL' in df_data.columns:
            daily_solar_kwh = df_data['Solar power (ALL) [kW] ALL'].resample('D').sum() / 60
        else:
            daily_solar_kwh = pd.Series(dtype=float)

        # B. Total AC Energy Output (kWh) & Online Hours
        pout_cols = [c for c in df_data.columns if c.startswith('XT-Pout a [kW]')]

        if pout_cols:
            df_data['Total_AC_Output_kW'] = df_data[pout_cols].sum(axis=1, skipna=True)
            daily_ac_output_kwh = df_data['Total_AC_Output_kW'].resample('D').sum() / 60
            daily_online_hours = (df_data['Total_AC_Output_kW'] > 0).resample('D').sum() / 60
        else:
            daily_ac_output_kwh = pd.Series(dtype=float)
            daily_online_hours = pd.Series(dtype=float)

        # C. Daily Battery SOC Analysis
        if 'BSP-SOC [%] 1' in df_data.columns:
            daily_min_soc = df_data['BSP-SOC [%] 1'].resample('D').min()
            
            min_soc_timestamp = df_data['BSP-SOC [%] 1'].resample('D').apply(
                lambda x: x.idxmin() if x.notna().any() else pd.NaT
            )
            daily_min_soc_time = min_soc_timestamp.dt.strftime('%H:%M')
            
            soc_6am = df_data['BSP-SOC [%] 1'].between_time('05:55', '06:05').resample('D').mean()
            soc_6pm = df_data['BSP-SOC [%] 1'].between_time('17:55', '18:05').resample('D').mean()
        else:
            daily_min_soc = pd.Series(dtype=float)
            daily_min_soc_time = pd.Series(dtype=str)
            soc_6am = pd.Series(dtype=float)
            soc_6pm = pd.Series(dtype=float)

        # Combine into a final summary table
        report_df = pd.DataFrame({
            'Solar_Yield_kWh': daily_solar_kwh.round(2) if not daily_solar_kwh.empty else None,
            'AC_Energy_Output_kWh': daily_ac_output_kwh.round(2) if not daily_ac_output_kwh.empty else None,
            'System_Online_Hours': daily_online_hours.round(2) if not daily_online_hours.empty else None,
            'SOC_6AM_%': soc_6am.round(1) if not soc_6am.empty else None,
            'SOC_6PM_%': soc_6pm.round(1) if not soc_6pm.empty else None,
            'Min_SOC_%': daily_min_soc,
            'Time_of_Min_SOC': daily_min_soc_time
        })

        # =========================================================
        # 5. Monthly Totals & KPI Calculations
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

        # --- Display Metrics ---
        st.subheader("Monthly Totals")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Solar Yield", f"{total_solar:,.2f} kWh")
        m2.metric("Total AC Energy Output", f"{total_ac:,.2f} kWh")
        m3.metric("System Online Time", f"{total_hours:,.2f} hrs")
        m4.metric("Average SOC (6 AM / 6 PM)", f"{avg_soc_6am:.1f}% / {avg_soc_6pm:.1f}%")

        st.divider()

        st.subheader("Key Performance Indicators (KPIs)")
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Specific Yield", f"{specific_yield:,.2f} kWh/kWp")
        k2.metric("Performance Ratio", f"{performance_ratio:.2f}%")
        k3.metric("Capacity Factor", f"{capacity_factor:.2f}%")
        k4.metric("Availability Factor", f"{availability_factor:.2f}%")
        st.info(f"**Target Solar Generation:** {target_generation:,.2f} kWh")

        # --- Display Daily Summary Table ---
        st.subheader("Daily Performance Summary")
        st.dataframe(report_df, use_container_width=True)

        # --- Download Button ---
        clean_grid_name = "".join(x for x in grid_name if x.isalnum() or x in " -_")
        output_filename = f'{clean_grid_name}_{review_period.replace(" ", "_")}_Report.csv'
        
        csv_data = report_df.to_csv().encode('utf-8')
        st.download_button(
            label="⬇️ Download Daily Report (CSV)",
            data=csv_data,
            file_name=output_filename,
            mime='text/csv',
        )

        # --- Display Events ---
        if not df_events.empty:
            st.divider()
            st.subheader("Top System Events / Faults")
            top_events = df_events['Message'].value_counts().head(5).reset_index()
            top_events.columns = ['Event Message', 'Count']
            st.dataframe(top_events, hide_index=True)