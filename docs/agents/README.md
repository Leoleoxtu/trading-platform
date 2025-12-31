# 📘 AI Providers & Schemas Documentation

## Overview

This module implements the foundation for Phase 3 (AI Core) of the trading platform. It provides:

1. **Multi-provider abstraction** for LLM access (Anthropic Claude, OpenAI GPT)
2. **Structured schemas** for NewsCards, Scenarios, and Signals
3. **Cost tracking** and rate limiting
4. **Failover support** and retry logic

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    AI Provider Layer                         │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐         ┌──────────────┐                 │
│  │   Anthropic  │         │    OpenAI    │                 │
│  │   Provider   │         │   Provider   │                 │
│  └──────┬───────┘         └──────┬───────┘                 │
│         │                        │                          │
│         └────────────┬───────────┘                          │
│                      │                                      │
│              ┌───────▼────────┐                            │
│              │  BaseProvider  │                            │
│              │   (Interface)  │                            │
│              └───────┬────────┘                            │
│                      │                                      │
│         ┌────────────┼────────────┐                        │
│         │            │            │                        │
│    ┌────▼─────┐ ┌───▼────┐ ┌────▼─────┐                  │
│    │  Fast    │ │ Medium │ │   Deep   │                  │
│    │ (Haiku/  │ │(Sonnet/│ │ (Opus/   │                  │
│    │ 4o-mini) │ │  4o)   │ │ o1)      │                  │
│    └──────────┘ └────────┘ └──────────┘                  │
└─────────────────────────────────────────────────────────────┘
                      │
                      ▼
         ┌────────────────────────┐
         │   Structured Schemas   │
         ├────────────────────────┤
         │ • NewsCard             │
         │ • Scenario             │
         │ • Signal               │
         └────────────────────────┘
```

---

## Components

### 1. Base Provider (`base_provider.py`)

Abstract interface that all providers must implement:

**Key Classes:**
- `BaseProvider`: Abstract base class
- `ModelTier`: Enum (FAST, MEDIUM, DEEP)
- `ProviderConfig`: Configuration dataclass
- `CompletionRequest`: Standardized request format
- `CompletionResponse`: Standardized response format

**Methods:**
```python
async def complete(request: CompletionRequest, tier: ModelTier) -> CompletionResponse
async def is_available() -> bool
def estimate_cost(tokens_in: int, tokens_out: int, tier: ModelTier) -> float
```

### 2. Anthropic Provider (`anthropic_provider.py`)

Implementation for Claude models with **LangSmith tracing**:

**Models:**
- **Fast**: `claude-haiku-4-5-20251001` (~$0.80/$4.00 per 1M tokens)
- **Medium**: `claude-sonnet-4-5-20250929` (~$3/$15 per 1M tokens)
- **Deep**: `claude-opus-4-20250514` (~$15/$75 per 1M tokens)

**Features:**
- Async API calls via `anthropic` SDK
- Exponential backoff retry
- Rate limit handling
- Cost estimation
- **🔥 LangSmith tracing** (automatic when configured)

### 3. OpenAI Provider (`openai_provider.py`)

Implementation for GPT models:

**Models:**
- **Fast**: `gpt-4o-mini` (~$0.15/$0.60 per 1M tokens)
- **Medium**: `gpt-4o` (~$2.50/$10 per 1M tokens)
- **Deep**: `o1-preview` (~$15/$60 per 1M tokens)

**Features:**
- Async API calls via `openai` SDK
- JSON mode support
- Retry logic
- Cost estimation

### 4. Schemas (`schemas.py`)

Pydantic models for structured data:

#### NewsCard
```python
class NewsCard(BaseModel):
    event_id: str
    timestamp: datetime
    entities: List[str]
    tickers: List[str]
    type: EventType  # product_announcement, earnings, etc.
    impact_direction: ImpactDirection  # positive, negative, mixed, neutral
    impact_strength: float  # 0.0-1.0
    time_horizon: TimeHorizon  # intraday, days, weeks, months
    novelty: Novelty  # new, repeat, update
    confidence: float  # 0.0-1.0
    uncertainties: List[str]
    why_it_matters: List[str]  # 3-5 bullet points
    invalidated_if: List[str]
    evidence_refs: List[str]
```

#### Scenario
```python
class Scenario(BaseModel):
    scenario_id: str
    ticker: str
    name: str
    bias: ScenarioBias  # bullish, bearish, neutral
    probability: float
    entry_conditions: List[str]
    invalidation_triggers: List[str]
    targets: Dict[str, float]
    reasoning: List[str]
    catalysts_pending: List[Dict[str, Any]]
```

#### Signal
```python
class Signal(BaseModel):
    signal_id: str
    ticker: str
    action: SignalAction  # BUY, SELL, HOLD
    confidence: float
    plan: Dict[str, Any]  # order_type, quantity, limits
    reasoning: List[str]
    matched_scenarios: List[str]
    risk_score: float
```

---

## Configuration

### `config/ai_providers.yaml`

```yaml
providers:
  - name: anthropic
    enabled: true
    weight: 0.6  # 60% of requests
    api_key: ${ANTHROPIC_API_KEY}
    models:
      fast: claude-haiku-4-5-20251001
      medium: claude-sonnet-4-5-20250929
      deep: claude-opus-4-20250514
    rate_limits:
      rpm: 50
      tpm: 100000
    
  - name: openai
    enabled: true
    weight: 0.4  # 40% of requests
    api_key: ${OPENAI_API_KEY}
    models:
      fast: gpt-4o-mini
      medium: gpt-4o
      deep: o1-preview
    rate_limits:
      rpm: 60
      tpm: 150000

selection_strategy:
  method: weighted_random
  tier_mapping:
    HELD: fast      # Positions held: fast response critical
    HIGH: medium    # High priority: balanced
    NORMAL: deep    # Normal: quality over speed
    LOW: deep       # Low: deep analysis

budget:
  daily_limit_usd: 500.0
  alert_at_pct: 80
  max_cost_per_call_usd: 1.0
```

---

## Usage Examples

### Example 1: Basic Completion

```python
from src.agents.providers import AnthropicProvider, ProviderConfig, CompletionRequest, ModelTier

# Configure provider
config = ProviderConfig(
    name="anthropic",
    api_key=os.getenv("ANTHROPIC_API_KEY"),
    models={
        "fast": "claude-haiku-4-5-20251001",
        "medium": "claude-sonnet-4-5-20250929",
        "deep": "claude-opus-4-20250514",
    }
)

provider = AnthropicProvider(config)

# Create request
request = CompletionRequest(
    prompt="Analyze this news: Apple announces new iPhone with AI features",
    system_prompt="You are a financial analyst expert",
    temperature=0.3,
    max_tokens=2000,
    json_mode=False
)

# Execute with medium tier
response = await provider.complete(request, tier=ModelTier.MEDIUM)

print(f"Response: {response.content}")
print(f"Cost: ${response.cost_usd:.4f}")
print(f"Latency: {response.latency_ms}ms")
```

### Example 2: NewsCard Generation

```python
from src.agents.schemas import NewsCard, EventType, ImpactDirection, TimeHorizon, Novelty
from datetime import datetime

newscard = NewsCard(
    event_id="550e8400-e29b-41d4-a716-446655440000",
    timestamp=datetime.utcnow(),
    entities=["Apple Inc", "Tim Cook"],
    tickers=["AAPL"],
    type=EventType.PRODUCT_ANNOUNCEMENT,
    impact_direction=ImpactDirection.POSITIVE,
    impact_strength=0.75,
    time_horizon=TimeHorizon.WEEKS,
    novelty=Novelty.NEW,
    confidence=0.85,
    uncertainties=["Market reception unclear"],
    why_it_matters=[
        "Could boost iPhone sales 10-15% in Q2",
        "Introduces AI features ahead of competitors"
    ],
    invalidated_if=["Delayed launch announcement"],
    evidence_refs=["minio://raw-events/rss/2024/12/31/abc123.json"]
)

# Validate and serialize
json_str = newscard.model_dump_json(indent=2)
```

### Example 3: Multi-Provider with Failover

```python
providers = [
    AnthropicProvider(anthropic_config),
    OpenAIProvider(openai_config)
]

async def complete_with_failover(request: CompletionRequest, tier: ModelTier):
    for provider in providers:
        try:
            if await provider.is_available():
                return await provider.complete(request, tier)
        except Exception as e:
            print(f"Provider {provider.name} failed: {e}")
            continue
    
    raise Exception("All providers failed")

response = await complete_with_failover(request, ModelTier.FAST)
```

---

## Testing

### Run Tests

```bash
# Set API keys
export ANTHROPIC_API_KEY="sk-ant-..."
export OPENAI_API_KEY="sk-..."

# Run test script
python examples/test_ai_providers.py
```

### Expected Output

```
============================================================
AI Providers & Schemas Test Suite
============================================================

=== Testing NewsCard Schema ===
✓ NewsCard created successfully
✓ Tickers (uppercased): ['AAPL']
✓ Type: product_announcement
✓ Impact: positive (0.75)
✓ Confidence: 0.85
✓ JSON serialization works (1234 bytes)

=== Testing Anthropic Provider ===
✓ Model: claude-haiku-4-5-20251001
✓ Response: 4
✓ Tokens: 15
✓ Cost: $0.0001
✓ Latency: 1234ms

=== Testing OpenAI Provider ===
✓ Model: gpt-4o-mini
✓ Response: 4
✓ Tokens: 12
✓ Cost: $0.0000
✓ Latency: 987ms

============================================================
Tests completed!
============================================================
```

---

## Cost Estimation

### Daily Budget Scenarios

**Conservative Mode (100 events/day, FAST tier)**
- Anthropic Haiku: ~$0.10/day
- OpenAI 4o-mini: ~$0.02/day
- **Total: ~$0.12/day**

**Normal Mode (1,000 events/day, MEDIUM tier)**
- Anthropic Sonnet: ~$3-5/day
- OpenAI 4o: ~$2-3/day
- **Total: ~$5-8/day**

**Performance Mode (10,000 events/day, DEEP tier overnight)**
- Anthropic Opus: ~$150-200/day
- OpenAI o1: ~$100-150/day
- **Total: ~$250-350/day**

---

## Next Steps

### Tâche 3.3: Prompt Template NewsCard
Create prompt engineering templates for NewsCard generation

### Tâche 3.4: Standardizer Core
Implement the Standardizer service that:
- Consumes from `events.triaged.v1`
- Calls LLM with prompt
- Validates and stores NewsCards
- Publishes to `newscards.v1`

### Tâche 3.5: Confidence Calibration
Implement empirical calibration of LLM confidence scores

---

## References

- **Anthropic SDK**: https://github.com/anthropics/anthropic-sdk-python
- **OpenAI SDK**: https://github.com/openai/openai-python
- **LangChain**: https://github.com/langchain-ai/langchain
- **LangSmith**: https://docs.smith.langchain.com/
- **Pydantic**: https://docs.pydantic.dev/

---

## 🔥 LangSmith Integration

### What is LangSmith?

LangSmith is a specialized monitoring and debugging platform for LLMs. It provides:
- **Detailed trace** of every prompt/response
- **Cost tracking** per conversation
- **Latency analysis** 
- **Quality evaluation** tools
- **A/B testing** capabilities
- **Datasets** for testing

### Configuration

1. **Sign up**: https://smith.langchain.com

2. **Get API key**: Settings → API Keys → Create API Key

3. **Configure `.env`**:
```bash
LANGCHAIN_TRACING_V2=true
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
LANGCHAIN_API_KEY=ls-your-api-key-here
LANGCHAIN_PROJECT=trading-platform-prod
```

4. **Done!** All Claude completions are now automatically traced.

### How It Works

The `AnthropicProvider.complete()` method is decorated with `@traceable`:

```python
@traceable(
    run_type="llm",
    name="anthropic_claude_completion",
    metadata={"provider": "anthropic"}
)
async def complete(self, request, tier):
    # Every call is automatically traced to LangSmith
    # No code changes needed!
    ...
```

### Testing

Run the integration test:

```bash
source venv/bin/activate
python examples/test_langsmith_integration.py
```

Then view traces at: https://smith.langchain.com/projects/trading-platform-prod

### Dashboard Features

**In LangSmith you'll see:**
- 📝 Full prompt text
- 💬 Complete response
- 🔢 Token counts (input/output)
- ⏱️ Latency in milliseconds
- 💰 Cost per call
- 🎯 Model used (Haiku/Sonnet)
- 🔗 Trace chains (multi-turn conversations)
- 🐛 Error stack traces

### Cost

- **Free tier**: 5,000 traces/month
- **Pro**: $39/month (50K traces)
- **Enterprise**: Custom pricing

### Alternative: Custom Dashboard

If you prefer free/self-hosted monitoring, use the custom dashboard:

```bash
source venv/bin/activate
bash scripts/start_ai_monitor.sh
```

Dashboard at: http://localhost:8010

**Comparison**:

| Feature | LangSmith | Custom Dashboard |
|---------|-----------|------------------|
| Cost | $39/mo after 5K | Free |
| Hosting | Cloud | Self-hosted |
| Prompt/Response | ✅ Full | ⚠️ Limited |
| Trace chains | ✅ | ❌ |
| Evaluation tools | ✅ | ❌ |
| Datasets | ✅ | ❌ |
| A/B testing | ✅ | ❌ |
| Real-time | ✅ | ✅ |
| Metrics | ✅ | ✅ |

**Recommendation**: Use both!
- LangSmith for debugging & quality analysis
- Custom dashboard for real-time monitoring

---

**Status**: ✅ Tasks 3.1 and 3.2 Complete | ✅ LangSmith Integrated
**Next**: Task 3.3 (Prompt Templates)
