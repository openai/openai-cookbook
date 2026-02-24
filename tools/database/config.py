"""
Database configuration management.
Loads settings from environment variables.
"""

import os
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote_plus

from dotenv import load_dotenv

# Load environment variables (tools/.env when run from repo)
load_dotenv()
_env_tools = os.path.join(os.path.dirname(__file__), "..", ".env")
if os.path.exists(_env_tools):
    load_dotenv(_env_tools)


@dataclass
class DatabaseConfig:
    """Database configuration from environment variables."""
    
    host: str
    port: int
    database: str
    user: str
    password: str
    charset: str = "utf8mb4"
    ssl_mode: str = "REQUIRED"
    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: int = 30
    
    @classmethod
    def from_env(cls) -> "DatabaseConfig":
        """Create config from environment variables."""
        return cls(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "3306")),
            database=os.getenv("DB_NAME", ""),
            user=os.getenv("DB_USER", ""),
            password=os.getenv("DB_PASSWORD", ""),
            charset=os.getenv("DB_CHARSET", "utf8mb4"),
            ssl_mode=os.getenv("DB_SSL_MODE", "REQUIRED"),
            pool_size=int(os.getenv("DB_POOL_SIZE", "5")),
            max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "10")),
            pool_timeout=int(os.getenv("DB_POOL_TIMEOUT", "30"))
        )
    
    @property
    def connection_url(self) -> str:
        """Generate SQLAlchemy connection URL. Password is URL-encoded for special chars (@, $, &)."""
        db_part = f"/{self.database}" if self.database else ""
        safe_password = quote_plus(self.password)
        return (
            f"mysql+pymysql://{self.user}:{safe_password}"
            f"@{self.host}:{self.port}{db_part}"
            f"?charset={self.charset}"
        )
    
    def validate(self) -> None:
        """Validate required configuration."""
        required_fields = ["host", "user", "password"]
        missing = [field for field in required_fields if not getattr(self, field)]
        
        if missing:
            raise ValueError(f"Missing required database config: {', '.join(missing)}")

# Global config instance
config = DatabaseConfig.from_env()