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

# Konfigurasi dari environment variables
SPREADSHEET_ID = os.getenv('SPREADSHEET_ID')

def auth_google_sheets():
    """Autentikasi menggunakan service account"""
    creds_json = os.getenv('GOOGLE_CREDENTIALS')
    creds_dict = json.loads(creds_json)
    scopes = ['https://www.googleapis.com/auth/spreadsheets']
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)

def save_to_google_sheets(data):
    """Simpan data ke Google Sheets"""
    try:
        client = auth_google_sheets()
        sheet = client.open_by_key(SPREADSHEET_ID)
        today = datetime.utcnow().strftime("%Y-%m-%d")
        
        try:
            worksheet = sheet.worksheet(today)
        except:
            worksheet = sheet.add_worksheet(title=today, rows=1000, cols=20)
            header = [
                "Timestamp", "Price", "VWAP", "RSI", "BB Upper", "BB Lower",
                "MACD Hist", "MACD Signal", "SMA50", "Volume", "News Score",
                "Decision", "Entry", "Take Profit", "Stop Loss", "Risk Ratio", "Logic"
            ]
            worksheet.append_row(header)
        
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
        
        worksheet.append_row(row)
        return True
    except Exception as e:
        print(f"Error saving to Google Sheets: {str(e)}")
        return False

def get_okx_data():
    """Ambil data dari OKX API"""
    try:
        url = "https://www.okx.com/api/v5/market/candles"
        params = {'instId': 'XAUT-USDT-SWAP', 'bar': '5m', 'limit': '100'}
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        
        if data['code'] != '0':
            return None
        
        # Proses data
        df = pd.DataFrame(data['data'], columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume', 
            'vol_ccy', 'vol_ccy_quote', 'confirm'
        ])
        
        # Konversi tipe data
        num_cols = ['open', 'high', 'low', 'close', 'vol_ccy_quote']
        df[num_cols] = df[num_cols].apply(pd.to_numeric)
        df['timestamp'] = pd.to_datetime(df['timestamp'].astype(int), unit='ms')
        df = df.sort_values('timestamp')
        
        # Hitung indikator
        current_price = df['close'].iloc[-1]
        volume = df['vol_ccy_quote'].iloc[-1]
        
        # VWAP
        df['typical'] = (df['high'] + df['low'] + df['close']) / 3
        df['cum_vol'] = df['vol_ccy_quote'].cumsum()
        df['cum_tp_vol'] = (df['typical'] * df['vol_ccy_quote']).cumsum()
        vwap = df['cum_tp_vol'].iloc[-1] / df['cum_vol'].iloc[-1]
        
        # RSI
        rsi = RSIIndicator(df['close'], window=7).rsi().iloc[-1]
        
        # Bollinger Bands
        bb = BollingerBands(df['close'], window=20, window_dev=2)
        bb_upper = bb.bollinger_hband().iloc[-1]
        bb_lower = bb.bollinger_lband().iloc[-1]
        
        # MACD
        macd = MACD(df['close'], window_slow=13, window_fast=5, window_sign=1)
        macd_hist = macd.macd_diff().iloc[-1]
        macd_signal = macd.macd_signal().iloc[-1]
        
        # SMA50
        sma50 = SMAIndicator(df['close'], window=50).sma_indicator().iloc[-1]
        
        return {
            'current_price': current_price,
            'vwap': vwap,
            'rsi': rsi,
            'bb_upper': bb_upper,
            'bb_lower': bb_lower,
            'macd_hist': macd_hist,
            'macd_signal': macd_signal,
            'sma50': sma50,
            'volume': volume
        }
    except Exception as e:
        print(f"Error getting OKX data: {str(e)}")
        return None

def analyze_news_sentiment():
    """Analisis sentimen berita"""
    try:
        query = "gold OR economic OR inflation OR fed"
        url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}"
        feed = feedparser.parse(url)
        
        total_score = 0
        high_impact_kws = ['fed', 'inflation', 'rate', 'interest', 'war', 'gold', 'dollar']
        
        for entry in feed.entries[:10]:
            if not hasattr(entry, 'published_parsed'):
                continue
                
            # Filter berita 24 jam
            pub_time = datetime(*entry.published_parsed[:6])
            if (datetime.utcnow() - pub_time) > timedelta(hours=24):
                continue
                
            # Analisis sentimen
            text = entry.title
            polarity = TextBlob(text).sentiment.polarity
            
            if polarity > 0.1: score = 1
            elif polarity < -0.1: score = -1
            else: score = 0
            
            # Cek high impact
            if any(kw in text.lower() for kw in high_impact_kws):
                score *= 2
                
            total_score += score
            
        return total_score
    except Exception as e:
        print(f"News error: {str(e)}")
        return 0

def trading_decision(tech, news_score):
    """Buat keputusan trading"""
    if not tech:
        return "ERROR", None, None, None, "", "No technical data"
    
    cp = tech['current_price']
    logic = []
    
    # Kondisi BUY
    buy_cond = [
        cp <= tech['bb_lower'] and tech['rsi'] < 35,
        tech['macd_hist'] > tech['macd_signal'],
        tech['volume'] > 20000,
        cp > tech['vwap']
    ]
    
    # Kondisi SELL
    sell_cond = [
        cp >= tech['bb_upper'] and tech['rsi'] > 65,
        tech['macd_hist'] < tech['macd_signal'],
        tech['volume'] > 20000,
        cp < tech['vwap']
    ]
    
    if sum(buy_cond) >= 3:
        decision = "BUY"
        entry = cp * 0.9995
        sl = max(tech['bb_lower'], cp * 0.998)
        tp = cp * 1.005 if news_score > 2 else cp * 1.003
        rr = "1:2.5" if news_score > 2 else "1:1.5"
        logic.append("Technical buy signal")
        
    elif sum(sell_cond) >= 3:
        decision = "SELL"
        entry = cp * 1.0005
        sl = min(tech['bb_upper'], cp * 1.002)
        tp = cp * 0.995 if news_score < -2 else cp * 0.997
        rr = "1:2.5" if news_score < -2 else "1:1.5"
        logic.append("Technical sell signal")
        
    else:
        decision = "HOLD"
        entry, sl, tp, rr = None, None, None, ""
        logic.append("No strong signal")
        
        # Override dengan sentimen kuat
        if news_score >= 3:
            decision = "BUY"
            entry, sl, tp = cp, cp * 0.998, cp * 1.004
            rr = "1:2"
            logic.append("Strong bullish news")
        elif news_score <= -3:
            decision = "SELL"
            entry, sl, tp = cp, cp * 1.002, cp * 0.996
            rr = "1:2"
            logic.append("Strong bearish news")
    
    # Tambahkan logika tambahan
    if decision != "HOLD":
        if cp > tech['sma50']:
            logic.append("Bullish trend")
        else:
            logic.append("Bearish trend")
    
    return decision, entry, tp, sl, rr, " | ".join(logic)

def main():
    print("Starting trading analysis...")
    
    # Ambil data
    tech_data = get_okx_data()
    news_score = analyze_news_sentiment()
    
    # Buat keputusan
    decision, entry, tp, sl, rr, logic = trading_decision(tech_data, news_score)
    
    # Siapkan data untuk spreadsheet
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
    
    # Simpan ke Google Sheets
    if save_to_google_sheets(data):
        print("Data saved successfully!")
    else:
        print("Failed to save data")

if __name__ == "__main__":
    main()