from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, HTMLResponse
from fastapi import HTTPException
from bson import ObjectId
from ..dependencies import get_auth_db, get_jarvis
from jarvis import JarvisSystem
from jarvis.protocols.loggers.mongo_logger import ProtocolUsageLogger, InteractionLogger

router = APIRouter(prefix="/admin", tags=["admin"])


def get_logs_db() -> sqlite3.Connection:
    """Get connection to jarvis_logs.db"""
    db_path = os.getenv("LOG_DB_PATH", "jarvis_logs.db")
    return sqlite3.connect(db_path, check_same_thread=False)


def get_mongo_logger() -> ProtocolUsageLogger:
    """Get MongoDB logger instance"""
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
    db_name = os.getenv("MONGO_DB_NAME", "protocol")
    return ProtocolUsageLogger(mongo_uri=mongo_uri, db_name=db_name)


def get_interaction_logger() -> InteractionLogger:
    """Get InteractionLogger instance"""
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
    db_name = os.getenv("MONGO_DB_NAME", "protocol")
    return InteractionLogger(mongo_uri=mongo_uri, db_name=db_name)


@router.get("/dashboard")
async def get_dashboard_summary(
    db: Optional[sqlite3.Connection] = Depends(get_auth_db),
    jarvis: Optional[JarvisSystem] = Depends(get_jarvis),
    log_days: int = 7,
    protocol_days: int = 30,
) -> Dict[str, Any]:
    """Get comprehensive dashboard summary with all analytics."""

    # Log stats
    logs_db = get_logs_db()
    try:
        logs_db.row_factory = sqlite3.Row
        total_logs = logs_db.execute("SELECT COUNT(*) FROM logs").fetchone()[0]
        level_counts = logs_db.execute(
            "SELECT level, COUNT(*) as count FROM logs GROUP BY level"
        ).fetchall()
        logs_by_level = {row["level"]: row["count"] for row in level_counts}
        logs_by_day = []
    finally:
        logs_db.close()

    # Protocol stats
    protocol_stats = {
        "total_executions": 0,
        "success_rate": 0.0,
        "average_latency_ms": None,
        "executions_by_protocol": [],
        "executions_by_day": [],
        "recent_executions": [],
        "top_protocols": [],
    }

    try:
        logger = get_mongo_logger()
        await logger.connect()
        total_executions = await logger._collection.count_documents({})
        successful = await logger._collection.count_documents({"success": True})
        success_rate = (
            (successful / total_executions * 100) if total_executions > 0 else 0.0
        )

        protocol_pipeline = [
            {
                "$group": {
                    "_id": "$protocol_name",
                    "count": {"$sum": 1},
                    "successful": {
                        "$sum": {"$cond": [{"$eq": ["$success", True]}, 1, 0]}
                    },
                    "avg_latency": {"$avg": "$latency_ms"},
                }
            },
            {"$sort": {"count": -1}},
        ]
        protocol_results = await logger._collection.aggregate(
            protocol_pipeline
        ).to_list(10)
        executions_by_protocol = [
            {
                "protocol_name": item["_id"],
                "total": item["count"],
                "successful": item["successful"],
                "success_rate": (
                    (item["successful"] / item["count"] * 100)
                    if item["count"] > 0
                    else 0
                ),
                "avg_latency_ms": item["avg_latency"],
            }
            for item in protocol_results
        ]

        protocol_stats = {
            "total_executions": total_executions,
            "success_rate": round(success_rate, 2),
            "average_latency_ms": None,
            "executions_by_protocol": executions_by_protocol,
            "executions_by_day": [],
            "recent_executions": [],
            "top_protocols": executions_by_protocol[:10],
        }
        await logger.close()
    except Exception:
        pass

    # User stats
    user_stats = {
        "total_users": 0,
        "users_with_profiles": 0,
        "total_interactions": 0,
        "active_users_30d": 0,
        "users_by_interaction_count": [],
    }

    if db:
        try:
            db.row_factory = sqlite3.Row
            total_users = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            users_with_profiles = db.execute(
                "SELECT COUNT(DISTINCT user_id) FROM user_profiles"
            ).fetchone()[0]
            interaction_count_rows = db.execute(
                "SELECT SUM(interaction_count) FROM user_profiles WHERE interaction_count IS NOT NULL"
            ).fetchone()
            total_interactions = interaction_count_rows[0] or 0
            cutoff_date = (datetime.now() - timedelta(days=30)).isoformat()
            active_users_30d = db.execute(
                "SELECT COUNT(DISTINCT user_id) FROM user_profiles WHERE last_seen >= ?",
                (cutoff_date,),
            ).fetchone()[0]

            users_by_interaction = db.execute(
                """SELECT user_id, interaction_count, name, last_seen 
                FROM user_profiles 
                WHERE interaction_count IS NOT NULL 
                ORDER BY interaction_count DESC LIMIT 20"""
            ).fetchall()

            user_stats = {
                "total_users": total_users,
                "users_with_profiles": users_with_profiles,
                "total_interactions": total_interactions,
                "active_users_30d": active_users_30d,
                "users_by_interaction_count": [
                    {
                        "user_id": row["user_id"],
                        "name": row["name"],
                        "interaction_count": row["interaction_count"],
                        "last_seen": row["last_seen"],
                    }
                    for row in users_by_interaction
                ],
            }
        except Exception:
            pass

    # Interaction stats from MongoDB
    interaction_stats = {
        "total_interactions": 0,
        "successful_interactions": 0,
        "interaction_success_rate": 0.0,
        "average_latency_ms": None,
    }

    try:
        interaction_logger = get_interaction_logger()
        await interaction_logger.connect()
        total_interactions = await interaction_logger._collection.count_documents({})
        successful_interactions = await interaction_logger._collection.count_documents(
            {"success": True}
        )
        interaction_success_rate = (
            (successful_interactions / total_interactions * 100)
            if total_interactions > 0
            else 0.0
        )

        # Calculate average latency
        latency_pipeline = [
            {"$match": {"latency_ms": {"$exists": True, "$ne": None}}},
            {"$group": {"_id": None, "avg_latency": {"$avg": "$latency_ms"}}},
        ]
        latency_result = await interaction_logger._collection.aggregate(
            latency_pipeline
        ).to_list(1)
        avg_latency = latency_result[0]["avg_latency"] if latency_result else None

        interaction_stats = {
            "total_interactions": total_interactions,
            "successful_interactions": successful_interactions,
            "interaction_success_rate": round(interaction_success_rate, 2),
            "average_latency_ms": round(avg_latency, 2) if avg_latency else None,
        }
        await interaction_logger.close()
    except Exception:
        pass

    # Memory stats
    memory_stats = {"total_memories": 0, "memories_by_user": {}, "collection_names": []}

    if jarvis and hasattr(jarvis, "vector_memory") and jarvis.vector_memory:
        try:
            total_memories = jarvis.vector_memory.collection.count()
            memory_stats = {
                "total_memories": total_memories,
                "memories_by_user": {},
                "collection_names": (
                    [jarvis.vector_memory.collection.name]
                    if hasattr(jarvis.vector_memory.collection, "name")
                    else []
                ),
            }
        except Exception:
            pass

    overview = {
        "total_users": user_stats["total_users"],
        "total_interactions": interaction_stats["total_interactions"],
        "total_logs": total_logs,
        "total_protocol_executions": protocol_stats["total_executions"],
        "protocol_success_rate": protocol_stats["success_rate"],
        "total_memories": memory_stats["total_memories"],
        "active_users_30d": user_stats["active_users_30d"],
        "interaction_success_rate": interaction_stats["interaction_success_rate"],
    }

    return {
        "overview": overview,
        "log_stats": {
            "total_logs": total_logs,
            "logs_by_level": logs_by_level,
            "logs_by_day": logs_by_day,
            "recent_logs": [],
        },
        "protocol_stats": protocol_stats,
        "user_stats": user_stats,
        "memory_stats": memory_stats,
    }


@router.get("/logs")
async def get_logs(
    limit: int = 100,
    level: Optional[str] = None,
    offset: int = 0,
) -> Dict[str, Any]:
    """Get logs with pagination and filtering."""
    logs_db = get_logs_db()
    try:
        logs_db.row_factory = sqlite3.Row

        query = "SELECT id, timestamp, level, action, details FROM logs"
        params = []

        if level:
            query += " WHERE level = ?"
            params.append(level.upper())

        query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = logs_db.execute(query, params).fetchall()

        total_query = "SELECT COUNT(*) FROM logs"
        if level:
            total_query += " WHERE level = ?"
            total_count = logs_db.execute(total_query, (level.upper(),)).fetchone()[0]
        else:
            total_count = logs_db.execute(total_query).fetchone()[0]

        logs = [
            {
                "id": row["id"],
                "timestamp": row["timestamp"],
                "level": row["level"],
                "action": row["action"],
                "details": row["details"],
            }
            for row in rows
        ]

        return {
            "logs": logs,
            "total": total_count,
            "limit": limit,
            "offset": offset,
        }
    finally:
        logs_db.close()


@router.get("/memories")
async def get_memories(
    jarvis: Optional[JarvisSystem] = Depends(get_jarvis),
    limit: int = 100,
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Get memories from ChromaDB."""
    if not jarvis or not hasattr(jarvis, "vector_memory") or not jarvis.vector_memory:
        return {
            "memories": [],
            "total": 0,
            "limit": limit,
        }

    try:
        collection = jarvis.vector_memory.collection

        # Get all memories
        where_filter = {}
        if user_id is not None:
            where_filter["user_id"] = user_id

        if where_filter:
            result = collection.get(where=where_filter, limit=limit)
        else:
            result = collection.get(limit=limit)

        documents = result.get("documents", [])
        metadatas = result.get("metadatas", [])
        ids = result.get("ids", [])

        memories = [
            {
                "id": ids[i],
                "text": documents[i] if i < len(documents) else "",
                "metadata": metadatas[i] if i < len(metadatas) else {},
            }
            for i in range(len(ids))
        ]

        return {
            "memories": memories,
            "total": len(memories),
            "limit": limit,
        }
    except Exception as e:
        return {
            "memories": [],
            "total": 0,
            "limit": limit,
            "error": str(e),
        }


@router.get("/dashboard/html", response_class=HTMLResponse)
async def get_dashboard_html() -> HTMLResponse:
    """Serve the admin dashboard HTML page."""
    dashboard_path = os.path.join(
        os.path.dirname(__file__), "..", "static", "admin_dashboard.html"
    )
    if os.path.exists(dashboard_path):
        return FileResponse(dashboard_path)
    else:
        raise HTTPException(
            status_code=404, detail=f"Dashboard HTML file not found at {dashboard_path}"
        )


@router.get("/logs/html", response_class=HTMLResponse)
async def get_logs_html() -> HTMLResponse:
    """Serve the logs viewer HTML page."""
    logs_path = os.path.join(
        os.path.dirname(__file__), "..", "static", "admin_logs.html"
    )
    if os.path.exists(logs_path):
        return FileResponse(logs_path)
    else:
        raise HTTPException(
            status_code=404, detail=f"Logs HTML file not found at {logs_path}"
        )


@router.get("/memories/html", response_class=HTMLResponse)
async def get_memories_html() -> HTMLResponse:
    """Serve the memories viewer HTML page."""
    memories_path = os.path.join(
        os.path.dirname(__file__), "..", "static", "admin_memories.html"
    )
    if os.path.exists(memories_path):
        return FileResponse(memories_path)
    else:
        raise HTTPException(
            status_code=404, detail=f"Memories HTML file not found at {memories_path}"
        )


@router.get("/interactions")
async def get_interactions(
    limit: int = 100,
    user_id: Optional[int] = None,
    intent: Optional[str] = None,
) -> Dict[str, Any]:
    """Get interaction history from MongoDB."""
    try:
        logger = get_interaction_logger()
        await logger.connect()
        interactions = await logger.get_recent_interactions(
            limit=limit, user_id=user_id, intent=intent
        )
        await logger.close()

        # Convert MongoDB documents to JSON-serializable format
        # Convert ObjectId to string and handle datetime serialization
        def convert_mongo_doc(doc):
            """Convert MongoDB document to JSON-serializable dict."""
            if isinstance(doc, dict):
                converted = {}
                for key, value in doc.items():
                    if isinstance(value, ObjectId):
                        converted[key] = str(value)
                    elif isinstance(value, datetime):
                        converted[key] = value.isoformat()
                    elif isinstance(value, dict):
                        converted[key] = convert_mongo_doc(value)
                    elif isinstance(value, list):
                        converted[key] = [convert_mongo_doc(item) for item in value]
                    else:
                        converted[key] = value
                return converted
            return doc

        serialized_interactions = [
            convert_mongo_doc(interaction) for interaction in interactions
        ]

        return {
            "interactions": serialized_interactions,
            "total": len(serialized_interactions),
            "limit": limit,
        }
    except Exception as e:
        return {
            "interactions": [],
            "total": 0,
            "limit": limit,
            "error": str(e),
        }


@router.get("/interactions/html", response_class=HTMLResponse)
async def get_interactions_html() -> HTMLResponse:
    """Serve the interactions viewer HTML page."""
    interactions_path = os.path.join(
        os.path.dirname(__file__), "..", "static", "admin_interactions.html"
    )
    if os.path.exists(interactions_path):
        return FileResponse(interactions_path)
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Interactions HTML file not found at {interactions_path}",
        )
