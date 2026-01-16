from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime
from .database import Base
from datetime import datetime

class UserDB(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(String, default="user") # 'admin' or 'user'

class ConverterDB(Base):
    __tablename__ = "converters"
    id = Column(Integer, primary_key=True, index=True)
    serial = Column(String, unique=True, index=True)
    brand = Column(String, index=True)
    description = Column(String)
    image = Column(String)
    weight_kg = Column(Float)
    pt_ppm = Column(Float)
    pd_ppm = Column(Float)
    rh_ppm = Column(Float)
    
# 🔥 NEW: Global Settings Table
class AppConfig(Base):
    __tablename__ = "app_config"
    id = Column(Integer, primary_key=True, index=True)
    
    # Defaults
    default_margin = Column(Float, default=82.0)
    default_days_out = Column(Integer, default=120)
    
    # Specific Interest Rates (Annual %)
    interest_pt = Column(Float, default=18.25)
    interest_pd = Column(Float, default=9.125)
    interest_rh = Column(Float, default=9.14)
    
    # Market Factors (1.0 = 100%, 0.98 = 98%)
    factor_calculator = Column(Float, default=1.0) 
    factor_converter = Column(Float, default=1.0)
    factor_market = Column(Float, default=1.0)
