"""
OpenAI Provider
Implements BaseProvider for GPT models (GPT-4o-mini, GPT-4o, o1)
"""

import asyncio
import json
from datetime import datetime
from typing import Optional

try:
    from openai import AsyncOpenAI, APIError, RateLimitError as OpenAIRateLimitError
except ImportError:
    raise ImportError(
        "openai package not installed. "
        "Install with: pip install openai"
    )

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
OPENAI_PRICING = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "o1-preview": {"input": 15.00, "output": 60.00},
    "o1": {"input": 15.00, "output": 60.00},
}


class OpenAIProvider(BaseProvider):
    """
    OpenAI GPT provider implementation
    
    Supports:
    - gpt-4o-mini (fast)
    - gpt-4o (medium)
    - o1-preview/o1 (deep)
    """
    
    def __init__(self, config):
        super().__init__(config)
        self.client = AsyncOpenAI(api_key=config.api_key)
        self._last_request_time = None
    
    async def complete(
        self,
        request: CompletionRequest,
        tier: ModelTier = ModelTier.MEDIUM
    ) -> CompletionResponse:
        """Execute completion using GPT"""
        model = self.get_model_name(tier)
        
        start_time = datetime.now()
        
        for attempt in range(self.config.max_retries):
            try:
                # Build messages
                messages = []
                if request.system_prompt:
                    messages.append({"role": "system", "content": request.system_prompt})
                messages.append({"role": "user", "content": request.prompt})
                
                # Prepare kwargs
                kwargs = {
                    "model": model,
                    "messages": messages,
                    "temperature": request.temperature,
                    "max_tokens": request.max_tokens,
                }
                
                # JSON mode for supported models
                if request.json_mode and not model.startswith("o1"):
                    kwargs["response_format"] = {"type": "json_object"}
                
                if request.stop_sequences:
                    kwargs["stop"] = request.stop_sequences
                
                # Call API
                response = await self.client.chat.completions.create(**kwargs)
                
                # Extract content
                content = response.choices[0].message.content
                
                # Calculate latency
                latency_ms = int((datetime.now() - start_time).total_seconds() * 1000)
                
                # Calculate tokens and cost
                tokens_in = response.usage.prompt_tokens
                tokens_out = response.usage.completion_tokens
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
                        "finish_reason": response.choices[0].finish_reason,
                        "attempt": attempt + 1,
                    }
                )
                
            except OpenAIRateLimitError as e:
                if attempt == self.config.max_retries - 1:
                    raise RateLimitError(f"Rate limit exceeded after {attempt + 1} attempts: {e}")
                # Exponential backoff
                await asyncio.sleep(2 ** attempt)
                
            except APIError as e:
                if "authentication" in str(e).lower() or "api_key" in str(e).lower():
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
        """Check if OpenAI API is available"""
        try:
            # Simple test request
            await self.client.chat.completions.create(
                model=self.get_model_name(ModelTier.FAST),
                messages=[{"role": "user", "content": "test"}],
                max_tokens=10
            )
            return True
        except Exception:
            return False
    
    def estimate_cost(self, tokens_in: int, tokens_out: int, tier: ModelTier) -> float:
        """Estimate cost based on OpenAI pricing"""
        model = self.get_model_name(tier)
        
        # Handle model variants
        model_key = model
        if model.startswith("o1-"):
            model_key = "o1-preview"  # Use o1-preview pricing for all o1 models
        
        if model_key not in OPENAI_PRICING:
            # Fallback to GPT-4o pricing
            pricing = OPENAI_PRICING["gpt-4o"]
        else:
            pricing = OPENAI_PRICING[model_key]
        
        cost_in = (tokens_in / 1_000_000) * pricing["input"]
        cost_out = (tokens_out / 1_000_000) * pricing["output"]
        
        return cost_in + cost_out
