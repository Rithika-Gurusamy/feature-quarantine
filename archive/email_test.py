import random
import smtplib
from email.mime.text import MIMEText
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, EmailStr

app = FastAPI()

otp_store = {}

SMTP_SERVER = "://gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = "your-email@gmail.com"
SENDER_PASSWORD = "your-email-app-password"

class EmailRequest(BaseModel):
    email: EmailStr

class VerifyRequest(BaseModel):
    email: EmailStr
    otp: str

def send_email(to_email: str, otp: str):
    msg = MIMEText(f"Your one-time password is: {otp}")
    msg["Subject"] = "Your OTP Code"
    msg["From"] = SENDER_EMAIL
    msg["To"] = to_email

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, to_email, msg.as_string())

@app.post("/send-otp")
def request_otp(data: EmailRequest):
    otp = str(random.randint(100000, 999999))
    otp_store[data.email] = otp
    try:
        send_email(data.email, otp)
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to send email")
    return {"message": "OTP sent successfully"}

@app.post("/verify-otp")
def verify_otp(data: VerifyRequest):
    stored_otp = otp_store.get(data.email)
    if not stored_otp or stored_otp != data.otp:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")
    
    del otp_store[data.email]
    return {"message": "OTP verified successfully"}


#twilio
import os
import random
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from twilio.rest import Client

app = FastAPI()

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "your_account_sid")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "your_auth_token")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "your_twilio_phone_number")

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
otp_store = {}

class SMSRequest(BaseModel):
    phone_number: str

class VerifyRequest(BaseModel):
    phone_number: str
    otp: str

@app.post("/send-otp")
def send_otp(data: SMSRequest):
    code = f"{random.randint(100000, 999999)}"
    otp_store[data.phone_number] = code
    
    try:
        twilio_client.messages.create(
            body=f"Your OTP is: {code}",
            from_=TWILIO_PHONE_NUMBER,
            to=data.phone_number
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send SMS: {str(e)}")
        
    return {"message": "OTP sent successfully"}

@app.post("/verify-otp")
def verify_otp(data: VerifyRequest):
    stored_code = otp_store.get(data.phone_number)
    if not stored_code or stored_code != data.otp:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")
    del otp_store[data.phone_number]
    return {"message": "OTP verified successfully"}



