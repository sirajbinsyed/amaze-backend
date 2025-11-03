import os
from datetime import timedelta

class Settings:
    DATABASE_URL: str = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/erp")
    JWT_SECRET: str = os.environ.get("JWT_SECRET", "change-me-in-prod")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

    @property
    def access_token_expires(self) -> timedelta:
        return timedelta(minutes=self.ACCESS_TOKEN_EXPIRE_MINUTES)

settings = Settings()
