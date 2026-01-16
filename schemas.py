from pydantic import BaseModel

class Token(BaseModel):
    access_token: str
    token_type: str
    role: str
    name: str

class UserCreate(BaseModel):
    full_name: str
    email: str
    password: str

class NewConverter(BaseModel):
    serial: str; brand: str; description: str; image: str
    weight_kg: float; pt_ppm: float; pd_ppm: float; rh_ppm: float

class CalcReq(BaseModel):
    serial: str; margin: float; currency: str="INR"

# 🔥 NEW: Config Schema
class ConfigUpdate(BaseModel):
    default_margin: float
    default_days_out: int
    interest_pt: float
    interest_pd: float
    interest_rh: float
    factor_calculator: float
    factor_converter: float
    factor_market: float
