from apscheduler.schedulers.asyncio import AsyncIOScheduler
import firebase_admin
from firebase_admin import credentials, messaging
import time
import asyncio
import os   # <--- Added
import json # <--- Added
from market_data import CACHE, OPENING_PRICES # (Maine dot hata diya relative import ka)

# Global State for Scheduler
LAST_KNOWN_PRICES = {"rh": 0, "pd": 0, "pt": 0}
LAST_ALERT_TIME = {"rh": 0, "pd": 0, "pt": 0}
ALERT_COOLDOWN = 4 * 3600  # 4 Hours

def init_firebase():
    # Check agar app pehle se initialized hai toh wapis mat karo
    if firebase_admin._apps:
        return

    try:
        # 1. Pehle Environment Variable Check karo (Render ke liye)
        firebase_env = os.getenv("FIREBASE_CREDENTIALS")
        
        if firebase_env:
            # Render Logic
            cred_dict = json.loads(firebase_env)
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
            print("✅ Scheduler: Firebase Initialized from Env Var")
        
        # 2. Agar Env nahi mila, toh Local File dhoondo (Laptop ke liye)
        elif os.path.exists("firebase_credentials.json"):
            cred = credentials.Certificate("firebase_credentials.json")
            firebase_admin.initialize_app(cred)
            print("✅ Scheduler: Firebase Initialized from Local File")
            
        else:
            print("⚠️ Scheduler Warning: Firebase Credentials NOT FOUND")

    except Exception as e:
        print(f"⚠️ Firebase Init Error: {e}")

async def check_prices_job():
    print("⏰ [Scheduler] Checking Prices for Alerts...")
    
    # We rely on market_data.py to update CACHE
    current_prices = CACHE.get('pgm_prices', {})
    
    for metal, price in current_prices.items():
        if price <= 0: continue
        
        last_price = LAST_KNOWN_PRICES.get(metal, 0)
        
        # Init Last Known If Empty
        if last_price == 0:
            LAST_KNOWN_PRICES[metal] = price
            continue

        # Calculate Change
        change_pct = ((price - last_price) / last_price) * 100
        
        # Check Alert Condition (> 2% Change)
        if abs(change_pct) >= 2.0:
            # Check Cooldown
            if time.time() - LAST_ALERT_TIME.get(metal, 0) > ALERT_COOLDOWN:
                # Send Alert
                direction = "🚀" if change_pct > 0 else "🔻"
                title = f"SB PGM Alert: {metal.upper()} {direction}"
                body = f"{metal.upper()} is {direction} by {change_pct:.1f}%! Current: ${price}"
                
                await send_fcm_alert(title, body)
                
                # Update State
                LAST_ALERT_TIME[metal] = time.time()
                LAST_KNOWN_PRICES[metal] = price
                print(f"🚀 Alert Sent: {title}")

async def send_fcm_alert(title, body):
    try:
        msg = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            topic="all_users"
        )
        messaging.send(msg)
    except Exception as e:
        print(f"Failed to send FCM: {e}")

# scheduler instance
scheduler = AsyncIOScheduler()

def start_scheduler():
    init_firebase()
    scheduler.add_job(check_prices_job, "interval", minutes=10)
    scheduler.start()
    print("✅ Scheduler Started (10 min cycle)")
