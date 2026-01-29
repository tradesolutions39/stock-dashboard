import streamlit as st
import pandas as pd
import nselib
from nselib import capital_market
import google.generativeai as genai

# Setup AI Brain
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel('gemini-1.5-flash')
except Exception:
    st.error("AI Key is missing! Add GEMINI_API_KEY to Streamlit Secrets.")

st.set_page_config(page_title="Vivek's Alpha Dashboard", layout="wide")
st.title("🇮🇳 Indian Market Accumulation Tracker")

ticker = st.text_input("Enter NSE Ticker (e.g., RELIANCE)", "RELIANCE")

if st.button("Fetch & Analyze Data"):
    with st.spinner("Fetching latest NSE data..."):
        try:
            # 1. Fetching Data
            data = capital_market.price_volume_and_deliverable_position_data(symbol=ticker, period='1M')
            
            # Fix for the KeyError: nselib uses 'DELIV_PERC' (with a C) or index names
            # We will clean the column names to be safe
            data.columns = [c.strip() for c in data.columns]
            
            # Find the correct column even if the name changes slightly
            target_col = [c for c in data.columns if 'DELIV' in c and 'PER' in c][0]
            data[target_col] = pd.to_numeric(data[target_col], errors='coerce')
            
            latest_deliv = data[target_col].iloc[-1]
            
            col1, col2 = st.columns(2)
            col1.metric(label="Latest Delivery %", value=f"{latest_deliv}%")
            
            if latest_deliv > 60:
                col2.success("💎 HIGH CONVICTION: Smart Money is in.")
            elif latest_deliv > 40:
                col2.info("✅ ACCUMULATION: Steady institutional buying.")
            else:
                col2.warning("⚠️ NEUTRAL/SPECULATIVE: Normal activity.")

            st.dataframe(data.tail(10))
            
        except Exception as e:
            st.error(f"Data Fetch Error: {e}")

st.divider()
st.subheader("🤖 AI Market Decoder (8-Point Analysis)")
analysis_type = st.selectbox("Select Your Strategy", [
    "Earnings Call Decoder (Summary & Sentiment)", 
    "Economic Moat Analysis (Competitive Edge)", 
    "Management Guidance Tracker", 
    "Risk Assessment (Financial & Operational)",
    "Growth Outlook (Next 2-3 Years)",
    "Peer Comparison (Sector Analysis)",
    "ESG & Governance Check",
    "Intrinsic Value Estimation"
])

if st.button("Run AI Analysis"):
    with st.spinner(f"AI is performing {analysis_type}..."):
        prompt = f"Perform a deep {analysis_type} for the Indian stock {ticker}. Provide a summary for a long-term investor."
        response = model.generate_content(prompt)
        st.markdown(response.text)
