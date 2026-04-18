import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()


class BaseConfig:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-jwt-secret")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(
        hours=int(os.getenv("JWT_EXPIRY_HOURS", 24))
    )

    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    STORAGE_PATH = os.getenv("STORAGE_PATH", "./storage")
    ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "admin-secret")

    FACE_MODEL = os.getenv("FACE_MODEL", "ArcFace")
    FACE_DETECTOR = os.getenv("FACE_DETECTOR", "retinaface")
    FACE_SIMILARITY_THRESHOLD = float(
        os.getenv("FACE_SIMILARITY_THRESHOLD", 0.40)
    )


class DevelopmentConfig(BaseConfig):
    DEBUG = True


class ProductionConfig(BaseConfig):
    DEBUG = False


config_by_name = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
}
