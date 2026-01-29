import nselib
from nselib import capital_market
import pandas as pd
from datetime import datetime, timedelta
import os
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# --- CONFIG ---
FOLDER_ID = os.environ.get("DRIVE_FOLDER_ID")
SERVICE_ACCOUNT_INFO = json.loads(os.environ.get("GCP_SERVICE_ACCOUNT"))

def authenticate_drive():
    creds = service_account.Credentials.from_service_account_info(
        SERVICE_ACCOUNT_INFO,
        scopes=['https://www.googleapis.com/auth/drive']
    )
    return build('drive', 'v3', credentials=creds)

def fetch_nse_data():
    # Try today, if no data (weekend/holiday), try yesterday
    for i in range(0, 5):
        date_obj = datetime.now() - timedelta(days=i)
        date_str = date_obj.strftime("%d-%m-%Y")
        print(f"Trying to fetch NSE Bhavcopy for: {date_str}")
        
        try:
            # THIS IS THE MAGIC: One call gets ALL stocks
            df = capital_market.bhav_copy_with_delivery(date_str)
            if df is not None and not df.empty:
                print("✅ Data fetched successfully!")
                return df, date_str
        except Exception as e:
            print(f"No data for {date_str}: {e}")
            pass
    return None, None

def upload_to_drive(df, date_str):
    filename = "latest_nse_data.csv"
    df.to_csv(filename, index=False)
    
    service = authenticate_drive()
    
    # 1. Search if file already exists
    query = f"name = '{filename}' and '{FOLDER_ID}' in parents and trashed = false"
    results = service.files().list(q=query, fields="files(id)").execute()
    files = results.get('files', [])
    
    media = MediaFileUpload(filename, mimetype='text/csv')
    
    if files:
        # Update existing file (So your dashboard always reads the same file ID)
        file_id = files[0]['id']
        service.files().update(fileId=file_id, media_body=media).execute()
        print(f"✅ Updated existing file on Drive: {file_id}")
    else:
        # Create new file
        file_metadata = {'name': filename, 'parents': [FOLDER_ID]}
        service.files().create(body=file_metadata, media_body=media).execute()
        print(f"✅ Created new file on Drive")

if __name__ == "__main__":
    df, date_str = fetch_nse_data()
    if df is not None:
        upload_to_drive(df, date_str)
    else:
        print("❌ Could not fetch data after multiple attempts.")
