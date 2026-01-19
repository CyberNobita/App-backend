from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType
from pydantic import EmailStr
import random
import os
from dotenv import load_dotenv

load_dotenv()

# Render ke Environment Variables se uthayenge
MAIL_USERNAME = os.getenv("MAIL_USERNAME", "tera_email@gmail.com")
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "wo_16_digit_wala_code") 

conf = ConnectionConfig(
    MAIL_USERNAME=MAIL_USERNAME,
    MAIL_PASSWORD=MAIL_PASSWORD,
    MAIL_FROM=MAIL_USERNAME,
    MAIL_PORT=465,
    MAIL_SERVER="smtp.gmail.com",
    MAIL_STARTTLS=False,
    MAIL_SSL_TLS=True,
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=True
)

# 1️⃣ OTP Generate karne ka function
def generate_otp():
    return str(random.randint(100000, 999999))

# 2️⃣ Email Bhejne ka function
async def send_otp_email(email: EmailStr, otp: str):
    html = f"""
    <h3>SB PGM Verification</h3>
    <p>Your OTP is: <strong>{otp}</strong></p>
    <p>This will expire in 5 minutes.</p>
    """

    message = MessageSchema(
        subject="SB PGM - Verify Your Email",
        recipients=[email],
        body=html,
        subtype=MessageType.html
    )

    fm = FastMail(conf)
    await fm.send_message(message)
