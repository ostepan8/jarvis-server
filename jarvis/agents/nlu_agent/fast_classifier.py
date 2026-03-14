"""Embedding-based fast-path classifier for NLU routing.

Uses the existing VectorMemoryService infrastructure (ChromaDB + OpenAI
embeddings) to classify user inputs without an LLM call. At startup,
populates a ChromaDB collection with example phrases for each capability.
At request time, embeds the input, finds nearest capability, and returns
it if confidence exceeds the threshold.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from ...services.vector_memory import VectorMemoryService
from ...logging import JarvisLogger


# Training phrases for each capability — used to populate the embedding index.
CAPABILITY_TRAINING_PHRASES: Dict[str, List[str]] = {
    # ----- Lights -----
    "lights_on": [
        "turn on the lights",
        "lights on",
        "turn the lights on",
        "switch on the lights",
        "light up the room",
        "enable the lights",
    ],
    "lights_off": [
        "turn off the lights",
        "lights off",
        "turn the lights off",
        "switch off the lights",
        "kill the lights",
        "disable the lights",
    ],
    "lights_color": [
        "make the lights red",
        "change lights to blue",
        "set lights to green",
        "lights yellow",
        "make it purple",
        "change the color to orange",
        "set the light color",
        "make the lights warm",
    ],
    "lights_brightness": [
        "dim the lights",
        "brighten the lights",
        "set brightness to 50",
        "make the lights brighter",
        "make it dimmer",
        "turn down the lights",
        "set lights to max brightness",
    ],
    "lights_toggle": [
        "toggle the lights",
        "toggle lights",
        "flip the lights",
    ],
    "lights_list": [
        "list all lights",
        "show me the lights",
        "what lights do I have",
        "how many lights",
    ],
    "lights_status": [
        "lights status",
        "are the lights on",
        "light status",
        "what's the light status",
    ],
    # ----- Roku / TV -----
    "roku_pause": [
        "pause the tv",
        "pause playback",
        "stop the video",
        "pause what's playing",
    ],
    "roku_play": [
        "play the tv",
        "resume playback",
        "press play",
        "unpause the tv",
    ],
    "roku_volume_up": [
        "turn up the volume",
        "volume up",
        "louder",
        "increase the volume",
        "make it louder",
    ],
    "roku_volume_down": [
        "turn down the volume",
        "volume down",
        "quieter",
        "decrease the volume",
    ],
    "roku_home": [
        "go to home on the tv",
        "press home on roku",
        "go home on tv",
    ],
    # ----- Calendar -----
    "get_all_events": [
        "show my calendar",
        "what's on my calendar",
        "list my events",
        "what do I have today",
        "show my schedule",
        "what's coming up",
    ],
    "get_next_event": [
        "what's my next meeting",
        "when's my next event",
        "next appointment",
        "what's next on my calendar",
    ],
    "schedule_appointment": [
        "schedule a meeting",
        "add an event",
        "create a calendar event",
        "book a meeting",
        "set up an appointment",
        "add to my calendar",
    ],
    # ----- Search -----
    "search": [
        "search for",
        "look up",
        "google",
        "find information about",
        "what is",
        "who is",
        "when did",
        "where is",
        "how many",
        "what's the capital of",
        "who wrote",
        "when was",
        "what year did",
        "what's the weather",
        "how's the weather",
        "what's the temperature",
        "is it cold outside",
        "is it raining",
        "weather in",
        "current weather",
        "weather forecast",
        "what's the forecast",
        "will it rain tomorrow",
    ],
    # ----- Memory -----
    "add_to_memory": [
        "remember that",
        "save this",
        "store this information",
        "keep in mind",
        "note that",
    ],
    "recall_from_memory": [
        "what do you remember about",
        "recall",
        "do you remember",
        "what did I tell you about",
    ],
    "store_fact": [
        "my favorite color is",
        "I like",
        "my name is",
        "remember my",
    ],
    "search_facts": [
        "what's my favorite",
        "what did I say about",
        "what do you know about me",
        "what's my",
    ],
    # ----- Chat -----
    "chat": [
        "hello",
        "hi",
        "how are you",
        "tell me a joke",
        "good morning",
        "thanks",
        "thank you",
        "what do you think about",
        "let's talk about",
        "hey jarvis",
    ],
    # ----- Canvas -----
    "get_courses": [
        "what courses am I taking",
        "show my courses",
        "list my classes",
    ],
    "get_comprehensive_homework": [
        "what homework do I have",
        "show my assignments",
        "what's due",
        "upcoming homework",
        "any assignments due",
    ],
    # ----- Device Monitor -----
    "device_status": [
        "how's my computer doing",
        "how is the machine doing",
        "check my system",
        "system status",
        "check CPU and memory usage",
        "is the disk almost full",
        "how much RAM is free",
        "what's my CPU at",
        "computer status",
        "how's the machine",
        "device status",
        "check my computer",
        "how's the cpu",
        "hows the cpu",
        "how's my ram",
        "hows my ram",
        "how much ram is being used",
        "how much memory is being used",
        "cpu usage",
        "ram usage",
        "memory usage",
        "disk usage",
        "how's my cpu doing",
        "how's my memory doing",
        "show cpu usage",
        "show ram usage",
        "show memory usage",
        "what's the cpu usage",
        "what's the memory usage",
        "what percent cpu",
        "what percent memory",
        "how much disk space is left",
        "how much storage do I have",
        "how's my disk",
        "how much cpu am I using",
    ],
    "device_diagnostics": [
        "what's eating all my RAM",
        "show top processes",
        "why is my computer slow",
        "what's using all the CPU",
        "diagnose my system",
        "what's hogging memory",
        "system diagnostics",
        "why is the fan so loud",
        "what's using so much memory",
        "what's using so much cpu",
        "why is my ram so high",
        "why is cpu usage high",
    ],
    "device_cleanup": [
        "clean up temp files",
        "free up disk space",
        "clear cache files",
        "clean up my computer",
        "delete temporary files",
        "reclaim disk space",
    ],
    "device_history": [
        "has CPU been high all day",
        "show memory trends",
        "what were thermals like overnight",
        "CPU history",
        "system performance over time",
        "memory usage trend",
        "temperature history",
    ],
    # ----- Capabilities -----
    "describe_capabilities": [
        "what can you do",
        "what can u do",
        "what are your capabilities",
        "help me understand what you do",
        "list your features",
        "show me what you can do",
        "what skills do you have",
        "what are you capable of",
        "tell me about yourself",
        "what do you do",
        "how can you help me",
        "what services do you offer",
        "features",
        "what things can you do",
        "what are you able to do",
        "help",
        "what can jarvis do",
        "what's available",
        "show capabilities",
        "capabilities list",
        "what functions do you have",
        "what stuff can you do",
        "show me your abilities",
        "what all can you do",
    ],
    "explain_capability": [
        "how does the calendar work",
        "explain the search feature",
        "tell me about the lighting system",
        "how do protocols work",
        "what can the todo agent do",
        "explain memory",
        "how does health monitoring work",
        "what is the device monitor",
        "how does roku control work",
        "tell me about the scheduler",
        "what can't you do",
        "what are your limitations",
        "how does jarvis work",
        "explain how you work",
        "what are you not able to do",
        "can you control my lights",
        "can you check my cpu",
        "can you manage my calendar",
        "are you able to search the web",
        "do you have a task manager",
    ],
    # ----- Health -----
    "system_health_check": [
        "is the system healthy",
        "health check",
        "what's down",
        "is everything running",
        "system health",
        "are all agents healthy",
        "any issues",
        "status check",
    ],
    "health_report": [
        "show health report",
        "health report",
        "full health report",
        "give me a health summary",
    ],
    "incident_list": [
        "list incidents",
        "show incidents",
        "any recent incidents",
        "what went wrong",
        "incident history",
    ],
    # ----- Notifications -----
    "send_notification": [
        "notify me",
        "send me a notification",
        "alert me",
        "send an alert",
        "ping me",
        "let me know",
        "send a notification",
        "push a notification",
        "remind me with a notification",
        "give me a heads up",
    ],
    "list_notifications": [
        "show my notifications",
        "what notifications did I get",
        "any notifications",
        "show recent alerts",
        "what did I miss",
        "notification history",
        "list my notifications",
        "recent notifications",
    ],
}


class FastPathClassifier:
    """Embedding-based fast-path classifier using ChromaDB.

    Confidence thresholds:
      - HIGH (>= 0.85): skip LLM entirely, route directly
      - MEDIUM (0.70 – 0.85): provide hint to LLM prompt
      - LOW (< 0.70): fall back to full LLM classification

    If the top-2 distinct capabilities are within 0.10 of each other,
    the input is ambiguous (possibly multi-capability) and we fall back.
    """

    HIGH_CONFIDENCE = 0.85
    MEDIUM_CONFIDENCE = 0.70
    MULTI_CAPABILITY_GAP = 0.10

    def __init__(
        self,
        vector_service: VectorMemoryService,
        logger: Optional[JarvisLogger] = None,
    ) -> None:
        self.logger = logger or JarvisLogger()
        self._vector_service = vector_service
        self._collection = vector_service.client.get_or_create_collection(
            name="capability_router",
            embedding_function=vector_service.embedding_function,
        )
        self._initialized = False

    async def initialize(
        self, training_phrases: Optional[Dict[str, List[str]]] = None
    ) -> None:
        """Populate the collection with training phrases.

        Detects stale collections by comparing the expected phrase count
        against what's stored.  If they differ (e.g. new capabilities were
        added), the collection is rebuilt automatically.
        """
        phrases = training_phrases or CAPABILITY_TRAINING_PHRASES

        expected_count = sum(len(v) for v in phrases.values())
        existing = await asyncio.to_thread(self._collection.count)

        if existing == expected_count:
            self.logger.log(
                "INFO",
                "FastPathClassifier already initialized",
                f"{existing} phrases in collection (up to date)",
            )
            self._initialized = True
            return

        # Collection is stale or empty — rebuild
        if existing > 0:
            self.logger.log(
                "INFO",
                "FastPathClassifier stale",
                f"Expected {expected_count} phrases, found {existing} — rebuilding",
            )
            await self.reinitialize(phrases)
            return

        ids: List[str] = []
        documents: List[str] = []
        metadatas: List[Dict[str, str]] = []
        for capability, phrase_list in phrases.items():
            for i, phrase in enumerate(phrase_list):
                ids.append(f"{capability}_{i}")
                documents.append(phrase)
                metadatas.append({"capability": capability})

        await asyncio.to_thread(
            self._collection.add,
            ids=ids,
            documents=documents,
            metadatas=metadatas,
        )
        self._initialized = True
        self.logger.log(
            "INFO",
            "FastPathClassifier initialized",
            f"Added {len(ids)} phrases for {len(phrases)} capabilities",
        )

    async def classify(self, user_input: str) -> Dict[str, Any]:
        """Classify user input using embedding similarity.

        Returns:
            {
                "confidence": "high" | "medium" | "low",
                "capability": str | None,
                "score": float,
                "hint_capabilities": list[str],  # for medium confidence
            }
        """
        if not self._initialized:
            return {"confidence": "low", "capability": None, "score": 0.0}

        result = await asyncio.to_thread(
            self._collection.query,
            query_texts=[user_input],
            n_results=5,
        )

        if (
            not result
            or not result.get("distances")
            or not result["distances"][0]
        ):
            return {"confidence": "low", "capability": None, "score": 0.0}

        distances = result["distances"][0]
        metadatas = result["metadatas"][0]

        # ChromaDB returns L2 distances. Convert to similarity score:
        # For normalized embeddings, similarity ~= 1 - (distance / 2)
        scores = [max(0.0, 1.0 - (d / 2.0)) for d in distances]

        top_score = scores[0]
        top_capability = metadatas[0]["capability"]

        # Gather unique capabilities with their best scores
        unique_capabilities: List[tuple[str, float]] = []
        seen: set[str] = set()
        for i, meta in enumerate(metadatas):
            cap = meta["capability"]
            if cap not in seen:
                unique_capabilities.append((cap, scores[i]))
                seen.add(cap)

        # If top-2 distinct capabilities are very close → ambiguous
        if len(unique_capabilities) >= 2:
            gap = unique_capabilities[0][1] - unique_capabilities[1][1]
            if (
                gap < self.MULTI_CAPABILITY_GAP
                and unique_capabilities[0][1] > self.MEDIUM_CONFIDENCE
            ):
                return {
                    "confidence": "low",
                    "capability": None,
                    "score": top_score,
                    "hint_capabilities": [c for c, _ in unique_capabilities[:3]],
                }

        if top_score >= self.HIGH_CONFIDENCE:
            return {
                "confidence": "high",
                "capability": top_capability,
                "score": top_score,
            }
        elif top_score >= self.MEDIUM_CONFIDENCE:
            return {
                "confidence": "medium",
                "capability": top_capability,
                "score": top_score,
                "hint_capabilities": [c for c, _ in unique_capabilities[:2]],
            }
        else:
            return {
                "confidence": "low",
                "capability": None,
                "score": top_score,
            }

    async def reinitialize(
        self, training_phrases: Optional[Dict[str, List[str]]] = None
    ) -> None:
        """Force re-initialization (deletes and recreates collection)."""
        await asyncio.to_thread(
            self._vector_service.client.delete_collection, "capability_router"
        )
        self._collection = self._vector_service.client.get_or_create_collection(
            name="capability_router",
            embedding_function=self._vector_service.embedding_function,
        )
        self._initialized = False
        await self.initialize(training_phrases)
