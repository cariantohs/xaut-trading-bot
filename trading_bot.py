import os
import feedparser
from textblob import TextBlob
import requests
import pandas as pd
import json
from datetime import datetime, timedelta
import urllib.parse
from ta.volatility import BollingerBands
from ta.momentum import RSIIndicator
from ta.trend import MACD, SMAIndicator
import gspread
from google.oauth2.service_account import Credentials
import sys

# Debugging: Print environment variables
print("Environment variables:")
print(f"SPREADSHEET_ID exists: {'SPREADSHEET_ID' in os.environ}")
print(f"GOOGLE_CREDENTIALS exists: {'GOOGLE_CREDENTIALS' in os.environ}")

# Konfigurasi
SPREADSHEET_ID = os.getenv('SPREADSHEET_ID')

def auth_google_sheets():
    """Autentikasi menggunakan service account"""
    creds_json = os.getenv('GOOGLE_CREDENTIALS')
    if not creds_json:
        print("GOOGLE_CREDENTIALS environment variable is missing")
        sys.exit(1)
    
    try:
        # Debugging: Print first 50 chars of credentials
        print(f"Credentials (first 50 chars): {creds_json[:50]}...")
        
        creds_dict = json.loads(creds_json)
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        return gspread.authorize(creds)
    except json.JSONDecodeError:
        print("Invalid JSON in GOOGLE_CREDENTIALS")
        sys.exit(1)
    except Exception as e:
        print(f"Authentication failed: {str(e)}")
        sys.exit(1)

def save_to_google_sheets(data):
    """Simpan data ke Google Sheets"""
    try:
        client = auth_google_sheets()
        print(f"Opening spreadsheet with ID: {SPREADSHEET_ID}")
        sheet = client.open_by_key(SPREADSHEET_ID)
        today = datetime.utcnow().strftime("%Y-%m-%d")
        
        try:
            worksheet = sheet.worksheet(today)
            print(f"Using existing worksheet: {today}")
        except gspread.WorksheetNotFound:
            print(f"Creating new worksheet: {today}")
            worksheet = sheet.add_worksheet(title=today, rows=1000, cols=20)
            header = [
                "Timestamp", "Price", "VWAP", "RSI", "BB Upper", "BB Lower",
                "MACD Hist", "MACD Signal", "SMA50", "Volume", "News Score",
                "Decision", "Entry", "Take Profit", "Stop Loss", "Risk Ratio", "Logic"
            ]
            worksheet.append_row(header)
            print("Header added")
        
        row = [
            data["timestamp"],
            data["price"],
            data["vwap"],
            data["rsi"],
            data["bb_upper"],
            data["bb_lower"],
            data["macd_hist"],
            data["macd_signal"],
            data["sma50"],
            data["volume"],
            data["news_score"],
            data["decision"],
            data["entry"],
            data["take_profit"],
            data["stop_loss"],
            data["risk_ratio"],
            data["logic"]
        ]
        
        print("Appending row to worksheet:")
        print(row)
        
        worksheet.append_row(row)
        print("Data saved successfully!")
        return True
    except Exception as e:
        print(f"Error saving to Google Sheets: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

# ... (fungsi lainnya tetap sama, pastikan semua ada) ...

def main():
    print(f"\n{'='*50}")
    print(f"Starting trading analysis at {datetime.utcnow().isoformat()}")
    
    try:
        tech_data = get_okx_data()
        news_score = analyze_news_sentiment()
        
        decision, entry, tp, sl, rr, logic = trading_decision(tech_data, news_score)
        
        data = {
            "timestamp": datetime.utcnow().isoformat(),
            "price": tech_data['current_price'] if tech_data else None,
            "vwap": tech_data['vwap'] if tech_data else None,
            "rsi": tech_data['rsi'] if tech_data else None,
            "bb_upper": tech_data['bb_upper'] if tech_data else None,
            "bb_lower": tech_data['bb_lower'] if tech_data else None,
            "macd_hist": tech_data['macd_hist'] if tech_data else None,
            "macd_signal": tech_data['macd_signal'] if tech_data else None,
            "sma50": tech_data['sma50'] if tech_data else None,
            "volume": tech_data['volume'] if tech_data else None,
            "news_score": news_score,
            "decision": decision,
            "entry": round(entry, 2) if entry else None,
            "take_profit": round(tp, 2) if tp else None,
            "stop_loss": round(sl, 2) if sl else None,
            "risk_ratio": rr,
            "logic": logic
        }
        
        print("\nData to be saved:")
        print(json.dumps(data, indent=2))
        
        if save_to_google_sheets(data):
            print("Data saved to Google Sheets successfully!")
        else:
            print("Failed to save data to Google Sheets")
            
    except Exception as e:
        print(f"Critical error in main: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()