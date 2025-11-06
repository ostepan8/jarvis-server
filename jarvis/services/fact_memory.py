from __future__ import annotations

import sqlite3
import json
import datetime
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, asdict


@dataclass
class UserFact:
    """Represents a structured fact about a user."""

    id: Optional[int] = None
    user_id: int = 0
    fact_text: str = ""
    category: str = "general"  # personal_info, preference, relationship, memory, etc.
    entity: Optional[str] = None  # What/whom the fact is about
    confidence: float = 1.0  # 0.0 to 1.0
    source: str = "conversation"  # conversation, explicit, inferred
    context: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    is_active: bool = True
    related_fact_ids: Optional[List[int]] = None


class FactMemoryService:
    """Structured fact storage service using SQLite for user-specific facts."""

    def __init__(self, db_path: Optional[str] = None):
        """Initialize the fact memory service."""
        if db_path is None:
            import os

            db_path = os.getenv("AUTH_DB_PATH", "auth.db")
        self.db_path = db_path
        self._init_schema()

    def _init_schema(self) -> None:
        """Initialize the database schema."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                fact_text TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'general',
                entity TEXT,
                confidence REAL DEFAULT 1.0,
                source TEXT DEFAULT 'conversation',
                context TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT,
                is_active INTEGER DEFAULT 1,
                related_fact_ids TEXT,
                FOREIGN KEY (user_id)
                    REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_facts_user_id ON user_facts(user_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_facts_category ON user_facts(category)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_facts_entity ON user_facts(entity)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_facts_active ON user_facts(user_id, is_active)"
        )
        conn.commit()
        conn.close()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection."""
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def add_fact(
        self,
        user_id: int,
        fact_text: str,
        category: str = "general",
        entity: Optional[str] = None,
        confidence: float = 1.0,
        source: str = "conversation",
        context: Optional[str] = None,
        related_fact_ids: Optional[List[int]] = None,
    ) -> int:
        """Add a new fact about a user."""
        conn = self._get_connection()
        now = datetime.datetime.now().isoformat()

        related_ids_json = json.dumps(related_fact_ids) if related_fact_ids else None

        cursor = conn.execute(
            """
            INSERT INTO user_facts 
            (user_id, fact_text, category, entity, confidence, source, context,
             created_at, updated_at, is_active, related_fact_ids)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                fact_text,
                category,
                entity,
                confidence,
                source,
                context,
                now,
                now,
                1,
                related_ids_json,
            ),
        )
        fact_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return fact_id

    def get_facts(
        self,
        user_id: int,
        category: Optional[str] = None,
        entity: Optional[str] = None,
        active_only: bool = True,
        min_confidence: float = 0.0,
        limit: Optional[int] = None,
    ) -> List[UserFact]:
        """Retrieve facts for a user with optional filtering."""
        conn = self._get_connection()

        query = "SELECT * FROM user_facts WHERE user_id = ?"
        params: List[Any] = [user_id]

        if active_only:
            query += " AND is_active = 1"
        if category:
            query += " AND category = ?"
            params.append(category)
        if entity:
            query += " AND entity = ?"
            params.append(entity)
        query += " AND confidence >= ?"
        params.append(min_confidence)
        query += " ORDER BY confidence DESC, created_at DESC"
        if limit:
            query += " LIMIT ?"
            params.append(limit)

        cursor = conn.execute(query, params)
        rows = cursor.fetchall()

        facts = []
        columns = [desc[0] for desc in cursor.description]
        for row in rows:
            fact_dict = dict(zip(columns, row))
            if fact_dict.get("related_fact_ids"):
                try:
                    fact_dict["related_fact_ids"] = json.loads(
                        fact_dict["related_fact_ids"]
                    )
                except Exception:
                    fact_dict["related_fact_ids"] = None
            else:
                fact_dict["related_fact_ids"] = None
            fact_dict["is_active"] = bool(fact_dict["is_active"])
            facts.append(UserFact(**fact_dict))

        conn.close()
        return facts

    def search_facts(
        self,
        user_id: int,
        query_text: str,
        category: Optional[str] = None,
        limit: int = 10,
    ) -> List[UserFact]:
        """Search facts by text content."""
        conn = self._get_connection()

        sql_query = """
            SELECT * FROM user_facts 
            WHERE user_id = ? 
            AND is_active = 1 
            AND fact_text LIKE ?
        """
        params: List[Any] = [user_id, f"%{query_text}%"]

        if category:
            sql_query += " AND category = ?"
            params.append(category)

        sql_query += " ORDER BY confidence DESC, created_at DESC LIMIT ?"
        params.append(limit)

        cursor = conn.execute(sql_query, params)
        rows = cursor.fetchall()

        facts = []
        columns = [desc[0] for desc in cursor.description]
        for row in rows:
            fact_dict = dict(zip(columns, row))
            if fact_dict.get("related_fact_ids"):
                try:
                    fact_dict["related_fact_ids"] = json.loads(
                        fact_dict["related_fact_ids"]
                    )
                except Exception:
                    fact_dict["related_fact_ids"] = None
            fact_dict["is_active"] = bool(fact_dict["is_active"])
            facts.append(UserFact(**fact_dict))

        conn.close()
        return facts

    def update_fact(
        self,
        fact_id: int,
        fact_text: Optional[str] = None,
        category: Optional[str] = None,
        confidence: Optional[float] = None,
        context: Optional[str] = None,
    ) -> bool:
        """Update an existing fact."""
        conn = self._get_connection()

        updates = []
        params = []

        if fact_text is not None:
            updates.append("fact_text = ?")
            params.append(fact_text)
        if category is not None:
            updates.append("category = ?")
            params.append(category)
        if confidence is not None:
            updates.append("confidence = ?")
            params.append(confidence)
        if context is not None:
            updates.append("context = ?")
            params.append(context)

        if updates:
            updates.append("updated_at = ?")
            params.append(datetime.datetime.now().isoformat())
            params.append(fact_id)

            conn.execute(
                f"UPDATE user_facts SET {', '.join(updates)} WHERE id = ?", params
            )
            conn.commit()

        conn.close()
        return len(updates) > 0

    def deactivate_fact(self, fact_id: int) -> bool:
        """Mark a fact as inactive (soft delete)."""
        conn = self._get_connection()
        conn.execute(
            "UPDATE user_facts SET is_active = 0, updated_at = ? WHERE id = ?",
            (datetime.datetime.now().isoformat(), fact_id),
        )
        conn.commit()
        conn.close()
        return True

    def check_conflicts(
        self, user_id: int, fact_text: str, category: Optional[str] = None
    ) -> List[UserFact]:
        """Check for potentially conflicting facts."""
        # Simple implementation - can be enhanced with semantic similarity
        facts = self.get_facts(user_id, category=category, active_only=True)
        # Return facts that might conflict - this is a placeholder
        # A more sophisticated implementation would use embeddings or NLP
        conflicts = []
        for fact in facts:
            # Simple keyword overlap check
            fact_words = set(fact.fact_text.lower().split())
            new_words = set(fact_text.lower().split())
            overlap = len(fact_words & new_words) / max(len(fact_words | new_words), 1)
            if overlap > 0.3:  # Threshold for potential conflict
                conflicts.append(fact)
        return conflicts

    def get_user_summary(self, user_id: int) -> Dict[str, Any]:
        """Get a summary of all facts about a user organized by category."""
        facts = self.get_facts(user_id, active_only=True)
        summary: Dict[str, Any] = {
            "total_facts": len(facts),
            "by_category": {},
            "top_entities": {},
        }

        for fact in facts:
            # Group by category
            if fact.category not in summary["by_category"]:
                summary["by_category"][fact.category] = []
            summary["by_category"][fact.category].append(
                {
                    "text": fact.fact_text,
                    "entity": fact.entity,
                    "confidence": fact.confidence,
                }
            )

            # Track entities
            if fact.entity:
                if fact.entity not in summary["top_entities"]:
                    summary["top_entities"][fact.entity] = 0
                summary["top_entities"][fact.entity] += 1

        return summary
