import streamlit as st
import pandas as pd
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
import io
import plotly.graph_objects as go
import yfinance as yf

# --- PAGE CONFIG ---
st.set_page_config(page_title="Vivek's Pro Dashboard", layout="wide")
st.title("📡 NSE Smart Accumulation Scanner")

# --- INITIALIZE STATE ---
if "search_ticker" not in st.session_state:
    st.session_state.search_ticker = ""

# --- 1. SETUP AI ---
model = None
try:
    if "GEMINI_API_KEY" in st.secrets:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        try:
            test_model = genai.GenerativeModel('gemini-1.5-flash')
            test_model.generate_content("test") 
            model = test_model
        except:
            available = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
            if available: model = genai.GenerativeModel(available[0])
except Exception:
    pass

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

# --- HELPER FUNCTIONS ---
def clean_column_names(df):
    df.columns = [str(c).replace('"', '').strip() for c in df.columns]
    return df

@st.cache_data(ttl=3600)
def load_daily_data():
    try:
        query = "name = 'latest_nse_data.csv' and trashed = false"
        results = drive_service.files().list(q=query, fields="files(id, name)").execute()
        files = results.get('files', [])
        if not files: return None
        
        file_id = files[0]['id']
        request = drive_service.files().get_media(fileId=file_id)
        downloaded = io.BytesIO(request.execute())
        return pd.read_csv(downloaded)
    except:
        return None

@st.cache_data(ttl=3600, show_spinner="Loading History...")
def load_history_data():
    try:
        query = "name = 'nse_history_data.csv' and trashed = false"
        results = drive_service.files().list(q=query, fields="files(id, name, createdTime)").execute()
        files = results.get('files', [])
        if not files: return None
        files.sort(key=lambda x: x.get('createdTime', ''), reverse=True)
        file_id = files[0]['id']
        request = drive_service.files().get_media(fileId=file_id)
        downloaded = io.BytesIO(request.execute())
        
        try:
            df = pd.read_csv(downloaded, usecols=lambda c: c in ['SYMBOL', 'CLOSE_PR', 'CLOSE_PRICE', 'DELIV_PER', 'DELIVERY_PER', 'Trade_Date', 'DATE1'], low_memory=False)
        except ValueError:
            downloaded.seek(0)
            df = pd.read_csv(downloaded, low_memory=False)

        df = clean_column_names(df)
        
        date_col = next((c for c in ['Trade_Date', 'DATE1', 'Date'] if c in df.columns), None)
        if date_col: df['Trade_Date'] = pd.to_datetime(df[date_col], errors='coerce')
        
        close_col = next((c for c in ['CLOSE_PR', 'CLOSE_PRICE'] if c in df.columns), None)
        if close_col: df.rename(columns={close_col: 'CLOSE_PRICE'}, inplace=True)
            
        deliv_col = next((c for c in ['DELIV_PER', 'DELIVERY_PER'] if c in df.columns), None)
        if deliv_col: df.rename(columns={deliv_col: 'DELIV_PER'}, inplace=True)

        return df
    except: return None

@st.cache_data(ttl=86400)
def get_fundamentals(ticker):
    try:
        stock = yf.Ticker(f"{ticker}.NS")
        info = stock.info
        fin = stock.financials
        
        sales_growth, opm_growth, eps_growth = "N/A", "N/A", "N/A"
        
        if not fin.empty and len(fin.columns) >= 2:
            curr = fin.iloc[:, 0]
            prev = fin.iloc[:, 1]
            if 'Total Revenue' in fin.index:
                sales_growth = "⬆️ Rising" if curr['Total Revenue'] > prev['Total Revenue'] else "⬇️ Falling"
            if 'Basic EPS' in fin.index:
                eps_growth = "⬆️ Rising" if curr['Basic EPS'] > prev['Basic EPS'] else "⬇️ Falling"
            if 'Operating Income' in fin.index and 'Total Revenue' in fin.index:
                opm_curr = (curr['Operating Income'] / curr['Total Revenue']) * 100
                opm_prev = (prev['Operating Income'] / prev['Total Revenue']) * 100
                opm_growth = "⬆️ Rising" if opm_curr > opm_prev else "⬇️ Falling"

        return {
            "PE Ratio": info.get("trailingPE", None),
            "ROE": info.get("returnOnEquity", None),
            "Market Cap (Cr)": info.get("marketCap", 0) / 10000000 if info.get("marketCap") else 0,
            "Sector": info.get("sector", "Unknown"),
            "Sales Trend": sales_growth,
            "OPM Trend": opm_growth,
            "EPS Trend": eps_growth
        }
    except: return None

# --- SECTOR FINDER (ON THE FLY) ---
@st.cache_data(ttl=86400)
def get_sector_for_list(ticker_list):
    # This function fetches sectors for a batch of stocks to show accumulation zones
    sector_map = {}
    for t in ticker_list[:15]: # Limit to top 15 to stay fast
        try:
            s = yf.Ticker(f"{t}.NS").info.get('sector', 'Others')
            sector_map[t] = s
        except:
            sector_map[t] = 'Unknown'
    return sector_map

# --- DATA PREP ---
if st.sidebar.button("🛠️ Reset/Refresh Data"):
    st.cache_data.clear()
    st.rerun()

daily_data = load_daily_data()
history_data = load_history_data()

if daily_data is None:
    st.error("❌ Daily data missing.")
    st.stop()

daily_data = clean_column_names(daily_data)
daily_deliv_col = next((c for c in daily_data.columns if "DELIV" in c and ("PER" in c or "%" in c)), None)
if not daily_deliv_col: daily_deliv_col = next((c for c in daily_data.columns if "%" in c), None)

if daily_deliv_col:
    daily_data[daily_deliv_col] = pd.to_numeric(daily_data[daily_deliv_col], errors='coerce').fillna(0)
    
    # --- NEW: TIMEFRAME CALCULATOR ---
    # We calculate the average delivery based on selected timeframe
    
    st.sidebar.header("⏳ Timeframe Selector")
    timeframe = st.sidebar.selectbox("Analyze Accumulation Over:", ["Last 1 Day", "Last 1 Week", "Last 1 Month"])
    
    analysis_df = pd.DataFrame()
    
    if timeframe == "Last 1 Day":
        # Use Daily Data directly
        analysis_df = daily_data.copy()
        analysis_df['Avg_Delivery'] = analysis_df[daily_deliv_col]
        
    elif history_data is not None:
        # Process History Data
        # Ensure Date sorting
        hist_sorted = history_data.sort_values(['SYMBOL', 'Trade_Date'])
        
        days = 5 if timeframe == "Last 1 Week" else 20
        
        # Calculate Mean of last N days per symbol
        # We take the last N rows for each symbol
        grouped = hist_sorted.groupby('SYMBOL').tail(days).groupby('SYMBOL')[['DELIV_PER', 'CLOSE_PRICE']].mean().reset_index()
        grouped.rename(columns={'DELIV_PER': 'Avg_Delivery', 'CLOSE_PRICE': 'Avg_Price'}, inplace=True)
        analysis_df = grouped
    else:
        st.warning("History data needed for Week/Month analysis. Using Daily data for now.")
        analysis_df = daily_data.copy()
        analysis_df['Avg_Delivery'] = analysis_df[daily_deliv_col]

    # --- STRICT FILTRATION (THE 80-98 RULE) ---
    # Filter: Delivery must be >= 80 AND <= 98 (Removing noise)
    
    filtered_df = analysis_df[
        (analysis_df['Avg_Delivery'] >= 80) & 
        (analysis_df['Avg_Delivery'] <= 98)
    ].sort_values('Avg_Delivery', ascending=False)
    
    # Format for display
    display_cols = ['SYMBOL', 'Avg_Delivery']
    if 'CLOSE_PRICE' in analysis_df.columns: 
        display_cols.insert(1, 'CLOSE_PRICE')
    elif 'Avg_Price' in analysis_df.columns:
        display_cols.insert(1, 'Avg_Price')
        
    # --- UI LAYOUT ---
    
    # 1. SECTOR INSIGHTS (Top Accumulating Sectors)
    st.subheader(f"🏆 Top Accumulation Zones ({timeframe})")
    if not filtered_df.empty:
        top_tickers = filtered_df.head(10)['SYMBOL'].tolist()
        
        # Fetch Sectors for these top winners
        with st.spinner("Identifying Sectors of Top Stocks..."):
            sector_map = get_sector_for_list(top_tickers)
            
        # Count Sectors
        sector_counts = pd.Series(sector_map.values()).value_counts()
        
        # Display as metric cards
        s_cols = st.columns(min(4, len(sector_counts)))
        for i, (sec, count) in enumerate(sector_counts.items()):
            if i < 4:
                s_cols[i].metric(label="Dominant Sector", value=sec, delta=f"{count} Stocks")
    else:
        st.info("No stocks matched the 80-98% criteria for this period.")

    st.divider()

    # 2. THE FILTERED LIST (Interactive)
    st.subheader(f"💎 High Quality Accumulation (80% - 98%)")
    st.caption(f"Showing stocks with consistent high delivery over {timeframe}. ETFs and 100% noise excluded.")
    
    # Interactive Table
    event = st.dataframe(
        filtered_df[display_cols].style.format({"Avg_Delivery": "{:.2f}%", "CLOSE_PRICE": "₹{:.2f}", "Avg_Price": "₹{:.2f}"}),
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="accumulation_table"
    )
    
    # Handle Click
    if len(event.selection.rows) > 0:
        idx = event.selection.rows[0]
        st.session_state.search_ticker = filtered_df.iloc[idx]['SYMBOL']

    st.divider()

    # --- STOCK ANALYZER (SEARCH BAR) ---
    st.subheader("🔍 Deep Dive Analyzer")
    col_search, col_stats = st.columns([1, 3])
    
    with col_search:
        search_ticker = st.text_input("Enter Ticker", key="search_ticker").upper().strip()

    if search_ticker:
        # Fetch fresh data for the selected stock
        row = daily_data[daily_data['SYMBOL'] == search_ticker]
        
        # Technical Stats
        if not row.empty:
            val = row[daily_deliv_col].iloc[0]
            price = row['CLOSE_PRICE'].iloc[0] if 'CLOSE_PRICE' in daily_data.columns else "-"
            
            if val > 80: color_txt = "green"
            elif val > 60: color_txt = "orange"
            else: color_txt = "red"
            
            with col_stats:
                st.markdown(f"### Today: ₹{price} | Delivery: :{color_txt}[{val}%]")
        
        # Fundamental Check
        with st.expander(f"📊 Fundamental Health Check: {search_ticker}", expanded=True):
            fund_data = get_fundamentals(search_ticker)
            if fund_data:
                c1, c2, c3, c4 = st.columns(4)
                pe = fund_data['PE Ratio']
                c1.metric("PE Ratio", f"{round(pe, 2)}" if pe else "N/A")
                c2.metric("ROE", f"{round(fund_data['ROE'] * 100, 2)}%" if fund_data['ROE'] else "N/A")
                c3.metric("Market Cap", f"₹{int(fund_data['Market Cap (Cr)'])} Cr")
                c4.metric("Sector", fund_data['Sector'])
                st.divider()
                g1, g2, g3 = st.columns(3)
                g1.metric("Sales Growth", fund_data['Sales Trend'])
                g2.metric("OPM (Margins)", fund_data['OPM Trend'])
                g3.metric("EPS (Profit)", fund_data['EPS Trend'])
            else:
                st.info("Fundamental data not available.")

        # History Chart
        if history_data is not None:
            if 'Trade_Date' in history_data.columns and 'DELIV_PER' in history_data.columns:
                stock_hist = history_data[history_data['SYMBOL'] == search_ticker].sort_values('Trade_Date')
                if not stock_hist.empty:
                    stock_hist['DELIV_PER'] = pd.to_numeric(stock_hist['DELIV_PER'], errors='coerce')
                    stock_hist['CLOSE_PRICE'] = pd.to_numeric(stock_hist['CLOSE_PRICE'], errors='coerce')
                    colors = []
                    for x in stock_hist['DELIV_PER']:
                        if x >= 80: colors.append('rgba(0, 100, 0, 0.8)')
                        elif x >= 60: colors.append('rgba(50, 205, 50, 0.7)')
                        elif x >= 40: colors.append('rgba(128, 128, 128, 0.6)')
                        else: colors.append('rgba(255, 0, 0, 0.6)')

                    fig = go.Figure()
                    fig.add_trace(go.Bar(x=stock_hist['Trade_Date'], y=stock_hist['DELIV_PER'], name='Delivery %', marker_color=colors, yaxis='y2'))
                    fig.add_trace(go.Scatter(x=stock_hist['Trade_Date'], y=stock_hist['CLOSE_PRICE'], name='Price', line=dict(color='black', width=2)))
                    fig.update_layout(title=f"{search_ticker} - Delivery Trend", yaxis=dict(title="Price"), yaxis2=dict(title="Delivery %", overlaying="y", side="right", range=[0, 100]), height=400, hovermode="x unified", showlegend=False)
                    st.plotly_chart(fig, use_container_width=True)
                else: st.info(f"No history found for {search_ticker}")
            else: st.error(f"Missing Columns in History.")
        else: st.info("Loading history file...")

    # AI Analysis
    st.divider()
    if st.button("Analyze Current Ticker") and search_ticker and model:
        row = daily_data[daily_data['SYMBOL'] == search_ticker]
        if not row.empty:
             val = row[daily_deliv_col].iloc[0]
             pr = row['CLOSE_PRICE'].iloc[0] if 'CLOSE_PRICE' in row else "N/A"
             fund_info = get_fundamentals(search_ticker)
             fund_txt = ""
             if fund_info:
                 fund_txt = (f"Fundamentals: Sales {fund_info['Sales Trend']}, Margins {fund_info['OPM Trend']}, EPS {fund_info['EPS Trend']}.")
             prompt = (f"Act as a stock market expert. Analyze {search_ticker}. Price: {pr}. Delivery: {val}%. {fund_txt} Combine Technical and Fundamental data. Turnaround or Compounder? Explain in 2-3 sentences.")
             with st.spinner("AI thinking..."):
                 st.write(model.generate_content(prompt).text)
