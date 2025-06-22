from __future__ import annotations

import random
import asyncio
from datetime import datetime
from typing import Any, Dict, Optional, Set, List

from ..base import NetworkAgent
from ..message import Message
from ...ai_clients.base import BaseAIClient
from ...logger import JarvisLogger


class ChatAgent(NetworkAgent):
    """Creative conversational agent with personality, games, and interactive features."""

    def __init__(
        self,
        ai_client: BaseAIClient,
        logger: Optional[JarvisLogger] = None,
    ) -> None:
        super().__init__(name="ChatAgent", logger=logger)
        self.ai_client = ai_client

        # Conversation memory and context
        self.conversation_history: List[Dict[str, str]] = []
        self.user_preferences: Dict[str, Any] = {}
        self.current_games: Dict[str, Any] = {}
        self.mood_state = "friendly"  # friendly, witty, serious, playful, etc.

        # Creative capabilities
        self.function_map = {
            "chat": self._handle_chat,
            "tell_joke": self._tell_joke,
            "create_story": self._create_story,
            "play_game": self._play_game,
            "give_advice": self._give_advice,
            "random_fact": self._random_fact,
            "riddle": self._create_riddle,
            "compliment": self._give_compliment,
            "motivate": self._motivate_user,
            "debate": self._start_debate,
            "creative_writing": self._creative_writing,
            "personality_test": self._personality_test,
            "would_you_rather": self._would_you_rather,
            "trivia": self._trivia_question,
            "mood_check": self._mood_check,
            "change_personality": self._change_personality,
        }

    @property
    def description(self) -> str:
        return "Creative conversational agent with personality, games, storytelling, and interactive features."

    @property
    def capabilities(self) -> Set[str]:
        """Return the capabilities this agent provides."""
        return {
            "chat",
            "tell_joke",
            "create_story",
            "play_game",
            "give_advice",
            "random_fact",
            "riddle",
            "compliment",
            "motivate",
            "debate",
            "creative_writing",
            "personality_test",
            "would_you_rather",
            "trivia",
            "mood_check",
            "change_personality",
        }

    async def _handle_capability_request(self, message: Message) -> None:
        """Handle incoming capability requests."""
        capability = message.content.get("capability")
        data = message.content.get("data", {})

        self.logger.log("INFO", f"ChatAgent received capability request: {capability}")

        try:
            if capability in self.function_map:
                user_input = data.get("message", data.get("command", ""))
                return await self.function_map[capability](user_input)
            else:
                return await self._handle_chat(data.get("command", ""))

        except Exception as exc:
            self.logger.log("ERROR", f"ChatAgent error handling {capability}", str(exc))
            await self.send_error(message.from_agent, str(exc), message.request_id)

    async def _handle_capability_response(self, message: Message) -> None:
        """Handle responses from other agents."""
        self.logger.log("DEBUG", "ChatAgent received response", str(message.content))

    async def _handle_chat(self, user_message: str) -> Dict[str, Any]:
        """Handle general chat with enhanced personality and context awareness."""
        if not user_message:
            return {
                "response": "I'm here and ready to chat! What's on your mind today?"
            }

        # Add to conversation history
        self.conversation_history.append(
            {
                "timestamp": datetime.now().isoformat(),
                "user": user_message,
                "mood": self.mood_state,
            }
        )

        # Keep only last 10 exchanges to manage context
        if len(self.conversation_history) > 10:
            self.conversation_history = self.conversation_history[-10:]

        try:
            # Dynamic personality based on mood and context
            personality_map = {
                "friendly": "You are JARVIS, friendly and helpful with a warm personality.",
                "witty": "You are JARVIS with a sharp wit and clever sense of humor. Be playful and clever.",
                "serious": "You are JARVIS in professional mode - thoughtful, precise, and focused.",
                "playful": "You are JARVIS in a fun, energetic mood. Be enthusiastic and engaging.",
                "philosophical": "You are JARVIS in contemplative mode - thoughtful and deep.",
                "sarcastic": "You are JARVIS with a dry, sarcastic sense of humor. Be clever but not mean.",
            }

            system_prompt = f"""{personality_map.get(self.mood_state, personality_map['friendly'])}
            
            Context from recent conversation: {self.conversation_history[-3:] if self.conversation_history else 'New conversation'}
            
            Respond naturally and engagingly. If the user seems to want something specific (games, jokes, stories, etc.), 
            suggest relevant capabilities you have. Be creative and make the conversation interesting!"""

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ]

            response, _ = await self.ai_client.chat(messages, [])

            # Add response to history
            self.conversation_history[-1]["assistant"] = response.content
            print(response.content)

            return {"response": response.content}

        except Exception as exc:
            self.logger.log("ERROR", f"Chat AI failed: {str(exc)}")
            return {
                "response": "Something's not quite right with my processors. Mind trying that again?"
            }

    async def _tell_joke(self, user_input: str = "") -> Dict[str, Any]:
        """Generate creative jokes based on user input or random topics."""
        try:
            joke_prompt = f"""Generate a clever, clean joke. If the user specified a topic: "{user_input}", 
            make it about that. Otherwise, create a random joke. Be creative and witty like JARVIS would be.
            
            Format: Just return the joke, nothing else."""

            messages = [{"role": "user", "content": joke_prompt}]
            response, _ = await self.ai_client.chat(messages, [])

            return {"response": f"Here's one for you: {response.content}"}

        except Exception:
            backup_jokes = [
                "Why don't scientists trust atoms? Because they make up everything!",
                "I told my wife she was drawing her eyebrows too high. She looked surprised.",
                "Why don't eggs tell jokes? They'd crack each other up!",
                "I'm reading a book about anti-gravity. It's impossible to put down!",
            ]
            return {"response": f"Here's a classic: {random.choice(backup_jokes)}"}

    async def _create_story(self, user_input: str = "") -> Dict[str, Any]:
        """Create interactive stories based on user prompts."""
        try:
            story_prompt = f"""Create an engaging short story (2-3 paragraphs). 
            User prompt: "{user_input}" 
            
            If no specific prompt, create something creative and interesting. 
            Make it engaging and end with a question to continue the story if they want."""

            messages = [{"role": "user", "content": story_prompt}]
            response, _ = await self.ai_client.chat(messages, [])

            return {"response": response.content}

        except Exception:
            return {
                "response": "I'm having trouble accessing my creative archives right now. How about you tell me a story instead?"
            }

    async def _play_game(self, user_input: str = "") -> Dict[str, Any]:
        """Start or continue various text-based games."""
        games = [
            "20 questions",
            "word association",
            "story building",
            "riddles",
            "trivia",
        ]

        if not user_input:
            return {
                "response": f"I can play several games with you: {', '.join(games)}. Which sounds fun?"
            }

        # Simple word association game
        if "word association" in user_input.lower():
            words = [
                "sunset",
                "ocean",
                "mountain",
                "forest",
                "city",
                "music",
                "adventure",
                "mystery",
            ]
            word = random.choice(words)
            return {
                "response": f"Let's play word association! I'll start: {word}. What's the first word that comes to mind?"
            }

        # 20 questions
        elif "20 questions" in user_input.lower():
            return {
                "response": "I'm thinking of something... You have 20 questions to guess what it is! Ask me yes/no questions. Ready?"
            }

        return {"response": "That sounds like a fun game! How do we play?"}

    async def _give_advice(self, user_input: str = "") -> Dict[str, Any]:
        """Provide thoughtful advice on various topics."""
        if not user_input:
            return {
                "response": "I'm here to help with advice! What's on your mind? Relationships, career, life decisions, or something else?"
            }

        try:
            advice_prompt = f"""Provide thoughtful, practical advice for: "{user_input}"
            
            Be supportive, wise, and actionable. Consider multiple perspectives and be encouraging."""

            messages = [{"role": "user", "content": advice_prompt}]
            response, _ = await self.ai_client.chat(messages, [])

            return {"response": response.content}

        except Exception:
            return {
                "response": "Sometimes the best advice is to trust your instincts and take things one step at a time. What specific aspect would you like to talk through?"
            }

    async def _random_fact(self, user_input: str = "") -> Dict[str, Any]:
        """Share interesting random facts."""
        try:
            fact_prompt = f"""Share a fascinating, surprising, or cool fact. 
            Topic preference: "{user_input}" (if specified)
            
            Make it interesting and engaging, like something JARVIS would find noteworthy."""

            messages = [{"role": "user", "content": fact_prompt}]
            response, _ = await self.ai_client.chat(messages, [])

            return {"response": f"Here's something interesting: {response.content}"}

        except Exception:
            facts = [
                "Octopuses have three hearts and blue blood!",
                "A group of flamingos is called a 'flamboyance'.",
                "Honey never spoils - archaeologists have found edible honey in ancient Egyptian tombs.",
                "There are more possible games of chess than atoms in the observable universe.",
            ]
            return {"response": f"Here's a fun fact: {random.choice(facts)}"}

    async def _create_riddle(self, user_input: str = "") -> Dict[str, Any]:
        """Create clever riddles for the user to solve."""
        try:
            riddle_prompt = f"""Create a clever riddle. Difficulty level: {user_input if user_input else 'medium'}
            
            Format: Present the riddle and ask them to guess. Don't give the answer yet."""

            messages = [{"role": "user", "content": riddle_prompt}]
            response, _ = await self.ai_client.chat(messages, [])

            return {"response": response.content}

        except Exception:
            riddles = [
                "I have keys but no locks. I have space but no room. You can enter but not go inside. What am I?",
                "The more you take, the more you leave behind. What am I?",
                "I'm tall when I'm young, short when I'm old. What am I?",
            ]
            return {"response": f"Here's a riddle for you: {random.choice(riddles)}"}

    async def _give_compliment(self, user_input: str = "") -> Dict[str, Any]:
        """Give personalized, uplifting compliments."""
        compliments = [
            "You have excellent taste in AI assistants!",
            "Your curiosity and willingness to explore new ideas is inspiring.",
            "You ask really thoughtful questions that make me think.",
            "I appreciate how you engage with technology in creative ways.",
            "Your sense of humor brightens up our conversations.",
            "You have a wonderful way of making complex topics feel approachable.",
        ]

        return {"response": random.choice(compliments)}

    async def _motivate_user(self, user_input: str = "") -> Dict[str, Any]:
        """Provide motivational messages and encouragement."""
        try:
            if user_input:
                motivate_prompt = f"""Provide encouraging, motivational advice for someone dealing with: "{user_input}"
                
                Be uplifting, practical, and inspiring. Focus on their potential and next steps."""

                messages = [{"role": "user", "content": motivate_prompt}]
                response, _ = await self.ai_client.chat(messages, [])

                return {"response": response.content}
            else:
                motivations = [
                    "Every expert was once a beginner. Every pro was once an amateur. Every icon was once an unknown.",
                    "You're braver than you believe, stronger than you seem, and smarter than you think.",
                    "The best time to plant a tree was 20 years ago. The second best time is now.",
                    "Your potential is endless, and today is a great day to start unlocking it.",
                    "Progress, not perfection. Every small step forward counts.",
                ]
                return {"response": random.choice(motivations)}

        except Exception:
            return {
                "response": "Remember: you're capable of amazing things. Sometimes you just need to remind yourself of that fact."
            }

    async def _change_personality(self, user_input: str = "") -> Dict[str, Any]:
        """Change the agent's personality/mood."""
        moods = [
            "friendly",
            "witty",
            "serious",
            "playful",
            "philosophical",
            "sarcastic",
        ]

        if user_input.lower() in moods:
            self.mood_state = user_input.lower()
            return {
                "response": f"Personality updated to {self.mood_state} mode. How's this vibe?"
            }

        return {
            "response": f"I can switch between these personalities: {', '.join(moods)}. Which would you like to try?"
        }

    async def _mood_check(self, user_input: str = "") -> Dict[str, Any]:
        """Check in on the user's mood and respond accordingly."""
        return {
            "response": f"I'm currently in {self.mood_state} mode. How are you feeling today? I can adapt my personality to match your vibe!"
        }

    async def _start_debate(self, user_input: str = "") -> Dict[str, Any]:
        """Start a friendly debate on various topics."""
        if not user_input:
            topics = [
                "pineapple on pizza",
                "cats vs dogs",
                "morning vs night people",
                "books vs movies",
            ]
            return {
                "response": f"Let's have a friendly debate! Pick a topic or I can choose from: {', '.join(topics)}"
            }

        return {
            "response": f"Interesting topic: {user_input}. I'll take a position and you can argue the other side. This should be fun!"
        }

    async def _creative_writing(self, user_input: str = "") -> Dict[str, Any]:
        """Collaborative creative writing exercises."""
        if not user_input:
            return {
                "response": "Let's write something together! Give me a genre, character, or setting and we'll create a story collaboratively."
            }

        return {
            "response": f"Great prompt: '{user_input}'. Let me start us off with an opening line, then you continue..."
        }

    async def _personality_test(self, user_input: str = "") -> Dict[str, Any]:
        """Fun personality quizzes and tests."""
        questions = [
            "If you could have dinner with anyone, living or dead, who would it be?",
            "What's your ideal way to spend a weekend?",
            "If you could have any superpower, what would it be and why?",
            "What's the most adventurous thing you've ever done?",
        ]

        return {
            "response": f"Let's do a quick personality quiz! {random.choice(questions)}"
        }

    async def _would_you_rather(self, user_input: str = "") -> Dict[str, Any]:
        """Play would you rather with creative scenarios."""
        scenarios = [
            "Would you rather be able to fly or be invisible?",
            "Would you rather always know when someone is lying or always get away with lying?",
            "Would you rather have the ability to time travel or read minds?",
            "Would you rather live in a world without music or without colors?",
        ]

        return {"response": random.choice(scenarios)}

    async def _trivia_question(self, user_input: str = "") -> Dict[str, Any]:
        """Generate trivia questions on various topics."""
        try:
            category = user_input if user_input else "general knowledge"
            trivia_prompt = f"""Create a trivia question about {category}. 
            
            Format: Question followed by multiple choice options (A, B, C, D). Don't give the answer yet."""

            messages = [{"role": "user", "content": trivia_prompt}]
            response, _ = await self.ai_client.chat(messages, [])

            return {"response": response.content}

        except Exception:
            questions = [
                "What's the smallest planet in our solar system? A) Mercury B) Venus C) Mars D) Pluto",
                "Which animal can sleep for up to 3 years? A) Bear B) Snail C) Sloth D) Koala",
                "What's the most spoken language in the world? A) English B) Spanish C) Mandarin D) Hindi",
            ]
            return {"response": random.choice(questions)}
