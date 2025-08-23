"""
Platform configuration management using Pydantic Settings.
"""

from typing import List, Optional, Dict
import json
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings as PydanticBaseSettings, SettingsConfigDict


class DatabaseConfig(PydanticBaseSettings):
    """TimescaleDB configuration."""
    
    host: str = Field(default="localhost", description="Database host")
    port: int = Field(default=5432, description="Database port")
    database: str = Field(default="platform_events", description="Database name")
    username: str = Field(default="platform", description="Database username")
    password: str = Field(default="platform_secure_pass", description="Database password")
    pool_size: int = Field(default=20, description="Connection pool size")
    max_overflow: int = Field(default=10, description="Max pool overflow")
    max_size: int = Field(default=30, description="Maximum pool size (use instead of max_overflow)")
    
    @property
    def url(self) -> str:
        """Get database URL."""
        return f"postgresql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"


class RedisConfig(PydanticBaseSettings):
    """Redis configuration."""
    
    host: str = Field(default="localhost", description="Redis host")
    port: int = Field(default=6379, description="Redis port")
    db: int = Field(default=0, description="Redis database number")
    password: Optional[str] = Field(default=None, description="Redis password")
    max_connections: int = Field(default=50, description="Max connections")
    decode_responses: bool = Field(default=True, description="Return strings instead of bytes from redis client")
    
    @property
    def url(self) -> str:
        """Get Redis URL."""
        auth = f":{self.password}@" if self.password else ""
        return f"redis://{auth}{self.host}:{self.port}/{self.db}"


class NATSConfig(PydanticBaseSettings):
    """NATS configuration."""
    
    servers: List[str] = Field(default=["nats://localhost:4222"], description="NATS servers")
    max_reconnect_attempts: int = Field(default=60, description="Max reconnection attempts")
    reconnect_time_wait: float = Field(default=2.0, description="Reconnect wait time")
    

class NetworkConfig(PydanticBaseSettings):
    """Single-chain network configuration with API key substitution.

    Prefer this over PLATFORM_RPC_URLS JSON. Use RPC_URL_TEMPLATE with {API_KEY} placeholder.
    """
    name: str = Field(default="sepolia", description="Network name (e.g., mainnet, sepolia, arbitrum, base)")
    chain_id: int = Field(default=11155111, description="EVM chain id")
    rpc_url_template: str = Field(default="https://eth-sepolia.g.alchemy.com/v2/{API_KEY}", description="RPC URL template with optional {API_KEY} placeholder")
    api_key: Optional[str] = Field(default=None, description="Provider API key to inject into RPC URL template")
    block_confirmations: int = Field(default=6, description="Blocks to wait for confirmations")

    def resolve_rpc_url(self) -> str:
        url = self.rpc_url_template
        if "{API_KEY}" in url:
            return url.replace("{API_KEY}", self.api_key or "")
        return url


class RayConfig(PydanticBaseSettings):
    """Ray distributed computing configuration."""
    
    address: Optional[str] = Field(default="ray://localhost:10001", description="Ray cluster address")
    num_cpus: Optional[int] = Field(default=4, description="Number of CPUs to use")
    num_gpus: Optional[int] = Field(default=0, description="Number of GPUs to use")
    object_store_memory: Optional[int] = Field(default=2147483648, description="Object store memory")

    @field_validator("address", mode="before")
    @classmethod
    def _normalize_address(cls, v):
        """Treat empty string or None as the default Ray Client address.
        Prevents accidental local raylet startup when env var is blank.
        """
        default_addr = "ray://localhost:10001"
        if v is None:
            return default_addr
        if isinstance(v, str) and v.strip() == "":
            return default_addr
        return v


class MLConfig(PydanticBaseSettings):
    """Machine Learning configuration."""
    
    model_cache_dir: str = Field(default="./models", description="ML model cache directory")
    gpu_memory_fraction: float = Field(default=0.8, description="GPU memory fraction to use")
    enable_onnx_optimization: bool = Field(default=True, description="Enable ONNX runtime optimizations")
    max_model_cache_size: int = Field(default=10, description="Maximum models to cache")


class PlatformConfig(PydanticBaseSettings):
    """Main platform configuration."""
    
    # Environment
    environment: str = Field(default="development", description="Environment (development/staging/production)")
    debug: bool = Field(default=True, description="Debug mode")
    
    # API configuration
    api_host: str = Field(default="0.0.0.0", description="API host")
    api_port: int = Field(default=8000, description="API port")
    
    # Component configurations
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    nats: NATSConfig = Field(default_factory=NATSConfig)
    ray: RayConfig = Field(default_factory=RayConfig)
    ml: MLConfig = Field(default_factory=MLConfig)
    network: NetworkConfig = Field(default_factory=NetworkConfig)
    # RPC URLs per chain id (e.g., {1: "https://mainnet.infura.io/v3/..."})
    rpc_urls: Dict[int, str] = Field(default_factory=dict)
    
    @field_validator("rpc_urls", mode="before")
    @classmethod
    def _coerce_rpc_urls(cls, v):
        """Allow env to provide JSON with string keys; coerce to Dict[int, str]."""
        if v in (None, ""):
            return {}
        data = v
        if isinstance(v, str):
            try:
                data = json.loads(v)
            except Exception:
                return {}
        if isinstance(data, dict):
            coerced = {}
            for k, val in data.items():
                try:
                    coerced[int(k)] = str(val)
                except Exception:
                    continue
            return coerced
        return v
    
    # Performance settings
    max_intent_queue_size: int = Field(default=10000, description="Maximum intent queue size")
    intent_processing_timeout: float = Field(default=30.0, description="Intent processing timeout")
    event_buffer_size: int = Field(default=1000, description="Event buffer size")
    # Feature flags
    enable_legacy_intent_queue: bool = Field(default=False, description="Enable legacy intent queue processor")
    
    # Pydantic Settings v2 configuration: load from .env by default
    model_config = SettingsConfigDict(
        env_prefix="PLATFORM_",
        env_nested_delimiter="__",
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
    )

    def get_rpc_url(self, chain_id: int) -> str:
        """Resolve the RPC URL for a chain.
        Back-compat: if rpc_urls is provided via env, prefer it. Else build from single network config.
        """
        if self.rpc_urls:
            return self.rpc_urls.get(chain_id, "")
        if chain_id == self.network.chain_id:
            return self.network.resolve_rpc_url()
        return ""


# Global configuration instance
config = PlatformConfig()
