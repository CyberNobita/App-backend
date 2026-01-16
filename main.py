from fastapi import FastAPI, Depends, HTTPException, File, UploadFile, Form
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import or_
import asyncio
import os
import shutil
import cloudinary
import cloudinary.uploader
from dotenv import load_dotenv

load_dotenv()

# Cloudinary Config (From Env)
cloudinary.config( 
  cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME"), 
  api_key = os.getenv("CLOUDINARY_API_KEY"), 
  api_secret = os.getenv("CLOUDINARY_API_SECRET"),
  secure = True
)

# Imports
from database import engine, get_db, Base
from models import UserDB, ConverterDB, AppConfig
from schemas import UserCreate, Token, NewConverter, CalcReq, ConfigUpdate
from auth import get_password_hash, verify_password, create_access_token, get_current_admin
from market_data import update_market_data, CACHE

# Init DB
Base.metadata.create_all(bind=engine)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

is_production = os.getenv("RENDER") 

app = FastAPI(
    # Agar Production (Render) pe hain toh Docs mat dikhao, warna dikhao
    docs_url=None if is_production else "/docs",
    redoc_url=None if is_production else "/redoc",
    openapi_url=None if is_production else "/openapi.json"
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

UPLOAD_DIR = "static/images"
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")



# --- 🧠 HELPER: GET CONFIG ---
def get_app_config(db: Session):
    return db.query(AppConfig).first()

# --- 🧠 CENTRAL CALCULATION LOGIC ---
# Updated to support specific Interest Rates per metal
def calculate_payout_logic(weight, pt, pd, rh, currency, db: Session, margin_override=None, days_override=None, factor_override=None, custom_usd=0.0):
    
    # 1. DB se Config Uthao
    conf = get_app_config(db)
    
    # 2. Values Set Karo (Override ya Default)
    c_margin = margin_override if margin_override is not None else conf.default_margin
    c_days = days_override if days_override is not None else conf.default_days_out
    
    # 3. Market Factor (Default from Config unless overridden)
    # Search ke liye Converter Factor use hoga, Calculator ke liye User ya Calc Factor
    c_factor = factor_override if factor_override is not None else conf.factor_converter

    # 4. Prices Fetch & Factor Apply
    spot_prices = CACHE.get('pgm_prices', {"pt":0,"pd":0,"rh":0})
    raw_data = CACHE.get('data', {}).get('raw', {})
    usd_rate = custom_usd if custom_usd > 0.1 else raw_data.get("usd_rate", 86.5)

    price_pt = spot_prices.get("pt", 0.0) * c_factor
    price_pd = spot_prices.get("pd", 0.0) * c_factor
    price_rh = spot_prices.get("rh", 0.0) * c_factor

    # 5. Math (Grams -> Ounces -> Base Value)
    grams_pt = (pt / 1000) * weight; oz_pt = grams_pt / 31.1035
    grams_pd = (pd / 1000) * weight; oz_pd = grams_pd / 31.1035
    grams_rh = (rh / 1000) * weight; oz_rh = grams_rh / 31.1035

    val_pt = oz_pt * price_pt
    val_pd = oz_pd * price_pd
    val_rh = oz_rh * price_rh
    
    # 6. Apply Margin Individual (Payout before interest)
    payout_pt = val_pt * (c_margin / 100)
    payout_pd = val_pd * (c_margin / 100)
    payout_rh = val_rh * (c_margin / 100)

    # 7. 🔥 APPLY SPECIFIC INTEREST RATES 🔥
    # Har metal ka apna rate database se aayega
    int_pt = 0.0; int_pd = 0.0; int_rh = 0.0

    if c_days > 0:
        int_pt = payout_pt * (conf.interest_pt / 100) * (c_days / 365)
        int_pd = payout_pd * (conf.interest_pd / 100) * (c_days / 365)
        int_rh = payout_rh * (conf.interest_rh / 100) * (c_days / 365)
    
    total_interest = int_pt + int_pd + int_rh
    total_payout_usd = (payout_pt + payout_pd + payout_rh) - total_interest

    # 8. Currency Conversion
    final_payout = total_payout_usd
    if currency == "INR": final_payout *= usd_rate; total_interest *= usd_rate

    return {
        "final_price": round(final_payout, 2),
        "interest": round(total_interest, 2),
        "rates": {"pt": price_pt, "pd": price_pd, "rh": price_rh},
        "usd_rate": usd_rate,
        "params": {"margin": c_margin, "days": c_days, "factor": c_factor}
    }

# --- ⚙️ ADMIN CONFIG ENDPOINTS ---
@app.get("/admin/config")
def get_config_api(db: Session = Depends(get_db)):
    return db.query(AppConfig).first()

@app.post("/admin/config")
def update_config_api(c: ConfigUpdate, db: Session = Depends(get_db), user: str = Depends(get_current_admin)):
    conf = db.query(AppConfig).first()
    conf.default_margin = c.default_margin
    conf.default_days_out = c.default_days_out
    conf.interest_pt = c.interest_pt
    conf.interest_pd = c.interest_pd
    conf.interest_rh = c.interest_rh
    conf.factor_calculator = c.factor_calculator
    conf.factor_converter = c.factor_converter
    conf.factor_market = c.factor_market
    db.commit()
    return {"success": True}

# --- 🔍 SEARCH API (Uses Converter Factor) ---
@app.get("/converters/search")
def search(q: str = "", currency: str = "USD", db: Session = Depends(get_db)):
    query = db.query(ConverterDB)
    if q: query = query.filter(or_(ConverterDB.serial.ilike(f"%{q}%"), ConverterDB.brand.ilike(f"%{q}%")))
    
    # 1. Fetch Config for Defaults
    conf = get_app_config(db)
    
    res = []
    for item in query.all():
        # 2. Calculate using Config defaults (Margin 82%, Days 120, etc.)
        calc = calculate_payout_logic(
            item.weight_kg, item.pt_ppm, item.pd_ppm, item.rh_ppm, currency, db,
            margin_override=conf.default_margin,
            days_override=conf.default_days_out,
            factor_override=conf.factor_converter
        )
        
        res.append({
            "serial": item.serial, "brand": item.brand, "image": item.image,"weight": item.weight_kg,
            "calculated_price": calc['final_price'],
            "ppm": {"pt": item.pt_ppm, "pd": item.pd_ppm, "rh": item.rh_ppm} 
        })
    return res

# --- 🧮 CALCULATOR API ---
class CalculatorRequest(BaseModel):
    weight: float; pt_ppm: float; pd_ppm: float; rh_ppm: float; currency: str = "USD"
    # Overrides allowed, but if null, DB defaults used
    margin_percent: float = None; days_out: int = None
    use_custom_price: bool = False; custom_pt: float=0; custom_pd: float=0; custom_rh: float=0; custom_usd: float=0

@app.post("/calculate")
def calculate_manual(req: CalculatorRequest, db: Session = Depends(get_db)):
    if req.use_custom_price:
        conf = get_app_config(db)
        
        # 1. Setup Parameters
        c_margin = req.margin_percent if req.margin_percent is not None else conf.default_margin
        c_days = req.days_out if req.days_out is not None else conf.default_days_out
        
        raw_data = CACHE.get('data', {}).get('raw', {})
        usd_rate = req.custom_usd if req.custom_usd > 0.1 else raw_data.get("usd_rate", 86.5)

        # 2. Math: Grams -> Ounces -> Value -> Margin
        # Pt
        grams_pt = (req.pt_ppm / 1000) * req.weight
        val_pt = (grams_pt / 31.1035) * req.custom_pt
        payout_pt = val_pt * (c_margin / 100)
        
        # Pd
        grams_pd = (req.pd_ppm / 1000) * req.weight
        val_pd = (grams_pd / 31.1035) * req.custom_pd
        payout_pd = val_pd * (c_margin / 100)
        
        # Rh
        grams_rh = (req.rh_ppm / 1000) * req.weight
        val_rh = (grams_rh / 31.1035) * req.custom_rh
        payout_rh = val_rh * (c_margin / 100)

        # 3. Interest Deduction (Specific Rates)
        int_pt = 0.0; int_pd = 0.0; int_rh = 0.0
        if c_days > 0:
            int_pt = payout_pt * (conf.interest_pt / 100) * (c_days / 365)
            int_pd = payout_pd * (conf.interest_pd / 100) * (c_days / 365)
            int_rh = payout_rh * (conf.interest_rh / 100) * (c_days / 365)
            
        total_interest = int_pt + int_pd + int_rh
        final_payout_usd = (payout_pt + payout_pd + payout_rh) - total_interest

        # 4. Currency Conversion
        if req.currency == "INR":
            final_payout_usd *= usd_rate
            total_interest *= usd_rate

        return {
            "final_price": round(final_payout_usd, 2),
            "interest_amount": round(total_interest, 2),
            "rates_used": {
                "usd": usd_rate, 
                "pt": req.custom_pt, 
                "pd": req.custom_pd, 
                "rh": req.custom_rh
            },
            "is_custom": True
        }
    
    else:
        # Fetch Config to check Calculator Factor
        conf = get_app_config(db)
        
        calc = calculate_payout_logic(
            req.weight, req.pt_ppm, req.pd_ppm, req.rh_ppm, req.currency, db,
            req.margin_percent, req.days_out, factor_override=conf.factor_calculator
        )
        return {
            "final_price": calc['final_price'],
            "interest_amount": calc['interest'],
            "rates_used": {**calc['rates'], "usd": calc['usd_rate']}, 
            "is_custom": False
        }

# --- 📈 LIVE RATES API (Applies Market Factor) ---
@app.get("/live_rates")
def get_rates(db: Session = Depends(get_db)):
    conf = get_app_config(db)
    factor = conf.factor_market # e.g. 0.98 or 1.0
    
    # Deep copy to avoid messing up cache
    original_data = CACHE["data"]
    response_data = {
        "metals": [], "energy": original_data.get("energy", []), 
        "forex": original_data.get("forex", []), "raw": original_data.get("raw", {}),
        "ai_insight": original_data.get("ai_insight", {})
    }
    
    # Apply Factor to Metals Only
    for m in original_data.get("metals", []):
        new_m = m.copy()
        # Apply factor ONLY to PGM scraped data, not everything if you want
        if m['name'] in ["Platinum", "Palladium", "Rhodium"]:
            new_m['price'] = m['price'] * factor
        response_data['metals'].append(new_m)
        
    return response_data

from scheduler import start_scheduler
from firebase_admin import messaging

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(update_market_data())
    start_scheduler() # Start the alert scheduler
    # 🔥 Initialize Defaults if not present
    db = SessionLocal()
    if not db.query(AppConfig).first():
        db.add(AppConfig(id=1))
        db.commit()
    db.close()

class TokenReq(BaseModel):
    token: str

@app.post("/update-token")
def update_token(req: TokenReq):
    try:
        # Subscribe to topic 'all_users'
        response = messaging.subscribe_to_topic([req.token], "all_users")
        print(f"Subscribed token: {response.success_count} success")
        return {"success": True}
    except Exception as e:
        print(f"Token Sub Error: {e}")
        return {"success": False, "error": str(e)}

# --- AUTH & ADMIN (Standard) ---
@app.post("/auth/register")
def register(user: UserCreate, db: Session = Depends(get_db)):
    if db.query(UserDB).filter(UserDB.email == user.email).first(): raise HTTPException(400, "Taken")
    role = "admin" if db.query(UserDB).count() == 0 else "user"
    db.add(UserDB(full_name=user.full_name, email=user.email, hashed_password=get_password_hash(user.password), role=role)); db.commit()
    return {"msg": "Registered", "role": role}

@app.post("/auth/login")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(UserDB).filter(UserDB.email == form.username).first()
    if not user or not verify_password(form.password, user.hashed_password): raise HTTPException(401, "Invalid")
    return {"access_token": create_access_token({"sub": user.email}), "token_type": "bearer", "role": user.role, "name": user.full_name}

@app.post("/admin/add_converter")
def add_conv(serial: str = Form(...), brand: str = Form(...), weight_kg: float = Form(...), pt_ppm: float = Form(...), pd_ppm: float = Form(...), rh_ppm: float = Form(...), image: UploadFile = File(...), db: Session = Depends(get_db), u: str = Depends(get_current_admin)):
    # Cloudinary Upload
    try:
        res = cloudinary.uploader.upload(image.file, folder="converters")
        image_url = res.get("secure_url")
    except Exception as e:
        raise HTTPException(500, f"Image Upload Failed: {e}")

    db.add(ConverterDB(serial=serial, brand=brand, image=image_url, weight_kg=weight_kg, pt_ppm=pt_ppm, pd_ppm=pd_ppm, rh_ppm=rh_ppm))
    try: db.commit()
    except: raise HTTPException(400, "Exists")
    return {"success": True}

@app.delete("/admin/delete_converter/{serial}")
def delete_conv(serial: str, db: Session = Depends(get_db), u: str = Depends(get_current_admin)):
    db.query(ConverterDB).filter(ConverterDB.serial == serial).delete()
    db.commit()
    return {"success": True}

@app.post("/admin/create_admin")
def create_adm(user: UserCreate, db: Session = Depends(get_db), u: str = Depends(get_current_admin)):
    if db.query(UserDB).filter(UserDB.email == user.email).first(): raise HTTPException(400, "Taken")
    db.add(UserDB(full_name=user.full_name, email=user.email, hashed_password=get_password_hash(user.password), role="admin")); db.commit()
    return {"success": True}



