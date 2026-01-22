import os
import requests
import random
from pydantic import EmailStr

# Environment Variables
# Ab humein sirf API KEY chahiye. 
# Render Env mein 'BREVO_API_KEY' naam se wo lambi key save kar dena.
BREVO_API_KEY = os.getenv("BREVO_API_KEY") 
SENDER_EMAIL = os.getenv("MAIL_USERNAME") # Tera login email
SENDER_NAME = "SB PGM App"

def generate_otp():
    return str(random.randint(100000, 999999))

async def send_otp_email(email: EmailStr, otp: str):
    url = "https://api.brevo.com/v3/smtp/email"

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
        "subject": "SB PGM - Verify OTP",
        "htmlContent": f"""
            <html>
                <body>
                    <h3>SB PGM Verification</h3>
                    <p>Your OTP code is: <strong style="font-size: 20px;">{otp}</strong></p>
                    <p>This code is valid for 10 minutes.</p>
                </body>
            </html>
        """
    }

    headers = {
        "accept": "application/json",
        "api-key": BREVO_API_KEY,  # Yahan SMTP Password nahi, API Key aayegi
        "content-type": "application/json"
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        
        # Check success
        if response.status_code == 201:
            print("Email sent successfully via API!")
            return True
        else:
            print(f"Failed to send email. Error: {response.text}")
            return False
            
    except Exception as e:
        print(f"API Connection Error: {e}")
        return False
