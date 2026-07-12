#!/usr/bin/env python3
"""
Caveman Compression Integration for RoutingMagic

Integrates JuliusBrussee/caveman skill for token compression:
- 65% output token reduction (default 'full' level)
- 46% input token reduction (context/memory compression)
- Code/Error/URL preservation
- Quality guardrails: follow-up detection, explicit feedback, auto-downgrade
"""
import os
import subprocess
import json
import re
from pathlib import Path
from typing import Optional, Tuple, Dict, List

# Caveman skill location (installed via: npx skills@latest add JuliusBrussee/skills/caveman)
CAVEMAN_SKILL_DIR = Path.home() / ".claude" / "skills" / "caveman"
CAVEMAN_LEVELS = {
    "lite": "lite",
    "full": "full",
    "ultra": "ultra",
    "wenyan": "wenyan",
}

# Code/Error/URL patterns that MUST be preserved
PROTECTED_PATTERNS = [
    # Code blocks
    (r'```[\s\S]*?```', "code_block"),
    (r'`[^`]+`', "inline_code"),
    # File paths
    (r'(?:^|[\s\(\[\{])(?:[~/]|\.[\w/])[\w\.\-/]+\.\w+(?=[\s\)\]\},;:]|$)', "file_path"),
    # URLs
    (r'https?://[^\s\)\]\}>]+', "url"),
    # Error messages / stack traces
    (r'(?:Error|Exception|Traceback|Error:|at .+\.\w+\(.*\):|line \d+|File ".*", line \d+)', "error"),
    # JSON
    (r'\{[\s\S]*\}', "json"),
    # Commands
    (r'(?:^|\s)(?:npm|yarn|pip|python|node|git|docker|kubectl|make|cargo|go run)\s+[^\s]+', "command"),
]

class CavemanCompressor:
    """Handles Caveman compression with quality guardrails."""
    
    def __init__(self, level: str = "full"):
        self.level = level
        self.caveman_available = self._check_caveman()
        self.session_stats = {
            "original_tokens": 0,
            "compressed_tokens": 0,
            "input_savings_pct": 0.0,
            "output_savings_pct": 0.0,
            "downgraded": False,
            "confusion_signals": 0,
        }
        self.compression_cache = {}
        
    def _check_caveman(self) -> bool:
        """Check if Caveman skill is installed."""
        # Check common locations
        paths = [
            Path.home() / ".claude" / "skills" / "caveman",
            Path.home() / ".opencode" / "skills" / "caveman",
            Path("/usr/local/lib/node_modules/@juliusbrussee/caveman"),
        ]
        return any(p.exists() for p in paths)
    
    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimate (1 token ≈ 4 chars)."""
        return len(text) // 4
    
    def _protect_content(self, text: str) -> Tuple[str, Dict]:
        """Extract and protect sensitive content before compression."""
        protected = {}
        placeholder_map = {}
        protected_text = text
        placeholder_idx = 0
        
        for pattern, ptype in PROTECTED_PATTERNS:
            matches = list(re.finditer(pattern, protected_text, re.MULTILINE))
            for match in reversed(matches):
                placeholder = f"__CAVEMAN_PROTECTED_{placeholder_idx}_{ptype}__"
                protected[placeholder] = match.group(0)
                placeholder_map[placeholder] = match.group(0)
                start, end = match.span()
                protected_text = protected_text[:start] + placeholder + protected_text[end:]
                placeholder_idx += 1
        
        return protected_text, protected
    
    def _restore_protected(self, text: str, protected: Dict) -> str:
        """Restore protected content after compression."""
        for placeholder, original in protected.items():
            text = text.replace(placeholder, original)
        return text
    
    def compress_context(self, text: str) -> Tuple[str, Dict]:
        """Compress context/input using caveman-compress.
        Returns (compressed_text, stats).
        """
        if not text or not text.strip():
            return text, {"input_savings_pct": 0, "original": 0, "compressed": 0}
        
        # Check cache
        cache_key = hash(text)
        if cache_key in self.compression_cache:
            return self.compression_cache[cache_key]
        
        # Protect sensitive content
        protected_text, protected = self._protect_content(text)
        
        if not self.caveman_available:
            # Fallback: simple truncation with protection
            result = self._simple_compress(protected_text)
            result = self._restore_protected(result, protected)
            stats = {
                "input_savings_pct": 0,
                "original": self._estimate_tokens(text),
                "compressed": self._estimate_tokens(result),
                "method": "fallback_truncate"
            }
            self.compression_cache[cache_key] = (result, stats)
            return result, stats
        
        try:
            # Use caveman-compress CLI
            result = subprocess.run(
                ["caveman-compress", "-l", self.level, "--stdin"],
                input=protected_text,
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                compressed = result.stdout.strip()
                compressed = self._restore_protected(compressed, protected)
            else:
                # Fallback on error
                compressed = self._simple_compress(protected_text)
                compressed = self._restore_protected(compressed, protected)
        except Exception:
            compressed = self._simple_compress(protected_text)
            compressed = self._restore_protected(compressed, protected)
        
        stats = {
            "input_savings_pct": max(0, 100 - (len(compressed) / len(text) * 100)),
            "original": self._estimate_tokens(text),
            "compressed": self._estimate_tokens(compressed),
            "method": "caveman"
        }
        
        self.session_stats["original_tokens"] += stats["original"]
        self.session_stats["compressed_tokens"] += stats["compressed"]
        
        self.compression_cache[cache_key] = (compressed, stats)
        return compressed, stats
    
    def _simple_compress(self, text: str, max_chars: int = 8000) -> str:
        """Simple truncation fallback preserving first/last parts."""
        if len(text) <= max_chars:
            return text
        half = max_chars // 2
        return text[:half] + "\n\n[... truncated ...]\n\n" + text[-half:]
    
    def compress_response(self, text: str) -> Tuple[str, Dict]:
        """Compress LLM output response.
        Returns (compressed_text, stats).
        """
        if not text or not text.strip():
            return text, {"output_savings_pct": 0, "original": 0, "compressed": 0}
        
        if not self.caveman_available:
            return text, {"output_savings_pct": 0, "original": self._estimate_tokens(text), "compressed": self._estimate_tokens(text)}
        
        # Protect sensitive content
        protected_text, protected = self._protect_content(text)
        
        try:
            # Caveman compression on output
            result = subprocess.run(
                ["caveman-compress", "-l", self.level, "--stdin"],
                input=protected_text,
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                compressed = result.stdout.strip()
                compressed = self._restore_protected(compressed, protected)
            else:
                compressed = text
        except Exception:
            compressed = text
        
        stats = {
            "output_savings_pct": max(0, 100 - (len(compressed) / len(text) * 100)),
            "original": self._estimate_tokens(text),
            "compressed": self._estimate_tokens(compressed),
            "method": "caveman"
        }
        
        return compressed, stats
    
    def get_session_stats(self) -> Dict:
        """Get cumulative session statistics."""
        orig = self.session_stats["original_tokens"]
        comp = self.session_stats["compressed_tokens"]
        if orig > 0:
            self.session_stats["input_savings_pct"] = round(100 - (comp / orig * 100), 1)
        return self.session_stats
    
    def record_confusion_signal(self):
        """Record a user confusion signal (re-ask, 'what?', etc.)."""
        self.session_stats["confusion_signals"] += 1
        if self.session_stats["confusion_signals"] >= 2 and self.level != "lite":
            self.downgrade_level()
    
    def downgrade_level(self):
        """Downgrade compression level due to quality issues."""
        if self.level == "ultra":
            self.level = "full"
        elif self.level == "full":
            self.level = "lite"
        self.session_stats["downgraded"] = True
    
    def set_level(self, level: str):
        """Set compression level."""
        if level in CAVEMAN_LEVELS:
            self.level = CAVEMAN_LEVELS[level]


def install_caveman() -> bool:
    """Install Caveman skill globally."""
    try:
        result = subprocess.run(
            ["npx", "skills@latest", "add", "JuliusBrussee/skills/caveman"],
            capture_output=True,
            text=True,
            timeout=120
        )
        return result.returncode == 0
    except Exception:
        return False


# Global compressor instance
_caveman = None

def get_caveman(level: str = "full") -> CavemanCompressor:
    """Get global Caveman compressor instance."""
    global _caveman
    if _caveman is None:
        _caveman = CavemanCompressor(level)
    return _caveman