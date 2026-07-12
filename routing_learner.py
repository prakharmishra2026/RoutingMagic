#!/usr/bin/env python3
"""
Routing Learner - Self-Improving Model Selection

Learns optimal model for each task type based on:
- Success rate (no re-ask, no confusion)
- Latency
- Token efficiency
- User feedback

Dynamically updates smart_route() logic.
"""
import os
import json
import sqlite3
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from collections import defaultdict
from threading import Lock

LEARN_DIR = Path.home() / ".routingmagic" / "learning"
LEARN_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = LEARN_DIR / "routing_learning.db"
LESSONS_FILE = LEARN_DIR / "lessons.md"

# Task type keywords for classification
TASK_KEYWORDS = {
    "reasoning": [
        "prove", "derive", "formal", "axiom", "theorem", "math", "logic",
        "step by step", "chain of thought", "deep analysis", "critically",
        "algorithm", "complexity", "optimize", "tradeoff", "trade-off"
    ],
    "coding": [
        "code", "fix bug", "refactor", "write function", "regex", "sql",
        "snippet", "debug", "react", "css", "html", "typescript", "python",
        "script", "api", "endpoint", "database", "frontend", "backend",
        "component", "function", "class", "module"
    ],
    "agentic": [
        "agent", "tool", "workflow", "pipeline", "orchestrat", "n8n",
        "webhook", "integration", "automate", "mcp", "function call",
        "json extraction", "structure this", "automation"
    ],
    "analysis": [
        "analyze", "compare", "evaluate", "assess", "summarize", "explain",
        "review", "audit", "security", "performance", "bottleneck",
        "pros and cons", "tradeoffs", "architecture"
    ],
    "general": [
        "what is", "how does", "define", "list", "quick", "simple", "basic",
        "explain", "describe", "tell me"
    ]
}

# Base routing weights per task type (updated by learner)
ROUTING_WEIGHTS = {
    "reasoning": {
        "model_score": 0.4,
        "latency_penalty": 0.1,
        "token_efficiency": 0.2,
        "success_rate": 0.3
    },
    "coding": {
        "model_score": 0.35,
        "latency_penalty": 0.15,
        "token_efficiency": 0.2,
        "success_rate": 0.3
    },
    "agentic": {
        "model_score": 0.3,
        "latency_penalty": 0.2,
        "token_efficiency": 0.15,
        "success_rate": 0.35
    },
    "analysis": {
        "model_score": 0.35,
        "latency_penalty": 0.1,
        "token_efficiency": 0.25,
        "success_rate": 0.3
    },
    "general": {
        "model_score": 0.25,
        "latency_penalty": 0.2,
        "token_efficiency": 0.25,
        "success_rate": 0.3
    }
}

DB_LOCK = Lock()

def _init_db():
    with DB_LOCK:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS routing_outcomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                task_type TEXT NOT NULL,
                model_used TEXT NOT NULL,
                success INTEGER NOT NULL,
                reasked INTEGER NOT NULL,
                confusion_signals INTEGER DEFAULT 0,
                latency_ms REAL NOT NULL,
                input_tokens INTEGER NOT NULL,
                output_tokens INTEGER NOT NULL,
                caveman_savings_pct REAL DEFAULT 0,
                user_feedback TEXT,
                council_invoked INTEGER DEFAULT 0,
                fallback_tier INTEGER DEFAULT 0,
                effort_level TEXT DEFAULT 'medium'
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS model_quality (
                model TEXT NOT NULL,
                task_type TEXT NOT NULL,
                total_calls INTEGER DEFAULT 0,
                success_count INTEGER DEFAULT 0,
                reask_count INTEGER DEFAULT 0,
                total_latency_ms REAL DEFAULT 0,
                total_input_tokens INTEGER DEFAULT 0,
                total_output_tokens INTEGER DEFAULT 0,
                total_caveman_savings REAL DEFAULT 0,
                positive_feedback INTEGER DEFAULT 0,
                negative_feedback INTEGER DEFAULT 0,
                last_updated TEXT NOT NULL,
                PRIMARY KEY (model, task_type)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS routing_lessons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                lesson_type TEXT NOT NULL,
                task_type TEXT,
                model TEXT,
                lesson_text TEXT NOT NULL,
                evidence TEXT,
                applied INTEGER DEFAULT 0
            )
        """)
        conn.commit()
        conn.close()

_init_db()

def classify_task(prompt: str) -> str:
    """Classify prompt into task type."""
    prompt_lower = prompt.lower()
    scores = defaultdict(int)
    
    for task_type, keywords in TASK_KEYWORDS.items():
        for kw in keywords:
            if kw in prompt_lower:
                scores[task_type] += 1
    
    if not scores:
        return "general"
    
    return max(scores, key=scores.get)

def record_outcome(
    task_type: str,
    model: str,
    success: bool,
    reasked: bool,
    confusion_signals: int,
    latency_ms: float,
    input_tokens: int,
    output_tokens: int,
    caveman_savings: float,
    user_feedback: str = None,
    council: bool = False,
    fallback_tier: int = 0,
    effort: str = "medium"
):
    """Record a routing outcome for learning."""
    with DB_LOCK:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Record raw outcome
        cursor.execute("""
            INSERT INTO routing_outcomes 
            (timestamp, task_type, model_used, success, reasked, confusion_signals,
             latency_ms, input_tokens, output_tokens, caveman_savings_pct,
             user_feedback, council_invoked, fallback_tier, effort_level)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.utcnow().isoformat() + "Z",
            task_type, model, int(success), int(reasked), confusion_signals,
            latency_ms, input_tokens, output_tokens, caveman_savings,
            user_feedback, int(council), fallback_tier, effort
        ))
        
        # Update aggregated model quality
        cursor.execute("""
            INSERT INTO model_quality 
            (model, task_type, total_calls, success_count, reask_count,
             total_latency_ms, total_input_tokens, total_output_tokens,
             total_caveman_savings, positive_feedback, negative_feedback, last_updated)
            VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(model, task_type) DO UPDATE SET
                total_calls = total_calls + 1,
                success_count = success_count + ?,
                reask_count = reask_count + ?,
                total_latency_ms = total_latency_ms + ?,
                total_input_tokens = total_input_tokens + ?,
                total_output_tokens = total_output_tokens + ?,
                total_caveman_savings = total_caveman_savings + ?,
                positive_feedback = positive_feedback + ?,
                negative_feedback = negative_feedback + ?,
                last_updated = ?
        """, (
            model, task_type,
            1 if success else 0, 1 if reasked else 0,
            latency_ms, input_tokens, output_tokens,
            caveman_savings,
            1 if user_feedback == "positive" else 0,
            1 if user_feedback == "negative" else 0,
            datetime.utcnow().isoformat() + "Z",
            1 if success else 0, 1 if reasked else 0,
            latency_ms, input_tokens, output_tokens,
            caveman_savings,
            1 if user_feedback == "positive" else 0,
            1 if user_feedback == "negative" else 0,
            datetime.utcnow().isoformat() + "Z"
        ))
        conn.commit()
        conn.close()


def get_model_quality(model: str, task_type: str) -> Optional[Dict]:
    """Get aggregated quality metrics for a model/task combination."""
    with DB_LOCK:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT total_calls, success_count, reask_count, total_latency_ms,
                   total_input_tokens, total_output_tokens, total_caveman_savings,
                   positive_feedback, negative_feedback
            FROM model_quality
            WHERE model = ? AND task_type = ?
        """, (model, task_type))
        row = cursor.fetchone()
        conn.close()
        
        if row and row[0] > 0:
            calls = row[0]
            return {
                "model": model,
                "task_type": task_type,
                "calls": calls,
                "success_rate": row[1] / calls if calls > 0 else 0,
                "reask_rate": row[2] / calls if calls > 0 else 0,
                "avg_latency_ms": row[3] / calls if calls > 0 else 0,
                "avg_input_tokens": row[4] / calls if calls > 0 else 0,
                "avg_output_tokens": row[5] / calls if calls > 0 else 0,
                "avg_caveman_savings": row[6] / calls if calls > 0 else 0,
                "positive_feedback": row[7],
                "negative_feedback": row[8],
                "feedback_score": (row[7] - row[8]) / max(calls, 1)
            }
    return None


def get_best_model_for_task(task_type: str, available_models: List[str]) -> Optional[str]:
    """Get best model for task based on learned quality."""
    best_model = None
    best_score = -1
    
    for model in available_models:
        quality = get_model_quality(model, task_type)
        if not quality:
            continue
        
        # Weighted score based on task type weights
        weights = ROUTING_WEIGHTS.get(task_type, ROUTING_WEIGHTS["general"])
        
        score = (
            weights["model_score"] * quality["success_rate"] +
            weights["latency_penalty"] * (1 / max(quality["avg_latency_ms"] / 1000, 1)) +
            weights["token_efficiency"] * (quality["avg_caveman_savings"] / 100) +
            weights["success_rate"] * quality["success_rate"]
        )
        
        if score > best_score:
            best_score = score
            best_model = model
    
    return best_model


def record_lesson(lesson_type: str, task_type: str, model: str, 
                  lesson_text: str, evidence: str = ""):
    """Record a learned lesson."""
    with DB_LOCK:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO routing_lessons 
            (timestamp, lesson_type, task_type, model, lesson_text, evidence)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            datetime.utcnow().isoformat() + "Z",
            lesson_type, task_type, model, lesson_text, evidence
        ))
        conn.commit()
        conn.close()
    
    # Also append to markdown lessons file
    with open(LESSONS_FILE, "a") as f:
        f.write(f"\n## {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n")
        f.write(f"- **Type**: {lesson_type}\n")
        f.write(f"- **Task**: {task_type}\n")
        f.write(f"- **Model**: {model}\n")
        f.write(f"- **Lesson**: {lesson_text}\n")
        if evidence:
            f.write(f"- **Evidence**: {evidence}\n")
        f.write("\n")


def get_recent_lessons(limit: int = 20) -> List[Dict]:
    """Get recent lessons."""
    with DB_LOCK:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT timestamp, lesson_type, task_type, model, lesson_text, evidence
            FROM routing_lessons
            ORDER BY timestamp DESC
            LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        conn.close()
    
    return [
        {
            "timestamp": r[0],
            "lesson_type": r[1],
            "task_type": r[2],
            "model": r[3],
            "lesson_text": r[4],
            "evidence": r[5]
        }
        for r in rows
    ]


def auto_improve_routing() -> Dict:
    """Analyze recent outcomes and suggest routing improvements."""
    with DB_LOCK:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Get recent outcomes (last 7 days)
        cutoff = (datetime.utcnow() - timedelta(days=7)).isoformat() + "Z"
        cursor.execute("""
            SELECT task_type, model_used, 
                   AVG(CASE WHEN success=1 THEN 1.0 ELSE 0.0 END) as success_rate,
                   AVG(reasked) as reask_rate,
                   AVG(confusion_signals) as avg_confusion,
                   AVG(latency_ms) as avg_latency,
                   AVG(caveman_savings_pct) as avg_caveman,
                   COUNT(*) as calls
            FROM routing_outcomes
            WHERE timestamp >= ?
            GROUP BY task_type, model_used
            HAVING calls >= 5
            ORDER BY task_type, success_rate DESC
        """, (cutoff,))
        rows = cursor.fetchall()
        conn.close()
    
    improvements = []
    for row in rows:
        task_type, model, success_rate, reask_rate, confusion, latency, caveman, calls = row
        
        # Flag underperforming models
        if success_rate < 0.7:
            improvements.append({
                "type": "underperforming_model",
                "task_type": task_type,
                "model": model,
                "issue": f"Low success rate: {success_rate:.1%}",
                "recommendation": f"Deprioritize {model} for {task_type}"
            })
        
        if reask_rate > 0.3:
            improvements.append({
                "type": "high_reask_rate",
                "task_type": task_type,
                "model": model,
                "issue": f"High re-ask rate: {reask_rate:.1%}",
                "recommendation": f"Consider alternative model for {task_type}"
            })
        
        if confusion > 1.5:
            improvements.append({
                "type": "high_confusion",
                "task_type": task_type,
                "model": model,
                "issue": f"High confusion signals: {confusion:.1f}",
                "recommendation": "Model responses unclear, try different model"
            })
    
    return {
        "analyzed_calls": sum(r[6] for r in rows),
        "models_analyzed": len(rows),
        "improvements": improvements
    }


def update_routing_weights_from_learning():
    """Update ROUTING_WEIGHTS based on learned patterns."""
    # This would dynamically adjust weights based on what works
    # For now, we just record the suggestion
    record_lesson(
        "weight_adjustment",
        "general",
        "system",
        "Consider adjusting routing weights based on empirical outcomes",
        "Auto-generated from auto_improve_routing()"
    )


def get_learning_status() -> Dict:
    """Get current learning system status."""
    with DB_LOCK:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Total outcomes
        cursor.execute("SELECT COUNT(*) FROM routing_outcomes")
        total_outcomes = cursor.fetchone()[0]
        
        # Model quality entries
        cursor.execute("SELECT COUNT(*) FROM model_quality")
        model_entries = cursor.fetchone()[0]
        
        # Lessons
        cursor.execute("SELECT COUNT(*) FROM routing_lessons")
        lessons = cursor.fetchone()[0]
        
        # Recent activity
        cutoff = (datetime.utcnow() - timedelta(days=7)).isoformat() + "Z"
        cursor.execute("SELECT COUNT(*) FROM routing_outcomes WHERE timestamp >= ?", (cutoff,))
        recent = cursor.fetchone()[0]
        
        conn.close()
    
    return {
        "total_outcomes": total_outcomes,
        "model_quality_entries": model_entries,
        "lessons_recorded": lessons,
        "last_7_days": recent,
        "routing_weights": ROUTING_WEIGHTS
    }


# Global learning instance
_routing_learner = None

def get_routing_learner() -> "RoutingLearner":
    global _routing_learner
    if _routing_learner is None:
        _routing_learner = RoutingLearner()
    return _routing_learner


class RoutingLearner:
    """High-level routing learner interface."""
    
    def __init__(self):
        self.lesson_count = 0
    
    def record(self, task_type: str, model: str, success: bool, reasked: bool,
               confusion: int, latency: float, in_tokens: int, out_tokens: int,
               caveman_savings: float, feedback: str = None, council: bool = False,
               fallback_tier: int = 0, effort: str = "medium"):
        """Record outcome and auto-learn."""
        record_outcome(task_type, model, success, reasked, confusion,
                      latency, in_tokens, out_tokens, caveman_savings,
                      feedback, council, fallback_tier, effort)
        
        # Auto-record lessons from patterns
        if not success or reasked:
            self._record_failure_lesson(task_type, model, reasked, confusion)
        
        if feedback == "negative":
            record_lesson("negative_feedback", task_type, model,
                         "User gave negative feedback on response quality",
                         f"Model: {model}, Task: {task_type}")
        elif feedback == "positive":
            record_lesson("positive_feedback", task_type, model,
                         "User satisfied with response quality",
                         f"Model: {model}, Task: {task_type}")
    
    def _record_failure_lesson(self, task_type: str, model: str, reasked: bool, confusion: int):
        """Record lesson from failure patterns."""
        if reasked:
            record_lesson("reask_pattern", task_type, model,
                         f"User re-asked after {model} response - model may not handle {task_type} well",
                         f"Reasked: {reasked}, Confusion: {confusion}")
        
        if confusion >= 2:
            record_lesson("high_confusion", task_type, model,
                         f"High confusion signals ({confusion}) for {model} on {task_type}",
                         f"Confusion count: {confusion}")
    
    def get_recommendations(self, task_type: str, available_models: List[str]) -> List[Tuple[str, float]]:
        """Get model recommendations for task type with scores."""
        recommendations = []
        for model in available_models:
            quality = get_model_quality(model, task_type)
            if not quality:
                continue
            
            weights = ROUTING_WEIGHTS.get(task_type, ROUTING_WEIGHTS["general"])
            score = (
                weights["model_score"] * quality["success_rate"] +
                weights["latency_penalty"] * (1 / max(quality["avg_latency_ms"] / 1000, 1)) +
                weights["token_efficiency"] * (quality["avg_caveman_savings"] / 100) +
                weights["success_rate"] * quality["success_rate"]
            )
            recommendations.append((model, round(score, 3)))
        
        recommendations.sort(key=lambda x: -x[1])
        return recommendations
    
    def get_stats(self) -> Dict:
        return get_learning_status()


# Backward compatibility
class RoutingLearner:
    """Legacy class name compatibility."""
    pass