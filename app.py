import streamlit as st
import pandas as pd
import nselib
from nselib import capital_market
import google.generativeai as genai

# --- 1. SETUP AI (Using the standard stable model) ---
try:
    if "GEMINI_API_KEY" in st.secrets:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        model = genai.GenerativeModel('gemini-1.5-flash') 
    else:
        st.error("⚠️ AI Key missing. Please check Streamlit Secrets.")
except Exception as e:
    st.error(f"AI Setup Error: {e}")

st.set_page_config(page_title="Vivek's Alpha Dashboard", layout="wide")
st.title("🇮🇳 Indian Market Accumulation Tracker")

# --- 2. INPUT ---
ticker = st.text_input("Enter NSE Ticker (e.g., RELIANCE)", "RELIANCE").upper().strip()

# --- 3. ROBUST DATA FETCHING ---
if st.button("Fetch & Analyze Data"):
    with st.spinner("Fetching data from NSE..."):
        try:
            # Fetch data
            data = capital_market.price_volume_and_deliverable_position_data(symbol=ticker, period='1M')
            
            if data is None or data.empty:
                st.error("No data received from NSE.")
            else:
                # --- CRITICAL FIX: CLEAN WEIRD COLUMN NAMES ---
                # This fixes the ï»¿"Symbol" and quoted headers seen in your screenshot
                data.columns = [c.replace('"', '').strip() for c in data.columns]
                
                # Target the exact column name seen in your logs
                target_col = "%DlyQttoTradedQty"
                
                # Fallback search if exact name differs
                if target_col not in data.columns:
                    possible_cols = [c for c in data.columns if "DlyQt" in c or "DELIV" in c]
                    if possible_cols:
                        target_col = possible_cols[0]
                
                if target_col in data.columns:
                    # Convert to numeric, forcing errors to NaN then filling with 0
                    data[target_col] = pd.to_numeric(data[target_col], errors='coerce').fillna(0)
                    
                    latest_val = data[target_col].iloc[-1]
                    
                    # Display Metrics
                    col1, col2 = st.columns(2)
                    col1.metric("Latest Delivery %", f"{latest_val}%")
                    
                    if latest_val > 60:
                        col2.success("💎 HIGH CONVICTION: Institutional Buying")
                    elif latest_val > 40:
                        col2.info("✅ ACCUMULATION: Smart Money Active")
                    else:
                        col2.warning("⚠️ NEUTRAL: Normal Activity")
                        
                    st.dataframe(data.tail(10))
                else:
                    st.error(f"Column '{target_col}' not found. Columns received: {list(data.columns)}")
                    
        except Exception as e:
            st.error(f"Critical Error: {e}")

# --- 4. AI ANALYSIS SECTION ---
st.divider()
st.subheader("🤖 AI Market Decoder")

analysis_list = [
    "Earnings Call Decoder", 
    "Economic Moat Analysis", 
    "Risk Assessment", 
    "Growth Outlook"
]
analysis_type = st.selectbox("Select Strategy", analysis_list)

if st.button("Run AI Analysis"):
    with st.spinner("AI is analyzing..."):
        try:
            # Specific prompt engineering
            prompt = (
                f"Act as a senior financial analyst. Perform a deep {analysis_type} "
                f"for the Indian stock '{ticker}' listed on NSE. "
                "Focus on factual data, risks, and institutional sentiment. "
                "Keep it concise and actionable for a long-term investor."
            )
            response = model.generate_content(prompt)
            st.markdown(response.text)
        except Exception as e:
            st.error(f"AI Error: {e}")
