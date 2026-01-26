import os
import random
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType
from dotenv import load_dotenv
from pydantic import EmailStr

# .env file load karo
load_dotenv()

# ✅ Zoho Configuration
conf = ConnectionConfig(
    MAIL_USERNAME=os.getenv("SMTP_USER"),
    MAIL_PASSWORD=os.getenv("SMTP_PASS"),
    MAIL_FROM=os.getenv("SMTP_FROM"),
    MAIL_PORT=465,
    MAIL_SERVER="smtp.zoho.in",    # Agar .in na chale toh .com try karna
    MAIL_STARTTLS=False,
    MAIL_SSL_TLS=True,
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=True
)

# ✅ Function 1: OTP Generate Karna (Jo tera main.py maang raha hai)
def generate_otp():
    return str(random.randint(100000, 999999))

# ✅ Function 2: Email Bhejna (Async)
async def send_otp_email(email_to: EmailStr, otp: str):
    
    # 🌑 DARK THEME HTML TEMPLATE (Professional Look)
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #121212; margin: 0; padding: 0; }}
            .container {{ max-width: 600px; margin: 0 auto; background-color: #1E1E1E; padding: 40px; border-radius: 12px; margin-top: 30px; border: 1px solid #333333; }}
            .header {{ text-align: center; border-bottom: 1px solid #333333; padding-bottom: 20px; margin-bottom: 30px; }}
            .logo-text {{ color: #ffffff; font-size: 24px; font-weight: bold; margin: 0; text-transform: uppercase; letter-spacing: 2px; }}
            .sub-text {{ color: #b0b0b0; font-size: 14px; margin-top: 5px; }}
            
            .content {{ text-align: center; }}
            .greeting {{ color: #ffffff; font-size: 18px; }}
            .message {{ color: #b0b0b0; line-height: 1.6; font-size: 15px; }}
            
            .otp-box {{ background-color: #252525; border: 1px dashed #00E676; border-radius: 8px; padding: 20px; margin: 25px 0; display: inline-block; min-width: 200px; }}
            .otp-code {{ font-size: 36px; font-weight: bold; color: #00E676; letter-spacing: 8px; margin: 0; font-family: monospace; }}
            
            .footer {{ text-align: center; color: #555555; font-size: 12px; margin-top: 40px; border-top: 1px solid #333333; padding-top: 20px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <p class="logo-text">SB PGM</p>
                <p class="sub-text">Security Verification</p>
            </div>
            
            <div class="content">
                <p class="greeting">Hello,</p>
                <p class="message">You requested a login verification code.</p>
                
                <div class="otp-box">
                    <p class="otp-code">{otp}</p>
                </div>
                
                <p class="message" style="font-size: 13px;">⚠️ Valid for 10 minutes only.<br>Do not share this code.</p>
            </div>
            
            <div class="footer">
                <p>&copy; 2026 SB PGM App. All rights reserved.</p>
                <p>Automated message.</p>
            </div>
        </div>
    </body>
    </html>
    """

    message = MessageSchema(
        subject="🔐 SB PGM Verification Code",
        recipients=[email_to],
        body=html_content,
        subtype=MessageType.html
    )

    fm = FastMail(conf)
    
    try:
        await fm.send_message(message)
        print(f"✅ OTP Sent to {email_to}")
        return True
    except Exception as e:
        print(f"❌ Error sending email: {e}")
        return False
