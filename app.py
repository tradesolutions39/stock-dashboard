import streamlit as st
import pandas as pd
import nselib
from nselib import capital_market
import google.generativeai as genai

# --- PAGE SETUP ---
st.set_page_config(page_title="Vivek's Alpha Dashboard", layout="wide")
st.title("🇮🇳 Indian Market Accumulation Tracker")

# --- SMART AI SETUP (The Fix) ---
# This block automatically finds a working model so you never get a 404 error again.
model = None
try:
    if "GEMINI_API_KEY" in st.secrets:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        
        # Ask Google which models are available for this key
        available_models = []
        try:
            for m in genai.list_models():
                if 'generateContent' in m.supported_generation_methods:
                    available_models.append(m.name)
        except Exception as e:
            st.warning(f"Could not list models: {e}. Defaulting to gemini-pro.")
        
        # Auto-select the best available model
        target_model = "models/gemini-pro" # Fallback default
        
        if 'models/gemini-1.5-flash' in available_models:
            target_model = 'gemini-1.5-flash'
        elif 'models/gemini-pro' in available_models:
            target_model = 'gemini-pro'
        elif available_models:
            target_model = available_models[0] # Pick the first one that exists
            
        model = genai.GenerativeModel(target_model)
    else:
        st.error("⚠️ AI Key missing. Please check Streamlit Secrets.")
except Exception as e:
    st.error(f"AI Connection Failed: {e}")

# --- INPUT SECTION ---
ticker = st.text_input("Enter NSE Ticker (e.g., RELIANCE)", "RELIANCE").upper().strip()

# --- DATA FETCHING ---
if st.button("Fetch & Analyze Data"):
    with st.spinner("Fetching data from NSE..."):
        try:
            data = capital_market.price_volume_and_deliverable_position_data(symbol=ticker, period='1M')
            
            if data is None or data.empty:
                st.error("No data received from NSE.")
            else:
                # CLEAN COLUMN NAMES (Fixes the weird symbols issue)
                data.columns = [c.replace('"', '').strip() for c in data.columns]
                
                # Robust Column Finder
                target_col = "%DlyQttoTradedQty"
                if target_col not in data.columns:
                    possible = [c for c in data.columns if "DlyQt" in c or "DELIV" in c]
                    if possible: target_col = possible[0]
                
                if target_col in data.columns:
                    # Clean data and handle non-numeric values
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
                    st.error(f"Delivery column not found. Available: {list(data.columns)}")
                    
        except Exception as e:
            st.error(f"Error: {e}")

# --- AI ANALYSIS SECTION ---
st.divider()
st.subheader("🤖 AI Market Decoder")
analysis_type = st.selectbox("Select Strategy", [
    "Earnings Call Decoder", 
    "Economic Moat Analysis", 
    "Risk Assessment", 
    "Growth Outlook"
])

if st.button("Run AI Analysis"):
    if not model:
        st.error("AI Model is not connected.")
    else:
        with st.spinner(f"AI is analyzing {ticker}..."):
            try:
                prompt = (
                    f"Act as a senior financial analyst. Perform a deep {analysis_type} "
                    f"for the Indian stock '{ticker}'. Focus on factual data and risks. "
                    "Keep it concise for a long-term investor."
                )
                response = model.generate_content(prompt)
                st.markdown(response.text)
            except Exception as e:
                st.error(f"AI Generation Error: {e}")
