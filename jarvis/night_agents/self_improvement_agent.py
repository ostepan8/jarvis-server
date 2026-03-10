from __future__ import annotations

import asyncio
from typing import Optional, Set

from .base import NightAgent
from ..agents.message import Message
from ..agents.response import AgentResponse
from ..logging import JarvisLogger
from ..services.self_improvement_service import SelfImprovementService, NightReport
from ..services.todo_service import TodoService


class SelfImprovementAgent(NightAgent):
    """Autonomous code improvement agent that runs during night mode.

    Discovers issues (log errors, test failures, tagged todos, code quality),
    executes fixes via Claude Code CLI in isolated git worktrees, runs tests,
    and auto-merges passing changes.
    """

    def __init__(
        self,
        project_root: str,
        todo_service: Optional[TodoService] = None,
        logger: Optional[JarvisLogger] = None,
        run_interval: int = 86400,
        log_db_path: str = "jarvis_logs.db",
    ) -> None:
        super().__init__("SelfImprovementAgent", logger)
        self._service = SelfImprovementService(
            project_root=project_root,
            todo_service=todo_service,
            log_db_path=log_db_path,
            logger=logger,
        )
        self._run_interval = run_interval
        self._last_report: Optional[NightReport] = None

    @property
    def description(self) -> str:
        return "Autonomously discovers and fixes issues in the Jarvis codebase during night mode"

    @property
    def capabilities(self) -> Set[str]:
        return {"run_self_improvement", "get_improvement_report"}

    async def _handle_capability_request(self, message: Message) -> None:
        capability = message.content.get("capability")

        if capability == "run_self_improvement":
            report = await self._run_cycle()
            result = AgentResponse(
                success=True,
                response=report.to_summary_text(),
                data=report.to_dict(),
                metadata={"agent": self.name},
            )
        elif capability == "get_improvement_report":
            report = self._service.get_latest_report()
            if report:
                result = AgentResponse(
                    success=True,
                    response=report.to_summary_text(),
                    data=report.to_dict(),
                    metadata={"agent": self.name},
                )
            else:
                result = AgentResponse(
                    success=True,
                    response="No improvement reports available yet.",
                    metadata={"agent": self.name},
                )
        else:
            result = AgentResponse(
                success=False,
                response=f"Unknown capability: {capability}",
                metadata={"agent": self.name},
            )

        await self.send_capability_response(
            to_agent=message.from_agent,
            result=result.to_dict(),
            request_id=message.request_id,
            original_message_id=message.id,
        )

    async def _handle_capability_response(self, message: Message) -> None:
        return None

    async def start_background_tasks(self) -> None:
        """Start the periodic improvement cycle."""
        self._create_background_task(self._periodic_improvement())

    async def _periodic_improvement(self) -> None:
        """Run the improvement cycle, then sleep for run_interval."""
        while True:
            try:
                await self._run_cycle()
            except Exception as exc:
                if self.logger:
                    self.logger.log(
                        "ERROR",
                        "Self-improvement cycle failed",
                        str(exc),
                    )
            await asyncio.sleep(self._run_interval)

    async def _run_cycle(self) -> NightReport:
        """Execute one improvement cycle and cache the report."""
        if self.logger:
            self.logger.log("INFO", "Self-improvement cycle starting", "")
        report = await self._service.run_improvement_cycle()
        self._last_report = report
        if self.logger:
            self.logger.log(
                "INFO",
                "Self-improvement cycle complete",
                f"Attempted: {report.tasks_attempted}, "
                f"Succeeded: {report.tasks_succeeded}, "
                f"Failed: {report.tasks_failed}",
            )
        return report
