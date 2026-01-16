from apscheduler.schedulers.asyncio import AsyncIOScheduler
import firebase_admin
from firebase_admin import credentials, messaging
import time
import asyncio
from market_data import CACHE, OPENING_PRICES

# Global State for Scheduler
LAST_KNOWN_PRICES = {"rh": 0, "pd": 0, "pt": 0}
LAST_ALERT_TIME = {"rh": 0, "pd": 0, "pt": 0}
ALERT_COOLDOWN = 4 * 3600  # 4 Hours

def init_firebase():
    try:
        if not firebase_admin._apps:
            cred = credentials.Certificate("firebase_credentials.json")
            firebase_admin.initialize_app(cred)
            print("✅ Firebase Initialized")
    except Exception as e:
        print(f"⚠️ Firebase Init Error (Check 'firebase_credentials.json'): {e}")

async def check_prices_job():
    print("⏰ [Scheduler] Checking Prices for Alerts...")
    
    # We rely on market_data.py to update CACHE, or we could scrape here.
    # Using CACHE is safer to avoid double-scraping bans.
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
        
        # Always update last known? No, logic says "Compare current with last known". 
        # If we update continuously, slow creep won't trigger. 
        # But if we don't update, a persistent 2% shift will trigger every 4 hours. 
        # User Logic: "If Price Change > 2% ... Check last_alert_time ... If > 4 hours ... send"
        # Implies we trigger ONCE for the shift.
        # I'll update LAST_KNOWN only when Alert is sent OR maybe reset daily?
        # Let's update LAST_KNOWN only on Alert to capture "Change since last alert". 
        # Wait, if price drops 1%, then another 1%, total 2%. We should capture that.
        # So we KEEP old price until 2% barrier crossed.

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

