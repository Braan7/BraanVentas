import os

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "change-me")
    # Render sets DATABASE_URL; fix deprecated scheme if needed
    _db_url = os.getenv("DATABASE_URL", "sqlite:///braan_dev.db")
    if _db_url.startswith("postgres://"):
        _db_url = _db_url.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_DATABASE_URI = _db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # External services
    SMM_API_URL = os.getenv("SMM_API_URL", "https://smmprodigyx.xyz/api/v2")
    SMM_API_KEY = os.getenv("SMM_API_KEY", "")
    DOCS_API_URL = os.getenv("DOCS_API_URL", "https://comidamaster.net/public")
    DOCS_API_KEY = os.getenv("DOCS_API_KEY", "")
    WHATSAPP_NUMBER = os.getenv("WHATSAPP_NUMBER", "+525648804810")

class Production(Config):
    pass

class Development(Config):
    DEBUG = True
