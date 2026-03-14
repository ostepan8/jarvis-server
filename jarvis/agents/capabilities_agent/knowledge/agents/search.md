# SearchAgent

**Class**: `SearchAgent`
**Module**: `jarvis/agents/search_agent/agent.py`
**Requires**: Google Search API credentials

## Capabilities

### search
Web search with AI-powered result synthesis.
- "What is the capital of France?"
- "Who wrote Hamlet?"
- "What's the weather in Boston?"
- "Latest news about AI"
- "How tall is the Eiffel Tower?"

## How It Works
1. User query is sent to Google Custom Search API
2. Top results are retrieved with snippets
3. AI client synthesizes results into a conversational answer
4. Both the synthesized answer and raw results are returned

## What It Handles
- Factual questions (who, what, when, where, how)
- Current events and news
- Weather queries (via web search)
- General knowledge lookup
- Definition and explanation queries

## Requirements
- `GOOGLE_SEARCH_API_KEY`: Google API key with Custom Search enabled
- `GOOGLE_SEARCH_ENGINE_ID`: Custom Search Engine ID
- If either is missing, SearchAgent is not registered at startup

## Architecture
- `GoogleSearchService` handles API calls with error handling
- AI client (strong or weak model) synthesizes search results
- Results include source URLs for attribution
