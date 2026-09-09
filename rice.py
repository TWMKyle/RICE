import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime

# --- 1. INITIAL APP PAGE SETUP ---
st.set_page_config(
    page_title="Rice Inventory Engine", 
    page_icon="🌾", 
    layout="wide"
)

st.title("🌾 Rice Inventory & Price Control Hub")
st.markdown("Monitor stock levels, calculate total valuation, and override item constraints smoothly.")
st.divider()

# --- 2. HARDCODE THE RICE SPREADSHEET URL DIRECTLY IN THE CODE ---
# 💡 Paste your complete, copied web browser address below:
RICE_SHEET_URL = "https://google.com"

try:
    # Connect using your shared universal credentials block
    conn = st.connection("gsheets", type=GSheetsConnection)
    
    # Read the designated data worksheet tab directly via the code URL
    master_df = conn.read(spreadsheet=RICE_SHEET_URL, worksheet="Rice_Inventory", ttl=0)
    
    # Verify expected column properties match
    required_cols = ["SKU", "Rice_Variety", "Bag_Weight_KG", "Stock_Count", "Cost_Price", "Retail_Price", "Last_Updated"]
    missing_cols = [col for col in required_cols if col not in master_df.columns]
    
    if missing_cols:
        st.error(f"❌ Missing expected columns in your sheet: {missing_cols}")
        st.info(f"📋 Columns currently found in your sheet: {list(master_df.columns)}")
        st.stop()
        
    # 💡 FIX: Clean currency text strings (strip out ₱, $, and commas) before making numeric evaluations
    for money_col in ["Cost_Price", "Retail_Price"]:
        master_df[money_col] = (
            master_df[money_col]
            .astype(str)
            .str.replace("₱", "", regex=False)
            .str.replace("$", "", regex=False)
            .str.replace(",", "", regex=False)
            .str.strip()
        )

    # Standardize types for safely executing calculations
    numeric_cols = ["Bag_Weight_KG", "Stock_Count", "Cost_Price", "Retail_Price"]
    for col in numeric_cols:
        master_df[col] = pd.to_numeric(master_df[col], errors='coerce').fillna(0)
        
except Exception as connection_error:
    st.error("❌ High-Level Pipeline Failure!")
    st.write("### 🔍 Technical Debug Details:")
    st.exception(connection_error)
    st.stop()

# --- 3. EXECUTIVE METRICS DASHBOARD ---
total_bags = int(master_df["Stock_Count"].sum())
total_weight_tons = (master_df["Stock_Count"] * master_df["Bag_Weight_KG"]).sum() / 1000
total_asset_value = (master_df["Stock_Count"] * master_df["Cost_Price"]).sum()
potential_revenue = (master_df["Stock_Count"] * master_df["Retail_Price"]).sum()

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Total Bags in Stock", f"{total_bags:,} bags")
with col2:
    st.metric("Total Weight Volume", f"{total_weight_tons:,.2f} Tons")
with col3:
    st.metric("Inventory Asset Cost", f"₱{total_asset_value:,.2f}")
with col4:
    st.metric("Estimated Retail Value", f"₱{potential_revenue:,.2f}")

st.divider()

# --- 4. DATA MANAGEMENT ENGINE ---
left_pane, right_pane = st.columns()

with left_pane:
    st.subheader("📋 Master Stock Manifest")
    st.markdown('<span style="color: white; font-size: 0.85rem;">✏️ Directly edit cells below to adjust stock counts or alter prices. New rows will auto-timestamp.</span>', unsafe_allow_html=True)
    
    # Render interactive spreadsheet grid
    edited_df = st.data_editor(
        master_df, 
        num_rows="dynamic", 
        use_container_width=True,
        column_config={
            "SKU": st.column_config.TextColumn("SKU Code", required=True),
            "Rice_Variety": st.column_config.SelectboxColumn("Rice Variety", options=["Jasmine", "Sinandomeng", "Basmati", "Brown Rice", "Sticky Rice"]),
            "Bag_Weight_KG": st.column_config.NumberColumn("Weight (KG)", min_value=1, format="%d kg"),
            "Stock_Count": st.column_config.NumberColumn("Bags Count", min_value=0, format="%d"),
            "Cost_Price": st.column_config.NumberColumn("Cost per Bag", min_value=0.0, format="₱%.2f"),
            "Retail_Price": st.column_config.NumberColumn("Retail per Bag", min_value=0.0, format="₱%.2f"),
            "Last_Updated": st.column_config.TextColumn("Last Modified", disabled=True)
        }
    )
    
    # Save Action Control
    if st.button("Save & Sync Stock Changes", type="primary"):
        with st.spinner("Writing transactions securely to cloud registry..."):
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
            edited_df["Last_Updated"] = current_time
            
            # Pass the same code URL back when updating the cloud
            conn.update(spreadsheet=RICE_SHEET_URL, data=edited_df, worksheet="Rice_Inventory")
            st.success("🎉 Inventory dashboard synchronized perfectly with cloud storage!")
            st.rerun()

with right_pane:
    st.subheader("⚠️ Low Stock Alerts")
    low_stock_threshold = 10
    low_stock_df = master_df[master_df["Stock_Count"] <= low_stock_threshold]
    
    if not low_stock_df.empty:
        for _, row in low_stock_df.iterrows():
            st.error(f"**{row['Rice_Variety']} ({row['SKU']})**\n\nOnly **{int(row['Stock_Count'])}** bags left!")
    else:
        st.success("✅ All stock volumes sit comfortably above threshold values.")
