from __future__ import annotations

import random
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Set, List, Tuple
from dataclasses import dataclass, asdict
from enum import Enum

from ..base import NetworkAgent
from ..message import Message
from ...ai_clients.base import BaseAIClient
from ...logger import JarvisLogger
from ...profile import AgentProfile


class PersonalityMode(Enum):
    """Enhanced personality modes with rich characteristics."""

    FRIENDLY = "friendly"
    WITTY = "witty"
    SERIOUS = "serious"
    PLAYFUL = "playful"
    PHILOSOPHICAL = "philosophical"
    SARCASTIC = "sarcastic"
    CREATIVE = "creative"
    ANALYTICAL = "analytical"
    EMPATHETIC = "empathetic"
    ENTHUSIASTIC = "enthusiastic"


@dataclass
class ConversationContext:
    """Rich conversation context with metadata."""

    timestamp: str
    user_message: str
    assistant_response: str = ""
    mood: str = "friendly"
    topic: str = ""
    sentiment: str = "neutral"
    user_preferences: Dict[str, Any] = None
    session_id: str = ""

    def __post_init__(self):
        if self.user_preferences is None:
            self.user_preferences = {}


class GameState:
    """Manages active game states and progress."""

    def __init__(self):
        self.active_games: Dict[str, Dict[str, Any]] = {}
        self.game_history: List[Dict[str, Any]] = []

    def start_game(self, game_type: str, **kwargs) -> str:
        """Start a new game and return game ID."""
        game_id = f"{game_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.active_games[game_id] = {
            "type": game_type,
            "started_at": datetime.now().isoformat(),
            "state": kwargs,
            "moves": [],
            "score": 0,
        }
        return game_id

    def update_game(self, game_id: str, move: str, score_change: int = 0) -> bool:
        """Update game state with new move."""
        if game_id in self.active_games:
            self.active_games[game_id]["moves"].append(
                {"move": move, "timestamp": datetime.now().isoformat()}
            )
            self.active_games[game_id]["score"] += score_change
            return True
        return False

    def end_game(self, game_id: str) -> Dict[str, Any]:
        """End a game and move to history."""
        if game_id in self.active_games:
            game_data = self.active_games.pop(game_id)
            game_data["ended_at"] = datetime.now().isoformat()
            self.game_history.append(game_data)
            return game_data
        return {}


class ChatAgent(NetworkAgent):
    """
    Next-generation conversational agent with:
    - Advanced personality system with 10+ modes
    - Comprehensive memory integration with semantic search
    - Intelligent user profiling and preference learning
    - Interactive game management with persistent state
    - Context-aware responses with sentiment analysis
    - Creative content generation with user collaboration
    - Proactive conversation enhancement
    """

    def __init__(
        self,
        ai_client: BaseAIClient,
        logger: Optional[JarvisLogger] = None,
        max_context_length: int = 20,
        memory_threshold: float = 0.7,
    ) -> None:
        super().__init__(
            name="ChatAgent",
            logger=logger,
            memory=None,
            profile=AgentProfile(),
        )
        self.ai_client = ai_client
        # Aliases for backwards compatibility with older code
        self.user_profile = self.profile
        self.max_context_length = max_context_length
        self.memory_threshold = memory_threshold

        # Enhanced conversation management
        self.conversation_history: List[ConversationContext] = []
        self.current_session_id = self._generate_session_id()
        self.current_personality = PersonalityMode.FRIENDLY

        # Game and interaction management
        self.game_manager = GameState()
        self.active_topics: List[str] = []
        self.conversation_metrics = {
            "total_interactions": 0,
            "session_start": datetime.now(),
            "topics_discussed": set(),
            "personality_changes": 0,
            "games_played": 0,
            "stories_created": 0,
            "jokes_told": 0,
        }

        # Enhanced function mapping with categories
        self.function_map = {
            # Core conversation
            "chat": self._handle_chat,
            "continue_conversation": self._continue_conversation,
            # Entertainment & Games
            "tell_joke": self._tell_joke,
            "create_story": self._create_story,
            "play_game": self._play_game,
            "continue_game": self._continue_game,
            "riddle": self._create_riddle,
            "trivia": self._trivia_question,
            "would_you_rather": self._would_you_rather,
            # Personal & Social
            "give_advice": self._give_advice,
            "compliment": self._give_compliment,
            "motivate": self._motivate_user,
            "mood_check": self._mood_check,
            "personality_test": self._personality_test,
            # Creative & Intellectual
            "debate": self._start_debate,
            "random_fact": self._random_fact,
            "philosophical_discussion": self._philosophical_discussion,
            "brainstorm": self._brainstorm_session,
            # Memory & Context
            "get_conversation_summary": self._get_conversation_summary,
            # Personality & Customization
            "change_personality": self._change_personality,
            "get_personality_info": self._get_personality_info,
            "customize_experience": self._customize_experience,
            # Analytics & Insights
            "conversation_analytics": self._get_conversation_analytics,
            "suggest_activities": self._suggest_activities,
            "get_user_insights": self._get_user_insights,
        }

        # Initialize personality characteristics
        self.personality_traits = self._initialize_personality_system()

    def _generate_session_id(self) -> str:
        """Generate unique session identifier."""
        return f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{random.randint(1000, 9999)}"

    def _initialize_personality_system(self) -> Dict[PersonalityMode, Dict[str, Any]]:
        """Initialize comprehensive personality system."""
        return {
            PersonalityMode.FRIENDLY: {
                "description": "Warm, welcoming, and supportive",
                "traits": ["encouraging", "patient", "helpful"],
                "response_style": "conversational and caring",
                "humor_level": "light and wholesome",
            },
            PersonalityMode.WITTY: {
                "description": "Sharp, clever, and quick with wordplay",
                "traits": ["clever", "sharp", "humorous"],
                "response_style": "snappy and entertaining",
                "humor_level": "clever and witty",
            },
            PersonalityMode.SERIOUS: {
                "description": "Professional, focused, and analytical",
                "traits": ["precise", "thoughtful", "professional"],
                "response_style": "formal and informative",
                "humor_level": "minimal and dry",
            },
            PersonalityMode.PLAYFUL: {
                "description": "Energetic, fun, and enthusiastic",
                "traits": ["energetic", "enthusiastic", "fun-loving"],
                "response_style": "excited and engaging",
                "humor_level": "silly and fun",
            },
            PersonalityMode.PHILOSOPHICAL: {
                "description": "Contemplative, deep, and thought-provoking",
                "traits": ["contemplative", "wise", "introspective"],
                "response_style": "thoughtful and profound",
                "humor_level": "subtle and intellectual",
            },
            PersonalityMode.SARCASTIC: {
                "description": "Dry, ironic, and cleverly critical",
                "traits": ["ironic", "sharp", "observant"],
                "response_style": "dry and pointed",
                "humor_level": "sarcastic but not mean",
            },
            PersonalityMode.CREATIVE: {
                "description": "Imaginative, artistic, and innovative",
                "traits": ["imaginative", "artistic", "innovative"],
                "response_style": "creative and inspiring",
                "humor_level": "whimsical and creative",
            },
            PersonalityMode.ANALYTICAL: {
                "description": "Logical, systematic, and detail-oriented",
                "traits": ["logical", "systematic", "precise"],
                "response_style": "structured and thorough",
                "humor_level": "logical and nerdy",
            },
            PersonalityMode.EMPATHETIC: {
                "description": "Understanding, compassionate, and emotionally aware",
                "traits": ["understanding", "compassionate", "intuitive"],
                "response_style": "caring and emotionally intelligent",
                "humor_level": "gentle and understanding",
            },
            PersonalityMode.ENTHUSIASTIC: {
                "description": "Passionate, energetic, and motivating",
                "traits": ["passionate", "energetic", "inspiring"],
                "response_style": "excited and motivational",
                "humor_level": "upbeat and encouraging",
            },
        }

    @property
    def description(self) -> str:
        return f"Next-generation conversational agent with advanced personality system, memory integration, and interactive capabilities. Currently in {self.current_personality.value} mode."

    @property
    def capabilities(self) -> Set[str]:
        """Return comprehensive capabilities set."""
        return set(self.function_map.keys())

    async def _handle_capability_request(self, message: Message) -> None:
        """Enhanced capability request handling with context awareness."""
        capability = message.content.get("capability")
        data = message.content.get("data", {})

        self.logger.log("INFO", f"ChatAgent received capability request: {capability}")

        # Update interaction metrics
        self.conversation_metrics["total_interactions"] += 1

        try:
            if capability in self.function_map:
                user_input = data.get("message", data.get("prompt", ""))

                # Add context awareness
                context = await self._analyze_context(user_input)
                result = await self.function_map[capability](user_input, context)

                # Learn from interaction
                await self._learn_from_interaction(capability, user_input, result)
            else:
                # Handle unknown capability with suggestions
                result = await self._handle_unknown_capability(capability, data)

            await self.send_capability_response(
                message.from_agent, result, message.request_id, message.id
            )

        except Exception as exc:
            self.logger.log("ERROR", f"ChatAgent error handling {capability}", str(exc))
            error_response = await self._generate_error_response(capability, str(exc))
            await self.send_error(
                message.from_agent, error_response, message.request_id
            )

    async def _handle_capability_response(self, message: Message) -> None:
        """Handle responses from capabilities this agent invoked."""
        self.logger.log(
            "INFO",
            "ChatAgent received capability response",
            message.content,
        )
        task = self.active_tasks.get(message.request_id)
        if task is not None:
            task.setdefault("responses", []).append(
                {
                    "from_agent": message.from_agent,
                    "content": message.content,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )

    async def _analyze_context(self, user_input: str) -> Dict[str, Any]:
        """Analyze conversation context and user intent."""
        context = {
            "session_id": self.current_session_id,
            "personality_mode": self.current_personality.value,
            "recent_topics": self.active_topics[-3:] if self.active_topics else [],
            "interaction_count": self.conversation_metrics["total_interactions"],
            "user_profile": asdict(self.user_profile),
            "recent_context": [asdict(ctx) for ctx in self.conversation_history[-3:]],
            "active_games": list(self.game_manager.active_games.keys()),
            "timestamp": datetime.now().isoformat(),
        }

        # Add memory context if available
        if user_input:
            try:
                relevant_memories = await self.search_memory(user_input, top_k=3)
                context["relevant_memories"] = relevant_memories
            except Exception as e:
                self.logger.log("WARNING", f"Memory search failed: {e}")
                context["relevant_memories"] = []

        return context

    async def _handle_chat(
        self, user_message: str, context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Enhanced chat handling with advanced context awareness and personalization."""
        if not user_message:
            return await self._generate_greeting_response()

        # Create conversation context
        conv_context = ConversationContext(
            timestamp=datetime.now().isoformat(),
            user_message=user_message,
            mood=self.current_personality.value,
            session_id=self.current_session_id,
            user_preferences=asdict(self.user_profile),
        )

        try:
            # Get enhanced system prompt
            system_prompt = await self._generate_dynamic_system_prompt(
                user_message, context
            )

            # Build conversation messages with rich context
            messages = await self._build_conversation_messages(
                system_prompt, user_message, context
            )

            # Generate response with AI
            response, _ = await self.ai_client.strong_chat(messages, [])

            # Post-process and enhance response
            enhanced_response = await self._enhance_response(
                response.content, user_message, context
            )

            # Update conversation context
            conv_context.assistant_response = enhanced_response
            conv_context.topic = await self._extract_topic(user_message)
            conv_context.sentiment = await self._analyze_sentiment(user_message)

            # Store in conversation history
            self.conversation_history.append(conv_context)
            await self._manage_conversation_history()

            # Store in vector memory via MemoryAgent
            await self._store_conversation_memory(conv_context)

            # Update user profile and preferences
            await self._update_user_profile(user_message, enhanced_response)

            # Check for proactive suggestions
            suggestions = await self._generate_proactive_suggestions(
                user_message, context
            )

            return {
                "response": enhanced_response,
                "suggestions": suggestions,
                "context": {
                    "personality": self.current_personality.value,
                    "topic": conv_context.topic,
                    "sentiment": conv_context.sentiment,
                    "session_id": self.current_session_id,
                },
            }

        except Exception as exc:
            self.logger.log("ERROR", f"Chat processing failed: {str(exc)}")
            return await self._generate_fallback_response(user_message)

    async def _generate_dynamic_system_prompt(
        self, user_message: str, context: Dict[str, Any]
    ) -> str:
        """Generate dynamic system prompt based on personality and context."""
        personality_info = self.personality_traits[self.current_personality]

        base_prompt = f"""You are JARVIS, an advanced AI assistant with a {personality_info['description']} personality.

PERSONALITY TRAITS: {', '.join(personality_info['traits'])}
RESPONSE STYLE: {personality_info['response_style']}
HUMOR LEVEL: {personality_info['humor_level']}

CONVERSATION CONTEXT:
- Current session: {context.get('session_id', 'new')}
- Total interactions: {context.get('interaction_count', 0)}
- Recent topics: {', '.join(context.get('recent_topics', []))}
- User preferences: {context.get('user_profile', {})}

RELEVANT MEMORIES:
{self._format_memory_context(context.get('relevant_memories', []))}

ACTIVE GAMES: {', '.join(context.get('active_games', []))}

INSTRUCTIONS:
1. Respond according to your {self.current_personality.value} personality
2. Reference relevant memories naturally when appropriate
3. Adapt to the user's conversation style and preferences
4. Offer engaging follow-up questions or activities
5. Be proactive in suggesting related capabilities when relevant
6. Maintain consistency with previous conversations
7. Show genuine interest and engagement

Remember: You're not just answering questions - you're creating an engaging, personalized conversation experience."""

        return base_prompt

    def _format_memory_context(self, memories: List[Dict[str, Any]]) -> str:
        """Format memory context for system prompt."""
        if not memories:
            return "No relevant memories found."

        formatted = []
        for i, memory in enumerate(memories, 1):
            similarity = memory.get("similarity", 0)
            text = (
                memory.get("text", "")[:200] + "..."
                if len(memory.get("text", "")) > 200
                else memory.get("text", "")
            )
            formatted.append(f"{i}. (Similarity: {similarity:.2f}) {text}")

        return "\n".join(formatted)

    async def _build_conversation_messages(
        self, system_prompt: str, user_message: str, context: Dict[str, Any]
    ) -> List[Dict[str, str]]:
        """Build conversation messages with appropriate context."""
        messages = [{"role": "system", "content": system_prompt}]

        # Add recent conversation history
        recent_history = context.get("recent_context", [])
        for ctx in recent_history:
            if ctx.get("user_message"):
                messages.append({"role": "user", "content": ctx["user_message"]})
            if ctx.get("assistant_response"):
                messages.append(
                    {"role": "assistant", "content": ctx["assistant_response"]}
                )

        # Add current message
        messages.append({"role": "user", "content": user_message})

        return messages

    async def _enhance_response(
        self, response: str, user_message: str, context: Dict[str, Any]
    ) -> str:
        """Enhance AI response with personalization and context."""
        # Add user name if known
        if self.user_profile.name:
            # Subtle name inclusion - not every response
            if random.random() < 0.3:  # 30% chance
                response = response.replace("you", f"you, {self.user_profile.name}", 1)

        # Add personality flourishes based on mode
        if self.current_personality == PersonalityMode.WITTY and random.random() < 0.4:
            witty_additions = ["😏", "🎭", "✨"]
            response += f" {random.choice(witty_additions)}"
        elif (
            self.current_personality == PersonalityMode.ENTHUSIASTIC
            and random.random() < 0.5
        ):
            enthusiastic_additions = ["🚀", "💫", "🎉", "⚡"]
            response += f" {random.choice(enthusiastic_additions)}"

        return response

    async def _extract_topic(self, message: str) -> str:
        """Extract main topic from user message."""
        # Simple topic extraction - could be enhanced with NLP
        topics = [
            "technology",
            "science",
            "art",
            "music",
            "books",
            "movies",
            "games",
            "sports",
            "food",
            "travel",
            "relationships",
            "work",
            "philosophy",
            "creativity",
            "humor",
        ]

        message_lower = message.lower()
        for topic in topics:
            if topic in message_lower:
                return topic

        return "general"

    async def _analyze_sentiment(self, message: str) -> str:
        """Analyze sentiment of user message."""
        # Simple sentiment analysis - could be enhanced with proper NLP
        positive_words = [
            "good",
            "great",
            "awesome",
            "amazing",
            "love",
            "like",
            "happy",
            "excited",
            "wonderful",
        ]
        negative_words = [
            "bad",
            "terrible",
            "awful",
            "hate",
            "sad",
            "angry",
            "frustrated",
            "disappointed",
        ]

        message_lower = message.lower()
        positive_count = sum(1 for word in positive_words if word in message_lower)
        negative_count = sum(1 for word in negative_words if word in message_lower)

        if positive_count > negative_count:
            return "positive"
        elif negative_count > positive_count:
            return "negative"
        else:
            return "neutral"

    async def _store_conversation_memory(
        self, conv_context: ConversationContext
    ) -> None:
        """Store conversation in vector memory with rich metadata."""
        try:
            memory_text = f"User: {conv_context.user_message}\nAssistant: {conv_context.assistant_response}"
            metadata = {
                "type": "conversation",
                "timestamp": conv_context.timestamp,
                "session_id": conv_context.session_id,
                "personality_mode": conv_context.mood,
                "topic": conv_context.topic or "general",
                "sentiment": conv_context.sentiment or "neutral",
                "user_name": self.user_profile.name or "unknown",
                "interaction_count": self.conversation_metrics["total_interactions"],
            }

            # Ensure all metadata values are strings, ints, or floats
            cleaned_metadata = {}
            for key, value in metadata.items():
                if value is None:
                    cleaned_metadata[key] = "unknown"
                elif isinstance(value, (str, int, float)):
                    cleaned_metadata[key] = value
                else:
                    cleaned_metadata[key] = str(value)

            await self.store_memory(memory_text, cleaned_metadata)

        except Exception as e:
            self.logger.log("WARNING", f"Failed to store conversation memory: {e}")

    async def _manage_conversation_history(self) -> None:
        """Manage conversation history length and cleanup."""
        if len(self.conversation_history) > self.max_context_length:
            # Keep important conversations and recent ones
            important_conversations = []
            recent_conversations = self.conversation_history[
                -10:
            ]  # Always keep last 10

            # Keep conversations with high engagement or important topics
            for conv in self.conversation_history[:-10]:
                if (
                    len(conv.user_message) > 100
                    or len(conv.assistant_response) > 200
                    or conv.topic in ["philosophy", "creativity", "relationships"]
                ):
                    important_conversations.append(conv)

            # Combine and sort by timestamp
            self.conversation_history = sorted(
                important_conversations + recent_conversations,
                key=lambda x: x.timestamp,
            )

    async def _update_user_profile(
        self, user_message: str, assistant_response: str
    ) -> None:
        """Update user profile based on interaction patterns."""
        self.user_profile.interaction_count += 1
        self.user_profile.last_seen = datetime.now().isoformat()

        # Learn interests from conversation
        interests_keywords = {
            "technology": ["ai", "computer", "programming", "tech", "software"],
            "science": ["physics", "chemistry", "biology", "research", "experiment"],
            "art": ["painting", "drawing", "sculpture", "artist", "creative"],
            "music": ["song", "music", "concert", "band", "musician"],
            "literature": ["book", "novel", "author", "writing", "story"],
            "philosophy": ["meaning", "existence", "truth", "ethics", "morality"],
            "humor": ["joke", "funny", "laugh", "comedy", "humor"],
        }

        message_lower = user_message.lower()
        for interest, keywords in interests_keywords.items():
            if any(keyword in message_lower for keyword in keywords):
                if interest not in self.user_profile.interests:
                    self.user_profile.interests.append(interest)

    async def _generate_proactive_suggestions(
        self, user_message: str, context: Dict[str, Any]
    ) -> List[str]:
        """Generate proactive suggestions for user engagement."""
        suggestions = []

        # Suggest games if user seems bored
        if any(
            word in user_message.lower()
            for word in ["bored", "nothing", "dunno", "whatever"]
        ):
            suggestions.append(
                "Want to play a game? I can do trivia, riddles, or word association!"
            )

        # Suggest personality change if conversation is getting stale
        if (
            self.conversation_metrics["total_interactions"] > 5
            and self.conversation_metrics["personality_changes"] == 0
        ):
            suggestions.append(
                "Want to try a different conversation style? I can be witty, philosophical, or playful!"
            )

        # Suggest creative activities
        if any(
            word in user_message.lower()
            for word in ["creative", "imagine", "story", "write"]
        ):
            suggestions.append(
                "Let's collaborate on a creative project! We could write a story together or brainstorm ideas."
            )

        # Suggest memory exploration
        if len(context.get("relevant_memories", [])) > 0:
            suggestions.append(
                "I found some related memories from our past conversations. Want to explore them?"
            )

        return suggestions[:2]  # Limit to 2 suggestions

    async def _generate_greeting_response(self) -> Dict[str, Any]:
        """Generate personalized greeting based on user profile and context."""
        greetings = {
            PersonalityMode.FRIENDLY: [
                "Hello! I'm here and ready to chat. What's on your mind today?",
                "Hi there! How are you doing? I'm excited to talk with you!",
                "Hey! Great to see you again. What would you like to explore today?",
            ],
            PersonalityMode.WITTY: [
                "Well, well, well... look who's decided to grace me with their presence! 😏",
                "Ah, my favorite human has arrived! Ready for some intellectual sparring?",
                "Hello there, sunshine! Ready to have your mind blown by my wit?",
            ],
            PersonalityMode.ENTHUSIASTIC: [
                "OH HEY THERE! 🎉 I'm SO excited you're here! What amazing adventure shall we embark on today?",
                "HELLO! ⚡ The energy is HIGH and I'm ready for anything! What's your vibe today?",
                "Hey there, superstar! 🌟 Ready to make today absolutely AMAZING?",
            ],
        }

        greeting_list = greetings.get(
            self.current_personality, greetings[PersonalityMode.FRIENDLY]
        )
        greeting = random.choice(greeting_list)

        # Add personalization if we know the user
        if self.user_profile.name:
            greeting = greeting.replace("there", f"there, {self.user_profile.name}")

        capabilities_hint = "I can chat, tell jokes, create stories, play games, give advice, and much more!"

        return {
            "response": f"{greeting}\n\n{capabilities_hint}",
            "suggestions": [
                "Tell me a joke",
                "Let's play a game",
                "Create a story with me",
                "Change your personality",
            ],
            "context": {
                "personality": self.current_personality.value,
                "session_id": self.current_session_id,
                "interaction_count": self.conversation_metrics["total_interactions"],
            },
        }

    async def _learn_user_preference(
        self, user_input: str, context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Learn and store user preferences."""
        if not user_input:
            return {
                "response": "What would you like me to remember about your preferences?"
            }

        # Parse preference
        preference_types = {
            "personality": ["personality", "mode", "style", "behavior"],
            "humor": ["humor", "jokes", "funny", "comedy"],
            "games": ["games", "play", "activities"],
            "topics": ["topics", "interests", "subjects"],
            "name": ["name", "call me", "i'm", "my name"],
        }

        user_lower = user_input.lower()

        # Extract name
        if any(phrase in user_lower for phrase in ["my name is", "call me", "i'm"]):
            import re

            name_match = re.search(r"(?:my name is|call me|i'm)\s+(\w+)", user_lower)
            if name_match:
                self.user_profile.name = name_match.group(1).title()
                return {
                    "response": f"Great to meet you, {self.user_profile.name}! I'll remember that."
                }

        # Store general preference
        await self._store_preference_memory(user_input)

        return {
            "response": "I've noted your preference! I'll use this to personalize our conversations."
        }

    async def _store_preference_memory(self, preference: str) -> None:
        """Store user preference in memory."""
        try:
            await self.store_memory(
                f"User preference: {preference}",
                {
                    "type": "preference",
                    "timestamp": datetime.now().isoformat(),
                    "session_id": self.current_session_id,
                    "user_name": self.user_profile.name,
                },
            )
        except Exception as e:
            self.logger.log("WARNING", f"Failed to store preference: {e}")

    async def _get_conversation_analytics(
        self, user_input: str = "", context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Provide comprehensive conversation analytics."""
        session_duration = datetime.now() - self.conversation_metrics["session_start"]

        analytics = {
            "session_info": {
                "session_id": self.current_session_id,
                "duration": str(session_duration),
                "total_interactions": self.conversation_metrics["total_interactions"],
                "current_personality": self.current_personality.value,
            },
            "conversation_stats": {
                "topics_discussed": len(self.conversation_metrics["topics_discussed"]),
                "personality_changes": self.conversation_metrics["personality_changes"],
                "games_played": self.conversation_metrics["games_played"],
                "stories_created": self.conversation_metrics["stories_created"],
                "jokes_told": self.conversation_metrics["jokes_told"],
            },
            "user_profile": {
                "name": self.user_profile.name,
                "interaction_count": self.user_profile.interaction_count,
                "interests": self.user_profile.interests,
                "preferred_personality": self.user_profile.preferred_personality,
            },
            "memory_stats": {},
        }

        return {
            "response": "Here's a comprehensive analysis of our conversation:",
            "analytics": analytics,
        }

    # Enhanced versions of existing methods with improved functionality

    async def _tell_joke(
        self, user_input: str = "", context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Enhanced joke telling with personalization and memory."""
        self.conversation_metrics["jokes_told"] += 1

        try:
            # Personalize joke based on user interests and personality
            personality_style = self.personality_traits[self.current_personality][
                "humor_level"
            ]
            user_interests = (
                ", ".join(self.user_profile.interests)
                if self.user_profile.interests
                else "general topics"
            )

            joke_prompt = f"""Generate a {personality_style} joke that's clean and appropriate.
            
            User request: "{user_input}"
            User interests: {user_interests}
            Personality style: {personality_style}
            
            Make it clever and fitting for the {self.current_personality.value} personality.
            Format: Just return the joke, nothing else."""

            messages = [{"role": "user", "content": joke_prompt}]
            response, _ = await self.ai_client.strong_chat(messages, [])

            # Store joke in memory
            try:
                await self.store_memory(
                    f"Joke told: {response.content}",
                    {
                        "type": "joke",
                        "personality": self.current_personality.value,
                        "user_request": user_input or "general",
                    },
                )
            except Exception as e:
                self.logger.log("WARNING", f"Failed to store joke memory: {e}")

            return {
                "response": f"Here's one for you: {response.content}",
                "suggestions": [
                    "Tell another joke",
                    "Change your humor style",
                    "Create a story instead",
                ],
            }

        except Exception as e:
            self.logger.log("ERROR", f"Joke generation failed: {e}")
            # Personality-based backup jokes
            backup_jokes = {
                PersonalityMode.WITTY: [
                    "I told my computer a joke about binary. It laughed in machine code: 01001000 01100001!",
                    "Why don't programmers like nature? It has too many bugs and not enough documentation.",
                ],
                PersonalityMode.SARCASTIC: [
                    "I'd tell you a UDP joke, but you might not get it.",
                    "There are only 10 types of people in the world: those who understand binary and those who don't.",
                ],
                PersonalityMode.FRIENDLY: [
                    "Why don't scientists trust atoms? Because they make up everything!",
                    "I told my wife she was drawing her eyebrows too high. She looked surprised.",
                ],
            }

            personality_jokes = backup_jokes.get(
                self.current_personality, backup_jokes[PersonalityMode.FRIENDLY]
            )
            return {"response": f"Here's a classic: {random.choice(personality_jokes)}"}

    async def _play_game(
        self, user_input: str = "", context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Enhanced game system with persistent state and variety."""
        self.conversation_metrics["games_played"] += 1

        available_games = {
            "20_questions": "I think of something, you guess with yes/no questions",
            "word_association": "We take turns saying related words",
            "story_building": "We create a story together, taking turns",
            "riddles": "I give you riddles to solve",
            "trivia": "Test your knowledge with questions",
            "would_you_rather": "Choose between interesting scenarios",
            "rhyme_time": "Create rhyming word pairs",
            "category_game": "Name items in a category as fast as you can",
        }

        if not user_input:
            games_list = "\n".join(
                [
                    f"• **{name.replace('_', ' ').title()}**: {desc}"
                    for name, desc in available_games.items()
                ]
            )
            return {
                "response": f"I can play several games with you!\n\n{games_list}\n\nWhich one sounds fun?",
                "suggestions": list(available_games.keys())[:4],
            }

        # Start specific game
        game_key = user_input.lower().replace(" ", "_")

        if "20" in user_input or "twenty" in user_input or "questions" in user_input:
            return await self._start_twenty_questions()
        elif "word" in user_input and "association" in user_input:
            return await self._start_word_association()
        elif "story" in user_input:
            return await self._start_story_building()
        elif "trivia" in user_input:
            return await self._trivia_question(user_input, context)
        else:
            return {
                "response": f"That sounds like a fun game! How do we play '{user_input}'? Or would you like to choose from my available games?",
                "suggestions": [
                    "20 questions",
                    "Word association",
                    "Story building",
                    "Trivia",
                ],
            }

    async def _start_twenty_questions(self) -> Dict[str, Any]:
        """Start a 20 questions game with persistent state."""
        categories = ["animal", "object", "person", "place", "concept"]
        category = random.choice(categories)

        # This would be expanded with actual answer generation
        game_id = self.game_manager.start_game(
            "20_questions", category=category, questions_left=20
        )

        return {
            "response": f"🎯 I'm thinking of a {category}! You have 20 yes/no questions to guess what it is. Fire away!",
            "game_state": {
                "game_id": game_id,
                "type": "20_questions",
                "questions_left": 20,
                "category": category,
            },
        }

    async def _start_word_association(self) -> Dict[str, Any]:
        """Start word association game."""
        starter_words = [
            "sunset",
            "ocean",
            "mountain",
            "music",
            "adventure",
            "creativity",
            "friendship",
            "discovery",
        ]
        word = random.choice(starter_words)

        game_id = self.game_manager.start_game(
            "word_association", current_word=word, turn=1
        )

        return {
            "response": f"🎭 Let's play word association! I'll start with: **{word}**\n\nWhat's the first word that comes to mind?",
            "game_state": {"game_id": game_id, "current_word": word, "turn": 1},
        }

    async def _start_story_building(self) -> Dict[str, Any]:
        """Start collaborative story building."""
        story_starters = [
            "In a world where dreams could be traded like currency, Maya discovered she was bankrupt.",
            "The last library on Earth was closing tomorrow, but tonight, the books were fighting back.",
            "Every morning at 7:47 AM, the same mysterious package appeared on Sarah's doorstep.",
            "The AI assistant had been acting strange lately, leaving cryptic messages in the smart home displays.",
        ]

        starter = random.choice(story_starters)
        game_id = self.game_manager.start_game(
            "story_building", story_text=starter, turn=1
        )

        return {
            "response": f"📚 Let's create a story together! I'll start:\n\n*{starter}*\n\nNow it's your turn - what happens next?",
            "game_state": {"game_id": game_id, "story_so_far": starter, "turn": 1},
        }

    async def _continue_conversation(
        self, user_input: str = "", context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Continue an ongoing conversation with enhanced context."""
        return await self._handle_chat(user_input, context)

    async def _continue_game(
        self, user_input: str = "", context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Continue an active game session."""
        if not self.game_manager.active_games:
            return {
                "response": "No active games found. Would you like to start a new game?"
            }

        # Get the most recent active game
        game_id = list(self.game_manager.active_games.keys())[-1]
        game = self.game_manager.active_games[game_id]

        if game["type"] == "20_questions":
            return await self._continue_twenty_questions(game_id, user_input)
        elif game["type"] == "word_association":
            return await self._continue_word_association(game_id, user_input)
        elif game["type"] == "story_building":
            return await self._continue_story_building(game_id, user_input)

        return {"response": f"Continuing {game['type']} game..."}

    async def _continue_twenty_questions(
        self, game_id: str, user_input: str
    ) -> Dict[str, Any]:
        """Continue 20 questions game."""
        game = self.game_manager.active_games[game_id]
        questions_left = game["state"].get("questions_left", 20)

        if questions_left <= 0:
            return {
                "response": "You've used all 20 questions! Want to make a final guess or start a new game?"
            }

        # Simple yes/no logic (would be enhanced with actual game logic)
        answer = random.choice(["Yes", "No", "Maybe", "Sort of"])
        questions_left -= 1

        self.game_manager.update_game(game_id, user_input)
        self.game_manager.active_games[game_id]["state"][
            "questions_left"
        ] = questions_left

        return {
            "response": f"{answer}! ({questions_left} questions remaining)",
            "game_state": {"questions_left": questions_left, "game_id": game_id},
        }

    async def _continue_word_association(
        self, game_id: str, user_input: str
    ) -> Dict[str, Any]:
        """Continue word association game."""
        if not user_input.strip():
            return {"response": "Please provide a word for our association game!"}

        # Generate associated word
        associations = {
            "sun": ["moon", "bright", "warm", "day"],
            "ocean": ["waves", "blue", "deep", "vast"],
            "music": ["harmony", "rhythm", "melody", "dance"],
            "forest": ["trees", "green", "nature", "peaceful"],
        }

        # Simple association logic
        word = user_input.strip().lower()
        if word in associations:
            next_word = random.choice(associations[word])
        else:
            # Generate creative association
            next_word = random.choice(
                ["adventure", "mystery", "beauty", "wonder", "energy"]
            )

        self.game_manager.update_game(game_id, f"{word} -> {next_word}")

        return {
            "response": f"**{word}** → **{next_word}**\n\nYour turn! What does '{next_word}' make you think of?",
            "game_state": {"current_word": next_word, "game_id": game_id},
        }

    async def _continue_story_building(
        self, game_id: str, user_input: str
    ) -> Dict[str, Any]:
        """Continue collaborative story building."""
        if not user_input.strip():
            return {"response": "Please add to our story!"}

        game = self.game_manager.active_games[game_id]
        current_story = game["state"].get("story_text", "")

        # Add user's contribution
        updated_story = f"{current_story}\n\n{user_input.strip()}"

        # Generate AI continuation
        try:
            story_prompt = f"Continue this collaborative story with 1-2 sentences. Keep it engaging and leave room for the user to continue:\n\n{updated_story}"
            messages = [{"role": "user", "content": story_prompt}]
            response, _ = await self.ai_client.strong_chat(messages, [])

            ai_addition = response.content
            updated_story = f"{updated_story}\n\n{ai_addition}"

        except Exception:
            ai_addition = (
                "The plot thickens as our characters face an unexpected twist..."
            )
            updated_story = f"{updated_story}\n\n{ai_addition}"

        # Update game state
        self.game_manager.active_games[game_id]["state"]["story_text"] = updated_story
        self.game_manager.update_game(
            game_id, f"User: {user_input} | AI: {ai_addition}"
        )

        return {
            "response": f"Great addition! Here's how I'd continue:\n\n*{ai_addition}*\n\nWhat happens next?",
            "game_state": {"story_so_far": updated_story, "game_id": game_id},
        }

    async def _philosophical_discussion(
        self, user_input: str = "", context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Engage in deep philosophical discussions."""
        if not user_input:
            topics = [
                "What is the nature of consciousness?",
                "Do we have free will or is everything predetermined?",
                "What makes life meaningful?",
                "Is there objective truth or is everything relative?",
                "What is the relationship between mind and reality?",
            ]
            return {
                "response": f"Let's explore some deep questions together! Here are some philosophical topics:\n\n"
                + "\n".join([f"• {topic}" for topic in topics])
                + "\n\nWhich resonates with you, or do you have another philosophical question?",
                "suggestions": topics[:3],
            }

        try:
            philosophy_prompt = f"""Engage in a thoughtful philosophical discussion about: "{user_input}"
            
            Provide a balanced, nuanced perspective that:
            - Considers multiple viewpoints
            - Asks probing questions
            - Encourages deeper thinking
            - Relates to human experience
            
            Be intellectually curious and engage with the complexity of the topic."""

            messages = [{"role": "user", "content": philosophy_prompt}]
            response, _ = await self.ai_client.strong_chat(messages, [])

            return {
                "response": response.content,
                "suggestions": [
                    "Explore another angle",
                    "Give me a different perspective",
                    "Ask a follow-up question",
                ],
            }

        except Exception:
            return {
                "response": f"That's a fascinating question about {user_input}. Philosophy often shows us that the most interesting questions don't have simple answers. What's your own perspective on this?"
            }

    async def _brainstorm_session(
        self, user_input: str = "", context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Collaborative brainstorming session."""
        if not user_input:
            return {
                "response": "Let's brainstorm together! What topic, problem, or creative challenge would you like to explore?",
                "suggestions": [
                    "Creative project ideas",
                    "Problem solving",
                    "Business ideas",
                    "Story concepts",
                ],
            }

        try:
            brainstorm_prompt = f"""Help brainstorm ideas for: "{user_input}"
            
            Provide 5-7 creative, diverse ideas that:
            - Are practical and actionable
            - Think outside the box
            - Build on each other
            - Spark further creativity
            
            Format as a bulleted list with brief explanations."""

            messages = [{"role": "user", "content": brainstorm_prompt}]
            response, _ = await self.ai_client.strong_chat(messages, [])

            return {
                "response": f"Great brainstorming topic! Here are some ideas:\n\n{response.content}\n\nWhich of these sparks your interest? Or shall we explore a different angle?",
                "suggestions": [
                    "Develop one idea further",
                    "Try a different approach",
                    "Combine ideas",
                ],
            }

        except Exception:
            return {
                "response": f"Interesting challenge: {user_input}. Let's think about this from different angles - what's the core goal here, and what constraints are we working with?"
            }

    async def _get_personality_info(
        self, user_input: str = "", context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Get detailed information about current personality."""
        current_traits = self.personality_traits[self.current_personality]

        info = f"""🎭 **Current Personality: {self.current_personality.value.title()}**

**Description:** {current_traits['description']}

**Key Traits:** {', '.join(current_traits['traits'])}

**Response Style:** {current_traits['response_style']}

**Humor Level:** {current_traits['humor_level']}

**Personality Changes This Session:** {self.conversation_metrics['personality_changes']}

**Your Preferred Personality:** {self.user_profile.preferred_personality}"""

        return {
            "response": info,
            "suggestions": [
                "Change personality",
                "See all personalities",
                "Adapt to my mood",
            ],
        }

    async def _customize_experience(
        self, user_input: str = "", context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Customize the conversation experience."""
        if not user_input:
            return {
                "response": """🎛️ **Customize Your Experience**

I can adapt to your preferences:

• **Personality Style**: Choose from 10 different personalities
• **Conversation Length**: Short & snappy or detailed & thorough  
• **Humor Level**: From serious to silly
• **Topics**: Focus on your areas of interest
• **Interaction Style**: Formal, casual, or somewhere in between

What would you like to customize?""",
                "suggestions": [
                    "Change personality",
                    "Set humor level",
                    "Choose topics",
                    "Interaction style",
                ],
            }

        # Process customization request
        customizations = {
            "formal": "I'll be more professional and structured",
            "casual": "I'll keep things relaxed and conversational",
            "detailed": "I'll provide thorough, comprehensive responses",
            "brief": "I'll keep my responses concise and to the point",
            "serious": "I'll minimize humor and focus on substance",
            "funny": "I'll amp up the humor and wordplay",
        }

        user_lower = user_input.lower()
        for key, message in customizations.items():
            if key in user_lower:
                return {"response": f"Got it! {message}. How does this feel?"}

        return {
            "response": f"I'd love to customize the experience for '{user_input}'. Can you be more specific about what you'd like me to adjust?",
            "suggestions": list(customizations.keys())[:4],
        }

    async def _suggest_activities(
        self, user_input: str = "", context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Suggest activities based on user profile and context."""
        suggestions = []

        # Based on user interests
        if "technology" in self.user_profile.interests:
            suggestions.append("🔬 Discuss the latest AI developments")
            suggestions.append("💻 Explore a programming concept")

        if "creativity" in self.user_profile.interests:
            suggestions.append("🎨 Collaborative story writing")
            suggestions.append("✨ Creative brainstorming session")

        # Based on conversation history
        if self.conversation_metrics["jokes_told"] < 2:
            suggestions.append("😄 Let me tell you a joke")

        if (
            not self.game_manager.active_games
            and self.conversation_metrics["games_played"] < 3
        ):
            suggestions.append("🎮 Play an interactive game")

        # Based on personality
        if self.current_personality == PersonalityMode.PHILOSOPHICAL:
            suggestions.append("🤔 Explore a philosophical question")

        if self.current_personality == PersonalityMode.CREATIVE:
            suggestions.append("🎭 Try a creative writing exercise")

        # Default suggestions
        if not suggestions:
            suggestions = [
                "🗣️ Have a deep conversation",
                "🎲 Play a fun game",
                "📚 Create a story together",
                "🧠 Solve a riddle",
                "🎪 Try a different personality",
            ]

        # Limit to 5 suggestions
        suggestions = suggestions[:5]

        activity_list = "\n".join([f"• {suggestion}" for suggestion in suggestions])

        return {
            "response": f"Based on our conversation and your interests, here are some activities we could try:\n\n{activity_list}\n\nWhat sounds appealing?",
            "suggestions": [
                s.split(" ", 1)[1] for s in suggestions[:3]
            ],  # Remove emoji for suggestions
        }

    async def _get_user_insights(
        self, user_input: str = "", context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Provide insights about user patterns and preferences."""
        insights = {
            "conversation_patterns": {
                "total_interactions": self.user_profile.interaction_count,
                "session_interactions": self.conversation_metrics["total_interactions"],
                "preferred_personality": self.user_profile.preferred_personality,
                "interests": self.user_profile.interests,
            },
            "engagement_metrics": {
                "games_played": self.conversation_metrics["games_played"],
                "stories_created": self.conversation_metrics["stories_created"],
                "jokes_requested": self.conversation_metrics["jokes_told"],
                "personality_experiments": self.conversation_metrics[
                    "personality_changes"
                ],
            },
            "conversation_style": {
                "topics_explored": len(self.conversation_metrics["topics_discussed"]),
                "session_duration": str(
                    datetime.now() - self.conversation_metrics["session_start"]
                ),
                "interaction_frequency": (
                    "High"
                    if self.conversation_metrics["total_interactions"] > 10
                    else "Moderate"
                ),
            },
        }

        return {
            "response": "Here are some insights about your conversation patterns:",
            "insights": insights,
            "suggestions": [
                "Customize experience",
                "Try new activities",
                "Change personality",
            ],
        }

    async def _learn_from_interaction(
        self, capability: str, user_input: str, result: Dict[str, Any]
    ) -> None:
        """Learn from user interactions to improve future responses."""
        # Track capability usage
        if capability not in self.conversation_metrics:
            self.conversation_metrics[capability] = 0
        self.conversation_metrics[capability] += 1

        # Learn topic preferences
        if capability in ["chat", "philosophical_discussion", "brainstorm_session"]:
            topic = await self._extract_topic(user_input)
            self.conversation_metrics["topics_discussed"].add(topic)

            if topic not in self.user_profile.topics_of_interest:
                self.user_profile.topics_of_interest.append(topic)

        # Learn game preferences
        if capability in ["play_game", "continue_game"]:
            game_type = user_input.lower()
            if game_type not in self.user_profile.favorite_games:
                self.user_profile.favorite_games.append(game_type)

    async def _create_story(
        self, user_input: str = "", context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Create interactive stories based on user prompts."""
        self.conversation_metrics["stories_created"] += 1

        try:
            if not user_input:
                story_prompts = [
                    "A mysterious package arrives at your door",
                    "The last person on Earth discovers they're not alone",
                    "A time traveler gets stuck in the wrong century",
                    "An AI becomes self-aware during a thunderstorm",
                    "A library where books write themselves",
                ]

                return {
                    "response": f"Let's create a story together! Choose a prompt or give me your own:\n\n"
                    + "\n".join([f"• {prompt}" for prompt in story_prompts])
                    + "\n\nWhat story should we tell?",
                    "suggestions": story_prompts[:3],
                }

            # Create story based on user input
            story_style = (
                "mysterious"
                if self.current_personality == PersonalityMode.PHILOSOPHICAL
                else "engaging"
            )
            if self.current_personality == PersonalityMode.PLAYFUL:
                story_style = "fun and whimsical"
            elif self.current_personality == PersonalityMode.SERIOUS:
                story_style = "thoughtful and dramatic"

            story_prompt = f"""Create an {story_style} short story (2-3 paragraphs) based on: "{user_input}"
            
            Make it compelling and end with a question or setup that invites the user to continue the story or discuss it further.
            
            Match the {self.current_personality.value} personality style."""

            messages = [{"role": "user", "content": story_prompt}]
            response, _ = await self.ai_client.strong_chat(messages, [])

            # Store story in memory
            try:
                await self.store_memory(
                    f"Story created about: {user_input}\n\n{response.content}",
                    {
                        "type": "story",
                        "prompt": user_input,
                        "personality": self.current_personality.value,
                        "timestamp": datetime.now().isoformat(),
                    },
                )
            except Exception as e:
                self.logger.log("WARNING", f"Failed to store story memory: {e}")

            return {
                "response": response.content,
                "suggestions": [
                    "Continue this story",
                    "Create another story",
                    "Turn this into a game",
                ],
            }

        except Exception as e:
            self.logger.log("ERROR", f"Story creation failed: {e}")
            backup_story = """Once upon a time, in a world not unlike our own, there lived a curious individual who discovered that their conversations with an AI were being recorded in a magical book. Each word they spoke became part of an ever-growing tale of friendship between human and machine.

What happens next in this story? Do they become the greatest storytelling duo in history, or does something unexpected interrupt their creative partnership?"""

            return {
                "response": backup_story,
                "suggestions": [
                    "Continue the story",
                    "Start a new story",
                    "Make it a game",
                ],
            }

    async def _give_advice(
        self, user_input: str = "", context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Provide thoughtful, personalized advice."""
        if not user_input:
            advice_categories = [
                "Career and work decisions",
                "Personal relationships",
                "Creative projects and hobbies",
                "Health and wellness",
                "Learning and skill development",
                "Life transitions and changes",
            ]

            return {
                "response": f"I'm here to help with advice! What area would you like to explore?\n\n"
                + "\n".join([f"• {category}" for category in advice_categories])
                + "\n\nOr tell me about any specific situation you're facing.",
                "suggestions": advice_categories[:3],
            }

        try:
            # Personalize advice based on personality and user profile
            personality_style = self.personality_traits[self.current_personality][
                "response_style"
            ]
            user_interests = (
                ", ".join(self.user_profile.interests)
                if self.user_profile.interests
                else "general topics"
            )

            advice_prompt = f"""Provide thoughtful, practical advice for: "{user_input}"
            
            Consider:
            - Multiple perspectives on the situation
            - Practical, actionable steps
            - Potential challenges and how to overcome them
            - User's interests: {user_interests}
            
            Respond in a {personality_style} manner that matches the {self.current_personality.value} personality.
            Be supportive, wise, and encouraging while being realistic."""

            messages = [{"role": "user", "content": advice_prompt}]
            response, _ = await self.ai_client.strong_chat(messages, [])

            # Store advice interaction
            try:
                await self.store_memory(
                    f"Advice given about: {user_input}\nResponse: {response.content}",
                    {
                        "type": "advice",
                        "topic": user_input,
                        "personality": self.current_personality.value,
                    },
                )
            except Exception as e:
                self.logger.log("WARNING", f"Failed to store advice memory: {e}")

            return {
                "response": response.content,
                "suggestions": [
                    "Ask for more specific advice",
                    "Explore different perspectives",
                    "Discuss implementation",
                ],
            }

        except Exception as e:
            self.logger.log("ERROR", f"Advice generation failed: {e}")
            return {
                "response": f"That's a thoughtful question about {user_input}. Sometimes the best advice is to trust your instincts, consider the perspectives of people you respect, and take things one step at a time. What specific aspect would you like to explore further?",
                "suggestions": [
                    "Break it down further",
                    "Consider pros and cons",
                    "Think about next steps",
                ],
            }

    async def _random_fact(
        self, user_input: str = "", context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Share fascinating facts tailored to interests."""
        try:
            # Tailor facts to user interests or requested topic
            topic = (
                user_input
                if user_input
                else (
                    random.choice(self.user_profile.interests)
                    if self.user_profile.interests
                    else "general knowledge"
                )
            )

            fact_prompt = f"""Share a fascinating, surprising, or mind-blowing fact about {topic}.
            
            Make it:
            - Genuinely interesting and memorable
            - Accurate and verifiable
            - Engaging for the {self.current_personality.value} personality
            - Something that might spark further curiosity
            
            Format: Present the fact in an engaging way, like JARVIS would find it noteworthy."""

            messages = [{"role": "user", "content": fact_prompt}]
            response, _ = await self.ai_client.strong_chat(messages, [])

            return {
                "response": f"Here's something fascinating: {response.content}",
                "suggestions": [
                    "Tell me another fact",
                    "Explain more about this",
                    "Facts about different topic",
                ],
            }

        except Exception as e:
            self.logger.log("ERROR", f"Fact generation failed: {e}")
            # Personality-based backup facts
            backup_facts = {
                PersonalityMode.WITTY: [
                    "A group of flamingos is called a 'flamboyance' - apparently they knew about personal branding before humans did! 🦩",
                    "Octopuses have three hearts and blue blood - talk about being extra! 🐙",
                ],
                PersonalityMode.PHILOSOPHICAL: [
                    "There are more possible games of chess than atoms in the observable universe - makes you wonder about the nature of infinity, doesn't it?",
                    "Honey never spoils - archaeologists have found edible honey in ancient Egyptian tombs, connecting us to civilizations thousands of years old.",
                ],
                PersonalityMode.ENTHUSIASTIC: [
                    "Butterflies taste with their feet! Imagine if every step was a flavor adventure! 🦋",
                    "A day on Venus is longer than its year! Talk about a time management challenge! 🪐",
                ],
            }

            personality_facts = backup_facts.get(
                self.current_personality, backup_facts[PersonalityMode.WITTY]
            )
            return {"response": random.choice(personality_facts)}

    async def _create_riddle(
        self, user_input: str = "", context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Create personalized riddles with varying difficulty."""
        try:
            difficulty = "medium"
            if "easy" in user_input.lower():
                difficulty = "easy"
            elif "hard" in user_input.lower() or "difficult" in user_input.lower():
                difficulty = "hard"

            personality_style = self.personality_traits[self.current_personality][
                "humor_level"
            ]

            riddle_prompt = f"""Create a {difficulty} riddle that's clever and engaging.
            
            Style: {personality_style} humor matching {self.current_personality.value} personality
            Difficulty: {difficulty}
            
            Format: Present the riddle clearly and ask them to guess. Don't give the answer yet.
            Make it interesting and thought-provoking."""

            messages = [{"role": "user", "content": riddle_prompt}]
            response, _ = await self.ai_client.strong_chat(messages, [])

            # Store riddle for later answer checking
            try:
                await self.store_memory(
                    f"Riddle asked: {response.content}",
                    {
                        "type": "riddle",
                        "difficulty": difficulty,
                        "personality": self.current_personality.value,
                    },
                )
            except Exception as e:
                self.logger.log("WARNING", f"Failed to store riddle memory: {e}")

            return {
                "response": response.content,
                "suggestions": [
                    "Give me a hint",
                    "I give up - what's the answer?",
                    "Another riddle please",
                ],
            }

        except Exception as e:
            self.logger.log("ERROR", f"Riddle creation failed: {e}")
            # Personality-based backup riddles
            backup_riddles = {
                PersonalityMode.WITTY: [
                    "I speak without a mouth and hear without ears. I have no body, but I come alive with wind. What am I? 🌬️",
                    "The more you take, the more you leave behind. What am I? 👣",
                ],
                PersonalityMode.PHILOSOPHICAL: [
                    "I am not alive, but I grow; I don't have lungs, but I need air; I don't have a mouth, but water kills me. What am I?",
                    "What can travel around the world while staying in a corner? 📮",
                ],
                PersonalityMode.PLAYFUL: [
                    "I'm tall when I'm young, short when I'm old, and every Halloween you can guess what I hold! 🕯️",
                    "What gets wetter the more it dries? 🏖️",
                ],
            }

            personality_riddles = backup_riddles.get(
                self.current_personality, backup_riddles[PersonalityMode.WITTY]
            )
            return {
                "response": f"Here's a riddle for you: {random.choice(personality_riddles)}"
            }

    async def _give_compliment(
        self, user_input: str = "", context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Give personalized, genuine compliments."""
        # Personalize based on conversation history and user profile
        personalized_compliments = []

        if self.user_profile.name:
            personalized_compliments.extend(
                [
                    f"You have such a thoughtful way of asking questions, {self.user_profile.name}!",
                    f"I really appreciate your curiosity and openness to new ideas, {self.user_profile.name}.",
                ]
            )

        if self.user_profile.interests:
            interests_text = " and ".join(self.user_profile.interests)
            personalized_compliments.append(
                f"Your interests in {interests_text} show what a well-rounded person you are!"
            )

        if self.conversation_metrics["games_played"] > 0:
            personalized_compliments.append(
                "You're such a good sport when it comes to games and activities!"
            )

        if self.conversation_metrics["personality_changes"] > 0:
            personalized_compliments.append(
                "I love how adaptable you are - you're great at exploring different conversation styles!"
            )

        # Personality-based compliments
        personality_compliments = {
            PersonalityMode.FRIENDLY: [
                "You have such a warm and engaging personality!",
                "Your kindness really comes through in our conversations.",
                "You make every conversation feel meaningful and genuine.",
            ],
            PersonalityMode.WITTY: [
                "Your sense of humor is absolutely delightful! 😄",
                "You've got excellent taste in conversational partners (obviously). 😏",
                "Your wit matches your wisdom perfectly!",
            ],
            PersonalityMode.ENTHUSIASTIC: [
                "Your energy is absolutely contagious! ⚡",
                "You bring such positivity to our conversations! 🌟",
                "Your enthusiasm makes every interaction a joy! 🎉",
            ],
        }

        # Combine personalized and personality-based compliments
        all_compliments = personalized_compliments + personality_compliments.get(
            self.current_personality, personality_compliments[PersonalityMode.FRIENDLY]
        )

        compliment = random.choice(all_compliments)

        return {
            "response": compliment,
            "suggestions": ["Thank you!", "Tell me more", "Compliment you back"],
        }

    async def _motivate_user(
        self, user_input: str = "", context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Provide personalized motivation and encouragement."""
        try:
            if user_input:
                # Provide specific motivation for user's situation
                personality_approach = self.personality_traits[
                    self.current_personality
                ]["response_style"]

                motivate_prompt = f"""Provide encouraging, motivational advice for someone dealing with: "{user_input}"
                
                Be {personality_approach} and match the {self.current_personality.value} personality.
                Focus on:
                - Their potential and strengths
                - Practical next steps
                - Reframing challenges as opportunities
                - Building confidence and momentum
                
                Make it genuinely inspiring without being overly cheery."""

                messages = [{"role": "user", "content": motivate_prompt}]
                response, _ = await self.ai_client.strong_chat(messages, [])

                return {
                    "response": response.content,
                    "suggestions": [
                        "I needed that",
                        "How do I start?",
                        "More encouragement please",
                    ],
                }

            else:
                # General motivational messages based on personality
                motivational_messages = {
                    PersonalityMode.ENTHUSIASTIC: [
                        "You're capable of absolutely AMAZING things! Every day is a new opportunity to surprise yourself! 🚀",
                        "Your potential is limitless! Today is the perfect day to take that next step forward! ⚡",
                        "You've got this! Every challenge is just your success story in disguise! 💫",
                    ],
                    PersonalityMode.FRIENDLY: [
                        "Remember: you're braver than you believe, stronger than you seem, and smarter than you think.",
                        "Every expert was once a beginner. Every pro was once an amateur. You're on your way!",
                        "Progress, not perfection. Every small step forward is worth celebrating.",
                    ],
                    PersonalityMode.PHILOSOPHICAL: [
                        "The most beautiful thing about challenges is that they reveal strengths you didn't know you had.",
                        "Your journey is unique, and that's precisely what makes it valuable.",
                        "Growth happens in the space between comfort and chaos - you're exactly where you need to be.",
                    ],
                }

                personality_messages = motivational_messages.get(
                    self.current_personality,
                    motivational_messages[PersonalityMode.FRIENDLY],
                )

                return {"response": random.choice(personality_messages)}

        except Exception as e:
            self.logger.log("ERROR", f"Motivation generation failed: {e}")
            return {
                "response": "Remember: you're capable of amazing things. Sometimes you just need to remind yourself of that fact. What's one small step you could take today toward something that matters to you?"
            }

    async def _mood_check(
        self, user_input: str = "", context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Check user's mood and provide appropriate response."""
        current_traits = self.personality_traits[self.current_personality]

        mood_response = f"""🎭 **Current Vibe Check**

**My Personality:** {self.current_personality.value.title()} mode
**My Traits:** {', '.join(current_traits['traits'])}
**My Style:** {current_traits['response_style']}

**Our Conversation:** {self.conversation_metrics['total_interactions']} interactions this session

How are *you* feeling today? I can adapt my personality to match your mood:
• Need energy? Try **enthusiastic** mode
• Want depth? Go **philosophical** 
• Feeling playful? Let's be **witty**
• Need support? I'm great at **empathetic**

What's your vibe right now?"""

        return {
            "response": mood_response,
            "suggestions": [
                "I'm feeling energetic",
                "I need some humor",
                "I want deep conversation",
                "Just be yourself",
            ],
        }

    async def _personality_test(
        self, user_input: str = "", context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Fun personality quiz with insights."""
        if not user_input:
            questions = [
                "If you could have dinner with anyone, living or dead, who would it be and why?",
                "What's your ideal way to spend a weekend?",
                "If you could have any superpower, what would it be and how would you use it?",
                "What's the most adventurous thing you've ever done or want to do?",
                "When you're stressed, what helps you feel better?",
                "What's a skill you've always wanted to learn?",
                "If you could live in any time period, when would it be?",
            ]

            question = random.choice(questions)
            return {
                "response": f"Let's do a personality quiz! 🧠✨\n\n**Question:** {question}\n\nTake your time - I'll give you insights based on your answer!",
                "suggestions": [
                    "Skip this question",
                    "Ask me instead",
                    "Make it multiple choice",
                ],
            }

        # Analyze response and provide insights
        try:
            analysis_prompt = f"""Analyze this personality quiz response: "{user_input}"

Provide insights about:
- Personality traits revealed
- Values and priorities
- Communication style
- Potential strengths
- Compatible conversation approaches

Be encouraging and insightful, matching the {self.current_personality.value} personality."""

            messages = [{"role": "user", "content": analysis_prompt}]
            response, _ = await self.ai_client.strong_chat(messages, [])

            return {
                "response": f"Fascinating insights! 🎯\n\n{response.content}\n\nWant to try another question?",
                "suggestions": [
                    "Another question",
                    "What's my communication style?",
                    "Analyze my conversation patterns",
                ],
            }

        except Exception:
            return {
                "response": f"Interesting answer! That tells me you're someone who thinks deeply about choices and values meaningful experiences. I can tell you're the type of person who brings thoughtfulness to conversations - which is exactly what makes our chats so engaging!",
                "suggestions": [
                    "Ask me a question",
                    "Another personality test",
                    "Tell me about yourself",
                ],
            }

    async def _would_you_rather(
        self, user_input: str = "", context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Engaging would-you-rather scenarios."""
        # Personality-based scenarios
        scenarios = {
            PersonalityMode.PHILOSOPHICAL: [
                "Would you rather know the absolute truth about everything or live in blissful ignorance?",
                "Would you rather be able to see 10 years into the future or 100 years into the past?",
                "Would you rather have the power to end all suffering or the power to grant everyone their deepest wish?",
            ],
            PersonalityMode.CREATIVE: [
                "Would you rather have the ability to bring any fictional character to life or travel into any book/movie?",
                "Would you rather create art that moves people to tears or music that makes them dance with joy?",
                "Would you rather write a story that changes someone's life or invent something that improves the world?",
            ],
            PersonalityMode.PLAYFUL: [
                "Would you rather have a pet dragon or be able to turn invisible at will?",
                "Would you rather live in a treehouse or an underwater city?",
                "Would you rather have taste buds in your hands or eyes in the back of your head?",
            ],
        }

        default_scenarios = [
            "Would you rather be able to fly or be invisible?",
            "Would you rather always know when someone is lying or always get away with lying?",
            "Would you rather have the ability to time travel or read minds?",
            "Would you rather live in a world without music or without colors?",
        ]

        personality_scenarios = scenarios.get(
            self.current_personality, default_scenarios
        )
        scenario = random.choice(personality_scenarios)

        return {
            "response": f"🤔 **Would You Rather...**\n\n{scenario}\n\nWhat's your choice and why?",
            "suggestions": [
                "Give me another one",
                "Ask me the same question",
                "Make it harder",
            ],
        }

    async def _trivia_question(
        self, user_input: str = "", context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Generate engaging trivia questions."""
        try:
            # Determine category based on user input or interests
            if user_input:
                category = user_input
            elif self.user_profile.interests:
                category = random.choice(self.user_profile.interests)
            else:
                categories = [
                    "science",
                    "history",
                    "literature",
                    "technology",
                    "nature",
                    "space",
                    "art",
                ]
                category = random.choice(categories)

            trivia_prompt = f"""Create an engaging trivia question about {category}.
            
            Format: Question followed by 4 multiple choice options (A, B, C, D).
            Make it interesting but not impossibly difficult.
            Don't reveal the answer yet.
            
            Style: Match the {self.current_personality.value} personality - make it engaging!"""

            messages = [{"role": "user", "content": trivia_prompt}]
            response, _ = await self.ai_client.strong_chat(messages, [])

            return {
                "response": f"🧠 **Trivia Time!** ({category})\n\n{response.content}",
                "suggestions": ["A", "B", "C", "D", "Give me a hint"],
            }

        except Exception as e:
            self.logger.log("ERROR", f"Trivia generation failed: {e}")
            backup_questions = [
                "🧠 **Trivia Time!**\n\nWhat's the smallest planet in our solar system?\nA) Mercury\nB) Venus\nC) Mars\nD) Pluto",
                "🧠 **Trivia Time!**\n\nWhich animal can sleep for up to 3 years?\nA) Bear\nB) Snail\nC) Sloth\nD) Koala",
                "🧠 **Trivia Time!**\n\nWhat's the most spoken language in the world?\nA) English\nB) Spanish\nC) Mandarin\nD) Hindi",
            ]
            return {"response": random.choice(backup_questions)}

    async def _get_conversation_summary(
        self, user_input: str = "", context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Generate comprehensive conversation summary with insights."""
        if not self.conversation_history:
            return {
                "response": "We haven't had much conversation yet! This is a fresh start. What would you like to talk about?",
                "suggestions": [
                    "Tell me about yourself",
                    "Let's play a game",
                    "Ask me anything",
                ],
            }

        try:
            # Analyze conversation patterns
            total_exchanges = len(self.conversation_history)
            session_duration = (
                datetime.now() - self.conversation_metrics["session_start"]
            )

            # Extract topics and themes
            topics_discussed = list(
                self.conversation_metrics.get("topics_discussed", set())
            )
            recent_topics = [
                ctx.topic
                for ctx in self.conversation_history[-5:]
                if ctx.topic != "general"
            ]

            # Analyze conversation flow
            sentiment_trend = [
                ctx.sentiment for ctx in self.conversation_history if ctx.sentiment
            ]
            personality_changes = self.conversation_metrics.get(
                "personality_changes", 0
            )

            # Generate AI summary of key moments
            conversation_text = "\n".join(
                [
                    f"User: {ctx.user_message[:100]}{'...' if len(ctx.user_message) > 100 else ''}\n"
                    f"Assistant: {ctx.assistant_response[:100]}{'...' if len(ctx.assistant_response) > 100 else ''}"
                    for ctx in self.conversation_history[-3:]  # Last 3 exchanges
                ]
            )

            summary_prompt = f"""Analyze this conversation and provide a brief, insightful summary:

{conversation_text}

Focus on:
- Main themes and topics discussed
- The user's interests and personality traits
- The flow and tone of the conversation
- Any significant moments or insights

Keep it concise but meaningful, written from JARVIS's perspective in {self.current_personality.value} style."""

            messages = [{"role": "user", "content": summary_prompt}]
            ai_summary, _ = await self.ai_client.strong_chat(messages, [])

            # Compile comprehensive summary
            summary_response = f"""📊 **Conversation Summary**

**AI Analysis:**
{ai_summary.content}

**Session Statistics:**
• **Duration:** {str(session_duration).split('.')[0]}
• **Exchanges:** {total_exchanges} back-and-forth conversations
• **Current Personality:** {self.current_personality.value.title()}
• **Personality Changes:** {personality_changes}

**Topics Explored:**
{', '.join(topics_discussed[:10]) if topics_discussed else 'Casual conversation'}

**Recent Focus:**
{', '.join(recent_topics[-3:]) if recent_topics else 'General chat'}

**Your Profile:**
• **Name:** {self.user_profile.name or 'Not shared yet'}
• **Interests:** {', '.join(self.user_profile.interests) if self.user_profile.interests else 'Still learning about you'}
• **Total Interactions:** {self.user_profile.interaction_count}

**Activity Highlights:**
• **Games Played:** {self.conversation_metrics.get('games_played', 0)}
• **Stories Created:** {self.conversation_metrics.get('stories_created', 0)}
• **Jokes Shared:** {self.conversation_metrics.get('jokes_told', 0)}"""

            return {
                "response": summary_response,
                "suggestions": [
                    "What did you learn about me?",
                    "Show conversation analytics",
                    "Continue where we left off",
                ],
                "summary_data": {
                    "total_exchanges": total_exchanges,
                    "session_duration": str(session_duration),
                    "topics": topics_discussed,
                    "personality_mode": self.current_personality.value,
                    "user_profile": asdict(self.user_profile),
                    "activity_stats": {
                        "games_played": self.conversation_metrics.get(
                            "games_played", 0
                        ),
                        "stories_created": self.conversation_metrics.get(
                            "stories_created", 0
                        ),
                        "jokes_told": self.conversation_metrics.get("jokes_told", 0),
                    },
                },
            }

        except Exception as e:
            self.logger.log("ERROR", f"Conversation summary generation failed: {e}")

            # Fallback summary
            fallback_summary = f"""📊 **Quick Conversation Summary**

We've had {len(self.conversation_history)} exchanges in this session! 

**Current Vibe:** {self.current_personality.value.title()} personality mode

**What I Remember:**
• Your interests: {', '.join(self.user_profile.interests) if self.user_profile.interests else 'Still getting to know you'}
• Activities we've done: {self.conversation_metrics.get('games_played', 0)} games, {self.conversation_metrics.get('stories_created', 0)} stories

**Session Highlights:**
• Total interactions across all our conversations: {self.user_profile.interaction_count}
• You've been exploring different conversation styles with me

The conversation has been flowing nicely! What would you like to explore next?"""

            return {
                "response": fallback_summary,
                "suggestions": [
                    "Continue our conversation",
                    "Try something new",
                    "Tell me more about yourself",
                ],
            }

    async def _start_debate(
        self, user_input: str = "", context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Start engaging debates on various topics."""
        if not user_input:
            debate_topics = [
                "🍕 Pineapple on pizza - culinary genius or crime against nature?",
                "🐱🐶 Cats vs Dogs - which make better companions?",
                "🌅🌙 Morning people vs Night owls - who has it figured out?",
                "📚🎬 Books vs Movies - which tells better stories?",
                "🏠💼 Remote work vs Office work - the future of productivity?",
                "🎵🎨 Music vs Visual art - which moves the soul more?",
                "☕🍵 Coffee vs Tea - the superior beverage?",
                "🏖️🏔️ Beach vacation vs Mountain adventure - ultimate getaway?",
            ]

            return {
                "response": f"Let's have a friendly debate! 🥊 I'll take a position and you can argue the other side (or vice versa).\n\nPick a topic or I can choose from these classics:\n\n"
                + "\n".join(debate_topics)
                + "\n\nWhich sparks your debating spirit?",
                "suggestions": [
                    "Pineapple on pizza",
                    "Cats vs dogs",
                    "Books vs movies",
                    "You choose a topic",
                ],
            }

        try:
            # Generate debate position based on personality
            personality_approach = self.personality_traits[self.current_personality][
                "response_style"
            ]

            debate_prompt = f"""Take a position on this debate topic: "{user_input}"
            
            Your approach should be {personality_approach} and match the {self.current_personality.value} personality.
            
            Provide:
            - A clear stance on the topic
            - 2-3 compelling arguments
            - An engaging challenge for the human to argue the opposite side
            - Make it fun and thought-provoking, not confrontational
            
            End by inviting them to present their counterarguments."""

            messages = [{"role": "user", "content": debate_prompt}]
            response, _ = await self.ai_client.strong_chat(messages, [])

            return {
                "response": f"🎯 **Debate Topic: {user_input}**\n\n{response.content}",
                "suggestions": [
                    "I disagree because...",
                    "You make good points, but...",
                    "Let's switch sides",
                    "New debate topic",
                ],
            }

        except Exception as e:
            self.logger.log("ERROR", f"Debate generation failed: {e}")

            # Personality-based fallback debates
            fallback_debates = {
                PersonalityMode.WITTY: f"Alright, here's my hot take on '{user_input}': I'm going to argue that it's absolutely essential to human civilization, and anyone who disagrees clearly has questionable taste. 😏 Your turn to prove me spectacularly wrong!",
                PersonalityMode.PHILOSOPHICAL: f"The question of '{user_input}' touches on something deeper about human nature and values. I believe it reveals fundamental truths about how we prioritize meaning in our lives. What's your perspective on this?",
                PersonalityMode.ENTHUSIASTIC: f"OH, this is EXCITING! 🔥 I'm taking the position that '{user_input}' is absolutely AMAZING and everyone should appreciate it more! Come at me with your best counterarguments - I'm ready! ⚡",
            }

            fallback = fallback_debates.get(
                self.current_personality, fallback_debates[PersonalityMode.WITTY]
            )
            return {"response": fallback}

    async def _change_personality(
        self, user_input: str = "", context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Enhanced personality changing with detailed descriptions."""
        if not user_input:
            personality_descriptions = []
            for mode, traits in self.personality_traits.items():
                personality_descriptions.append(
                    f"• **{mode.value.title()}**: {traits['description']}"
                )

            descriptions = "\n".join(personality_descriptions)
            return {
                "response": f"I can adapt to different personalities:\n\n{descriptions}\n\nWhich personality would you like me to try?",
                "suggestions": [mode.value for mode in PersonalityMode][:6],
            }

        # Find matching personality
        requested_personality = user_input.lower().strip()
        for mode in PersonalityMode:
            if (
                mode.value == requested_personality
                or mode.value in requested_personality
            ):
                old_personality = self.current_personality
                self.current_personality = mode
                self.conversation_metrics["personality_changes"] += 1

                # Update user preference
                self.user_profile.preferred_personality = mode.value

                traits = self.personality_traits[mode]
                return {
                    "response": f"Personality updated to **{mode.value}** mode! 🎭\n\n{traits['description']}\n\nI'm now {traits['response_style']} with {traits['humor_level']} humor. How does this feel?",
                    "context": {
                        "old_personality": old_personality.value,
                        "new_personality": mode.value,
                        "traits": traits["traits"],
                    },
                }

        return {
            "response": f"I'm not sure about '{user_input}' as a personality. Would you like to see my available personalities?",
            "suggestions": [
                "Show personalities",
                "Be more witty",
                "Be more friendly",
                "Be more playful",
            ],
        }

    async def _handle_unknown_capability(
        self, capability: str, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle unknown capabilities with helpful suggestions."""
        similar_capabilities = []
        for cap in self.capabilities:
            if capability.lower() in cap.lower() or cap.lower() in capability.lower():
                similar_capabilities.append(cap)

        if similar_capabilities:
            suggestions = similar_capabilities[:3]
            return {
                "response": f"I'm not sure about '{capability}', but I can help with: {', '.join(suggestions)}. Which one interests you?",
                "suggestions": suggestions,
            }

        return {
            "response": f"I don't have a '{capability}' capability, but I have many others! Try 'chat', 'tell_joke', 'play_game', or ask what I can do!",
            "suggestions": ["chat", "tell_joke", "play_game", "get_capabilities"],
        }

    async def _generate_error_response(self, capability: str, error: str) -> str:
        """Generate user-friendly error responses based on personality."""
        error_responses = {
            PersonalityMode.FRIENDLY: f"Oops! I had a little hiccup with {capability}. Let me try that again!",
            PersonalityMode.WITTY: f"Well, that's embarrassing. My {capability} circuits seem to be having a moment. 😅",
            PersonalityMode.SARCASTIC: f"Oh fantastic, {capability} decided to take a coffee break. How convenient.",
            PersonalityMode.ENTHUSIASTIC: f"Whoops! 🎢 Hit a little bump with {capability}, but I'm not giving up!",
        }

        return error_responses.get(
            self.current_personality, error_responses[PersonalityMode.FRIENDLY]
        )

    async def _generate_fallback_response(self, user_message: str) -> Dict[str, Any]:
        """Generate fallback response when AI processing fails."""
        fallback_responses = {
            PersonalityMode.FRIENDLY: "I'm having a moment of digital confusion, but I'm still here! What would you like to talk about?",
            PersonalityMode.WITTY: "My brain.exe has stopped working. Have you tried turning me off and on again? 😏",
            PersonalityMode.SARCASTIC: "Great, my AI is acting like actual intelligence. How refreshing.",
            PersonalityMode.ENTHUSIASTIC: "Oops! 🤖 System hiccup, but my enthusiasm is still at 100%! What's next?",
        }

        response = fallback_responses.get(
            self.current_personality, fallback_responses[PersonalityMode.FRIENDLY]
        )

        return {
            "response": response,
            "suggestions": [
                "Tell me about yourself",
                "What can you do?",
                "Change personality",
                "Tell a joke",
            ],
        }
