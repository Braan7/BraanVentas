import os
from dotenv import load_dotenv
from datetime import timedelta
load_dotenv()
class Config:
    SECRET_KEY = os.getenv("SECRET_KEY","change-me")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL","sqlite:///app.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    REMEMBER_COOKIE_DURATION = timedelta(days=30)
    ADMIN_WHATSAPP = os.getenv("ADMIN_WHATSAPP","+525648804810")
    SMM_API_URL = os.getenv("SMM_API_URL","")
    SMM_API_KEY = os.getenv("SMM_API_KEY","")
    DOCS_API_URL = os.getenv("DOCS_API_URL","")
    DOCS_API_KEY = os.getenv("DOCS_API_KEY","")
    MAINTENANCE = os.getenv("MAINTENANCE","false").lower() == "true"
