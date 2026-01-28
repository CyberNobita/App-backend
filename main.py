from fastapi import FastAPI, Depends, HTTPException, File, UploadFile, Form
from pydantic import BaseModel, EmailStr
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
from datetime import datetime
import secrets

# Cloudinary Config (From Env)
load_dotenv()
cloudinary.config( 
  cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME"), 
  api_key = os.getenv("CLOUDINARY_API_KEY"), 
  api_secret = os.getenv("CLOUDINARY_API_SECRET"),
  secure = True
)

# Imports (Fixed: Added get_current_user)
from database import engine, get_db, Base
from models import UserDB, ConverterDB, AppConfig
from schemas import UserCreate, Token, NewConverter, CalcReq, ConfigUpdate
from auth import get_password_hash, verify_password, create_access_token, get_current_admin, get_current_user
from market_data import update_market_data, CACHE
from email_service import send_otp_email, generate_otp 

# Init DB
Base.metadata.create_all(bind=engine)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

UPLOAD_DIR = "static/images"
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")


# --- 🧠 HELPER & CALCULATOR LOGIC (SAME AS BEFORE) ---
def get_app_config(db: Session):
    return db.query(AppConfig).first()

def calculate_payout_logic(weight, pt, pd, rh, currency, db: Session, margin_override=None, days_override=None, factor_override=None, custom_usd=0.0):
    conf = get_app_config(db)
    c_margin = margin_override if margin_override is not None else conf.default_margin
    c_days = days_override if days_override is not None else conf.default_days_out
    c_factor = factor_override if factor_override is not None else conf.factor_converter

    spot_prices = CACHE.get('pgm_prices', {"pt":0,"pd":0,"rh":0})
    raw_data = CACHE.get('data', {}).get('raw', {})
    usd_rate = custom_usd if custom_usd > 0.1 else raw_data.get("usd_rate", 86.5)

    price_pt = spot_prices.get("pt", 0.0) * c_factor
    price_pd = spot_prices.get("pd", 0.0) * c_factor
    price_rh = spot_prices.get("rh", 0.0) * c_factor

    grams_pt = (pt / 1000) * weight; oz_pt = grams_pt / 31.1035
    grams_pd = (pd / 1000) * weight; oz_pd = grams_pd / 31.1035
    grams_rh = (rh / 1000) * weight; oz_rh = grams_rh / 31.1035

    val_pt = oz_pt * price_pt
    val_pd = oz_pd * price_pd
    val_rh = oz_rh * price_rh
    
    payout_pt = val_pt * (c_margin / 100)
    payout_pd = val_pd * (c_margin / 100)
    payout_rh = val_rh * (c_margin / 100)

    int_pt = 0.0; int_pd = 0.0; int_rh = 0.0
    if c_days > 0:
        int_pt = payout_pt * (conf.interest_pt / 100) * (c_days / 365)
        int_pd = payout_pd * (conf.interest_pd / 100) * (c_days / 365)
        int_rh = payout_rh * (conf.interest_rh / 100) * (c_days / 365)
    
    total_interest = int_pt + int_pd + int_rh
    total_payout_usd = (payout_pt + payout_pd + payout_rh) - total_interest

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

# --- 🔍 SEARCH API ---
@app.get("/converters/search")
def search(q: str = "", currency: str = "USD", db: Session = Depends(get_db)):
    query = db.query(ConverterDB)
    if q: query = query.filter(or_(ConverterDB.serial.ilike(f"%{q}%"), ConverterDB.brand.ilike(f"%{q}%")))
    
    conf = get_app_config(db)
    res = []
    for item in query.all():
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
    margin_percent: float = None; days_out: int = None
    use_custom_price: bool = False; custom_pt: float=0; custom_pd: float=0; custom_rh: float=0; custom_usd: float=0

@app.post("/calculate")
def calculate_manual(req: CalculatorRequest, db: Session = Depends(get_db)):
    if req.use_custom_price:
        conf = get_app_config(db)
        c_margin = req.margin_percent if req.margin_percent is not None else conf.default_margin
        c_days = req.days_out if req.days_out is not None else conf.default_days_out
        
        raw_data = CACHE.get('data', {}).get('raw', {})
        usd_rate = req.custom_usd if req.custom_usd > 0.1 else raw_data.get("usd_rate", 86.5)

        grams_pt = (req.pt_ppm / 1000) * req.weight
        val_pt = (grams_pt / 31.1035) * req.custom_pt
        payout_pt = val_pt * (c_margin / 100)
        
        grams_pd = (req.pd_ppm / 1000) * req.weight
        val_pd = (grams_pd / 31.1035) * req.custom_pd
        payout_pd = val_pd * (c_margin / 100)
        
        grams_rh = (req.rh_ppm / 1000) * req.weight
        val_rh = (grams_rh / 31.1035) * req.custom_rh
        payout_rh = val_rh * (c_margin / 100)

        int_pt = 0.0; int_pd = 0.0; int_rh = 0.0
        if c_days > 0:
            int_pt = payout_pt * (conf.interest_pt / 100) * (c_days / 365)
            int_pd = payout_pd * (conf.interest_pd / 100) * (c_days / 365)
            int_rh = payout_rh * (conf.interest_rh / 100) * (c_days / 365)
            
        total_interest = int_pt + int_pd + int_rh
        final_payout_usd = (payout_pt + payout_pd + payout_rh) - total_interest

        if req.currency == "INR":
            final_payout_usd *= usd_rate
            total_interest *= usd_rate

        return {
            "final_price": round(final_payout_usd, 2),
            "interest_amount": round(total_interest, 2),
            "rates_used": {"usd": usd_rate, "pt": req.custom_pt, "pd": req.custom_pd, "rh": req.custom_rh},
            "is_custom": True
        }
    else:
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

# --- 📈 LIVE RATES API ---
@app.get("/live_rates")
def get_rates(db: Session = Depends(get_db)):
    conf = get_app_config(db)
    factor = conf.factor_market
    original_data = CACHE["data"]
    response_data = {
        "metals": [], "energy": original_data.get("energy", []), 
        "forex": original_data.get("forex", []), "raw": original_data.get("raw", {}),
        "ai_insight": original_data.get("ai_insight", {})
    }
    for m in original_data.get("metals", []):
        new_m = m.copy()
        if m['name'] in ["Platinum", "Palladium", "Rhodium"]:
            new_m['price'] = m['price'] * factor
        response_data['metals'].append(new_m)
    return response_data

from scheduler import start_scheduler
from firebase_admin import messaging

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(update_market_data())
    start_scheduler()
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
        response = messaging.subscribe_to_topic([req.token], "all_users")
        print(f"Subscribed token: {response.success_count} success")
        return {"success": True}
    except Exception as e:
        print(f"Token Sub Error: {e}")
        return {"success": False, "error": str(e)}


# ==========================================
# 🔥 AUTHENTICATION & OTP SYSTEM 🔥
# ==========================================

# --- SCHEMAS ---
class VerifyOTPRequest(BaseModel):
    email: EmailStr
    otp: str

class ResetPasswordRequest(BaseModel):
    email: EmailStr
    otp: str
    new_password: str

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

class CompleteSignupRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str

# 👉 1. SEND OTP API (New Signup + Resend Logic)
@app.post("/auth/send-otp")
async def send_otp(email: str, full_name: str = "User", db: Session = Depends(get_db)):
    email = email.lower()
    current_time = datetime.utcnow()
    
    user = db.query(UserDB).filter(UserDB.email == email).first()

    if user:
        # Check if Registration Complete
        if user.hashed_password:
             raise HTTPException(status_code=400, detail="Email already registered. Please Login.")
        
        # Resend Logic for Ghost Users
        if user.otp_created_at:
            time_diff = (current_time - user.otp_created_at).total_seconds() / 60
            if user.otp_attempts == 1 and time_diff < 1:
                wait_sec = int(60 - (time_diff * 60))
                raise HTTPException(status_code=429, detail=f"Please wait {wait_sec} seconds before resending.")
            elif 2 <= user.otp_attempts < 5 and time_diff < 5:
                raise HTTPException(status_code=429, detail="Please wait 5 minutes before resending.")
            elif user.otp_attempts >= 5:
                if time_diff < 30:
                    raise HTTPException(status_code=429, detail="Too many attempts. Try again after 30 minutes.")
                else:
                    user.otp_attempts = 0

        otp = generate_otp()
        user.otp = otp
        user.otp_created_at = current_time
        user.otp_attempts += 1
        db.commit()
        
        await send_otp_email(email, otp)
        return {"message": "OTP sent/resent successfully"}

    else:
        # New User (Check for First User Admin Rule)
        user_count = db.query(UserDB).count()
        role = "admin" if user_count == 0 else "user"

        otp = generate_otp()
        new_user = UserDB(
            email=email,
            full_name=full_name,
            otp=otp,
            otp_created_at=current_time,
            otp_attempts=1,
            is_verified=False,
            role=role # Set role here
        )
        db.add(new_user)
        db.commit()
        
        await send_otp_email(email, otp)
        return {"message": "OTP sent successfully"}

@app.post("/auth/forgot-password-otp")
async def forgot_password_otp(email: str, db: Session = Depends(get_db)):
    email = email.lower()
    current_time = datetime.utcnow()
    
    # 1. Check User
    user = db.query(UserDB).filter(UserDB.email == email).first()

    # Agar User nahi hai -> Error
    if not user:
        raise HTTPException(status_code=404, detail="User not found with this email.")

    # Agar User hai par Signup poora nahi kiya (Ghost User) -> Error
    if not user.hashed_password:
        raise HTTPException(status_code=400, detail="Account incomplete. Please Sign Up first.")

    # 2. Resend Time Logic (Wahi same logic)
    if user.otp_created_at:
        time_diff = (current_time - user.otp_created_at).total_seconds() / 60
        
        if user.otp_attempts == 1 and time_diff < 1:
            wait_sec = int(60 - (time_diff * 60))
            raise HTTPException(status_code=429, detail=f"Please wait {wait_sec} seconds before resending.")
        elif 2 <= user.otp_attempts < 5 and time_diff < 5:
            raise HTTPException(status_code=429, detail="Please wait 5 minutes before resending.")
        elif user.otp_attempts >= 5:
            if time_diff < 30:
                raise HTTPException(status_code=429, detail="Too many attempts. Try again after 30 minutes.")
            else:
                user.otp_attempts = 0

    # 3. Send OTP
    otp = generate_otp()
    user.otp = otp
    user.otp_created_at = current_time
    user.otp_attempts += 1
    db.commit()
    
    await send_otp_email(email, otp)
    return {"message": "OTP sent to your email."}


# 👉 2. VERIFY OTP API
@app.post("/auth/verify-otp")
async def verify_otp(req: VerifyOTPRequest, db: Session = Depends(get_db)):
    email = req.email.lower()
    otp_input = req.otp.strip()
    current_time = datetime.utcnow()

    user = db.query(UserDB).filter(UserDB.email == email).first()
    
    if not user:
        raise HTTPException(status_code=400, detail="User not found or OTP expired.")

    if user.otp != otp_input:
        raise HTTPException(status_code=400, detail="Invalid OTP")

    if user.otp_created_at:
        time_diff = (current_time - user.otp_created_at).total_seconds() / 60
        if time_diff > 10:
             raise HTTPException(status_code=400, detail="OTP Expired. Please request a new one.")

    user.is_verified = True
    user.otp = None         
    user.otp_attempts = 0   
    db.commit()             

    return {"message": "Email Verified Successfully. Please set your password."}


# 👉 3. COMPLETE SIGNUP (Set Password for New User)
@app.post("/auth/complete-signup")
async def complete_signup(req: CompleteSignupRequest, db: Session = Depends(get_db)):
    email = req.email.lower()
    
    user = db.query(UserDB).filter(UserDB.email == email).first()
    
    if not user:
        raise HTTPException(status_code=400, detail="User not found")
    
    if not user.is_verified:
        raise HTTPException(status_code=400, detail="Email not verified. Verify OTP first.")

    user.hashed_password = get_password_hash(req.password)
    user.full_name = req.full_name 
    db.commit()

    access_token = create_access_token({"sub": user.email})
    return {
        "message": "Account Created Successfully",
        "access_token": access_token,
        "token_type": "bearer",
        "role": user.role,
        "name": user.full_name
    }


# 👉 4. RESET PASSWORD (Forgot Password Flow)
@app.post("/auth/reset-password")
async def reset_password(req: ResetPasswordRequest, db: Session = Depends(get_db)):
    email = req.email.lower()
    otp_input = req.otp.strip()
    current_time = datetime.utcnow()

    user = db.query(UserDB).filter(UserDB.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.otp != otp_input:
        raise HTTPException(status_code=400, detail="Invalid OTP")

    if user.otp_created_at:
        time_diff = (current_time - user.otp_created_at).total_seconds() / 60
        if time_diff > 10:
            raise HTTPException(status_code=400, detail="OTP Expired. Please request a new one.")

    user.hashed_password = get_password_hash(req.new_password)
    user.otp = None
    user.otp_attempts = 0
    user.is_verified = True
    db.commit()

    return {"message": "Password reset successfully. You can now login."}


# 👉 5. CHANGE PASSWORD (Logged In Settings)
@app.post("/auth/change-password")
async def change_password(
    req: ChangePasswordRequest, 
    db: Session = Depends(get_db), 
    current_user: UserDB = Depends(get_current_user) # 👈 Now imported correctly
):
    if not verify_password(req.old_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect old password")

    if req.old_password == req.new_password:
        raise HTTPException(status_code=400, detail="New password cannot be the same as old password")

    current_user.hashed_password = get_password_hash(req.new_password)
    db.commit()

    return {"message": "Password changed successfully"}


# 👉 6. LOGIN (With Check for Incomplete Signup)
@app.post("/auth/login")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(UserDB).filter(UserDB.email == form.username).first()
    
    # User not found
    if not user:
        raise HTTPException(401, "Invalid credentials")

    # Ghost User check (Password not set yet)
    if not user.hashed_password:
        raise HTTPException(401, "Registration incomplete. Please Sign Up again.")

    # Wrong Password
    if not verify_password(form.password, user.hashed_password):
        raise HTTPException(401, "Invalid credentials")

    return {"access_token": create_access_token({"sub": user.email}), "token_type": "bearer", "role": user.role, "name": user.full_name}


# --- GOOGLE AUTH ---
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

class GoogleAuthReq(BaseModel):
    token: str

@app.post("/auth/google")
def google_auth(req: GoogleAuthReq, db: Session = Depends(get_db)):
    try:
        GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
        id_info = id_token.verify_oauth2_token(req.token, google_requests.Request(), GOOGLE_CLIENT_ID)
        
        email = id_info.get("email")
        name = id_info.get("name")
        
        if not email: raise HTTPException(400, "Invalid Google Token")
        
        user = db.query(UserDB).filter(UserDB.email == email).first()
        
        if not user:
            # Auto Register
            password = secrets.token_hex(16)
            user = UserDB(
                full_name=name, 
                email=email, 
                hashed_password=get_password_hash(password),
                role="user",
                is_verified=True
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            
        access_token = create_access_token({"sub": user.email})
        return {
            "access_token": access_token, 
            "token_type": "bearer", 
            "role": user.role, 
            "name": user.full_name
        }
        
    except ValueError as e:
        raise HTTPException(400, f"Token Verification Failed: {str(e)}")
    except Exception as e:
        raise HTTPException(500, f"Login Failed: {str(e)}")

# --- ADMIN ROUTES ---
@app.post("/admin/add_converter")
def add_conv(serial: str = Form(...), brand: str = Form(...), weight_kg: float = Form(...), pt_ppm: float = Form(...), pd_ppm: float = Form(...), rh_ppm: float = Form(...), image: UploadFile = File(...), db: Session = Depends(get_db), u: str = Depends(get_current_admin)):
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

class UpdateProfileRequest(BaseModel):
    full_name: str

@app.put("/auth/update-profile")
async def update_profile(
    req: UpdateProfileRequest, 
    db: Session = Depends(get_db), 
    current_user: UserDB = Depends(get_current_user)
):
    # Sirf Name update karega, Email nahi chhedega
    current_user.full_name = req.full_name
    db.commit()
    
    return {
        "message": "Profile updated successfully", 
        "name": current_user.full_name
    }

