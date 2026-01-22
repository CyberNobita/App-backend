import os
import requests
import random
from pydantic import EmailStr

# Render Env se API Key uthao
API_KEY = os.getenv("BREVO_API_KEY") 
SENDER_EMAIL = os.getenv("MAIL_USERNAME") # Tera login email
SENDER_NAME = "SB PGM App"

# OTP Generate karne ka logic
def generate_otp():
    return str(random.randint(100000, 999999))

async def send_otp_email(email: EmailStr, otp: str):
    # Brevo ka Transactional Email URL (Ye SMTP nahi, API hai)
    url = "https://api.brevo.com/v3/smtp/email"

    # Data jo bhejna hai
    payload = {
        "sender": {
            "name": SENDER_NAME,
            "email": SENDER_EMAIL
        },
        "to": [
            {
                "email": email,
                "name": "User"
            }
        ],
        "subject": "Verification Code - SB PGM",
        "htmlContent": f"""
            <html>
                <body>
                    <div style="font-family: Arial, sans-serif; padding: 20px; border: 1px solid #ddd;">
                        <h2 style="color: #00E676;">SB PGM Verification</h2>
                        <p>Your OTP code is:</p>
                        <h1 style="letter-spacing: 5px; color: #333;">{otp}</h1>
                        <p>This code is valid for 10 minutes.</p>
                        <hr>
                        <p style="font-size: 12px; color: #888;">If you didn't request this, please ignore.</p>
                    </div>
                </body>
            </html>
        """
    }

    headers = {
        "accept": "application/json",
        "api-key": API_KEY,  # Yahan API Key jayegi
        "content-type": "application/json"
    }

    try:
        # Request bhejo
        response = requests.post(url, json=payload, headers=headers)
        
        if response.status_code == 201:
            print(f"OTP Sent to {email}")
            return True
        else:
            print(f"Error sending email: {response.text}")
            return False
            
    except Exception as e:
        print(f"Connection Error: {e}")
        return False
