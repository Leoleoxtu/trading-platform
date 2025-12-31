"""
Anthropic Claude Provider
Implements BaseProvider for Claude models (Haiku, Sonnet, Opus)

With LangSmith tracing integration for monitoring and debugging.
"""

import asyncio
import json
from datetime import datetime
from typing import Optional

try:
    from anthropic import AsyncAnthropic, APIError, RateLimitError as AnthropicRateLimitError
except ImportError:
    raise ImportError(
        "anthropic package not installed. "
        "Install with: pip install anthropic"
    )

try:
    from langsmith import traceable
    LANGSMITH_AVAILABLE = True
except ImportError:
    LANGSMITH_AVAILABLE = False
    # Fallback decorator that does nothing
    def traceable(*args, **kwargs):
        def decorator(func):
            return func
        return decorator

from .base_provider import (
    BaseProvider,
    CompletionRequest,
    CompletionResponse,
    ModelTier,
    ProviderError,
    RateLimitError,
    AuthenticationError,
)


# Pricing per 1M tokens (as of Dec 2024)
ANTHROPIC_PRICING = {
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
    "claude-sonnet-4-5-20250929": {"input": 3.00, "output": 15.00},
    "claude-opus-4-20250514": {"input": 15.00, "output": 75.00},
}


class AnthropicProvider(BaseProvider):
    """
    Anthropic Claude provider implementation
    
    Supports:
    - claude-haiku (fast)
    - claude-sonnet (medium)
    - claude-opus (deep)
    """
    
    def __init__(self, config):
        super().__init__(config)
        self.client = AsyncAnthropic(api_key=config.api_key)
        self._last_request_time = None
    
    @traceable(
        run_type="llm",
        name="anthropic_claude_completion",
        metadata={"provider": "anthropic"}
    )
    async def complete(
        self,
        request: CompletionRequest,
        tier: ModelTier = ModelTier.MEDIUM
    ) -> CompletionResponse:
        """
        Execute completion using Claude with LangSmith tracing
        
        When LANGCHAIN_TRACING_V2=true in .env, this method automatically:
        - Logs the prompt and response to LangSmith
        - Tracks tokens, cost, latency
        - Enables debugging and analysis in LangSmith UI
        """
        model = self.get_model_name(tier)
        
        start_time = datetime.now()
        
        for attempt in range(self.config.max_retries):
            try:
                # Build messages
                messages = [{"role": "user", "content": request.prompt}]
                
                # Prepare kwargs
                kwargs = {
                    "model": model,
                    "max_tokens": request.max_tokens,
                    "temperature": request.temperature,
                    "messages": messages,
                }
                
                if request.system_prompt:
                    kwargs["system"] = request.system_prompt
                
                if request.stop_sequences:
                    kwargs["stop_sequences"] = request.stop_sequences
                
                # Call API
                response = await self.client.messages.create(**kwargs)
                
                # Extract content
                content = response.content[0].text
                
                # Calculate latency
                latency_ms = int((datetime.now() - start_time).total_seconds() * 1000)
                
                # Calculate tokens and cost
                tokens_in = response.usage.input_tokens
                tokens_out = response.usage.output_tokens
                cost = self.estimate_cost(tokens_in, tokens_out, tier)
                
                return CompletionResponse(
                    content=content,
                    model=model,
                    provider=self.name,
                    tokens_used=tokens_in + tokens_out,
                    cost_usd=cost,
                    latency_ms=latency_ms,
                    timestamp=datetime.now(),
                    metadata={
                        "tokens_in": tokens_in,
                        "tokens_out": tokens_out,
                        "stop_reason": response.stop_reason,
                        "attempt": attempt + 1,
                    }
                )
                
            except AnthropicRateLimitError as e:
                if attempt == self.config.max_retries - 1:
                    raise RateLimitError(f"Rate limit exceeded after {attempt + 1} attempts: {e}")
                # Exponential backoff
                await asyncio.sleep(2 ** attempt)
                
            except APIError as e:
                if "authentication" in str(e).lower():
                    raise AuthenticationError(f"Authentication failed: {e}")
                if attempt == self.config.max_retries - 1:
                    raise ProviderError(f"API error after {attempt + 1} attempts: {e}")
                await asyncio.sleep(2 ** attempt)
                
            except Exception as e:
                if attempt == self.config.max_retries - 1:
                    raise ProviderError(f"Unexpected error: {e}")
                await asyncio.sleep(2 ** attempt)
        
        raise ProviderError("Max retries exceeded")
    
    async def is_available(self) -> bool:
        """Check if Anthropic API is available"""
        try:
            # Simple test request
            await self.client.messages.create(
                model=self.get_model_name(ModelTier.FAST),
                max_tokens=10,
                messages=[{"role": "user", "content": "test"}]
            )
            return True
        except Exception:
            return False
    
    def estimate_cost(self, tokens_in: int, tokens_out: int, tier: ModelTier) -> float:
        """Estimate cost based on Claude pricing"""
        model = self.get_model_name(tier)
        
        if model not in ANTHROPIC_PRICING:
            # Fallback to Sonnet pricing
            pricing = ANTHROPIC_PRICING["claude-sonnet-4-5-20250929"]
        else:
            pricing = ANTHROPIC_PRICING[model]
        
        cost_in = (tokens_in / 1_000_000) * pricing["input"]
        cost_out = (tokens_out / 1_000_000) * pricing["output"]
        
        return cost_in + cost_out
