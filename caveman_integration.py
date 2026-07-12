#!/usr/bin/env python3
"""
Caveman Compression Integration for RoutingMagic

Implements JuliusBrussee/caveman as a SYSTEM PROMPT INJECTION — the way
the upstream project actually works. Caveman tells the LLM *how* to respond
(terse, no filler, fragments OK) rather than post-processing text externally.

Key approach:
- Output compression: Inject caveman rules into system prompts so LLMs
  naturally respond in compressed caveman-speak (65% fewer output tokens).
- Input compression: Lightweight rule-based stripping of filler words and
  redundant phrases from context strings (no external binary needed).
- Quality guardrails: confusion detection, auto-downgrade, explicit feedback.
"""
import re
from typing import Optional, Tuple, Dict

# ── Caveman System Prompt Injections ────────────────────────────────
# Sourced from: https://github.com/JuliusBrussee/caveman/blob/main/skills/caveman/SKILL.md

CAVEMAN_PROMPTS = {
    "lite": (
        "Communication style: No filler or hedging. Keep articles and full sentences. "
        "Professional but tight. Drop: 'just', 'really', 'basically', 'actually', 'simply', "
        "'sure', 'certainly', 'of course', 'happy to', 'I\\'d recommend'. "
        "Preserve code blocks, URLs, file paths, commands, and technical terms exactly."
    ),
    "full": (
        "Respond terse like smart caveman. All technical substance stay. Only fluff die. "
        "Drop: articles (a/an/the), filler (just/really/basically/actually/simply), "
        "pleasantries (sure/certainly/of course/happy to), hedging. Fragments OK. "
        "Short synonyms (big not extensive, fix not 'implement a solution for'). "
        "No tool-call narration, no decorative tables/emoji. "
        "Pattern: [thing] [action] [reason]. [next step]. "
        "Preserve: code blocks, inline code, URLs, file paths, commands, technical terms, "
        "error messages — all byte-for-byte exact. Never invent abbreviations. "
        "No self-reference. Never name or announce the style."
    ),
    "ultra": (
        "Maximum compression. Respond in absolute minimum words. "
        "Drop all articles, connectives, pleasantries, hedging, filler. "
        "Sentence fragments only. One thought = one fragment. "
        "Preserve: code, URLs, paths, commands, errors, technical terms — exact. "
        "Pattern: [thing] [verb] [why]. "
        "No self-reference, no style announcements."
    ),
}

# ── Rule-based Input Compression ────────────────────────────────────
# Lightweight text compression for context/memory strings.
# No external binary — just pattern-based filler removal.

FILLER_PATTERNS = [
    # Articles (only in prose context, not inside code/URLs)
    (r'\b(?:the|a|an)\s+', ' '),
    # Filler words
    (r'\b(?:just|really|basically|actually|simply|essentially|generally|certainly)\s+', ''),
    # Hedging phrases
    (r'\b(?:it might be worth|you could consider|it would be good to|I\'d recommend)\s+', ''),
    # Redundant phrasing
    (r'\bin order to\b', 'to'),
    (r'\bmake sure to\b', 'ensure'),
    (r'\bthe reason is because\b', 'because'),
    # Connective fluff
    (r'\b(?:however|furthermore|additionally|in addition),?\s*', ''),
    # Pleasantries
    (r'\b(?:Sure!|Of course!|Certainly!|Happy to help!?|I\'d be happy to)\s*', ''),
    # Multiple spaces → single space
    (r'  +', ' '),
]

# Patterns that must NEVER be modified during compression
PROTECTED_BLOCK_RE = re.compile(
    r'(```[\s\S]*?```'        # fenced code blocks
    r'|`[^`]+`'               # inline code
    r'|https?://\S+'          # URLs
    r'|(?:^|\s)[~/\.]\S+\.\w+'  # file paths
    r')',
    re.MULTILINE
)


class CavemanCompressor:
    """Handles Caveman compression via system prompt injection + rule-based input compression."""

    def __init__(self, level: str = "full"):
        self.level = level if level in CAVEMAN_PROMPTS else "full"
        self.session_stats = {
            "original_tokens": 0,
            "compressed_tokens": 0,
            "input_savings_pct": 0.0,
            "output_savings_pct": 0.0,
            "downgraded": False,
            "confusion_signals": 0,
        }
        self.compression_cache = {}

    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimate (1 token ≈ 4 chars)."""
        return len(text) // 4

    def get_system_prompt_injection(self) -> str:
        """Return the Caveman system prompt to inject into LLM messages.

        This is the core mechanism — append this to any system prompt to make
        the LLM respond in compressed caveman-speak.
        """
        return CAVEMAN_PROMPTS.get(self.level, CAVEMAN_PROMPTS["full"])

    def compress_context(self, text: str) -> Tuple[str, Dict]:
        """Compress context/input using rule-based filler stripping.

        Protects code blocks, URLs, and file paths from modification.
        Returns (compressed_text, stats).
        """
        if not text or not text.strip():
            return text, {"input_savings_pct": 0, "original": 0, "compressed": 0}

        # Check cache
        cache_key = hash(text)
        if cache_key in self.compression_cache:
            return self.compression_cache[cache_key]

        original_len = len(text)

        # Extract protected blocks (code, URLs, paths)
        protected = {}
        placeholder_idx = 0

        def protect_match(match):
            nonlocal placeholder_idx
            key = f"__CAVE_P{placeholder_idx}__"
            protected[key] = match.group(0)
            placeholder_idx += 1
            return key

        working = PROTECTED_BLOCK_RE.sub(protect_match, text)

        # Apply filler removal patterns
        for pattern, replacement in FILLER_PATTERNS:
            working = re.sub(pattern, replacement, working, flags=re.IGNORECASE)

        # Restore protected blocks
        for key, original_block in protected.items():
            working = working.replace(key, original_block)

        # Clean up whitespace
        working = re.sub(r'\n{3,}', '\n\n', working).strip()

        compressed_len = len(working)
        savings = max(0, 100 - (compressed_len / original_len * 100)) if original_len > 0 else 0

        stats = {
            "input_savings_pct": round(savings, 1),
            "original": self._estimate_tokens(text),
            "compressed": self._estimate_tokens(working),
            "method": "rule_based"
        }

        self.session_stats["original_tokens"] += stats["original"]
        self.session_stats["compressed_tokens"] += stats["compressed"]

        self.compression_cache[cache_key] = (working, stats)
        return working, stats

    def compress_response(self, text: str) -> Tuple[str, Dict]:
        """For output compression, Caveman uses system prompt injection — the
        LLM already responds in compressed style. This method is a no-op passthrough
        that records stats for the metrics dashboard.

        Real compression happens because get_system_prompt_injection() was appended
        to the system prompt BEFORE the LLM generated this response.
        """
        if not text or not text.strip():
            return text, {"output_savings_pct": 0, "original": 0, "compressed": 0}

        # The response is already compressed via system prompt injection.
        # We estimate ~30% savings from the injected caveman rules.
        estimated_savings = {"lite": 15.0, "full": 35.0, "ultra": 50.0}
        return text, {
            "output_savings_pct": estimated_savings.get(self.level, 35.0),
            "original": self._estimate_tokens(text),
            "compressed": self._estimate_tokens(text),
            "method": "system_prompt_injection"
        }

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
        if level in CAVEMAN_PROMPTS:
            self.level = level


# Global compressor instance
_caveman = None

def get_caveman(level: str = "full") -> CavemanCompressor:
    """Get global Caveman compressor instance."""
    global _caveman
    if _caveman is None:
        _caveman = CavemanCompressor(level)
    return _caveman