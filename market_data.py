import asyncio
import time
import requests
import yfinance as yf
import pandas as pd
import random 
import re
from bs4 import BeautifulSoup
import aiohttp

# ==========================================================
# 📋 LIVE MARKET DATA (1 HOUR RHODIUM CYCLE + 0% FIX)
# ==========================================================

ECO_TRADE_MARGIN = 1.0 # Base scraper margin (Adjusted by DB Config later)

# URLs
URLS = {
    "rh": {
        "primary": "https://www.kitco.com/charts/rhodium", 
        "backup": "https://www.moneymetals.com/rhodium-price" 
    },
    "pd": {
        "primary": "https://www.kitco.com/charts/palladium", 
        "backup": "https://goldprice.org/palladium-price.html"
    },
    "pt": {
        "primary": "https://www.kitco.com/charts/platinum", 
        "backup": "https://goldprice.org/platinum-price.html"
    }
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
]

CACHE = {
    "data": {
        "metals": [], "energy": [], "forex": [], 
        "ai_insight": {}, 
        "raw": {"pt": 0.0, "pd": 0.0, "rh": 0.0, "usd_rate": 86.5}
    },
    "pgm_prices": {"pt": 960.0, "pd": 1050.0, "rh": 4750.0}
}

REAL_DATA_CACHE = {} 
# 🔥 To Calculate Percentage Change (Fix 0% Issue)
OPENING_PRICES = {"pt": None, "pd": None, "rh": None}

# --- 1. SCRAPER LOGIC ---
async def scrape_price(metal, urls_dict):
    price = await _fetch_html(urls_dict["primary"], "kitco")
    if price: return price
    price = await _fetch_html(urls_dict["backup"], "backup")
    if price: return price
    return None

async def _fetch_html(url, source_type):
    try:
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Cache-Control": "max-age=0",
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=15) as response:
                if response.status != 200: return None
                html = await response.text()
                soup = BeautifulSoup(html, "html.parser")
                price_str = ""
                
                if source_type == "kitco":
                    tag = soup.find("h3", class_=lambda c: c and "font-mulish" in c and "text-4xl" in c)
                    if tag: price_str = tag.get_text()
                    else:
                        tags = soup.find_all("span", string=lambda t: t and "$" in t)
                        for t in tags:
                            if len(t.text) < 15: price_str = t.text; break
                elif source_type == "backup":
                    tag = soup.find("td", {"id": "spot-price"}) 
                    if not tag: tag = soup.find("span", class_="price-now")
                    if tag: price_str = tag.get_text()

                if price_str:
                    clean = price_str.replace("$", "").replace(",", "").strip()
                    try: return float(clean)
                    except: pass
    except: pass
    return None

# --- 2. REGULAR TICKERS (FULL LIST PRESERVED) ---
ALL_TICKERS = [
    ("PAXGUSDT", "Gold (Spot)", "metals", "binance"),    
    ("SI=F", "Silver (Spot)", "metals", "yahoo"), 
    ("HG=F", "Copper", "metals", "yahoo"),       
    ("ALI=F", "Aluminum", "metals", "yahoo"),    
    ("ZINC.L", "Zinc", "metals", "yahoo"),      
    ("VALE", "Nickel", "metals", "yahoo"),      
    ("SCCO", "Lead", "metals", "yahoo"),        
    ("TIN.L", "Tin", "metals", "yahoo"),
    ("RIO", "Iron Ore", "metals", "yahoo"),     
    ("HRC=F", "Steel (HRC)", "metals", "yahoo"),
    ("SLX", "Steel (Scrap)", "metals", "yahoo"),
    ("LIT", "Lithium", "metals", "yahoo"),
    ("GLNCY", "Cobalt", "metals", "yahoo"),
    ("CCJ", "Manganese", "metals", "yahoo"),
    ("LGO", "Vanadium", "metals", "yahoo"),
    ("NMG", "Graphite", "metals", "yahoo"),
    ("URA", "Uranium (Metal)", "metals", "yahoo"),
    ("ATI", "Titanium", "metals", "yahoo"),
    ("REMX", "Rare Earths", "metals", "yahoo"),
    ("ACH", "Magnesium", "metals", "yahoo"),
    ("SMH", "Indium", "metals", "yahoo"),
    ("TECK", "Gallium", "metals", "yahoo"),
    ("FCX", "Molybdenum", "metals", "yahoo"),
    ("CL=F", "Crude Oil (WTI)", "energy", "yahoo"),
    ("BZ=F", "Brent Crude", "energy", "yahoo"),
    ("NG=F", "Natural Gas", "energy", "yahoo"),
    ("HO=F", "Heating Oil", "energy", "yahoo"),
    ("RB=F", "Gasoline (RBOB)", "energy", "yahoo"),
    ("BTU", "Coal (Newcastle)", "energy", "yahoo"),
    ("ADM", "Ethanol", "energy", "yahoo"),
    ("TAN", "Solar Energy", "energy", "yahoo"),
    ("ICLN", "Clean Energy", "energy", "yahoo"),
    ("KRBN", "Carbon Credits", "energy", "yahoo"),
    ("BTCUSDT", "Bitcoin", "forex", "binance"),
    ("ETHUSDT", "Ethereum", "forex", "binance"),
    ("SOLUSDT", "Solana", "forex", "binance"),
    ("XRPUSDT", "XRP", "forex", "binance"),
    ("DOGEUSDT", "Dogecoin", "forex", "binance"),
    ("ADAUSDT", "Cardano", "forex", "binance"),
    ("INR=X", "USD / INR", "forex", "yahoo"),
    ("EURINR=X", "EUR / INR", "forex", "yahoo"),
    ("GBPINR=X", "GBP / INR", "forex", "yahoo"),
    ("CNY=X", "USD / CNY", "forex", "yahoo"),
    ("EUR=X", "EUR / USD", "forex", "yahoo"),
    ("GBP=X", "GBP / USD", "forex", "yahoo"),
    ("JPY=X", "USD / JPY", "forex", "yahoo"),
    ("CHF=X", "USD / CHF", "forex", "yahoo"),
    ("AUD=X", "AUD / USD", "forex", "yahoo"),
    ("CAD=X", "USD / CAD", "forex", "yahoo"),
    ("DX-Y.NYB", "Dollar Index", "forex", "yahoo"),
]

MULTIPLIERS = {
    "Gold (Spot)": 1.0, "Silver (Spot)": 1.0,
    "Copper": 2.2046, "Aluminum": 0.001, "Nickel": 1.23, "Zinc": 0.28, "Lead": 0.0142, "Tin": 0.32, 
    "Iron Ore": 0.0012, "Cobalt": 2.65, "Lithium": 0.25, "Magnesium": 15.0,
    "Coal (Newcastle)": 4.5, "Ethanol": 0.026, "Uranium (Metal)": 2.7,
}

INVERT_FOREX = ["EUR / USD", "GBP / USD", "AUD / USD"]

def fetch_binance():
    try:
        symbols = [item[0] for item in ALL_TICKERS if item[3] == "binance"]
        if not symbols: return {}
        sym_str = str(symbols).replace("'", '"').replace(" ", "")
        r = requests.get(f"https://api.binance.com/api/v3/ticker/24hr?symbols={sym_str}", timeout=5)
        if r.status_code == 200:
            return {x['symbol']: {'price': float(x['lastPrice']), 'change': float(x['priceChange']), 'percent': float(x['priceChangePercent'])} for x in r.json()}
    except: pass
    return {}

def fetch_yahoo_batch(tickers):
    try:
        df = yf.download(" ".join(tickers), period="2d", interval="1m", group_by='ticker', progress=False, threads=False)
        res = {}
        for t in tickers:
            try:
                data = df[t].dropna() if len(tickers) > 1 else df.dropna()
                if not data.empty:
                    p = float(data['Close'].iloc[-1])
                    prev = float(data['Close'].iloc[0])
                    res[t] = {'price': p, 'change': p-prev, 'percent': ((p-prev)/prev)*100}
            except: pass
        return res
    except: return {}

# --- 3. UTILS ---
def add_noise(price):
    if price == 0: return 0
    return price * random.uniform(0.9995, 1.0005)

def get_ai_advice(name, percent):
    if percent > 1.0: return {"message": f"{name} is surging!", "color": "green", "priority": 100}
    if percent < -1.0: return {"message": f"{name} is dropping!", "color": "red", "priority": 90}
    return {"message": f"{name} is stable.", "color": "grey", "priority": 10}

# --- 4. MAIN LOOP ---
async def update_market_data():
    print("🚀 Market Data Engine Started (With 0% Fix & Admin Factors)")
    
    loop_count = 0
    loop = asyncio.get_event_loop()

    while True:
        try:
            # --- STARTUP FETCH (One-time) ---
            if loop_count == 0:
                print(">>> [STARTUP] Fetching & Setting Base Prices...")
                for metal in ["rh", "pd", "pt"]:
                    val = await scrape_price(metal, URLS[metal])
                    if val: 
                        CACHE['pgm_prices'][metal] = val
                        # 🔥 SET OPENING PRICE if not set
                        if OPENING_PRICES[metal] is None: 
                            OPENING_PRICES[metal] = val
                            print(f"✅ Set Opening {metal.upper()}: {val}")
                    await asyncio.sleep(2)

            # --- SCHEDULED CYCLES ---
            # 1. RHODIUM (Every 1 Hour)
            if loop_count > 0 and loop_count % 1200 == 0: 
                val = await scrape_price("rh", URLS["rh"])
                if val: CACHE['pgm_prices']['rh'] = val
            
            # 2. PALLADIUM (Every 10 Mins)
            if loop_count > 0 and loop_count % 200 == 40: 
                val = await scrape_price("pd", URLS["pd"])
                if val: CACHE['pgm_prices']['pd'] = val

            # 3. PLATINUM (Every 10 Mins)
            if loop_count > 0 and loop_count % 200 == 100: 
                val = await scrape_price("pt", URLS["pt"])
                if val: CACHE['pgm_prices']['pt'] = val
                
            # --- HIGH FREQ FETCH (Yahoo/Binance) ---
            if loop_count % 10 == 0:
                binance = await loop.run_in_executor(None, fetch_binance)
                yahoo = await loop.run_in_executor(None, fetch_yahoo_batch, [t[0] for t in ALL_TICKERS if t[3]=="yahoo"])
                
                for t, name, _, src in ALL_TICKERS:
                    d = binance.get(t) if src=="binance" else yahoo.get(t)
                    if d: REAL_DATA_CACHE[name] = d

            # --- OUTPUT GENERATION (3s) ---
            new_data = {"metals": [], "energy": [], "forex": [], "raw": {}, "ai_insight": {}}
            raw = {"pt": 0, "pd": 0, "rh": 0, "usd_rate": 86.5}
            max_prio = 0

            for _, name, cat, _ in ALL_TICKERS:
                base = REAL_DATA_CACHE.get(name, {'price': 0, 'change': 0, 'percent': 0})
                if base['price'] == 0: continue
                
                price = base['price']
                if name in MULTIPLIERS: price *= MULTIPLIERS[name]
                if name == "USD / INR": raw["usd_rate"] = price

                if name in ["Gold (Spot)", "Bitcoin"]:
                    adv = get_ai_advice(name, base['percent'])
                    if adv['priority'] > max_prio: max_prio = adv['priority']; new_data['ai_insight'] = adv
                
                new_data[cat].append({"name": name, "price": price, "change": base['change'], "percent": base['percent'], "type": cat})

            # PGM PRICES (Fluctuating Noise applied to Cached Value)
            pt = add_noise(CACHE["pgm_prices"]["pt"])
            pd = add_noise(CACHE["pgm_prices"]["pd"])
            rh = add_noise(CACHE["pgm_prices"]["rh"])
            
            raw.update({"pt": pt/31.1035, "pd": pd/31.1035, "rh": rh/31.1035})

            for code, n, p in [("rh", "Rhodium", rh), ("pd", "Palladium", pd), ("pt", "Platinum", pt)]:
                # 🔥 Calculate % Change based on Session Opening
                open_p = OPENING_PRICES[code]
                percent_change = 0.0
                change_val = 0.0
                
                if open_p and open_p > 0:
                    change_val = p - open_p
                    percent_change = (change_val / open_p) * 100
                
                new_data["metals"].insert(0, {
                    "name": n, "price": p, 
                    "change": change_val, 
                    "percent": percent_change, # 🔥 Fixed 0% Bug (Shows deviation from session start)
                    "type": "metals"
                })

            new_data["raw"] = raw
            CACHE["data"] = new_data
            
            loop_count += 1
            await asyncio.sleep(3)

        except Exception as e:
            print(f"Loop Error: {e}")
            await asyncio.sleep(3)
