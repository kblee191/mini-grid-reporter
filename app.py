# --- MODE B: HISTORICAL DATABASE EXPLORER ---
elif app_mode == "📜 View Historical Archive Dashboard":
    st.subheader("📜 Historical Mini-Grid Data Explorer")
    
    try:
        # ADDED ttl=0 HERE to force fresh portfolio list
        available_grids_df = conn.query("SELECT DISTINCT grid_name FROM minigrid_daily_reports;", ttl=0)
        
        if not available_grids_df.empty:
            selected_grid = st.selectbox("Select Mini-Grid Portfolio:", available_grids_df['grid_name'])
            
            # ADDED ttl=0 HERE to force fresh data pull for the selected grid
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
