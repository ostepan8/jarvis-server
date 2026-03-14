# MemoryAgent

**Class**: `MemoryAgent`
**Module**: `jarvis/agents/memory_agent/__init__.py`
**Always enabled**

## Capabilities

### add_to_memory
Store information in the vector memory system.
- "Remember that my dog's name is Max"
- "Save this: the wifi password is on the fridge"
- "Keep in mind that I'm allergic to peanuts"

### recall_from_memory
Search vector memory using semantic similarity.
- "What do you remember about my pets?"
- "Do you remember the wifi password?"
- "What did I tell you about my allergies?"

### store_fact
Store a structured key-value fact.
- "My favorite color is blue"
- "I like pizza"
- "My name is John"

### search_facts
Search structured facts.
- "What's my favorite color?"
- "What do you know about me?"
- "What's my name?"

## Memory Architecture

### Layer 1: Vector Memory (ChromaDB)
- Semantic similarity search using OpenAI embeddings
- Best for: general knowledge, context, narrative information
- Requires `OPENAI_API_KEY` for embeddings
- Persisted to `~/.jarvis/chromadb/`

### Layer 2: Fact Memory
- Structured key-value storage
- Best for: user preferences, discrete facts
- In-memory with persistence

### Layer 3: Markdown Vault
- Persistent markdown files organized by topic
- Directory: `~/.jarvis/memory/`
- Short-term notes auto-promote to long-term after TTL (default 7 days)
- AI-assisted consolidation of related memories
- Human-readable format

## Cross-Agent Memory
All agents inherit `remember()` and `recall()` methods from `NetworkAgent`. Any agent can store or retrieve memories through the MemoryAgent without direct coupling.

## Configuration
- `memory_dir`: ChromaDB persist directory
- `memory_vault_dir`: Markdown vault location
- `memory_short_term_ttl_days`: Days before short-term promotion (default 7)
- `memory_auto_promote`: Auto-promote short-term to long-term (default true)
- `memory_auto_consolidate`: Merge related memories (default false)
