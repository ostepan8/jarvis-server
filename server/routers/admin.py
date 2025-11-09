from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, HTMLResponse
from fastapi import HTTPException
from bson import ObjectId
from ..dependencies import get_auth_db, get_jarvis, get_fact_service
from jarvis import JarvisSystem
from jarvis.services.fact_memory import FactMemoryService

router = APIRouter(prefix="/admin", tags=["admin"])


def get_logs_db() -> sqlite3.Connection:
    """Get connection to jarvis_logs.db"""
    db_path = os.getenv("LOG_DB_PATH", "jarvis_logs.db")
    return sqlite3.connect(db_path, check_same_thread=False)


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

    if jarvis and jarvis.usage_logger:
        try:
            logger = jarvis.usage_logger
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

    if jarvis and jarvis.interaction_logger:
        try:
            interaction_logger = jarvis.interaction_logger
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
        except Exception:
            pass

    # Memory stats
    memory_stats = {"total_memories": 0, "memories_by_user": {}, "collection_names": []}

    # Access vector_memory through agent refs
    vector_memory = jarvis._agent_refs.get("vector_memory") if hasattr(jarvis, "_agent_refs") else None
    if vector_memory:
        try:
            total_memories = vector_memory.collection.count()
            memory_stats = {
                "total_memories": total_memories,
                "memories_by_user": {},
                "collection_names": (
                    [vector_memory.collection.name]
                    if hasattr(vector_memory.collection, "name")
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
    # Access vector_memory through agent refs
    vector_memory = jarvis._agent_refs.get("vector_memory") if (jarvis and hasattr(jarvis, "_agent_refs")) else None
    if not vector_memory:
        return {
            "memories": [],
            "total": 0,
            "limit": limit,
        }

    try:
        collection = vector_memory.collection

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
    jarvis: Optional[JarvisSystem] = Depends(get_jarvis),
    limit: int = 100,
    user_id: Optional[int] = None,
    intent: Optional[str] = None,
) -> Dict[str, Any]:
    """Get interaction history from MongoDB."""
    if not jarvis or not jarvis.interaction_logger:
        return {
            "interactions": [],
            "total": 0,
            "limit": limit,
            "error": "Jarvis system or interaction logger not available",
        }
    
    try:
        logger = jarvis.interaction_logger
        interactions = await logger.get_recent_interactions(
            limit=limit, user_id=user_id, intent=intent
        )

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


@router.post("/facts/test")
async def test_facts(
    fact_service: FactMemoryService = Depends(get_fact_service),
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Test fact memory operations."""
    # Use provided user_id, or default from env, or 1
    if user_id is None:
        user_id = int(os.getenv("DEFAULT_USER_ID", "1"))

    test_results = {
        "success": True,
        "tests": [],
        "errors": [],
        "user_id": user_id,
    }

    try:
        # Test 1: Add a fact
        test_fact_text = "Test fact: User loves Italian food"
        test_fact_id = fact_service.add_fact(
            user_id=user_id,
            fact_text=test_fact_text,
            category="preference",
            entity="food",
            confidence=0.9,
            source="test",
        )
        test_results["tests"].append(
            {
                "name": "add_fact",
                "passed": test_fact_id is not None,
                "fact_id": test_fact_id,
            }
        )

        # Test 2: Retrieve the fact
        facts = fact_service.get_facts(user_id=user_id, category="preference")
        found_fact = next((f for f in facts if f.id == test_fact_id), None)
        test_results["tests"].append(
            {
                "name": "get_facts",
                "passed": found_fact is not None
                and found_fact.fact_text == test_fact_text,
                "facts_count": len(facts),
            }
        )

        # Test 3: Search facts
        search_results = fact_service.search_facts(
            user_id=user_id, query_text="Italian", category="preference"
        )
        found_in_search = any(f.id == test_fact_id for f in search_results)
        test_results["tests"].append(
            {
                "name": "search_facts",
                "passed": found_in_search,
                "search_results_count": len(search_results),
            }
        )

        # Test 4: Check for conflicts
        conflicts = fact_service.check_conflicts(
            user_id=user_id,
            fact_text="User prefers Italian cuisine",
            category="preference",
        )
        has_conflict = any(f.id == test_fact_id for f in conflicts)
        test_results["tests"].append(
            {
                "name": "check_conflicts",
                "passed": has_conflict,
                "conflicts_count": len(conflicts),
            }
        )

        # Test 5: Get user summary
        summary = fact_service.get_user_summary(user_id=user_id)
        test_results["tests"].append(
            {
                "name": "get_user_summary",
                "passed": summary["total_facts"] > 0,
                "summary": summary,
            }
        )

        # Cleanup: Deactivate the test fact
        if test_fact_id:
            fact_service.deactivate_fact(test_fact_id)
            test_results["tests"].append(
                {
                    "name": "deactivate_fact",
                    "passed": True,
                }
            )

        # Check if all tests passed
        test_results["success"] = all(test["passed"] for test in test_results["tests"])

    except Exception as e:
        test_results["success"] = False
        test_results["errors"].append(str(e))

    return test_results
