import streamlit as st
import pandas as pd
import nselib
from nselib import capital_market

st.set_page_config(page_title="Vivek's Alpha Dashboard", layout="wide")

st.title("🇮🇳 Indian Market Accumulation Tracker")
st.write("Tracking Smart Money through Delivery Percentages")

# Input for stock name
ticker = st.text_input("Enter NSE Ticker (e.g., RELIANCE, SBIN, TCS)", "RELIANCE")

if st.button("Fetch & Analyze Data"):
    try:
        # 1. Fetch Data
        data = capital_market.price_volume_and_deliverable_position_data(symbol=ticker, period='1M')
        data['DELIV_PER'] = pd.to_numeric(data['DELIV_PER'], errors='coerce')
        
        # 2. Latest Metric
        latest_deliv = data['DELIV_PER'].iloc[-1]
        
        col1, col2 = st.columns(2)
        col1.metric(label="Latest Delivery %", value=f"{latest_deliv}%")
        
        # 3. Apply your 1-20%, 20-40% logic
        if latest_deliv > 60:
            col2.success("💎 HIGH CONVICTION: Strong Institutional Accumulation")
        elif latest_deliv > 40:
            col2.info("✅ ACCUMULATION: Smart Money is buying")
        elif latest_deliv > 20:
            col2.warning("⚠️ NEUTRAL: Normal retail activity")
        else:
            col2.error("📉 SPECULATIVE: Mostly intraday/weak hands")

        st.dataframe(data.tail(10))

        # Placeholder for your AI Prompts
        st.divider()
        st.subheader("🤖 AI Market Decoder (8-Point Analysis)")
        if st.button("Run Earnings & Moat Analysis"):
            st.write("Connecting to your 2TB Data Hub and Gemini AI...")
            # We will add the prompt logic here in the next step
            
    except Exception as e:
        st.error(f"Error fetching data. Check ticker name. Details: {e}")
