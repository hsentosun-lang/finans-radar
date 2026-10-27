import yfinance as yf
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
import os

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///finans_verileri.db")
engine = create_engine(DATABASE_URL)

INDICES = {
    "BIST 30": ["AKBNK.IS", "ARCLK.IS", "ASELS.IS", "BIMAS.IS", "THYAO.IS", "TUPRS.IS"], 
    "S&P 500 Teknoloji": ["AAPL", "MSFT", "NVDA", "GOOGL", "META"],
    "Kripto": ["BTC-USD", "ETH-USD"]
}

def create_table():
    with engine.connect() as conn:
        conn.execute(text('''
            CREATE TABLE IF NOT EXISTS market_data (
                date DATE, index_name VARCHAR(50), ticker VARCHAR(50),
                close FLOAT, high FLOAT, low FLOAT, volume FLOAT,
                sma_50 FLOAT, sma_100 FLOAT, sma_200 FLOAT,
                vol_sma_20 FLOAT, vol_sigma_2 FLOAT, vol_sigma_3 FLOAT,
                daily_return FLOAT, weekly_return FLOAT,
                z_score_daily FLOAT, z_score_weekly FLOAT,
                percentile_rank FLOAT, atr_ratio FLOAT, ekstrem_skor INTEGER,
                UNIQUE(date, ticker)
            )
        '''))
        conn.commit()

def calculate_indicators(df):
    df['sma_50'] = df['Close'].rolling(window=50).mean()
    df['sma_100'] = df['Close'].rolling(window=100).mean()
    df['sma_200'] = df['Close'].rolling(window=200).mean()
    
    df['vol_sma_20'] = df['Volume'].rolling(window=20).mean()
    vol_std = df['Volume'].rolling(window=20).std()
    df['vol_sigma_2'] = df['vol_sma_20'] + (vol_std * 2)
    df['vol_sigma_3'] = df['vol_sma_20'] + (vol_std * 3)

    df['daily_return'] = df['Close'].pct_change()
    df['weekly_return'] = df['Close'].pct_change(periods=5)
    
    df['z_score_daily'] = (df['daily_return'] - df['daily_return'].rolling(252).mean()) / df['daily_return'].rolling(252).std()
    df['z_score_weekly'] = (df['weekly_return'] - df['weekly_return'].rolling(252).mean()) / df['weekly_return'].rolling(252).std()
    df['percentile_rank'] = df['daily_return'].rolling(252).rank(pct=True) * 100

    high_low = df['High'] - df['Low']
    high_close = (df['High'] - df['Close'].shift()).abs()
    low_close = (df['Low'] - df['Close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    
    df['atr_ratio'] = tr.rolling(5).mean() / tr.rolling(20).mean()

    df['ekstrem_skor'] = 0
    df.loc[df['z_score_daily'].abs() > 2.5, 'ekstrem_skor'] += 30
    df.loc[df['z_score_weekly'].abs() > 2.0, 'ekstrem_skor'] += 30
    df.loc[(df['percentile_rank'] < 2) | (df['percentile_rank'] > 98), 'ekstrem_skor'] += 20
    df.loc[df['atr_ratio'] > 1.5, 'ekstrem_skor'] += 20

    return df

def update_data():
    create_table()
    for index_name, tickers in INDICES.items():
        for ticker in tickers:
            with engine.connect() as conn:
                result = conn.execute(text(f"SELECT COUNT(*) FROM market_data WHERE ticker = '{ticker}'")).scalar()
            
            if result == 0:
                data = yf.download(ticker, period="3y", progress=False)
                if data.empty: continue
                new_data = calculate_indicators(data).dropna(subset=['percentile_rank', 'sma_200'])
            else:
                query = f"SELECT date, close, high, low, volume FROM market_data WHERE ticker = '{ticker}' ORDER BY date DESC LIMIT 300"
                db_data = pd.read_sql_query(query, engine)
                db_data.rename(columns={'close':'Close', 'high':'High', 'low':'Low', 'volume':'Volume'}, inplace=True)
                db_data['date'] = pd.to_datetime(db_data['date'])
                db_data = db_data.sort_values('date').set_index('date')
                
                recent_yf = yf.download(ticker, period="5d", progress=False)[['Close', 'High', 'Low', 'Volume']]
                combined = pd.concat([db_data, recent_yf])
                combined = combined[~combined.index.duplicated(keep='last')].sort_index()
                
                combined = calculate_indicators(combined)
                new_data = combined[combined.index > db_data.index.max()]
                if new_data.empty: continue

            df_insert = new_data[['Close', 'High', 'Low', 'Volume', 'sma_50', 'sma_100', 'sma_200', 
                                  'vol_sma_20', 'vol_sigma_2', 'vol_sigma_3', 'daily_return', 'weekly_return', 
                                  'z_score_daily', 'z_score_weekly', 'percentile_rank', 'atr_ratio', 'ekstrem_skor']].copy()
            df_insert.reset_index(inplace=True)
            df_insert.rename(columns={'Date': 'date', 'Datetime': 'date', 'Close': 'close', 'High': 'high', 'Low': 'low', 'Volume': 'volume'}, inplace=True)
            df_insert['ticker'] = ticker
            df_insert['index_name'] = index_name
            df_insert['date'] = pd.to_datetime(df_insert['date']).dt.date
            
            with engine.connect() as conn:
                for _, row in df_insert.iterrows():
                    row = row.replace({np.nan: None}) 
                    cols = ", ".join(row.keys())
                    params = ", ".join([f":{k}" for k in row.keys()])
                    updates = ", ".join([f"{k}=EXCLUDED.{k}" for k in row.keys() if k not in ['date', 'ticker']])
                    sql = text(f"INSERT INTO market_data ({cols}) VALUES ({params}) ON CONFLICT (date, ticker) DO UPDATE SET {updates}")
                    try: conn.execute(sql, row.to_dict())
                    except: pass
                conn.commit()

if __name__ == "__main__":
    update_data()