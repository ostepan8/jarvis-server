# NLUAgent

**Class**: `NLUAgent`
**Module**: `jarvis/agents/nlu_agent/__init__.py`
**Always enabled** (core routing agent)

## Capabilities

### intent_matching
Classify user input and route to the appropriate agent(s).

This is not a user-facing capability — it's the routing layer that makes everything else work.

## How Routing Works

### Fast Path (Embedding-Based)
1. User input is embedded using OpenAI embeddings
2. Compared against training phrases in ChromaDB
3. If confidence >= 0.85: route directly (no LLM call)
4. If confidence 0.70-0.85: provide hint to LLM
5. If confidence < 0.70: fall back to full LLM classification

### LLM Classification
1. All registered capabilities are listed in the prompt
2. LLM returns a JSON DAG: `{"dag": {"capability": [dependencies]}}`
3. DAG enables parallel execution of independent capabilities

### DAG Execution
- Capabilities with no dependencies execute in parallel
- Results from earlier steps feed into dependent steps
- Aggregated final response sent back to user

### Classification Cache
- TTL-based cache (default 120s) avoids re-classifying identical inputs
- Max 500 cached entries

## Multi-Capability Handling
The NLU can classify a single user request into multiple capabilities:
- "What's the weather and add a meeting at 3pm" → search + create_event
- Dependencies expressed in DAG: `{"search": [], "chat": ["search"]}`

## Training Phrases
The fast classifier uses curated training phrases per capability. These are defined in `fast_classifier.py` and cover common phrasings for each intent.
