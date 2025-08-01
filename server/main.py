from __future__ import annotations

import os
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv


from jarvis import JarvisLogger, JarvisSystem, JarvisConfig
from jarvis.constants import DEFAULT_PORT
from server.database import init_database, close_database
from server.routers.jarvis import router as jarvis_router
from server.routers.auth import router as auth_router
from server.routers.protocols import router as protocol_router
from server.routers.users import router as users_router
from server.routers.agents import router as agents_router


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="Jarvis API")
    origins = [
        "http://localhost:3000",  # React default
        "http://localhost:3001",  # Alternative React port
        "http://localhost:5173",  # Vite default
        "http://localhost:8080",  # Alternative frontend
        "http://127.0.0.1:3000",  # Alternative localhost format
        "http://127.0.0.1:5173",  # Alternative Vite format
    ]
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(jarvis_router, prefix="/jarvis", tags=["jarvis"])
    app.include_router(agents_router, prefix="/agents", tags=["agents"])
    app.include_router(auth_router, prefix="/auth", tags=["auth"])
    app.include_router(protocol_router, prefix="/protocols", tags=["protocols"])
    app.include_router(users_router, prefix="/users", tags=["users"])

    # Add startup and shutdown events
    @app.on_event("startup")
    async def startup_event() -> None:
        """Initialize the collaborative Jarvis system."""
        load_dotenv()
        level_name = os.getenv("JARVIS_LOG_LEVEL", "INFO").upper()
        level = getattr(logging, level_name, logging.INFO)
        app.state.logger = JarvisLogger(log_level=level)

        config = JarvisConfig(
            ai_provider="openai",
            api_key=os.getenv("OPENAI_API_KEY"),
            calendar_api_url=os.getenv("CALENDAR_API_URL", "http://localhost:8080"),
            repo_path=os.getenv("REPO_PATH", "."),
            response_timeout=float(os.getenv("JARVIS_RESPONSE_TIMEOUT", 15.0)),
        )

        jarvis_system = JarvisSystem(config)
        await jarvis_system.initialize()
        app.state.jarvis_system = jarvis_system
        app.state.user_systems = {}

        # Initialize database
        app.state.auth_db = init_database()

    @app.on_event("shutdown")
    async def shutdown_event() -> None:
        jarvis_system: JarvisSystem | None = getattr(app.state, "jarvis_system", None)
        if jarvis_system:
            await jarvis_system.shutdown()

        logger: JarvisLogger | None = getattr(app.state, "logger", None)
        if logger:
            logger.close()

        close_database(getattr(app.state, "auth_db", None))

    return app


app = create_app()


def run():
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=DEFAULT_PORT)


if __name__ == "__main__":
    run()
