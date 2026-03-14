# Information Skills

## Web Search
**Agent**: SearchAgent
**Requires**: Google Search API credentials

Search the web and synthesize answers from results.

### What You Can Do
| Capability | Description | Example |
|-----------|-------------|---------|
| `search` | Web search with AI synthesis | "What is the capital of France?" |

### How It Works
- Uses Google Custom Search API
- AI client synthesizes search results into conversational answers
- Handles factual questions, current events, general knowledge
- Also handles weather queries via web search

### Requirements
- `GOOGLE_SEARCH_API_KEY` and `GOOGLE_SEARCH_ENGINE_ID` configured
- If not configured, SearchAgent is not registered

---

## Memory System
**Agent**: MemoryAgent
**Always enabled**

Triple-layered memory: vector search (ChromaDB), structured facts, and markdown vault.

### What You Can Do
| Capability | Description | Example |
|-----------|-------------|---------|
| `add_to_memory` | Store information in vector memory | "Remember that my dog's name is Max" |
| `recall_from_memory` | Search vector memory | "What do you remember about my pets?" |
| `store_fact` | Store structured fact | "My favorite color is blue" |
| `search_facts` | Search structured facts | "What's my favorite color?" |

### Memory Layers
1. **Vector Memory** (ChromaDB): Semantic similarity search for general knowledge. Requires `OPENAI_API_KEY` for embeddings.
2. **Fact Memory**: Key-value structured storage for user preferences and facts.
3. **Markdown Vault** (~/.jarvis/memory/): Persistent markdown files organized by topic with automatic short-term to long-term promotion.

### Memory Features
- Auto-consolidation of related memories
- Short-term memory TTL (default 7 days) with auto-promotion
- Per-user memory isolation
- All agents can store/recall via `remember()` and `recall()` base methods

---

## Conversation
**Agent**: ChatAgent
**Always enabled**

General-purpose conversational AI with fact storage and profile management.

### What You Can Do
| Capability | Description | Example |
|-----------|-------------|---------|
| `chat` | General conversation | "Tell me a joke" |
| `store_fact` | Save user preference | "I prefer dark mode" |
| `get_facts` | Retrieve user facts | "What do you know about me?" |
| `update_profile` | Update user profile | "My timezone is EST" |

### Multi-Turn Support
ChatAgent supports `dialogue` mode for multi-turn agent-to-agent conversations. It can act as a lead agent in multi-agent coordination via the CollaborationMixin.

### Tool Use
ChatAgent has access to tools for fact storage and retrieval, enabling it to persist information across conversations.

---

## Canvas (Academic)
**Agent**: CanvasAgent
**Feature Flag**: `enable_canvas`

Integration with Canvas LMS for academic course and assignment tracking.

### What You Can Do
| Capability | Description | Example |
|-----------|-------------|---------|
| `get_courses` | List enrolled courses | "What courses am I taking?" |
| `get_comprehensive_homework` | View assignments and due dates | "What homework do I have?" |

### Requirements
- Canvas API credentials configured
- Canvas service handles API communication
