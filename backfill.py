import pandas as pd
from nselib import capital_market
from datetime import date, timedelta
import time
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io
import os

# --- AUTHENTICATION ---
service_account_info = eval(os.environ["GCP_SERVICE_ACCOUNT"])
creds = service_account.Credentials.from_service_account_info(
    service_account_info,
    scopes=['https://www.googleapis.com/auth/drive']
)
drive_service = build('drive', 'v3', credentials=creds)
FOLDER_ID = os.environ["DRIVE_FOLDER_ID"]

# --- DATE SETUP ---
today = date.today()
start_date = today - timedelta(days=365) # Last 1 Year
print(f"🔄 Starting Backfill from {start_date} to {today}...")

full_data = pd.DataFrame()

# --- LOOP THROUGH LAST 365 DAYS ---
current_date = start_date
while current_date <= today:
    # Skip Weekends (Saturday=5, Sunday=6)
    if current_date.weekday() < 5:
        date_str = current_date.strftime("%d-%m-%Y")
        print(f"Fetching: {date_str}...", end=" ")
        
        try:
            # FIX: Using 'bhav_copy_with_delivery' specifically for single-day dumps
            df = capital_market.bhav_copy_with_delivery(date_str)
            
            if df is not None and not df.empty:
                # Add a Date Column (Crucial for history)
                df['Trade_Date'] = current_date
                
                # Append to Master List
                full_data = pd.concat([full_data, df], ignore_index=True)
                print("✅ Done")
            else:
                print("❌ No Data (Holiday?)")
                
        except Exception as e:
            # Short error message to keep logs clean
            print(f"⚠️ Skipped: {e}")
            
        # Sleep to avoid getting blocked by NSE
        time.sleep(1) 
        
    current_date += timedelta(days=1)

# --- UPLOAD TO DRIVE ---
if not full_data.empty:
    print(f"💾 Saving {len(full_data)} rows to Google Drive...")
    
    # Clean Columns
    full_data.columns = [c.replace('"', '').strip() for c in full_data.columns]
    
    # Save to CSV in Memory
    csv_buffer = io.BytesIO()
    full_data.to_csv(csv_buffer, index=False)
    csv_buffer.seek(0)
    
    # Check if file exists to overwrite or create new
    file_metadata = {
        'name': 'nse_history_data.csv',
        'parents': [FOLDER_ID]
    }
    
    media = MediaIoBaseUpload(csv_buffer, mimetype='text/csv', resumable=True)
    
    # First, try to find existing file to overwrite (to avoid duplicates)
    try:
        query = "name = 'nse_history_data.csv' and trashed = false"
        results = drive_service.files().list(q=query, fields="files(id)").execute()
        files = results.get('files', [])
        
        if files:
            # Update existing file
            file_id = files[0]['id']
            drive_service.files().update(
                fileId=file_id,
                media_body=media
            ).execute()
            print("🚀 SUCCESS! Existing History File Updated.")
        else:
            # Create new file
            drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()
            print("🚀 SUCCESS! New History File Created.")
            
    except Exception as e:
        print(f"Upload Error: {e}")

else:
    print("⚠️ No data was collected.")
