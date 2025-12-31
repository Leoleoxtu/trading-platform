"""
Simple test/example for AI providers
Demonstrates usage of multi-provider setup
"""

import asyncio
import os
from src.agents.providers import (
    AnthropicProvider,
    OpenAIProvider,
    ProviderConfig,
    CompletionRequest,
    ModelTier,
)


async def test_anthropic():
    """Test Anthropic Claude provider"""
    print("\n=== Testing Anthropic Provider ===")
    
    config = ProviderConfig(
        name="anthropic",
        api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        models={
            "fast": "claude-haiku-4-5-20251001",
            "medium": "claude-sonnet-4-5-20250929",
            "deep": "claude-opus-4-20250514",
        },
        weight=0.6,
    )
    
    provider = AnthropicProvider(config)
    
    # Test fast tier
    request = CompletionRequest(
        prompt="What is 2+2? Answer in one word.",
        temperature=0.0,
        max_tokens=10,
    )
    
    try:
        response = await provider.complete(request, tier=ModelTier.FAST)
        print(f"✓ Model: {response.model}")
        print(f"✓ Response: {response.content}")
        print(f"✓ Tokens: {response.tokens_used}")
        print(f"✓ Cost: ${response.cost_usd:.4f}")
        print(f"✓ Latency: {response.latency_ms}ms")
    except Exception as e:
        print(f"✗ Error: {e}")


async def test_openai():
    """Test OpenAI GPT provider"""
    print("\n=== Testing OpenAI Provider ===")
    
    config = ProviderConfig(
        name="openai",
        api_key=os.getenv("OPENAI_API_KEY", ""),
        models={
            "fast": "gpt-4o-mini",
            "medium": "gpt-4o",
            "deep": "o1-preview",
        },
        weight=0.4,
    )
    
    provider = OpenAIProvider(config)
    
    # Test fast tier
    request = CompletionRequest(
        prompt="What is 2+2? Answer in one word.",
        temperature=0.0,
        max_tokens=10,
    )
    
    try:
        response = await provider.complete(request, tier=ModelTier.FAST)
        print(f"✓ Model: {response.model}")
        print(f"✓ Response: {response.content}")
        print(f"✓ Tokens: {response.tokens_used}")
        print(f"✓ Cost: ${response.cost_usd:.4f}")
        print(f"✓ Latency: {response.latency_ms}ms")
    except Exception as e:
        print(f"✗ Error: {e}")


async def test_newscard_schema():
    """Test NewsCard schema validation"""
    print("\n=== Testing NewsCard Schema ===")
    
    from src.agents.schemas import NewsCard, EventType, ImpactDirection, TimeHorizon, Novelty
    from datetime import datetime
    
    try:
        newscard = NewsCard(
            event_id="test-123",
            timestamp=datetime.utcnow(),
            entities=["Apple Inc", "Tim Cook"],
            tickers=["aapl"],  # Will be uppercased automatically
            type=EventType.PRODUCT_ANNOUNCEMENT,
            impact_direction=ImpactDirection.POSITIVE,
            impact_strength=0.75,
            time_horizon=TimeHorizon.WEEKS,
            novelty=Novelty.NEW,
            confidence=0.85,
            uncertainties=["Market reception unclear"],
            why_it_matters=[
                "Could boost iPhone sales 10-15%",
                "Introduces AI features ahead of competitors",
            ],
            invalidated_if=["Delayed launch"],
            evidence_refs=["minio://raw-events/test.json"],
        )
        
        print("✓ NewsCard created successfully")
        print(f"✓ Tickers (uppercased): {newscard.tickers}")
        print(f"✓ Type: {newscard.type.value}")
        print(f"✓ Impact: {newscard.impact_direction.value} ({newscard.impact_strength})")
        print(f"✓ Confidence: {newscard.confidence}")
        
        # Test JSON serialization
        json_data = newscard.model_dump_json(indent=2)
        print(f"✓ JSON serialization works ({len(json_data)} bytes)")
        
    except Exception as e:
        print(f"✗ Error: {e}")


async def main():
    """Run all tests"""
    print("=" * 60)
    print("AI Providers & Schemas Test Suite")
    print("=" * 60)
    
    # Test schemas (no API key needed)
    await test_newscard_schema()
    
    # Test providers (requires API keys)
    if os.getenv("ANTHROPIC_API_KEY"):
        await test_anthropic()
    else:
        print("\n⚠️  Skipping Anthropic test (ANTHROPIC_API_KEY not set)")
    
    if os.getenv("OPENAI_API_KEY"):
        await test_openai()
    else:
        print("\n⚠️  Skipping OpenAI test (OPENAI_API_KEY not set)")
    
    print("\n" + "=" * 60)
    print("Tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
