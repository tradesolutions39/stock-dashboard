import streamlit as st
import pandas as pd
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
import io

# --- PAGE CONFIG ---
st.set_page_config(page_title="Vivek's Pro Dashboard", layout="wide")
st.title("📡 NSE Daily Scanner (Drive Connected)")

# --- 1. ROBUST AI SETUP ---
model = None
try:
    if "GEMINI_API_KEY" in st.secrets:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        # Smart Model Selector
        try:
            # Try Flash first (Fast & Free)
            test_model = genai.GenerativeModel('gemini-1.5-flash')
            test_model.generate_content("test") 
            model = test_model
        except:
            # Fallback to Pro or whatever is available
            available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
            if available_models:
                model = genai.GenerativeModel(available_models[0])
            else:
                st.warning("⚠️ AI Error: No models available.")
except Exception as e:
    st.warning(f"AI disabled: {e}")

# --- 2. SETUP GOOGLE DRIVE ---
try:
    if "gcp_service_account" in st.secrets:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = service_account.Credentials.from_service_account_info(
            creds_dict,
            scopes=['https://www.googleapis.com/auth/drive.readonly']
        )
        drive_service = build('drive', 'v3', credentials=creds)
    else:
        st.error("⚠️ Secrets Error: 'gcp_service_account' missing.")
        st.stop()
except Exception as e:
    st.error(f"Authentication Error: {e}")
    st.stop()

# --- 3. LOAD DATA ---
@st.cache_data(ttl=3600)
def load_data_from_drive():
    try:
        query = "name = 'latest_nse_data.csv' and trashed = false"
        results = drive_service.files().list(q=query, fields="files(id, name)").execute()
        files = results.get('files', [])
        
        if not files: return None
        
        file_id = files[0]['id']
        request = drive_service.files().get_media(fileId=file_id)
        downloaded = io.BytesIO(request.execute())
        
        return pd.read_csv(downloaded)
    except Exception as e:
        st.error(f"Drive Read Error: {e}")
        return None

# --- 4. DASHBOARD UI ---
with st.spinner("Accessing Cloud Database..."):
    data = load_data_from_drive()

if data is None:
    st.error("❌ Data file not found. Please run the GitHub Action.")
else:
    # --- CLEANING & COLUMN FIX ---
    data.columns = [c.replace('"', '').strip() for c in data.columns]
    
    # Priority 1: Look for exact NSE percentage column
    target_col = "%DlyQttoTradedQty"
    
    # Priority 2: Look for columns with '%' or 'Per' (to avoid Quantity)
    if target_col not in data.columns:
        possible = [c for c in data.columns if "%" in c or "PER" in c.upper()]
        if possible: target_col = possible[0]
        else: target_col = None

    if target_col:
        # Force numeric conversion
        data[target_col] = pd.to_numeric(data[target_col], errors='coerce').fillna(0)
        
        # --- SECTION A: SEARCH BAR ---
        st.subheader("🔍 Check Individual Stock")
        col_search, col_display = st.columns([1, 3])
        
        # We store the search in a variable to use it later in AI section
        search_ticker = col_search.text_input("Search Ticker (e.g. TARACHAND)", "").upper().strip()
            
        with col_display:
            if search_ticker:
                stock_row = data[data['SYMBOL'] == search_ticker]
                if not stock_row.empty:
                    val = stock_row[target_col].iloc[0]
                    price = stock_row['CLOSE_PRICE'].iloc[0] if 'CLOSE_PRICE' in data.columns else "N/A"
                    
                    # Display Stats
                    st.metric(f"{search_ticker} Delivery %", f"{val}%", f"Price: {price}")
                    st.dataframe(stock_row)
                else:
                    st.warning(f"Ticker '{search_ticker}' not found in today's data.")

        # --- SECTION B: BUCKETS ---
        st.divider()
        st.subheader("📊 Market Delivery Scanner")
        
        display_cols = ['SYMBOL', 'SERIES', 'CLOSE_PRICE', target_col]
        display_cols = [c for c in display_cols if c in data.columns]
        
        tab1, tab2, tab3 = st.tabs(["🔥 Strong (>80%)", "💎 Accumulation (60-80%)", "⚠️ Weak (<40%)"])
        
        with tab1:
            df = data[data[target_col] >= 80].sort_values(by=target_col, ascending=False)
            st.dataframe(df[display_cols], use_container_width=True)
        with tab2:
            df = data[(data[target_col] >= 60) & (data[target_col] < 80)].sort_values(by=target_col, ascending=False)
            st.dataframe(df[display_cols], use_container_width=True)
        with tab3:
            df = data[data[target_col] < 40].sort_values(by=target_col, ascending=False)
            st.dataframe(df[display_cols], use_container_width=True)

        # --- SECTION C: AI STOCK DECODER (FIXED) ---
        st.divider()
        st.subheader("🤖 AI Stock Decoder")
        
        # Auto-fill the AI input with the Search Ticker if it exists
        default_val = search_ticker if search_ticker else ""
        
        col1, col2 = st.columns([1, 4])
        with col1:
            ai_ticker = st.text_input("Enter Ticker to Decode", value=default_val).upper().strip()
            analyze_btn = st.button("Generate AI Report")
        
        with col2:
            if analyze_btn and ai_ticker:
                if not model:
                    st.error("AI Model is not connected. Check API Key.")
                else:
                    # Find data for this ticker
                    stock_row = data[data['SYMBOL'] == ai_ticker]
                    
                    if not stock_row.empty:
                        del_per = stock_row[target_col].iloc[0]
                        price = stock_row['CLOSE_PRICE'].iloc[0] if 'CLOSE_PRICE' in stock_row else "N/A"
                        
                        prompt = (
                            f"Act as a professional stock analyst. "
                            f"The Indian stock '{ai_ticker}' has a Delivery Percentage of {del_per}% at a price of {price}. "
                            "Explain what this indicates (Accumulation vs Distribution). "
                            "Provide a concise outlook for a swing trader."
                        )
                        
                        with st.spinner(f"AI is analyzing {ai_ticker}..."):
                            try:
                                response = model.generate_content(prompt)
                                st.markdown(response.text)
                            except Exception as e:
                                st.error(f"AI Error: {e}")
                    else:
                        st.warning(f"Could not find data for '{ai_ticker}' to analyze.")
    else:
        st.error(f"Could not find a Percentage column. Available: {list(data.columns)}")
