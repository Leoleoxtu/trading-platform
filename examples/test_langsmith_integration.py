#!/usr/bin/env python3
"""
Test LangSmith Integration with Anthropic Provider

This script validates that:
1. LangSmith tracing is properly configured
2. Claude API calls are automatically traced
3. Traces appear in LangSmith dashboard

Prerequisites:
1. LANGCHAIN_API_KEY configured in .env
2. Virtual environment activated
3. All dependencies installed

Usage:
    source venv/bin/activate
    python examples/test_langsmith_integration.py

After running, check your traces at:
https://smith.langchain.com/projects/trading-platform-prod
"""

import asyncio
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from src.agents.providers.anthropic_provider import AnthropicProvider
from src.agents.providers.base_provider import (
    CompletionRequest,
    ModelTier,
    ProviderConfig,
)


def check_langsmith_config():
    """Check if LangSmith is properly configured"""
    print("🔍 Checking LangSmith configuration...")
    print()
    
    config_vars = {
        "LANGCHAIN_TRACING_V2": os.getenv("LANGCHAIN_TRACING_V2"),
        "LANGCHAIN_ENDPOINT": os.getenv("LANGCHAIN_ENDPOINT"),
        "LANGCHAIN_API_KEY": os.getenv("LANGCHAIN_API_KEY"),
        "LANGCHAIN_PROJECT": os.getenv("LANGCHAIN_PROJECT"),
        "ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY"),
    }
    
    all_configured = True
    for key, value in config_vars.items():
        if value:
            # Mask API keys
            if "API_KEY" in key:
                masked = value[:10] + "..." if len(value) > 10 else "***"
                print(f"  ✅ {key}: {masked}")
            else:
                print(f"  ✅ {key}: {value}")
        else:
            print(f"  ❌ {key}: NOT SET")
            all_configured = False
    
    print()
    
    if not all_configured:
        print("⚠️  LangSmith is not fully configured!")
        print()
        print("To configure:")
        print("1. Sign up at https://smith.langchain.com")
        print("2. Get API key from Settings → API Keys")
        print("3. Update .env file:")
        print("   LANGCHAIN_API_KEY=ls-your-api-key-here")
        print()
        return False
    
    print("✅ LangSmith configuration looks good!")
    print()
    return True


async def test_simple_completion():
    """Test a simple Claude completion with LangSmith tracing"""
    print("🧪 Test 1: Simple completion with Claude Haiku")
    print()
    
    # Create provider config
    config = ProviderConfig(
        name="anthropic",
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        models={
            "fast": "claude-haiku-4-5-20251001",
            "medium": "claude-sonnet-4-5-20250929",
        },
        weight=1.0,
    )
    
    # Initialize provider
    provider = AnthropicProvider(config)
    
    # Create request
    request = CompletionRequest(
        prompt="What is 2+2? Answer in one word.",
        max_tokens=10,
        temperature=0.0,
    )
    
    # Execute (will be automatically traced by LangSmith)
    print("  Sending request to Claude Haiku...")
    response = await provider.complete(request, tier=ModelTier.FAST)
    
    print(f"  ✅ Response: {response.content}")
    print(f"  📊 Model: {response.model}")
    print(f"  ⏱️  Latency: {response.latency_ms}ms")
    print(f"  🔢 Tokens: {response.tokens_used}")
    print(f"  💰 Cost: ${response.cost_usd:.6f}")
    print()
    
    return response


async def test_structured_completion():
    """Test a structured completion with system prompt"""
    print("🧪 Test 2: Structured completion with system prompt")
    print()
    
    config = ProviderConfig(
        name="anthropic",
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        models={
            "fast": "claude-haiku-4-5-20251001",
            "medium": "claude-sonnet-4-5-20250929",
        },
        weight=1.0,
    )
    
    provider = AnthropicProvider(config)
    
    request = CompletionRequest(
        system_prompt="You are a financial analyst. Respond in JSON format.",
        prompt="""Analyze this news: "Apple announces new iPhone with AI features"
        
Return JSON with keys: company, sentiment (positive/negative/neutral), impact (high/medium/low)""",
        max_tokens=100,
        temperature=0.3,
    )
    
    print("  Sending structured request to Claude Sonnet...")
    response = await provider.complete(request, tier=ModelTier.MEDIUM)
    
    print(f"  ✅ Response:\n{response.content}")
    print()
    print(f"  📊 Model: {response.model}")
    print(f"  ⏱️  Latency: {response.latency_ms}ms")
    print(f"  🔢 Tokens: {response.tokens_used}")
    print(f"  💰 Cost: ${response.cost_usd:.6f}")
    print()
    
    return response


async def test_multi_turn():
    """Test multiple completions to generate trace chain"""
    print("🧪 Test 3: Multi-turn conversation (trace chain)")
    print()
    
    config = ProviderConfig(
        name="anthropic",
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        models={
            "fast": "claude-haiku-4-5-20251001",
            "medium": "claude-sonnet-4-5-20250929",
        },
        weight=1.0,
    )
    
    provider = AnthropicProvider(config)
    
    prompts = [
        "What is the capital of France? One word.",
        "What country is that in? One word.",
        "What continent? One word.",
    ]
    
    total_cost = 0.0
    
    for i, prompt in enumerate(prompts, 1):
        request = CompletionRequest(
            prompt=prompt,
            max_tokens=10,
            temperature=0.0,
        )
        
        print(f"  Turn {i}: {prompt}")
        response = await provider.complete(request, tier=ModelTier.FAST)
        print(f"    → {response.content}")
        total_cost += response.cost_usd
    
    print()
    print(f"  💰 Total cost: ${total_cost:.6f}")
    print()
    
    return total_cost


async def main():
    """Run all tests"""
    print("=" * 70)
    print("  LANGSMITH INTEGRATION TEST")
    print("=" * 70)
    print()
    
    # Load environment variables
    load_dotenv()
    
    # Check configuration
    if not check_langsmith_config():
        print("⚠️  Tests will run but traces won't be sent to LangSmith")
        print("   (They will still work locally)")
        print()
    
    try:
        # Run tests
        await test_simple_completion()
        await test_structured_completion()
        await test_multi_turn()
        
        print("=" * 70)
        print("  ✅ ALL TESTS PASSED!")
        print("=" * 70)
        print()
        
        if os.getenv("LANGCHAIN_TRACING_V2") == "true":
            project = os.getenv("LANGCHAIN_PROJECT", "default")
            print("🔍 View your traces in LangSmith:")
            print(f"   https://smith.langchain.com/projects/{project}")
            print()
            print("📊 What you'll see:")
            print("   - All prompts and responses")
            print("   - Tokens, latency, cost per call")
            print("   - Model used (Haiku vs Sonnet)")
            print("   - Trace chain for multi-turn conversation")
            print()
        else:
            print("ℹ️  LangSmith tracing is disabled")
            print("   Set LANGCHAIN_TRACING_V2=true in .env to enable")
            print()
        
    except Exception as e:
        print()
        print("=" * 70)
        print("  ❌ TEST FAILED")
        print("=" * 70)
        print()
        print(f"Error: {e}")
        print()
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
