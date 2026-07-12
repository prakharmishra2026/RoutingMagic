#!/usr/bin/env python3
"""
Caveman Quality Loop - Self-Improving Compression Quality

Implements the feedback loop for Caveman compression quality:
- Follow-up detection (re-asks, confusion signals)
- Explicit feedback command (/caveman-feedback)
- Auto-downgrade on quality issues
- Automatic prompt improvement for Caveman
- Lesson persistence
"""
import os
import json
import re
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict

QUALITY_DIR = Path.home() / ".routingmagic" / "quality"
QUALITY_DIR.mkdir(parents=True, exist_ok=True)

CAVEMAN_CONFIG_FILE = QUALITY_DIR / "caveman_config.json"
QUALITY_LESSONS_FILE = QUALITY_DIR / "caveman_lessons.json"
FEEDBACK_LOG_FILE = QUALITY_DIR / "feedback_log.jsonl"

# Default Caveman configuration
DEFAULT_CAVEMAN_CONFIG = {
    "level": "full",
    "auto_downgrade": True,
    "confusion_threshold": 2,
    "protected_patterns": [
        "code_block", "inline_code", "file_path", "url", "error", "json", "command"
    ],
    "validation_queries": [
        "Does the answer still contain all code blocks?",
        "Are error messages preserved exactly?",
        "Are file paths and URLs intact?",
        "Is the technical accuracy maintained?",
        "Would a developer understand this?",
    ],
    "compression_stats": {
        "total_sessions": 0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_savings_pct": 0.0,
        "downgrades": 0,
        "feedback_positive": 0,
        "feedback_negative": 0,
    }
}


@dataclass
class QualityLesson:
    """A learned lesson about compression quality."""
    timestamp: str
    trigger: str  # "confusion_signal", "explicit_feedback", "auto_downgrade"
    context: str  # What was being compressed
    issue: str    # What went wrong
    action_taken: str
    level_before: str
    level_after: str
    lesson_text: str


class CavemanQualityLoop:
    """Manages Caveman compression quality and self-improvement."""
    
    def __init__(self):
        self.config = self._load_config()
        self.lessons = self._load_lessons()
        self.session_confusion_count = 0
        self.session_feedback = None
        
    def _load_config(self) -> Dict:
        if CAVEMAN_CONFIG_FILE.exists():
            try:
                with open(CAVEMAN_CONFIG_FILE) as f:
                    return json.load(f)
            except Exception:
                pass
        return DEFAULT_CAVEMAN_CONFIG.copy()
    
    def _save_config(self):
        with open(CAVEMAN_CONFIG_FILE, "w") as f:
            json.dump(self.config, f, indent=2)
    
    def _load_lessons(self) -> List[Dict]:
        if QUALITY_LESSONS_FILE.exists():
            try:
                with open(QUALITY_LESSONS_FILE) as f:
                    return json.load(f)
            except Exception:
                pass
        return []
    
    def _save_lessons(self):
        with open(QUALITY_LESSONS_FILE, "w") as f:
            json.dump(self.lessons, f, indent=2)
    
    def _log_feedback(self, feedback_type: str, details: Dict):
        """Log feedback to JSONL file."""
        entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "type": feedback_type,
            **details
        }
        with open(FEEDBACK_LOG_FILE, "a") as f:
            f.write(json.dumps(entry) + "\n")
    
    # ===== Quality Guardrails =====
    
    def record_confusion_signal(self, context: str = ""):
        """Record a user confusion signal (re-ask, 'what?', 'explain')."""
        self.session_confusion_count += 1
        self.config["compression_stats"]["total_sessions"] = \
            self.config["compression_stats"].get("total_sessions", 0) + 1
        
        if self.session_confusion_count >= self.config["confusion_threshold"]:
            self._trigger_auto_downgrade(context)
    
    def record_explicit_feedback(self, feedback: str, context: str = ""):
        """Record explicit user feedback via /caveman-feedback command."""
        feedback = feedback.lower().strip()
        self.session_feedback = feedback
        
        self._log_feedback("explicit", {
            "feedback": feedback,
            "context": context[:200],
            "level": self.config["level"]
        })
        
        if "terse" in feedback or "brief" in feedback or "too short" in feedback:
            self.config["compression_stats"]["feedback_negative"] = \
                self.config["compression_stats"].get("feedback_negative", 0) + 1
            self._trigger_auto_downgrade(context, reason="explicit_feedback")
        elif "good" in feedback or "right" in feedback or "perfect" in feedback:
            self.config["compression_stats"]["feedback_positive"] = \
                self.config["compression_stats"].get("feedback_positive", 0) + 1
        
        self._save_config()
    
    def _trigger_auto_downgrade(self, context: str, reason: str = "confusion_signals"):
        """Auto-downgrade compression level due to quality issues."""
        level_order = ["ultra", "full", "lite"]
        current = self.config["level"]
        
        if current in level_order and level_order.index(current) < len(level_order) - 1:
            new_level = level_order[level_order.index(current) + 1]
            
            # Record lesson
            lesson = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "trigger": "auto_downgrade",
                "reason": reason,
                "context": context[:500],
                "level_before": current,
                "level_after": level_order[level_order.index(current) + 1],
                "lesson_text": f"Auto-downgraded from {current} to {level_order[level_order.index(current) + 1]} due to {reason}: {context[:200]}"
            }
            self.lessons.append(lesson)
            self._save_lessons()
            
            # Update config
            self.config["level"] = level_order[level_order.index(current) + 1]
            self.config["compression_stats"]["downgrades"] = \
                self.config["compression_stats"].get("downgrades", 0) + 1
            self._save_config()
            
            return True, level_order[level_order.index(current) + 1]
        
        return False, current
    
    def validate_compression(self, original: str, compressed: str) -> Tuple[bool, List[str]]:
        """Validate compression quality against protected patterns."""
        issues = []
        
        # Check code blocks preserved
        orig_code = re.findall(r'```[\s\S]*?```', original)
        comp_code = re.findall(r'```[\s\S]*?```', compressed)
        if len(orig_code) != len(comp_code):
            issues.append(f"Code blocks lost: {len(orig_code)} → {len(comp_code)}")
        
        # Check inline code
        orig_inline = re.findall(r'`[^`]+`', original)
        comp_inline = re.findall(r'`[^`]+`', compressed)
        if len(orig_inline) != len(comp_inline):
            issues.append(f"Inline code lost: {len(orig_inline)} → {len(comp_inline)}")
        
        # Check file paths
        orig_paths = re.findall(r'(?:^|[\s\(\[\{])(?:[~/]|\.[\w/])[\w\.\-/]+\.\w+', original)
        comp_paths = re.findall(r'(?:^|[\s\(\[\{])(?:[~/]|\.[\w/])[\w\.\-/]+\.\w+', compressed)
        if len(set(orig_paths) - set(comp_paths)) > 0:
            issues.append("Some file paths lost")
        
        # Check URLs
        orig_urls = set(re.findall(r'https?://[^\s\)\]\}>]+', original))
        comp_urls = set(re.findall(r'https?://[^\s\)\]\}>]+', compressed))
        if orig_urls - comp_urls:
            issues.append("Some URLs lost")
        
        # Check error messages
        orig_errors = re.findall(r'(?:Error|Exception|Traceback|Error:)', original, re.IGNORECASE)
        comp_errors = re.findall(r'(?:Error|Exception|Traceback|Error:)', compressed, re.IGNORECASE)
        if len(orig_errors) != len(comp_errors):
            issues.append("Error messages may be truncated")
        
        return len(issues) == 0, issues
    
    def get_validation_prompt(self, original: str, compressed: str) -> str:
        """Generate a validation prompt for LLM-based quality check."""
        return f"""Validate this compression. Original vs Compressed:

ORIGINAL ({len(original)} chars):
{original[:2000]}...

COMPRESSED ({len(compressed)} chars):
{compressed[:2000]}...

Check: Are all code blocks, file paths, URLs, error messages, and technical details preserved? Is the answer still accurate and usable?

Reply YES/NO and list any issues."""

    # ===== Self-Improvement Loop =====
    
    def generate_improved_prompt(self, failed_examples: List[Dict]) -> str:
        """Generate improved Caveman prompt based on failure patterns."""
        issues = {}
        for ex in failed_examples:
            for issue in ex.get("issues", []):
                issues[issue] = issues.get(issue, 0) + 1
        
        prompt = "IMPROVED CAVEMAN PROMPT:\n\n"
        prompt += "Previous failures:\n"
        for issue, count in sorted(issues.items(), key=lambda x: -x[1])[:5]:
            prompt += f"  - {issue} ({count}x)\n"
        
        prompt += "\nImproved compression rules:\n"
        prompt += "1. ALWAYS preserve: code blocks, inline code, file paths, URLs, error messages\n"
        prompt += "2. For technical explanations: keep all variable names, function names, exact commands\n"
        prompt += "3. If user re-asks or says 'what?', compression was too aggressive\n"
        prompt += "4. Preserve all JSON, YAML, config snippets exactly\n"
        prompt += "5. Never abbreviate technical terms (API, JWT, SQL, etc.)\n"
        
        return prompt
    
    def auto_improve_from_sessions(self, min_sessions: int = 10) -> bool:
        """Analyze recent sessions and improve Caveman prompts."""
        from metrics_collector import get_savings_summary
        
        savings = get_savings_summary(days=7)
        
        if savings.get("total_sessions", 0) < min_sessions:
            return False
        
        # Get sessions with quality issues
        from metrics_collector import DB_PATH
        import sqlite3
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT session_id, model_used, task_type, caveman_output_savings_pct,
                   confusion_signals, user_feedback, caveman_level
            FROM sessions
            WHERE timestamp >= datetime('now', '-7 days')
            AND (confusion_signals > 0 OR user_feedback IS NOT NULL)
            ORDER BY timestamp DESC
            LIMIT 50
        """)
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            return False
        
        # Analyze patterns
        failed_examples = []
        for row in rows:
            if row[4] > 0 or row[5]:  # confusion_signals or feedback
                failed_examples.append({
                    "model": row[1],
                    "task": row[2],
                    "savings": row[3],
                    "confusion": row[4],
                    "feedback": row[5],
                    "level": row[6]
                })
        
        if failed_examples:
            improved_prompt = self.generate_improved_prompt(failed_examples)
            
            # Save improved prompt as lesson
            lesson = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "trigger": "auto_improve",
                "failed_count": len(failed_examples),
                "improved_prompt": improved_prompt,
                "lesson_text": f"Auto-generated improved Caveman prompt from {len(failed_examples)} quality failures"
            }
            self.lessons.append(lesson)
            self._save_lessons()
            
            return True
        
        return False
    
    def get_status(self) -> Dict:
        """Get current quality status."""
        return {
            "level": self.config["level"],
            "auto_downgrade": self.config["auto_downgrade"],
            "confusion_threshold": self.config["confusion_threshold"],
            "session_confusion": self.session_confusion_count,
            "session_feedback": self.session_feedback,
            "stats": self.config["compression_stats"],
            "recent_lessons": self.lessons[-5:] if self.lessons else [],
        }
    
    def reset_session(self):
        """Reset session counters."""
        self.session_confusion_count = 0
        self.session_feedback = None


# Global instance
_quality_loop = None

def get_quality_loop() -> CavemanQualityLoop:
    global _quality_loop
    if _quality_loop is None:
        _quality_loop = CavemanQualityLoop()
    return _quality_loop