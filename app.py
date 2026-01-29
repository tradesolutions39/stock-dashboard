import streamlit as st
import pandas as pd
import nselib
from nselib import capital_market
import google.generativeai as genai
import time

# --- PAGE CONFIG ---
st.set_page_config(page_title="Vivek's Market Scanner", layout="wide")

# --- AI SETUP ---
model = None
try:
    if "GEMINI_API_KEY" in st.secrets:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        # Auto-select best model
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        target_model = 'models/gemini-1.5-flash' if 'models/gemini-1.5-flash' in available_models else 'models/gemini-pro'
        model = genai.GenerativeModel(target_model)
except:
    pass

# --- HELPER FUNCTIONS ---
def clean_columns(df):
    df.columns = [c.replace('"', '').strip() for c in df.columns]
    return df

def get_delivery_column(df):
    target_col = "%DlyQttoTradedQty"
    if target_col not in df.columns:
        possible = [c for c in df.columns if "DlyQt" in c or "DELIV" in c]
        if possible: return possible[0]
    return target_col

# --- SIDEBAR ---
st.sidebar.title("🚀 Navigation")
app_mode = st.sidebar.radio("Mode", ["🔍 Single Stock Analysis", "📡 Market Scanner"])

# ==========================================
# MODE 1: SINGLE STOCK
# ==========================================
if app_mode == "🔍 Single Stock Analysis":
    st.title("🇮🇳 Deep Dive Analysis")
    ticker = st.text_input("Enter NSE Ticker", "RELIANCE").upper().strip()
    
    if st.button("Fetch Data"):
        try:
            data = capital_market.price_volume_and_deliverable_position_data(symbol=ticker, period='1M')
            data = clean_columns(data)
            col_name = get_delivery_column(data)
            
            if col_name in data.columns:
                data[col_name] = pd.to_numeric(data[col_name], errors='coerce').fillna(0)
                latest = data[col_name].iloc[-1]
                
                st.metric("Latest Delivery %", f"{latest}%")
                
                if latest >= 80: st.success("🔥 INST. BUYING (80-100%)")
                elif latest >= 60: st.success("💎 HIGH CONVICTION (60-80%)")
                elif latest >= 40: st.info("✅ ACCUMULATION (40-60%)")
                else: st.warning("⚠️ WEAK/TRADING (<40%)")
                
                st.dataframe(data.tail(10))
                
                if model and st.button("AI Analysis"):
                    with st.spinner("AI Analyzing..."):
                        response = model.generate_content(f"Analyze accumulation for {ticker}")
                        st.write(response.text)
        except Exception as e:
            st.error(f"Error: {e}")

# ==========================================
# MODE 2: MARKET SCANNER (ALL STOCKS)
# ==========================================
elif app_mode == "📡 Market Scanner":
    st.title("📡 Full Market Scanner")
    st.info("ℹ️ Scans ALL NSE listed stocks for Delivery %.")
    
    # 1. Fetch Full Stock List
    try:
        @st.cache_data(ttl=86400) # Cache list for 24 hours to save time
        def get_all_stocks():
            return capital_market.equity_list()
            
        stock_df = get_all_stocks()
        all_tickers = stock_df['SYMBOL'].tolist()
        st.write(f"Total Stocks Found: **{len(all_tickers)}**")
        
    except Exception as e:
        st.error("Could not fetch stock list. Using Nifty 50 fallback.")
        all_tickers = ["RELIANCE", "TCS", "INFY"] # Fallback

    # 2. Batch Selection (The Fix for Timeouts)
    batch_size = 200
    total_batches = (len(all_tickers) // batch_size) + 1
    batch_options = [f"Batch {i+1}: Stocks {i*batch_size} - {(i+1)*batch_size}" for i in range(total_batches)]
    
    selected_batch = st.sidebar.selectbox("Select Batch to Scan", batch_options)
    
    # Get tickers for selected batch
    batch_index = batch_options.index(selected_batch)
    start_idx = batch_index * batch_size
    end_idx = start_idx + batch_size
    current_tickers = all_tickers[start_idx:end_idx]
    
    st.write(f"Scanning **{len(current_tickers)}** stocks in this batch...")

    scan_type = st.radio("Metric", ["Daily (Latest Data)", "Weekly Avg (5 Days)"], horizontal=True)

    if st.button("Start Batch Scan"):
        results = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for i, ticker in enumerate(current_tickers):
            try:
                status_text.text(f"Scanning {ticker} ({i+1}/{len(current_tickers)})...")
                
                # Fetch Data
                df = capital_market.price_volume_and_deliverable_position_data(symbol=ticker, period='1M')
                df = clean_columns(df)
                col_name = get_delivery_column(df)
                
                if col_name in df.columns:
                    df[col_name] = pd.to_numeric(df[col_name], errors='coerce').fillna(0)
                    
                    if scan_type == "Daily (Latest Data)":
                        val = df[col_name].iloc[-1]
                    else:
                        val = df[col_name].tail(5).mean()
                    
                    # Store Result
                    results.append({
                        "Symbol": ticker, 
                        "Delivery %": round(val, 2), 
                        "Close Price": df['ClosePrice'].iloc[-1] if 'ClosePrice' in df.columns else 0
                    })
            except:
                pass # Skip errors
            
            # Update Progress
            progress_bar.progress((i + 1) / len(current_tickers))
            
        status_text.text("✅ Scan Complete!")
        
        # 3. Display Results in Buckets
        if results:
            df_res = pd.DataFrame(results)
            
            # Tabs for Buckets
            tab1, tab2, tab3, tab4 = st.tabs(["🔥 80-100%", "💎 60-80%", "✅ 40-60%", "⚠️ <40%"])
            
            with tab1:
                st.dataframe(df_res[df_res['Delivery %'] >= 80])
            with tab2:
                st.dataframe(df_res[(df_res['Delivery %'] >= 60) & (df_res['Delivery %'] < 80)])
            with tab3:
                st.dataframe(df_res[(df_res['Delivery %'] >= 40) & (df_res['Delivery %'] < 60)])
            with tab4:
                st.dataframe(df_res[df_res['Delivery %'] < 40])
