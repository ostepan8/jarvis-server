from ..base import NetworkAgent
from ...ai_clients.base import BaseAIClient
from ...logger import JarvisLogger
from typing import Optional
from ...profile import AgentProfile

class ChatAgent(NetworkAgent):
    """
    Next-generation conversational agent
    """
    def __init__(
        self,
        ai_client: BaseAIClient,
        logger: Optional[JarvisLogger] = None,
    ) -> None:
        super().__init__(
            name="ChatAgent",
            logger=logger,
            memory=None,
            profile=AgentProfile(),
        )
        self.ai_client = ai_client
