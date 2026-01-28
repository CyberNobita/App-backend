import os
import random
import resend
from dotenv import load_dotenv

# .env file load karo
load_dotenv()

# ✅ Resend API Configuration
# .env se key uthayega
resend.api_key = os.getenv("RESEND_API_KEY")

# ✅ Function 1: OTP Generate Karna (Tera same function)
def generate_otp():
    return str(random.randint(100000, 999999))

# ✅ Function 2: Email Bhejna (Latest Resend API Method)
async def send_otp_email(email_to: str, otp: str):
    
    # 🌑 DARK THEME HTML TEMPLATE (Tera Wala Same Professional Look)
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

    try:
        # Resend API call (Bahut Fast hai)
        params = {
            "from": "SB PGM <noreply@sbpgm.com>",  # Agar domain verify nahi hai toh ye use kar
            # "from": "Support <support@sbpgm.com>",   # Jab domain verify ho jaye tab ye khol dena
            "to": [email_to],
            "subject": "🔐 SB PGM Verification Code",
            "html": html_content,
        }

        email = resend.Emails.send(params)
        print(f"✅ OTP Sent via Resend to {email_to}")
        return True

    except Exception as e:
        print(f"❌ Error sending email via Resend: {e}")
        return False
