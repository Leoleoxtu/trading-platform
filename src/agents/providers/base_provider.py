"""
Base Provider Interface
Abstract class for all LLM provider implementations
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional
from datetime import datetime


class ModelTier(Enum):
    """Model tier categories based on speed/quality tradeoff"""
    FAST = "fast"      # Ultra-fast responses (< 2s), lower quality
    MEDIUM = "medium"  # Balanced speed/quality (2-5s)
    DEEP = "deep"      # Maximum quality, slower (5-30s)


@dataclass
class ProviderConfig:
    """Configuration for an AI provider"""
    name: str
    api_key: str
    models: Dict[str, str]  # tier -> model_name mapping
    weight: float = 1.0
    max_retries: int = 3
    timeout: int = 30
    rate_limit_rpm: Optional[int] = None
    rate_limit_tpm: Optional[int] = None


@dataclass
class CompletionRequest:
    """Standardized completion request"""
    prompt: str
    system_prompt: Optional[str] = None
    temperature: float = 0.3
    max_tokens: int = 2000
    json_mode: bool = False
    stop_sequences: Optional[List[str]] = None


@dataclass
class CompletionResponse:
    """Standardized completion response"""
    content: str
    model: str
    provider: str
    tokens_used: int
    cost_usd: float
    latency_ms: int
    timestamp: datetime
    metadata: Optional[Dict[str, Any]] = None


class BaseProvider(ABC):
    """
    Abstract base class for all LLM providers
    
    Implementations must support:
    - Three tier model selection (fast/medium/deep)
    - Retry logic with exponential backoff
    - Rate limiting awareness
    - Cost tracking
    - Streaming support (optional)
    """
    
    def __init__(self, config: ProviderConfig):
        self.config = config
        self.name = config.name
        self._validate_config()
    
    def _validate_config(self):
        """Validate provider configuration"""
        # Require at least fast and medium tiers (deep is optional)
        required_tiers = {"fast", "medium"}
        if not required_tiers.issubset(self.config.models.keys()):
            raise ValueError(
                f"{self.name} provider missing required model tiers. "
                f"Expected at least: {required_tiers}, Got: {set(self.config.models.keys())}"
            )
        
        if not self.config.api_key:
            raise ValueError(f"{self.name} provider requires api_key")
    
    @abstractmethod
    async def complete(
        self,
        request: CompletionRequest,
        tier: ModelTier = ModelTier.MEDIUM
    ) -> CompletionResponse:
        """
        Execute completion request
        
        Args:
            request: Completion request parameters
            tier: Model tier to use (fast/medium/deep)
            
        Returns:
            CompletionResponse with result and metadata
            
        Raises:
            ProviderError: On API errors after retries exhausted
        """
        pass
    
    @abstractmethod
    async def is_available(self) -> bool:
        """
        Check if provider is currently available
        
        Returns:
            True if provider can handle requests
        """
        pass
    
    def get_model_name(self, tier: ModelTier) -> str:
        """Get model name for given tier"""
        return self.config.models.get(tier.value)
    
    @abstractmethod
    def estimate_cost(self, tokens_in: int, tokens_out: int, tier: ModelTier) -> float:
        """
        Estimate cost in USD for given token counts
        
        Args:
            tokens_in: Input tokens
            tokens_out: Output tokens
            tier: Model tier
            
        Returns:
            Estimated cost in USD
        """
        pass
    
    def __str__(self) -> str:
        return f"{self.name}Provider(weight={self.config.weight})"


class ProviderError(Exception):
    """Base exception for provider errors"""
    pass


class RateLimitError(ProviderError):
    """Raised when rate limit is exceeded"""
    pass


class AuthenticationError(ProviderError):
    """Raised on authentication failures"""
    pass


class ModelNotFoundError(ProviderError):
    """Raised when requested model doesn't exist"""
    pass
