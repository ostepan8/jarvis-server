from __future__ import annotations

import json
import datetime
from typing import Any, Dict, List, Optional, Set

from ..base import NetworkAgent
from ..message import Message
from ...services.vector_memory import VectorMemoryService
from ...services.fact_memory import FactMemoryService
from ...services.markdown_memory import MarkdownMemoryService
from ...logging import JarvisLogger
from ...ai_clients.base import BaseAIClient


class MemoryAgent(NetworkAgent):
    """Agent providing shared memory services via a markdown vault, with
    optional vector and structured-fact backends for semantic search.

    The markdown vault is the source of truth.  Vector memory and the fact
    service are used as optional enhancement layers for semantic search and
    structured queries respectively.
    """

    def __init__(
        self,
        memory_service: Optional[VectorMemoryService] = None,
        fact_service: Optional[FactMemoryService] = None,
        logger: Optional[JarvisLogger] = None,
        ai_client: Optional[BaseAIClient] = None,
        markdown_memory: Optional[MarkdownMemoryService] = None,
    ) -> None:
        super().__init__("MemoryAgent", logger, memory=memory_service)
        self.vector_memory = memory_service
        self.fact_service = fact_service or FactMemoryService()
        self.ai_client = ai_client
        self.markdown_memory = markdown_memory

    @property
    def description(self) -> str:
        return "Stores and retrieves memories for other agents"

    @property
    def capabilities(self) -> Set[str]:
        return {
            "add_to_memory",
            "recall_from_memory",
            "store_fact",
            "get_facts",
            "extract_facts",
            "search_facts",
            "browse_memories",
            "consolidate_memories",
            "promote_memory",
            "memory_stats",
        }

    # ------------------------------------------------------------------
    # Metadata helpers
    # ------------------------------------------------------------------

    def _sanitize_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Convert metadata to ChromaDB-compatible format (str, int, float only)."""
        sanitized = {}
        for key, value in metadata.items():
            if isinstance(value, (str, int, float)):
                sanitized[key] = value
            elif isinstance(value, bool):
                sanitized[key] = str(value).lower()
            elif isinstance(value, list):
                sanitized[key] = ", ".join(str(item) for item in value)
            elif isinstance(value, dict):
                sanitized[key] = json.dumps(value)
            elif value is None:
                sanitized[key] = ""
            else:
                sanitized[key] = str(value)
        return sanitized

    # ------------------------------------------------------------------
    # Capability dispatch
    # ------------------------------------------------------------------

    async def _handle_capability_request(self, message: Message) -> None:
        capability = message.content.get("capability")
        data = message.content.get("data", {})
        user_id = data.get("user_id")

        handler = {
            "add_to_memory": self._handle_add_to_memory,
            "store_fact": self._handle_store_fact,
            "get_facts": self._handle_get_facts,
            "extract_facts": self._handle_extract_facts,
            "search_facts": self._handle_search_facts,
            "recall_from_memory": self._handle_recall,
            "browse_memories": self._handle_browse_memories,
            "consolidate_memories": self._handle_consolidate_memories,
            "promote_memory": self._handle_promote_memory,
            "memory_stats": self._handle_memory_stats,
        }.get(capability)

        if handler:
            await handler(message, data, user_id)

    # ------------------------------------------------------------------
    # add_to_memory
    # ------------------------------------------------------------------

    async def _handle_add_to_memory(
        self, message: Message, data: Dict[str, Any], user_id: Optional[int]
    ) -> None:
        content = data.get("prompt", "")
        metadata = data.get("metadata", {})

        if not content:
            await self.send_error(
                message.from_agent,
                "No content provided to remember",
                message.request_id,
            )
            return

        try:
            # Determine category and tags via AI or heuristics
            category = metadata.get("category", "personal")
            tags = metadata.get("tags", [])
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",") if t.strip()]
            source = metadata.get("source", "conversation")

            # Use AI for better categorisation when available
            if self.ai_client and not metadata.get("category"):
                ai_meta = await self._generate_enhanced_metadata(content, metadata)
                category = ai_meta.get("category", category)
                if isinstance(ai_meta.get("topics"), str):
                    tags = [t.strip() for t in ai_meta["topics"].split(",")]

            # --- Primary: markdown vault ---
            mem_id = None
            if self.markdown_memory:
                entry = await self.markdown_memory.store(
                    content=content,
                    category=category,
                    tags=tags,
                    source=source,
                    confidence=float(metadata.get("confidence", 0.8)),
                )
                mem_id = entry.memory_id

            # --- Secondary: vector memory ---
            if self.vector_memory:
                enhanced_metadata = await self._generate_enhanced_metadata(
                    content, metadata
                )
                vec_id = await self.vector_memory.add_memory(
                    content, enhanced_metadata, user_id=user_id
                )
                if mem_id is None:
                    mem_id = vec_id

            confirmation = await self._generate_memory_confirmation(
                content, {"category": category, "topics": ", ".join(tags)}
            )

            await self.send_capability_response(
                message.from_agent,
                {"response": confirmation, "success": True, "memory_id": mem_id},
                message.request_id,
                message.id,
            )
        except Exception as exc:
            await self.send_error(message.from_agent, str(exc), message.request_id)

    # ------------------------------------------------------------------
    # store_fact
    # ------------------------------------------------------------------

    async def _handle_store_fact(
        self, message: Message, data: Dict[str, Any], user_id: Optional[int]
    ) -> None:
        fact_text = data.get("fact_text", "")
        category = data.get("category", "general")
        entity = data.get("entity")
        confidence = data.get("confidence", 1.0)
        source = data.get("source", "explicit")
        context = data.get("context")

        if not fact_text or user_id is None:
            await self.send_error(
                message.from_agent,
                "fact_text and user_id are required",
                message.request_id,
            )
            return

        try:
            conflicts = self.fact_service.check_conflicts(
                user_id, fact_text, category
            )

            fact_id = self.fact_service.add_fact(
                user_id=user_id,
                fact_text=fact_text,
                category=category,
                entity=entity,
                confidence=confidence,
                source=source,
                context=context,
            )

            # Write to markdown vault
            if self.markdown_memory:
                tags = [entity] if entity else []
                await self.markdown_memory.store(
                    content=fact_text,
                    category=category,
                    tags=tags,
                    source=source,
                    confidence=float(confidence),
                    section=entity,
                )

            # Write to vector memory
            if self.vector_memory:
                await self.vector_memory.add_memory(
                    fact_text,
                    {
                        "fact_id": fact_id,
                        "category": category,
                        "entity": entity,
                        "type": "fact",
                    },
                    user_id=user_id,
                )

            conflict_msg = ""
            if conflicts:
                conflict_msg = (
                    f" Note: Found {len(conflicts)} potentially conflicting facts."
                )

            await self.send_capability_response(
                message.from_agent,
                {
                    "response": f"Fact stored successfully.{conflict_msg}",
                    "fact_id": fact_id,
                    "conflicts": len(conflicts),
                },
                message.request_id,
                message.id,
            )
        except Exception as exc:
            await self.send_error(message.from_agent, str(exc), message.request_id)

    # ------------------------------------------------------------------
    # get_facts
    # ------------------------------------------------------------------

    async def _handle_get_facts(
        self, message: Message, data: Dict[str, Any], user_id: Optional[int]
    ) -> None:
        category = data.get("category")
        entity = data.get("entity")
        limit = data.get("limit", 10)

        if user_id is None:
            await self.send_error(
                message.from_agent, "user_id is required", message.request_id
            )
            return

        try:
            facts = self.fact_service.get_facts(
                user_id=user_id,
                category=category,
                entity=entity,
                limit=limit,
            )
            await self.send_capability_response(
                message.from_agent,
                {
                    "facts": [
                        {
                            "id": f.id,
                            "text": f.fact_text,
                            "category": f.category,
                            "entity": f.entity,
                            "confidence": f.confidence,
                        }
                        for f in facts
                    ],
                    "count": len(facts),
                },
                message.request_id,
                message.id,
            )
        except Exception as exc:
            await self.send_error(message.from_agent, str(exc), message.request_id)

    # ------------------------------------------------------------------
    # extract_facts
    # ------------------------------------------------------------------

    async def _handle_extract_facts(
        self, message: Message, data: Dict[str, Any], user_id: Optional[int]
    ) -> None:
        conversation_text = data.get("conversation_text", "")

        if not conversation_text or user_id is None:
            await self.send_error(
                message.from_agent,
                "conversation_text and user_id are required",
                message.request_id,
            )
            return

        try:
            extracted_facts = await self._extract_facts_from_conversation(
                conversation_text, user_id
            )
            await self.send_capability_response(
                message.from_agent,
                {"extracted_facts": extracted_facts, "count": len(extracted_facts)},
                message.request_id,
                message.id,
            )
        except Exception as exc:
            await self.send_error(message.from_agent, str(exc), message.request_id)

    # ------------------------------------------------------------------
    # search_facts
    # ------------------------------------------------------------------

    async def _handle_search_facts(
        self, message: Message, data: Dict[str, Any], user_id: Optional[int]
    ) -> None:
        query = data.get("prompt", "")
        limit = data.get("limit", 10)

        if not query:
            await self.send_error(
                message.from_agent,
                "No query provided for search",
                message.request_id,
            )
            return

        try:
            fact_results = []
            vault_results = []

            # Search markdown vault (no user scoping needed — it's the user's vault)
            if self.markdown_memory:
                vault_hits = await self.markdown_memory.recall(query, top_k=limit)
                vault_results = [
                    {
                        "text": h.get("content", ""),
                        "category": h.get("category", ""),
                        "source": "vault",
                        "score": h.get("score", 0),
                    }
                    for h in vault_hits
                ]

            # Search structured facts
            if user_id is not None:
                facts = self.fact_service.search_facts(user_id, query, limit=limit)
                fact_results = [
                    {
                        "id": f.id,
                        "text": f.fact_text,
                        "category": f.category,
                        "entity": f.entity,
                        "confidence": f.confidence,
                    }
                    for f in facts
                ]

            all_results = fact_results + vault_results
            response_text = (
                f"Found {len(all_results)} results matching '{query}'."
                if all_results
                else f"No results found matching '{query}'."
            )

            await self.send_capability_response(
                message.from_agent,
                {
                    "response": response_text,
                    "facts": fact_results,
                    "vault_results": vault_results,
                    "count": len(all_results),
                },
                message.request_id,
                message.id,
            )
        except Exception as exc:
            await self.send_error(message.from_agent, str(exc), message.request_id)

    # ------------------------------------------------------------------
    # recall_from_memory
    # ------------------------------------------------------------------

    async def _handle_recall(
        self, message: Message, data: Dict[str, Any], user_id: Optional[int]
    ) -> None:
        query = data.get("prompt", "")
        top_k = data.get("top_k", 5)

        if not query:
            await self.send_error(
                message.from_agent,
                "No query provided for recall",
                message.request_id,
            )
            return

        try:
            all_results: List[Dict[str, Any]] = []

            # --- Primary: markdown vault search ---
            if self.markdown_memory:
                vault_hits = await self.markdown_memory.recall(query, top_k=top_k)
                for hit in vault_hits:
                    all_results.append(
                        {
                            "text": hit.get("content", ""),
                            "metadata": {
                                "category": hit.get("category", ""),
                                "source": "vault",
                                "date": hit.get("date", ""),
                            },
                        }
                    )

            # --- Secondary: vector memory search ---
            if self.vector_memory:
                enhanced_query = await self._enhance_recall_query(query)
                vec_results = await self.vector_memory.similarity_search(
                    enhanced_query, top_k=top_k, user_id=user_id
                )
                all_results.extend(vec_results)

            # --- Tertiary: structured facts ---
            if user_id is not None:
                facts = self.fact_service.search_facts(user_id, query, limit=top_k)
                for f in facts:
                    all_results.append(
                        {
                            "text": f.fact_text,
                            "metadata": {
                                "category": f.category,
                                "entity": f.entity,
                                "type": "fact",
                            },
                        }
                    )

            # Deduplicate by content
            seen = set()
            unique: List[Dict[str, Any]] = []
            for r in all_results:
                txt = r.get("text", "").strip().lower()
                if txt and txt not in seen:
                    seen.add(txt)
                    unique.append(r)

            # Rank and summarise
            filtered = await self._filter_and_rank_results(unique, query)
            summary = await self._summarize_results(filtered, query)

            await self.send_capability_response(
                message.from_agent,
                {
                    "response": summary,
                    "memories_found": len(filtered) if filtered else 0,
                },
                message.request_id,
                message.id,
            )
        except Exception as exc:
            await self.send_error(message.from_agent, str(exc), message.request_id)

    # ------------------------------------------------------------------
    # browse_memories (NEW)
    # ------------------------------------------------------------------

    async def _handle_browse_memories(
        self, message: Message, data: Dict[str, Any], user_id: Optional[int]
    ) -> None:
        try:
            if not self.markdown_memory:
                await self.send_capability_response(
                    message.from_agent,
                    {"response": "Markdown vault is not configured.", "overview": {}},
                    message.request_id,
                    message.id,
                )
                return

            overview = await self.markdown_memory.browse_vault()

            # Build human-readable summary
            st_count = sum(v["entries"] for v in overview["short_term"].values())
            lt_count = sum(v["entries"] for v in overview["long_term"].values())
            cust_count = sum(v["entries"] for v in overview["custom"].values())

            parts = [
                f"Short-term: {st_count} entries across {len(overview['short_term'])} daily logs.",
                f"Long-term: {lt_count} entries across {len(overview['long_term'])} categories.",
            ]
            if cust_count:
                parts.append(
                    f"Custom: {cust_count} entries across {len(overview['custom'])} files."
                )

            await self.send_capability_response(
                message.from_agent,
                {"response": " ".join(parts), "overview": overview},
                message.request_id,
                message.id,
            )
        except Exception as exc:
            await self.send_error(message.from_agent, str(exc), message.request_id)

    # ------------------------------------------------------------------
    # consolidate_memories (NEW)
    # ------------------------------------------------------------------

    async def _handle_consolidate_memories(
        self, message: Message, data: Dict[str, Any], user_id: Optional[int]
    ) -> None:
        category = data.get("category", "personal")

        try:
            if not self.markdown_memory:
                await self.send_error(
                    message.from_agent,
                    "Markdown vault is not configured.",
                    message.request_id,
                )
                return

            result = await self.markdown_memory.consolidate(
                category, ai_client=self.ai_client
            )

            response = (
                f"Consolidated '{category}': {result['original_count']} entries -> "
                f"{result['consolidated']}. "
                f"Removed {result['removed_duplicates']} duplicates."
            )

            await self.send_capability_response(
                message.from_agent,
                {"response": response, **result},
                message.request_id,
                message.id,
            )
        except Exception as exc:
            await self.send_error(message.from_agent, str(exc), message.request_id)

    # ------------------------------------------------------------------
    # promote_memory (NEW)
    # ------------------------------------------------------------------

    async def _handle_promote_memory(
        self, message: Message, data: Dict[str, Any], user_id: Optional[int]
    ) -> None:
        memory_id = data.get("memory_id", "")
        target_category = data.get("category")
        section = data.get("section")

        if not memory_id:
            await self.send_error(
                message.from_agent,
                "memory_id is required",
                message.request_id,
            )
            return

        try:
            if not self.markdown_memory:
                await self.send_error(
                    message.from_agent,
                    "Markdown vault is not configured.",
                    message.request_id,
                )
                return

            success = await self.markdown_memory.promote(
                memory_id, target_category, section
            )

            if success:
                response = f"Memory {memory_id} promoted to long-term storage."
            else:
                response = f"Could not find memory {memory_id} in short-term logs."

            await self.send_capability_response(
                message.from_agent,
                {"response": response, "success": success},
                message.request_id,
                message.id,
            )
        except Exception as exc:
            await self.send_error(message.from_agent, str(exc), message.request_id)

    # ------------------------------------------------------------------
    # memory_stats (NEW)
    # ------------------------------------------------------------------

    async def _handle_memory_stats(
        self, message: Message, data: Dict[str, Any], user_id: Optional[int]
    ) -> None:
        try:
            stats: Dict[str, Any] = {}

            if self.markdown_memory:
                stats = await self.markdown_memory.get_stats()

            if user_id is not None:
                try:
                    fact_summary = self.fact_service.get_user_summary(user_id)
                    stats["fact_summary"] = fact_summary
                except Exception:
                    pass

            response = (
                f"Vault: {stats.get('total_entries', 0)} total entries "
                f"({stats.get('short_term_entries', 0)} short-term, "
                f"{stats.get('long_term_entries', 0)} long-term). "
                f"{stats.get('topic_count', 0)} topics indexed."
            )

            await self.send_capability_response(
                message.from_agent,
                {"response": response, "stats": stats},
                message.request_id,
                message.id,
            )
        except Exception as exc:
            await self.send_error(message.from_agent, str(exc), message.request_id)

    # ------------------------------------------------------------------
    # AI helper methods (kept for backward compat and enhancement)
    # ------------------------------------------------------------------

    async def _generate_memory_confirmation(
        self, content: str, metadata: Dict[str, Any]
    ) -> str:
        """Generate a confirmation response for stored memories."""
        if not self.ai_client:
            return f"I've remembered that: {content}"

        category = metadata.get("category", "information")
        topics = metadata.get("topics", "")

        prompt = f"""The user asked me to remember: "{content}"

    I've successfully stored this memory with the following details:
    - Category: {category}
    - Topics: {topics}

    Generate a brief, natural confirmation response that:
    - Confirms I've remembered the information
    - Shows understanding of what was stored
    - Uses a conversational tone
    - Keep it concise (1-2 sentences)

    Example responses:
    - "Got it! I've noted that your favorite cookies are Insomnia Cookies."
    - "Remembered! I've stored that preference about Insomnia Cookies for you."
    - "Perfect, I've made a note that Insomnia Cookies are your go-to favorite."

    Generate a similar confirmation response:"""

        try:
            response, _ = await self.ai_client.weak_chat(
                [{"role": "user", "content": prompt}],
                [],
            )
            return response.content.strip()
        except Exception as exc:
            if self.logger:
                self.logger.log(
                    "WARNING", "Memory confirmation generation failed", str(exc)
                )
            return f"I've remembered: {content}"

    async def _generate_enhanced_metadata(
        self, content: str, base_metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Use AI to generate rich metadata for better recall."""
        if not self.ai_client:
            return self._sanitize_metadata(base_metadata)

        prompt = f"""Analyze this memory content and generate structured metadata to help with future recall:

Content: "{content}"

Generate metadata in the following categories:
1. Topics: Main subjects/themes (max 5 keywords)
2. Entities: People, places, organizations mentioned
3. Actions: What actions or events are described
4. Context: When/where/why this might be relevant
5. Intent: What the user might want to recall this for
6. Emotional_tone: The mood or sentiment
7. Urgency: How time-sensitive this information is (low/medium/high)
8. Category: General category (personal, work, learning, reminder, etc.)

Respond in JSON format only:
{{
    "topics": ["keyword1", "keyword2"],
    "entities": ["entity1", "entity2"],
    "actions": ["action1", "action2"],
    "context": "brief context description",
    "intent": "likely recall scenarios",
    "emotional_tone": "tone description",
    "urgency": "low/medium/high",
    "category": "category name"
}}"""

        try:
            response, _ = await self.ai_client.weak_chat(
                [{"role": "user", "content": prompt}],
                [],
            )

            ai_metadata = json.loads(response.content.strip())
            ai_metadata = self._sanitize_metadata(ai_metadata)

            enhanced_metadata = {
                **self._sanitize_metadata(base_metadata),
                **ai_metadata,
            }

            enhanced_metadata.update(
                {
                    "stored_at": datetime.datetime.now().isoformat(),
                    "content_length": len(content),
                    "ai_enhanced": "true",
                }
            )

            return enhanced_metadata

        except Exception as exc:
            if self.logger:
                self.logger.log("WARNING", "AI metadata generation failed", str(exc))
            return {**self._sanitize_metadata(base_metadata), "ai_enhanced": "false"}

    async def _enhance_recall_query(self, original_query: str) -> str:
        """Use AI to enhance the recall query with related terms and concepts."""
        if not self.ai_client:
            return original_query

        prompt = f"""Enhance this memory recall query to find more relevant results:

Original query: "{original_query}"

Generate an enhanced query that includes:
1. Synonyms and related terms
2. Different ways the concept might be expressed
3. Context that might be associated with this topic

Respond with just the enhanced query text (no explanations):"""

        try:
            response, _ = await self.ai_client.weak_chat(
                [{"role": "user", "content": prompt}],
                [],
            )

            enhanced = response.content.strip()
            return f"{original_query} {enhanced}"

        except Exception as exc:
            if self.logger:
                self.logger.log("WARNING", "Query enhancement failed", str(exc))
            return original_query

    async def _filter_and_rank_results(
        self, results: list[Dict[str, Any]], original_query: str
    ) -> list[Dict[str, Any]]:
        """Use AI to filter and rank results by relevance to the original query."""
        if not results or not self.ai_client:
            return results

        results_text = ""
        for i, result in enumerate(results):
            metadata = result.get("metadata", {})
            results_text += f"\nResult {i+1}:\nContent: {result.get('text', '')}\n"
            results_text += f"Topics: {metadata.get('topics', '')}\n"
            results_text += f"Category: {metadata.get('category', 'unknown')}\n"
            results_text += f"Context: {metadata.get('context', '')}\n---"

        prompt = f"""Given this user query: "{original_query}"

Rank these memory results by relevance (1 being most relevant). Consider:
- Direct content match
- Topical relevance
- Contextual appropriateness
- Likely user intent

Results to rank:
{results_text}

Respond with just the result numbers in order of relevance (e.g., "3,1,5,2,4"):"""

        try:
            response, _ = await self.ai_client.weak_chat(
                [{"role": "user", "content": prompt}],
                [],
            )

            ranking = [int(x.strip()) - 1 for x in response.content.strip().split(",")]

            reordered = []
            for idx in ranking:
                if 0 <= idx < len(results):
                    reordered.append(results[idx])

            ranked_indices = set(ranking)
            for i, result in enumerate(results):
                if i not in ranked_indices:
                    reordered.append(result)

            return reordered[:3]

        except Exception as exc:
            if self.logger:
                self.logger.log("WARNING", "Result filtering failed", str(exc))
            return results[:3]

    async def _summarize_results(
        self, results: list[Dict[str, Any]] | None, query: str
    ) -> str:
        """Summarize memory search results using the attached AI client with query context."""
        if not results:
            return "I couldn't recall anything matching that, sir."

        memory_context = []
        for i, r in enumerate(results):
            text = r.get("text", "")
            metadata = r.get("metadata", {})
            context_info = f"Category: {metadata.get('category', 'unknown')}, Context: {metadata.get('context', '')}"
            memory_context.append(f"{i+1}. {text}\n   [{context_info}]")

        memory_lines = "\n".join(memory_context)

        if not self.ai_client:
            return memory_lines

        prompt = f"""The user asked to recall: '{query}'

Based on this request, provide a helpful response using these relevant memories:

{memory_lines}

Instructions:
- Directly address what the user was looking for
- Synthesize information from multiple memories if relevant
- Use a natural, conversational tone
- If the memories contain actionable information, highlight it
- Keep the response concise but comprehensive"""

        try:
            msg, _ = await self.ai_client.weak_chat(
                [{"role": "user", "content": prompt}],
                [],
            )
            return msg.content
        except Exception as exc:
            if self.logger:
                self.logger.log("ERROR", "Memory summary failed", str(exc))
            return memory_lines

    async def _extract_facts_from_conversation(
        self, conversation_text: str, user_id: int
    ) -> List[Dict[str, Any]]:
        """Use AI to extract structured facts from conversation text."""
        if not self.ai_client:
            return []

        prompt = f"""Analyze this conversation and extract specific facts about the user:

Conversation:
{conversation_text}

Extract facts that represent:
1. Personal information (name, age, location, occupation, etc.)
2. Preferences (likes, dislikes, favorite things)
3. Relationships (family, friends, colleagues mentioned)
4. Important memories or experiences
5. Skills, hobbies, or interests
6. Goals or plans

For each fact, provide:
- fact_text: The fact as a clear statement
- category: personal_info, preference, relationship, memory, skill, goal
- entity: What/who the fact is about (if applicable)
- confidence: 0.0 to 1.0 based on certainty

Respond ONLY with a JSON array of fact objects:
[
    {{
        "fact_text": "The user's name is Alice",
        "category": "personal_info",
        "entity": "user",
        "confidence": 1.0
    }},
    {{
        "fact_text": "Alice loves Italian food",
        "category": "preference",
        "entity": "food",
        "confidence": 0.9
    }}
]

If no facts can be extracted, return an empty array []."""

        try:
            response, _ = await self.ai_client.weak_chat(
                [{"role": "user", "content": prompt}], []
            )

            facts_json = json.loads(response.content.strip())
            if not isinstance(facts_json, list):
                return []

            stored_facts = []
            for fact_data in facts_json:
                try:
                    fact_id = self.fact_service.add_fact(
                        user_id=user_id,
                        fact_text=fact_data.get("fact_text", ""),
                        category=fact_data.get("category", "general"),
                        entity=fact_data.get("entity"),
                        confidence=float(fact_data.get("confidence", 0.8)),
                        source="extracted",
                        context="Extracted from conversation",
                    )

                    # Also store in markdown vault
                    if self.markdown_memory:
                        await self.markdown_memory.store(
                            content=fact_data.get("fact_text", ""),
                            category=fact_data.get("category", "general"),
                            tags=[fact_data.get("entity", "")],
                            source="extracted",
                            confidence=float(fact_data.get("confidence", 0.8)),
                        )

                    # Also store in vector memory
                    if self.vector_memory:
                        await self.vector_memory.add_memory(
                            fact_data.get("fact_text", ""),
                            {
                                "fact_id": fact_id,
                                "category": fact_data.get("category", "general"),
                                "entity": fact_data.get("entity"),
                                "type": "fact",
                                "source": "extracted",
                            },
                            user_id=user_id,
                        )

                    stored_facts.append(
                        {
                            "fact_id": fact_id,
                            "fact_text": fact_data.get("fact_text", ""),
                            "category": fact_data.get("category", "general"),
                        }
                    )
                except Exception as exc:
                    if self.logger:
                        self.logger.log(
                            "WARNING", "Failed to store extracted fact", str(exc)
                        )

            return stored_facts

        except Exception as exc:
            if self.logger:
                self.logger.log(
                    "ERROR", "Fact extraction from conversation failed", str(exc)
                )
            return []

    async def _handle_capability_response(self, message: Message) -> None:
        pass
