#!/usr/bin/env python3
"""Universal Chat Wrapper & Smart Router

Supports:
  - NVIDIA NIM models (glm-5.1, deepseek-v4-flash, nemotron, etc.)
  - OpenAI models
  - OpenRouter models (free/paid)
  - Smart Routing: Auto-selects the best NVIDIA free model based on task.
  - Dual-Tier Context: Instant context sniffing or deep codebase summarization.
  - Fallback loops, cost tracking, workspaces, failsafes, error interception.
"""
import os
import sys
import re
import json
import subprocess
import shutil
import tempfile
import hashlib
import time
import select
import shlex
import atexit
import tty
import termios
import concurrent.futures
import urllib.request
from pathlib import Path
from datetime import datetime, timezone
from openai import OpenAI
from dotenv import load_dotenv
from caveman_integration import get_caveman
from metrics_collector import record_session, format_savings_dashboard, get_savings_summary, get_savings_breakdown, get_model_efficiency_ranking, export_savings_csv, get_current_session_savings, SessionMetrics
from caveman_quality_loop import get_quality_loop
from routing_learner import get_routing_learner
from model_registry_updater import get_fallback_chain as get_dynamic_fallback_chain, load_registry, get_reasoning_models, get_coding_models, get_long_context_models

# --- Shell command security helpers ---
# Characters that enable subshell execution or command chaining.
# Deliberately narrow: blocks ; | & ` and $( ${ variable expansions and redirects < >
# Does NOT block bare $ (e.g. inside quoted strings like python3 -c "...$var...")
# because shell=False+shlex means the shell never interprets them.
_SHELL_DANGEROUS = re.compile(r'[;|&`<>]|\$[({]')

_CONFUSION_PATTERNS = [
    "what?", "again?", "rephrase", "didn't understand", "didn't get that",
    "too short", "too terse", "more detail please", "not what i asked",
    "not what i meant", "that's not helpful", "try again"
]

def _sanitize_cmd(cmd: str) -> tuple[bool, str]:
    """Return (is_safe, reason). Blocks shell metacharacters that enable injection.
    
    Allows: ls -la, npm start, python3 -c "...", VAR=x prog (shlex handles these safely)
    Blocks: rm -rf; echo, $(whoami), `id`, cat x | grep y, echo x > file
    """
    if _SHELL_DANGEROUS.search(cmd):
        return False, f"Blocked: command contains unsafe shell characters: {_SHELL_DANGEROUS.search(cmd).group()!r}"
    return True, ""

_SAFE_COMMIT_SHA: str | None = None

# Load API keys from user's own config (portable, no hardcoded paths)
# Priority: ~/.routingmagic/.env (user setup) > ~/global.env (legacy) > env vars
_ROUTING_MAGIC_ENV = os.path.expanduser("~/.routingmagic/.env")
load_dotenv(_ROUTING_MAGIC_ENV)
load_dotenv(os.path.expanduser("~/global.env"))

def _has_any_api_access():
    """Check if any API access method is available."""
    has_or = bool(os.getenv("OPENROUTER_API_KEY"))
    has_gem = bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
    has_zai = bool(os.getenv("ZAI_API_KEY") or os.getenv("ZHIPUAI_API_KEY"))
    has_nv = bool(os.getenv("NVAPI_KEY") or os.getenv("NVIDIA_API_KEY"))
    has_oai = bool(os.getenv("OPENAI_API_KEY"))
    return any([has_or, has_gem, has_zai, has_nv, has_oai])


def _get_fallback_chain():
    """Get dynamic fallback chain from model registry (NIM → OpenRouter → opencode → paid)."""
    try:
        # Use registry directory from repo (versioned) or fallback to home
        repo_registry = Path(__file__).parent / "registry"
        home_registry = Path.home() / ".routingmagic" / "registry"
        registry_dir = repo_registry if repo_registry.exists() else home_registry
        
        chain = get_dynamic_fallback_chain("general", registry_dir)
        if chain:
            return chain
    except Exception as e:
        print(f"[Fallback] Registry unavailable, using hardcoded: {e}")
    
    # Ultimate hardcoded fallback
    return [
        "nvidia/deepseek-ai/deepseek-v4-flash",
        "nvidia/z-ai/glm-5.2",
        "nvidia/nvidia/nemotron-3-ultra-550b-a55b",
        "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free",
        "openrouter/poolside/laguna-s-2.1:free",
        "opencode/nemotron-3-ultra-free",
        "gemini-2.5-pro",
    ]


def _get_council_fallback_models():
    """Get council fallback models from registry, spread across providers for resilience."""
    try:
        repo_registry = Path(__file__).parent / "registry"
        home_registry = Path.home() / ".routingmagic" / "registry"
        registry_dir = repo_registry if repo_registry.exists() else home_registry
        
        registry = load_registry(registry_dir)
        all_models = registry.nim_models + registry.openrouter_models + registry.opencode_models
        
        # Filter out degraded models
        now = datetime.now(timezone.utc)
        healthy_models = [
            m for m in all_models
            if not m.degraded_until or datetime.fromisoformat(m.degraded_until.replace("Z", "+00:00")) < now
        ]
        
        if not healthy_models:
            raise ValueError("No healthy models in registry")
        
        # Spread across sources: NIM, OpenRouter, opencode
        chain = []
        seen = set()
        
        # Priority: NIM direct (different provider), then OpenRouter, then opencode
        for source in ["nim", "openrouter", "opencode"]:
            for m in healthy_models:
                if m.source == source and m.id not in seen:
                    chain.append(m.id)
                    seen.add(m.id)
                    if len(chain) >= 6:
                        break
            if len(chain) >= 6:
                break
        
        # Add direct provider models if API keys available (Gemini, Z.ai)
        has_gem = bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
        has_zai = bool(os.getenv("ZAI_API_KEY") or os.getenv("ZHIPUAI_API_KEY"))
        
        if has_gem and "gemini-2.5-flash" not in seen:
            chain.insert(0, "gemini-2.5-flash")
        if has_zai and "glm-4.5-flash" not in seen:
            chain.insert(1 if has_gem else 0, "glm-4.5-flash")
        
        if chain:
            return chain[:6]
    except Exception as e:
        print(f"[Council] Registry unavailable, using hardcoded: {e}")
    
    # Hardcoded fallback
    chain = []
    has_gem = bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
    has_zai = bool(os.getenv("ZAI_API_KEY") or os.getenv("ZHIPUAI_API_KEY"))
    has_or = bool(os.getenv("OPENROUTER_API_KEY"))
    has_nv = bool(os.getenv("NVAPI_KEY") or os.getenv("NVIDIA_API_KEY"))
    
    if has_gem:
        chain.append("gemini-2.5-flash")
    if has_zai:
        chain.append("glm-4.5-flash")
    if has_or:
        chain.extend(["google/gemma-4-31b-it:free", "nvidia/nemotron-3-super-120b-a12b:free"])
    if has_nv:
        chain.extend(["nvidia/nemotron-3-ultra-550b-a55b", "nvidia/llama-3.3-nemotron-super-49b-v1.5"])
    
    return chain[:6] if chain else ["gemini-2.5-flash"]


def _check_api_keys():
    """Check API keys status. Returns True if any access method available."""
    has_or = bool(os.getenv("OPENROUTER_API_KEY"))
    has_gem = bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
    has_zai = bool(os.getenv("ZAI_API_KEY") or os.getenv("ZHIPUAI_API_KEY"))
    has_nv = bool(os.getenv("NVAPI_KEY") or os.getenv("NVIDIA_API_KEY"))
    has_oai = bool(os.getenv("OPENAI_API_KEY"))
    
    if any([has_or, has_gem, has_zai, has_nv, has_oai]):
        return True
    
    print("\033[91m┌──────────────────────────────────────────────────────────────┐")
    print("│  ✗ No API keys configured in ~/.routingmagic/.env            │")
    print("│                                                              │")
    print("│  Run the interactive setup wizard to add your free keys:     │")
    print("│    python3 ~/Projects/RoutingMagic/setup_keys.py             │")
    print("│                                                              │")
    print("│  Get free OpenRouter key:                                    │")
    print("│    https://openrouter.ai/keys                                │")
    print("└──────────────────────────────────────────────────────────────┘\033[0m")
    return False

WORKSPACE = "default"
TEMP_MEM_FILE = f".rm_session_{WORKSPACE}.json"
SESSION_DIR = os.path.expanduser("~/Projects/RoutingMagic/sessions")
SESSION_COST = 0.0
MAX_BUDGET = 5.0
PINNED_CONTEXT = []
request_timestamps = []
daily_requests = 0

# Mapping of NVIDIA NIM models to their specific API keys
NVIDIA_API_MAP = {
    "nvidia/nemotron-3-ultra-550b-a55b": "NVAPI_KEY_NEMOTRON_ULTRA_550B",
    "nvidia/llama-3.3-nemotron-super-49b-v1.5": "NVAPI_KEY_NEMOTRON_SUPER_49B",
    "nvidia/llama-3.1-nemotron-nano-vl-8b-v1": "NVAPI_KEY_NEMOTRON_VL_8B",
    "nvidia/nvidia-nemotron-nano-9b-v2": "NVAPI_KEY_NEMOTRON_NANO_9B",
    "nvidia/nemotron-ocr-v1": "NVAPI_KEY_NEMOTRON_OCR",
    "nvidia/nemotron-voicechat": "NVAPI_KEY_NEMOTRON_VOICECHAT",
    "nvidia/nv-embedqa-e5-v5": "NVAPI_KEY_NV_EMBEDQA",
    "deepseek-ai/deepseek-v4-flash": "NVAPI_KEY_DEEPSEEK_V4_FLASH",
    "moonshotai/kimi-k2.6": "NVAPI_KEY_KIMI_K2_6",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning": "NVAPI_KEY_NEMOTRON_OMNI_30B",
    "nvidia/nemotron-3.5-content-safety": "NVAPI_KEY_NEMOTRON_SAFETY",
    "mistralai/mistral-medium-3.5-128b": "NVAPI_KEY_MISTRAL_MEDIUM",
    "stepfun-ai/step-3.7-flash": "NVAPI_KEY_STEP_FLASH",
    "google/gemma-4-31b-it": "NVAPI_KEY_GEMMA_31B",
    "minimaxai/minimax-m2.7": "NVAPI_KEY_MINIMAX",
    "nvidia/cosmos3-nano-reasoner": "NVAPI_KEY_COSMOS",
    "nvidia/z-ai/glm-5.1": "NVAPI_KEY"
}

def get_instant_context():
    """Builds a ~150 token context string in milliseconds without calling any APIs."""
    cwd = os.getcwd()
    project_name = os.path.basename(cwd)
    tech_stack = []
    
    if os.path.exists("package.json"):
        try:
            with open("package.json", "r") as f:
                data = json.load(f)
                deps = list(data.get("dependencies", {}).keys()) + list(data.get("devDependencies", {}).keys())
                tech_stack.extend(deps[:15])
        except Exception:
            pass
    if os.path.exists("requirements.txt"):
        tech_stack.append("Python dependencies present")
        
    readme_snippet = ""
    if os.path.exists("README.md"):
        try:
            with open("README.md", "r") as f:
                lines = f.readlines()
                readme_snippet = "".join(lines[:5]).strip()
        except Exception:
            pass
            
    try:
        dirs = [d for d in os.listdir(".") if os.path.isdir(d) and not d.startswith(".")]
    except Exception:
        dirs = []
        
    context = f"Project Context:\n- Directory: {cwd} (Name: {project_name})\n"
    if tech_stack:
        context += f"- Tech Stack/Dependencies: {', '.join(tech_stack)}\n"
    if dirs:
        context += f"- Root Folders: {', '.join(dirs[:10])}\n"
    if readme_snippet:
        context += f"- README excerpt: {readme_snippet}\n"
        
    return context

def get_deep_context():
    """Builds a comprehensive codebase payload and uses a fast model to summarize it."""
    cwd = os.getcwd()
    project_name = os.path.basename(cwd)
    
    # 1. First priority: Check for documentation/history files generated by Claude Code
    history_files = ["memory.md", "progress.md", "scratchpad.md", "lessons.md"]
    found_docs = {}
    for f in history_files:
        if os.path.exists(f):
            try:
                with open(f, "r") as fd:
                    content_snippet = fd.read().strip()
                    if content_snippet:
                        found_docs[f] = content_snippet
            except Exception:
                pass
                
    if found_docs:
        print("\033[92m[Smart Router] Found project history files. Using them for deep context directly.\033[0m")
        combined_context = f"Project Deep Context (extracted from history files in {project_name}):\n\n"
        for name, data in found_docs.items():
            combined_context += f"=== {name} ===\n{data}\n\n"
        return combined_context

    # 2. Fallback: Standard scan & summarization
    content = f"Repository Context for {project_name}:\n\n"
    
    try:
        # Get tree of max 2 levels to avoid huge output
        tree_output = subprocess.check_output(["ls", "-R"], stderr=subprocess.DEVNULL, text=True)
        content += "Directory Tree:\n" + tree_output[:2000] + "\n\n"
    except Exception:
        pass
        
    files_to_read = ["README.md", "package.json", "schema.sql", "schema_v2.sql", "requirements.txt", "pyproject.toml"]
    for f in files_to_read:
        if os.path.exists(f):
            try:
                with open(f, "r") as fd:
                    content += f"--- {f} ---\n{fd.read()[:5000]}\n\n"
            except Exception:
                pass
                
    summarizer_models = ["deepseek-ai/deepseek-v4-flash", "google/gemma-4-31b-it", "mistralai/mistral-medium-3.5-128b"]
    prompt = f"Summarize the architecture, tech stack, and purpose of this codebase based on the following context. Be concise and focus on structural elements useful for a developer.\n\n{content}"
    
    print("\033[93m[Smart Router] Scanning codebase for deep context...\033[0m")
    
    for model in summarizer_models:
        try:
            client, target = get_client_and_model(model, is_summarizer=True)
            kwargs = {
                "model": target,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3
            }
            if "deepseek-v4-flash" in target:
                kwargs["extra_body"] = {"chat_template_kwargs":{"thinking":True,"reasoning_effort":"low"}}
                
            resp = client.chat.completions.create(**kwargs)
            summary = resp.choices[0].message.content
            print(f"\033[92m[Smart Router] Codebase summarized via {model}.\033[0m")
            return f"Project Deep Context:\n{summary}"
        except Exception as e:
            print(f"\033[91m[Smart Router] Summarizer {model} failed. Trying next...\033[0m")
            
    print("\033[91m[Smart Router] All summarizer models failed. Falling back to instant context.\033[0m")
    return get_instant_context()

# Check API keys
_check_api_keys()

class SessionContext:
    """Session-scoped context for managing active REPL state, including pasted images."""
    def __init__(self):
        import uuid
        self.session_id = uuid.uuid4().hex[:8]
        self.temp_dir = tempfile.TemporaryDirectory(prefix=f"rm_pasted_{self.session_id}_")
        self.image_paths = []
        self.image_hashes = set()
        
    def __enter__(self):
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()
        
    def add_image_from_clipboard(self) -> str | None:
        """Saves clipboard image to the temp directory and registers it.
        Returns the absolute file path, or "duplicate" if it's already added, or None on failure.
        """
        temp_file_name = f"image_{len(self.image_paths)}.png"
        dest_path = os.path.join(self.temp_dir.name, temp_file_name)
        
        if not check_clipboard_has_image():
            return None
            
        ext = extract_clipboard_image(dest_path)
        if not ext:
            return None
            
        if ext != ".png":
            new_path = os.path.splitext(dest_path)[0] + ext
            try:
                os.rename(dest_path, new_path)
                dest_path = new_path
            except Exception:
                pass
                
        try:
            with open(dest_path, "rb") as f:
                file_hash = hashlib.md5(f.read()).hexdigest()
        except Exception:
            file_hash = dest_path
            
        if file_hash in self.image_hashes:
            try:
                os.remove(dest_path)
            except Exception:
                pass
            return "duplicate"
            
        self.image_hashes.add(file_hash)
        self.image_paths.append(dest_path)
        return dest_path
        
    def clear(self):
        """Clears current image queue and resets temp directory."""
        self.image_paths = []
        self.image_hashes = set()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass
        import uuid
        self.session_id = uuid.uuid4().hex[:8]
        self.temp_dir = tempfile.TemporaryDirectory(prefix=f"rm_pasted_{self.session_id}_")
        
    def cleanup(self):
        """Clean up the temporary directory."""
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

def parse_image_args(args) -> tuple[list[str], str]:
    """Parse command-line arguments to separate image file paths from the text prompt."""
    image_paths = []
    prompt_parts = []
    
    img_exts = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".tiff", ".bmp"}
    
    for arg in args:
        ext = os.path.splitext(arg.lower())[1]
        if ext in img_exts and os.path.exists(arg):
            image_paths.append(os.path.abspath(arg))
        else:
            prompt_parts.append(arg)
            
    prompt = " ".join(prompt_parts)
    return image_paths, prompt

def check_clipboard_has_image():
    """Check if macOS clipboard contains an image format."""
    try:
        res = subprocess.run(["osascript", "-e", "clipboard info"], capture_output=True, text=True, timeout=6)
        if res.returncode != 0:
            print(f"\033[91m[Vision Debug] osascript failed with code {res.returncode}. Stderr: {res.stderr.strip()}\033[0m")
            return False
        info = res.stdout
        found = False
        for img_class in ["«class PNGf»", "PNGf", "JPEG picture", "GIF picture", "TIFF picture"]:
            if img_class in info:
                found = True
                break
        if not found:
            formats = info.replace("\n", " ").strip()
            print(f"\033[93m[Vision Debug] No image class found. Current clipboard contains: {formats}\033[0m")
        return found
    except Exception as e:
        print(f"\033[91m[Vision Debug] check_clipboard exception: {e}\033[0m")
    return False

def extract_clipboard_image(dest_path):
    """Write clipboard image data to dest_path using AppleScript.
    Returns the file extension (e.g. '.png') if successful, else None.
    """
    try:
        res = subprocess.run(["osascript", "-e", "clipboard info"], capture_output=True, text=True, timeout=6)
        if res.returncode != 0:
            print(f"\033[91m[Vision Debug] extract clipboard info failed with code {res.returncode}. Stderr: {res.stderr.strip()}\033[0m")
            return None
        info = res.stdout
        
        img_class = None
        ext = ".png"
        if "«class PNGf»" in info or "PNGf" in info:
            img_class = "«class PNGf»"
            ext = ".png"
        elif "JPEG picture" in info:
            img_class = "JPEG picture"
            ext = ".jpg"
        elif "TIFF picture" in info:
            img_class = "TIFF picture"
            ext = ".tiff"
        elif "GIF picture" in info:
            img_class = "GIF picture"
            ext = ".gif"
            
        if not img_class:
            print(f"\033[91m[Vision Debug] No compatible image class found for extraction. Clipboard info: {info.strip()}\033[0m")
            return None
            
        if os.path.exists(dest_path):
            try:
                os.remove(dest_path)
            except Exception:
                pass
                
        cmd = [
            "osascript",
            "-e", f'set f to open for access POSIX file "{dest_path}" with write permission',
            "-e", 'try',
            "-e", 'set eof f to 0',
            "-e", f'write (the clipboard as {img_class}) to f',
            "-e", 'close access f',
            "-e", 'on error e',
            "-e", 'try',
            "-e", 'close access f',
            "-e", 'end try',
            "-e", 'error e',
            "-e", 'end try'
        ]
        res2 = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if res2.returncode == 0 and os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
            return ext
        else:
            print(f"\033[91m[Vision Debug] extract write command failed with code {res2.returncode}. Stderr: {res2.stderr.strip()}\033[0m")
    except Exception as e:
        print(f"\033[91m[Vision Debug] extract_clipboard exception: {e}\033[0m")
    return None

def get_clipboard_text():
    """Extract plain text from macOS clipboard using pbpaste."""
    try:
        res = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        pass
    return ""

def run_vision_query(image_paths, prompt, model_name=None, detail="auto"):
    """Base64-encodes multiple images and queries a vision-capable model
    with a fallback chain.
    """
    import base64
    if isinstance(image_paths, str):
        image_paths = [image_paths]
        
    if len(image_paths) > 10:
        print("\033[91mError: Maximum of 10 images can be processed at once.\033[0m")
        return None
        
    content_list = [{"type": "text", "text": prompt}]
    total_base64_len = 0
    
    for image_path in image_paths:
        if not os.path.exists(image_path):
            print(f"\033[91mError: Image path {image_path} does not exist.\033[0m")
            return None
            
        try:
            with open(image_path, "rb") as f:
                img_data = f.read()
                base64_image = base64.b64encode(img_data).decode("utf-8")
        except Exception as e:
            print(f"\033[91mError base64-encoding image {image_path}: {e}\033[0m")
            return None
            
        total_base64_len += len(base64_image)
        if total_base64_len > 25 * 1024 * 1024:
            print("\033[91mError: Cumulative base64 image payload size exceeds 25MB limit.\033[0m")
            return None
            
        ext = os.path.splitext(image_path)[1].lower()
        mime_type = "image/png"
        if ext in [".jpg", ".jpeg"]:
            mime_type = "image/jpeg"
        elif ext == ".gif":
            mime_type = "image/gif"
        elif ext == ".webp":
            mime_type = "image/webp"
            
        content_list.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:{mime_type};base64,{base64_image}",
                "detail": detail
            }
        })
        
    messages = [
        {
            "role": "user",
            "content": content_list
        }
    ]
    
    # Vision fallback chain
    vision_fallback = [
        "nvidia/llama-3.1-nemotron-nano-vl-8b-v1",
        "google/gemini-2.5-flash:free",
        "openai/gpt-4o-mini"
    ]
    if model_name:
        vision_fallback = [model_name] + [m for m in vision_fallback if m != model_name]
        
    resp = None
    selected_model = None
    for attempt in vision_fallback:
        try:
            client, selected_model = get_client_and_model(attempt)
            resp = client.chat.completions.create(
                model=selected_model,
                messages=messages,
                stream=True
            )
            break
        except Exception as e:
            continue
            
    if not resp:
        print("\033[91m[Vision] All vision models failed to start the request.\033[0m")
        return None
        
    print(f"\033[96m🤖 Vision ({selected_model}):\033[0m\n", end="", flush=True)
    assistant_reply = ""
    for chunk in resp:
        if not getattr(chunk, "choices", None) or len(chunk.choices) == 0:
            continue
        content = getattr(chunk.choices[0].delta, "content", None)
        if content:
            print(content, end="", flush=True)
            assistant_reply += content
    print()
    return assistant_reply

# ═══════════════════════════════════════════════════════════════════════════════
#  MYTHOS-INSPIRED ROUTING — Adaptive Computation Time (ACT) & Multi-Pass
#  Inspired by OpenMythos recurrent-depth transformer architecture:
#  - ACT: Dynamically select reasoning effort based on task complexity
#  - Multi-pass: Structured prompts for iterative refinement (analyze → verify → finalize)
#  - MoE-style: Route to specialist models based on task domain
# ═══════════════════════════════════════════════════════════════════════════════

# Models that support reasoning tokens (OpenRouter reasoning parameter)
REASONING_MODELS = {
    "zhipu/glm-4.5-air": {"effort": True},           # Thinking mode
    "nvidia/nemotron-3-ultra-550b-a55b": {"effort": True},  # Deep reasoning
    "openai/gpt-oss-120b": {"effort": True},          # Configurable reasoning
    "qwen/qwen3-coder:free": {"effort": True},        # Coding reasoning
}

# Multi-pass prompting templates (Loop-based reasoning)
MULTI_PASS_TEMPLATES = {
    "reasoning": """
## Pass 1: Initial Analysis
Analyze this problem step by step. Identify key components, constraints, and assumptions.

## Pass 2: Verification
Review your initial analysis. Check for:
- Logical consistency
- Missing considerations
- Edge cases
- Alternative approaches

## Pass 3: Final Answer
Based on your verification, provide the refined final answer with confidence level.
""",
    "coding": """
## Pass 1: Understand Requirements
- What does this code need to do?
- What are the edge cases and error conditions?

## Pass 2: Design Solution
- Plan the algorithm or approach
- Identify potential issues and optimizations

## Pass 3: Implement & Verify
- Write the code
- Test against edge cases
- Add error handling
""",
    "analysis": """
## Pass 1: Data Gathering
- Identify relevant information
- Organize by category

## Pass 2: Pattern Recognition
- Find relationships and patterns
- Identify anomalies

## Pass 3: Synthesis
- Draw conclusions
- Support with evidence
"""
}


def select_reasoning_effort(prompt: str, task_type: str = "general") -> str:
    """ACT-inspired effort selection: Dynamically select reasoning effort based on prompt analysis.
    
    Inspired by OpenMythos Adaptive Computation Time (ACT) which stops looping when answer converges.
    Maps prompt complexity to reasoning effort levels: low/medium/high.
    
    Returns effort level string for OpenRouter reasoning parameter.
    """
    prompt_lower = prompt.lower()
    
    # Easy tasks → low effort (fast, cheap)
    easy_patterns = r'\b(simple|basic|what is|define|list|quick|just|short|brief|name|yes|no)\b'
    if re.search(easy_patterns, prompt_lower):
        return "low"
    
    # Medium tasks → medium effort
    medium_patterns = r'\b(explain|compare|how to|summarize|describe|write|create|update|modify)\b'
    if re.search(medium_patterns, prompt_lower):
        return "medium"
    
    # Hard tasks → high effort (deep reasoning)
    hard_patterns = r'\b(prove|derive|formal|axiom|theorem|recursive|latent|multi.?hop|deep reasoning|complex logic|architect|design system|algorithm|optimize|analyze deeply|critically|audit|financial|trade.?off|step.?by.?step|chain.?of.?thought)\b'
    if re.search(hard_patterns, prompt_lower):
        return "high"
    
    # Task-type based defaults
    task_effort_map = {
        "reasoning": "high",
        "coding": "medium",
        "analysis": "medium",
        "general": "medium"
    }
    
    return task_effort_map.get(task_type, "medium")


def get_multi_pass_prompt(prompt: str, task_type: str = "general") -> str:
    """Add Mythos-inspired multi-pass structure to prompt for complex tasks.
    
    Inspired by OpenMythos recurrent-depth reasoning where the same block runs multiple iterations.
    Structures prompts for iterative refinement: analyze → verify → finalize.
    """
    # Only add multi-pass for complex tasks
    effort = select_reasoning_effort(prompt, task_type)
    if effort != "high":
        return prompt  # Don't modify simple prompts
    
    template = MULTI_PASS_TEMPLATES.get(task_type, MULTI_PASS_TEMPLATES["analysis"])
    
    return f"{prompt}\n\n{template}"


def get_reasoning_params(model: str, effort: str = "medium") -> dict:
    """Get reasoning parameters for models that support reasoning tokens.
    
    Inspired by OpenMythos latent-space reasoning (no intermediate token emission).
    Uses OpenRouter's reasoning parameter for hidden multi-step thinking.
    """
    if model not in REASONING_MODELS:
        return {}
    
    config = REASONING_MODELS[model]
    
    if config.get("effort"):
        return {"reasoning": {"effort": effort}}
    
    return {}


def smart_route(prompt):
    """Intelligently routes the prompt to the best available free model.
    
    Enhanced with Mythos-inspired techniques:
    - ACT: Effort-aware routing (high-effort tasks get reasoning models)
    - MoE-style: Task-specific specialist selection
    Updated July 2026: GLM models no longer free on OpenRouter.
    """
    prompt_lower = prompt.lower()
    
    # Classify task type for MoE-style routing
    task_type = classify_task(prompt)
    
def smart_route(prompt):
    """Intelligently routes the prompt to the best available free model.
    
    Enhanced with Mythos-inspired techniques:
    - ACT: Effort-aware routing (high-effort tasks get reasoning models)
    - MoE-style: Task-specific specialist selection
    - Registry-driven: Uses dynamic model registry for latest models
    Updated August 2026: Uses NIM direct + OpenRouter free + opencode built-in
    """
    prompt_lower = prompt.lower()
    
    # Classify task type for MoE-style routing
    task_type = classify_task(prompt)
    
    # Get effort level (ACT-inspired)
    effort = select_reasoning_effort(prompt, task_type)
    
    # 0. Council Deliberation -> Multi-agent council protocol
    if re.search(r'\b(council|deliberate|critically? audit|council-deliberation|llm-council|council deliberation)\b', prompt_lower):
        return "council", "llm_council_deliberation"
    
    # Try to get dynamic models from registry
    dynamic_models = None
    try:
        repo_registry = Path(__file__).parent / "registry"
        home_registry = Path.home() / ".routingmagic" / "registry"
        registry_dir = repo_registry if repo_registry.exists() else home_registry
        registry = load_registry(registry_dir)
        all_models = registry.nim_models + registry.openrouter_models + registry.opencode_models
        dynamic_models = all_models
    except Exception:
        pass
    
    # Helper to find best model from registry for a category
    def find_best_model(category, prefer_reasoning=False):
        if not dynamic_models:
            return None
        candidates = [m for m in dynamic_models if m.category == category]
        if not candidates:
            return None
        if prefer_reasoning:
            candidates = [m for m in candidates if m.has_reasoning]
        if not candidates:
            candidates = [m for m in dynamic_models if m.category == category]
        if not candidates:
            return None
        candidates.sort(key=lambda x: x.score, reverse=True)
        return candidates[0].id
    
    # 1. Deep Reasoning (high effort) -> Reasoning-capable models
    if effort == "high":
        # Prefer models with reasoning tokens
        if re.search(r'\b(prove|derive|formal|axiom|theorem|recursive|latent|multi.?hop|deep reasoning|complex logic)\b', prompt_lower):
            model = find_best_model("reasoning_flagship", prefer_reasoning=True) or find_best_model("reasoning", prefer_reasoning=True)
            if model:
                return model, "mythos_reasoning_effort"
            return "openai/gpt-oss-120b:free", "mythos_reasoning_effort"
        
        if re.search(r'\b(math|financial analysis|tradeoffs|trade-offs|step-by-step|chain of thought|deep analysis)\b', prompt_lower):
            model = find_best_model("reasoning_flagship", prefer_reasoning=True) or find_best_model("reasoning", prefer_reasoning=True)
            if model:
                return model, "mythos_deep_reasoning"
            return "nvidia/nemotron-3-ultra-550b-a55b:free", "mythos_deep_reasoning"
        
        # Phi-4 Mini Reasoning for focused reasoning
        if re.search(r'\b(analyze|critically|audit|algorithm|proof|equation|derivation)\b', prompt_lower):
            model = find_best_model("reasoning", prefer_reasoning=True)
            if model:
                return model, "mythos_reasoning_focused"
            return "microsoft/phi-4-mini-reasoning:free", "mythos_reasoning_focused"
        
        # Default high-effort: best reasoning model
        model = find_best_model("reasoning_flagship") or find_best_model("reasoning")
        if model:
            return model, "mythos_high_effort"
        return "openai/gpt-oss-120b:free", "mythos_high_effort"
    
    # 2. Long Document RAG & Heavy Agentic Planning -> Best long-context model
    if re.search(r'\b(large repo|long doc|architecture|strategy|plan|tool orchestration|codebase reasoning|massive context|rag|planning)\b', prompt_lower):
        model = find_best_model("long_context")
        if model:
            return model, "long_context_agentic"
        return "nvidia/nemotron-3-super-120b-a12b:free", "long_context_agentic"
    
    # 3. Code Generation & Fixing -> Qwen3 Coder (MoE-style: coding specialist)
    if re.search(r'\b(code|fix bug|refactor|write function|regex|sql|snippet|debug|react|css|html|typescript|python|script)\b', prompt_lower):
        model = find_best_model("coding")
        if model:
            return model, "fast_coding"
        return "qwen/qwen3-coder:free", "fast_coding"
    
    # 4. Agentic Workflows & Tool Use -> Best agentic model
    if re.search(r'\b(n8n|tool call|json extraction|workflow|extract data|structure this|json)\b', prompt_lower):
        model = find_best_model("agentic")
        if model:
            return model, "n8n_tool_calling"
        return "meta-llama/llama-3.3-70b-instruct:free", "n8n_tool_calling"
    
    # 5. Vision / Chart Parsing -> Nemotron VL 8B (NVIDIA NIM)
    if re.search(r'\b(image|chart|graph|vision|parse screenshot|look at this picture)\b', prompt_lower):
        model = find_best_model("vision")
        if model:
            return model, "stock_chart_vision"
        return "nvidia/llama-3.1-nemotron-nano-vl-8b-v1", "stock_chart_vision"
    
    # 6. Financial Document OCR -> Nemotron OCR v1 (NVIDIA NIM)
    if re.search(r'\b(ocr|pdf|annual report|bse filing|table extraction|scan document)\b', prompt_lower):
        return "nvidia/nemotron-ocr-v1", "financial_doc_ocr"
    
    # 7. Voice / Audio -> Nemotron Voicechat (NVIDIA NIM)
    if re.search(r'\b(voice|audio|speech|listen|transcribe)\b', prompt_lower):
        return "nvidia/nemotron-voicechat", "voice_trigger"
    
    # 8. Omni-modal fallback -> Nemotron Nano Omni 30B (NVIDIA NIM)
    if re.search(r'\b(video|multimodal|omni)\b', prompt_lower):
        return "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning", "multimodal_omni"
    
    # 9. Financial modeling -> MiniMax-M2.7 (NVIDIA NIM)
    if re.search(r'\b(financial|stock|valuation|portfolio|trading|quant|model)\b', prompt_lower):
        model = find_best_model("long_context")  # MiniMax-M2.7 is long_context
        if model and "minimax" in model:
            return model, "financial_modeling"
        return "minimaxai/minimax-m2.7", "financial_modeling"
    
    # 10. Security / Audit -> Best reasoning model
    if re.search(r'\b(security|audit|vulnerability|threat|pentest|secure)\b', prompt_lower):
        model = find_best_model("reasoning_flagship") or find_best_model("reasoning")
        if model:
            return model, "security_audit"
        return "nvidia/nemotron-3-ultra-550b-a55b:free", "security_audit"
    
    # Default General Tasks -> Best general model
    model = find_best_model("general")
    if model:
        return model, "default_general"
    return "google/gemma-4-31b-it:free", "default_general"


def classify_task(prompt: str) -> str:
    """Classify task type for MoE-style routing.
    
    Returns: 'reasoning', 'coding', 'agentic', 'analysis', or 'general'
    """
    prompt_lower = prompt.lower()
    
    if re.search(r'\b(prove|derive|formal|axiom|theorem|math|reason|deep analysis|critically|audit)\b', prompt_lower):
        return "reasoning"
    elif re.search(r'\b(code|fix|refactor|write function|debug|react|css|html|typescript|python|script)\b', prompt_lower):
        return "coding"
    elif re.search(r'\b(agent|tool|workflow|pipeline|json|extract|automate)\b', prompt_lower):
        return "agentic"
    elif re.search(r'\b(analyze|compare|evaluate|assess|summarize|explain)\b', prompt_lower):
        return "analysis"
    else:
        return "general"

# Models that do NOT accept a temperature parameter
NO_TEMPERATURE_MODELS = {"o3-mini", "o1", "o1-mini", "o1-preview", "o3"}

def get_client_and_model(model_name, is_summarizer=False):
    clean_model = model_name
    # Ensure timeout is snappy so the user doesn't wait forever before failover
    req_timeout = 15 if is_summarizer else 25
    
    # NVIDIA NIM models — identified by presence in map, or by common vendor prefixes
    # NOTE: glm-4.5-flash, glm-4-flash etc. are Z.ai models and must NOT match here.
    # Only nvidia/-prefixed GLM models (nvidia/z-ai/glm-5.1) should match.
    nvidia_vendors = ("nvidia/", "deepseek-ai/", "moonshotai/", "mistralai/", "google/gemma",
                      "minimaxai/", "stepfun-ai/")
    _is_direct_zai = any(model_name.startswith(p) for p in ("glm-", "z-ai/glm-", "zhipu/"))
    _is_nvidia_glm = model_name.startswith("nvidia/") and "glm" in model_name
    if (model_name in NVIDIA_API_MAP or any(model_name.startswith(v) for v in nvidia_vendors) or _is_nvidia_glm) and not model_name.endswith(":free") and not _is_direct_zai:
        # Strip the top-level "nvidia/" org prefix if present (e.g. nvidia/z-ai/glm-5.1 → z-ai/glm-5.1)
        if model_name.startswith("nvidia/") and model_name.count("/") >= 2:
            # e.g. "nvidia/z-ai/glm-5.1" → "z-ai/glm-5.1"
            clean_model = model_name[len("nvidia/"):]
        elif model_name.startswith("nvidia/") and model_name.count("/") == 1:
            # e.g. "nvidia/nemotron-..." — keep as is, NVIDIA API accepts the full ID
            clean_model = model_name
        else:
            clean_model = model_name
            
        key_env_var = NVIDIA_API_MAP.get(model_name, "NVAPI_KEY")
        api_key = os.getenv(key_env_var) or os.getenv("NVAPI_KEY") or os.getenv("NVIDIA_API_KEY")
        base_url = "https://integrate.api.nvidia.com/v1"
        if not api_key:
            raise RuntimeError(
                f"NVIDIA NIM API key not found (looked for {key_env_var}, NVAPI_KEY, NVIDIA_API_KEY).\n"
                "Run: python3 ~/Projects/RoutingMagic/setup_keys.py\n"
                "Or add NVAPI_KEY to ~/.routingmagic/.env\n"
                "Get a free key: https://build.nvidia.com/nim/dashboard"
            )
        return OpenAI(api_key=api_key, base_url=base_url, timeout=req_timeout, max_retries=0), clean_model

    # Google Gemini direct models via native Google AI Studio OpenAI-compatible endpoint
    gemini_prefixes = ("gemini-", "google/gemini-")
    if any(model_name.startswith(p) for p in gemini_prefixes) and not model_name.endswith(":free"):
        clean_model = model_name[len("google/"):] if model_name.startswith("google/") else model_name
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError(
                "Google Gemini API key not found (looked for GEMINI_API_KEY).\n"
                "Run: python3 ~/Projects/RoutingMagic/setup_keys.py\n"
                "Get a free key: https://aistudio.google.com/apikey"
            )
        base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
        return OpenAI(api_key=api_key, base_url=base_url, timeout=req_timeout, max_retries=0), clean_model

    # Z.ai / Zhipu AI direct models (GLM-4.7-Flash, GLM-4.5-Flash free tier)
    zai_prefixes = ("glm-", "z-ai/glm-", "zhipu/")
    if any(model_name.startswith(p) for p in zai_prefixes) and not model_name.endswith(":free"):
        clean_model = model_name.split("/")[-1]
        api_key = os.getenv("ZAI_API_KEY") or os.getenv("ZHIPUAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "Z.ai / Zhipu AI API key not found (looked for ZAI_API_KEY).\n"
                "Run: python3 ~/Projects/RoutingMagic/setup_keys.py\n"
                "Get a free key: https://open.bigmodel.cn"
            )
        base_url = "https://open.bigmodel.cn/api/paas/v4/"
        return OpenAI(api_key=api_key, base_url=base_url, timeout=req_timeout, max_retries=0), clean_model

    # DeepSeek direct models (deepseek-v4-flash, deepseek-chat, deepseek-reasoner)
    deepseek_prefixes = ("deepseek-", "deepseek/")
    if any(model_name.startswith(p) for p in deepseek_prefixes) and not model_name.endswith(":free"):
        clean_model = model_name.split("/")[-1]
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise RuntimeError(
                "DeepSeek API key not found (looked for DEEPSEEK_API_KEY).\n"
                "Run: python3 ~/Projects/RoutingMagic/setup_keys.py\n"
                "Get an API key: https://platform.deepseek.com"
            )
        base_url = "https://api.deepseek.com/v1"
        return OpenAI(api_key=api_key, base_url=base_url, timeout=req_timeout, max_retries=0), clean_model

    # OpenAI direct models (o3-mini, gpt-*, o1-*)
    if model_name.startswith("openai/") or model_name.startswith("gpt-") or model_name.startswith("o1") or model_name.startswith("o3"):
        if model_name.startswith("openai/"):
            clean_model = model_name[len("openai/"):]
        else:
            clean_model = model_name
        api_key = os.getenv("OPENAI_API_KEY") or "sk-placeholder-key"
        return OpenAI(api_key=api_key, timeout=req_timeout, max_retries=0), clean_model

    # OpenRouter direct connection
    if model_name.startswith("openrouter/"):
        clean_model = model_name[len("openrouter/"):]
    else:
        clean_model = model_name

    base_url = "https://openrouter.ai/api/v1"
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OpenRouter API key not found (OPENROUTER_API_KEY).\n"
            "Run: python3 ~/Projects/RoutingMagic/setup_keys.py\n"
            "Get a free key: https://openrouter.ai/keys"
        )
        
    return OpenAI(api_key=api_key, base_url=base_url, timeout=req_timeout, max_retries=0), clean_model

def save_temp_memory(messages):
    try:
        with open(TEMP_MEM_FILE, "w") as f:
            json.dump(messages, f)
    except Exception:
        pass

def load_temp_memory():
    if os.path.exists(TEMP_MEM_FILE):
        try:
            with open(TEMP_MEM_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return None



def compress_context(messages):
    if len(messages) <= 6:
        return messages
    
    sys_msg = messages[0]
    recent_msgs = messages[-3:]
    middle_msgs = messages[1:-3]
    hist = json.dumps(middle_msgs)
    
    prompt = f"Summarize the key technical decisions, bugs fixed, and current goal of this chat history. Be concise.\n\n{hist}"
    
    fallback_chain = ["google/gemma-4-31b-it:free", "nvidia/nemotron-3-super-120b-a12b:free", "openai/gpt-oss-120b:free", "qwen/qwen3-coder:free"]
    summary = None
    
    for target_model in fallback_chain:
        try:
            client, target = get_client_and_model(target_model, is_summarizer=True)
            resp = client.chat.completions.create(
                model=target,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )
            summary = resp.choices[0].message.content.strip()
            print(f"\033[92m[Smart Router] Context compressed via {target_model}.\033[0m")
            break
        except Exception as e:
            continue
            
    if not summary:
        return messages
        
    return [
        sys_msg,
        {"role": "assistant", "content": f"[SYSTEM: Previous context summary]\n{summary}"}
    ] + recent_msgs

def chat_oneshot(model, prompt, use_deep_context=False):
    """Single-prompt chat with Mythos-inspired ACT effort selection and multi-pass prompting."""
    # Early exit if no API access available
    if not _has_any_api_access():
        _check_api_keys()
        sys.exit(1)
    
    if model == "council":
        return run_council(prompt, use_deep_context=use_deep_context)
    
    if model == "smart":
        target_model, task_type = smart_route(prompt)
        print(f"\033[94m[Smart Router] Selected '{target_model}' for task type: {task_type}\033[0m")
    else:
        target_model = model
        task_type = classify_task(prompt)

    # ACT-inspired effort selection
    effort = select_reasoning_effort(prompt, task_type)
    print(f"\033[94m[ACT] Reasoning effort: {effort}\033[0m")

    if use_deep_context:
        context_str = get_deep_context()
    else:
        context_str = get_instant_context()

    caveman = get_caveman()
    compressed_ctx, ctx_stats = caveman.compress_context(context_str)
    if ctx_stats.get("input_savings_pct", 0) > 10:
        context_str = compressed_ctx
        print(f"\033[94m[Caveman] Context compressed: {ctx_stats['input_savings_pct']:.0f}% savings\033[0m")

    caveman_rules = caveman.get_system_prompt_injection()
    system_instruction = (
        "You are a rigorous analytical assistant trained on Charlie Munger's mental models. "
        "1. INVERSION: Identify failure paths and how to avoid them.\n"
        "2. FIRST PRINCIPLES: Strip away assumptions; answer from the irreducible truth.\n"
        "3. NO FLUFF: Avoid generic advice. Give clear, specific, actionable insights.\n"
        f"4. COMMUNICATION STYLE: {caveman_rules}\n"
        f"Context:\n{context_str}"
    )
    system_message = {"role": "system", "content": system_instruction}

    # Multi-pass prompting for high-effort tasks
    if effort == "high":
        enhanced_prompt = get_multi_pass_prompt(prompt, task_type)
        user_message = {"role": "user", "content": enhanced_prompt}
        print(f"\033[94m[Multi-pass] Added structured reasoning template\033[0m")
    else:
        user_message = {"role": "user", "content": prompt}

    # Dynamic fallback chain based on available API keys
    fallback_chain = [target_model] + _get_fallback_chain()
    seen = set()
    fallback_chain = [x for x in fallback_chain if not (x in seen or seen.add(x))]

    success = False
    for attempt_model in fallback_chain:
        if attempt_model == "council":
            try:
                run_council(prompt, use_deep_context=use_deep_context)
                success = True
                break
            except Exception as e:
                print(f"\n\033[91m[Error with council] {e}\033[0m")
                if attempt_model != fallback_chain[-1]:
                    print("\033[93mTrying fallback model...\033[0m")
                continue

        try:
            temp_client, final_model_id = get_client_and_model(attempt_model)
            
            # Build extra_body with Mythos-inspired reasoning parameters
            extra_body = {}
            
            # Get reasoning params for models that support reasoning tokens
            reasoning_params = get_reasoning_params(final_model_id, effort)
            if reasoning_params:
                extra_body.update(reasoning_params)
                print(f"\033[94m[Latent reasoning] Enabled hidden thinking for {final_model_id}\033[0m")
            
            # Legacy model-specific params
            if "nemotron-3-ultra" in final_model_id:
                extra_body = {"chat_template_kwargs":{"enable_thinking":True},"reasoning_budget":4096}
            elif "deepseek-v4-flash" in final_model_id:
                extra_body = {"chat_template_kwargs":{"thinking":True,"reasoning_effort":"high"}}
            
            base_model_id = final_model_id.split("/")[-1].split(":")[0]
            supports_temperature = base_model_id not in NO_TEMPERATURE_MODELS
            
            kwargs = {
                "model": final_model_id,
                "messages": [system_message, user_message],
                "stream": True
            }
            if supports_temperature:
                kwargs["temperature"] = 0.7
            if extra_body:
                kwargs["extra_body"] = extra_body

            print(f"\n\033[96m🤖 assistant ({final_model_id}):\033[0m\n", end="", flush=True)
            resp = temp_client.chat.completions.create(**kwargs)
            was_reasoning = False
            reasoning_start_time = None
            accumulated_reasoning = ""
            for chunk in resp:
                if _check_user_interrupt():
                    sys.stdout.write("\r\033[K")
                    print("\n\033[91m🛑 [Interrupted] User typed /exit -> stopping response cleanly.\033[0m")
                    try:
                        resp.close()
                    except Exception:
                        pass
                    return
                if not getattr(chunk, "choices", None) or len(chunk.choices) == 0:
                    continue
                    
                delta = chunk.choices[0].delta
                reasoning = getattr(delta, "reasoning_content", None)
                if reasoning:
                    if not was_reasoning:
                        was_reasoning = True
                        reasoning_start_time = time.time()
                        accumulated_reasoning = ""
                    accumulated_reasoning += reasoning
                    elapsed = time.time() - reasoning_start_time
                    snippet = accumulated_reasoning.replace("\n", " ").replace("\r", " ")
                    if len(snippet) > 60:
                        snippet = "..." + snippet[-57:]
                    sys.stdout.write(f"\r\033[K\033[90m[Thinking {elapsed:.1f}s] {snippet}\033[0m")
                    sys.stdout.flush()
                    
                content = getattr(delta, "content", None)
                if content:
                    if was_reasoning:
                        sys.stdout.write("\r\033[K")
                        sys.stdout.flush()
                        was_reasoning = False
                        
                    print(content, end="", flush=True)
            if was_reasoning:
                sys.stdout.write("\r\033[K")
                sys.stdout.flush()
            print()
            try:
                from metrics_collector import SessionMetrics, record_session
                record_session(SessionMetrics(
                    session_id=f"oneshot_{int(time.time())}",
                    timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    model_used=attempt_model,
                    task_type=task_type,
                    input_tokens=caveman.session_stats.get("original_tokens", 0),
                    output_tokens=caveman.session_stats.get("compressed_tokens", 0),
                    caveman_input_savings_pct=caveman.session_stats.get("input_savings_pct", 0),
                    caveman_output_savings_pct=0.0,
                    mythos_effort=effort,
                    council_invoked=attempt_model == "council",
                    fallback_tier=0,
                    latency_ms=0,
                    user_reasked=False,
                    confusion_signals=0,
                    user_feedback=None,
                    caveman_level=caveman.level,
                    caveman_downgraded=False,
                    reask_count=0,
                    cost_usd=0.0
                ))
                get_routing_learner().record_outcome(task_type, attempt_model, success=True, reask=False)
            except Exception:
                pass
            success = True
            break
        except Exception as e:
            print(f"\n\033[91m[Error with {attempt_model}] {e}\033[0m")
            if attempt_model != fallback_chain[-1]:
                print("\033[93mTrying fallback model...\033[0m")
            continue
            
    if not success:
        raise RuntimeError("All models in the fallback chain failed for chat_oneshot.")


def avg_price_per_m(model):
    """Calculate average price per million tokens."""
    p = model.get("pricing", {}) or {}
    try:
        prompt = float(p.get("prompt", 0) or 0)
        completion = float(p.get("completion", 0) or 0)
    except (TypeError, ValueError):
        return float("inf")
    if prompt < 0 or completion < 0:
        return float("inf")
    return (prompt + completion) / 2.0 * 1_000_000.0

def get_dynamic_model(models_list, free=True, price_ceiling=None, required_params=None, min_context=128000, fallback_default=None):
    """Dynamically selects the latest model passing the criteria from the registry."""
    if not models_list:
        return fallback_default

    passers = []
    for m in models_list:
        # Check pricing
        ap = avg_price_per_m(m)
        if free:
            if ap != 0.0:
                continue
        else:
            if ap == float("inf"):
                continue
            if price_ceiling is not None and ap > price_ceiling:
                continue
                
        # Check context length
        if (m.get("context_length") or 0) < min_context:
            continue
            
        # Check supported parameters
        sp = set(m.get("supported_parameters", []) or [])
        if required_params:
            if not set(required_params).issubset(sp):
                continue
                
        passers.append(m)

    if not passers:
        return fallback_default

    # Sort candidates DESC:
    # 1. Has structured outputs
    # 2. Created timestamp (latest first)
    # 3. Cheapest first (-avg_price)
    # 4. Context length (larger first)
    def sort_key(model):
        sp = set(model.get("supported_parameters", []) or [])
        has_struct = 1 if "structured_outputs" in sp else 0
        created = model.get("created") or 0
        neg_price = -avg_price_per_m(model)
        ctx = model.get("context_length") or 0
        return (has_struct, created, neg_price, ctx)

    passers.sort(key=sort_key, reverse=True)
    return passers[0]["id"]


def _query_model(model_name, messages, temperature=0.7, effort="medium", timeout=45):
    """Query a model with Mythos-inspired reasoning parameters.
    
    Enhanced with ACT-inspired effort selection for Council deliberation.
    """
    client, target_model = get_client_and_model(model_name)
    base_model_id = target_model.split("/")[-1].split(":")[0]
    supports_temperature = base_model_id not in NO_TEMPERATURE_MODELS
    
    kwargs = {
        "model": target_model,
        "messages": messages,
    }
    if supports_temperature:
        kwargs["temperature"] = temperature
        
    # Build extra_body with Mythos-inspired reasoning parameters
    extra_body = {}
    
    # Get reasoning params for models that support reasoning tokens
    reasoning_params = get_reasoning_params(target_model, effort)
    if reasoning_params:
        extra_body.update(reasoning_params)
    
    # Legacy model-specific params (fallback)
    if "nemotron-3-ultra" in target_model:
        extra_body = {"chat_template_kwargs": {"enable_thinking": True}, "reasoning_budget": 4096}
    elif "deepseek-v4-flash" in target_model:
        extra_body = {"chat_template_kwargs": {"thinking": True, "reasoning_effort": "high"}}
        
    if extra_body:
        kwargs["extra_body"] = extra_body
        
    resp = client.chat.completions.create(**kwargs, timeout=timeout)
    if resp is None:
        raise RuntimeError("OpenRouter returned None response.")
    choices = getattr(resp, "choices", None)
    if choices is None:
        raise RuntimeError("OpenRouter response choices field is None.")
    if len(choices) == 0:
        raise RuntimeError("OpenRouter response choices list is empty.")
    choice = choices[0]
    if choice is None:
        raise RuntimeError("OpenRouter response first choice is None.")
    message = getattr(choice, "message", None)
    if message is None:
        raise RuntimeError("OpenRouter response choice message is None.")
    content = getattr(message, "content", None)
    if content is None:
        raise RuntimeError("OpenRouter response choice message content is None.")
    return content

def _query_model_with_timing(model_name, messages, temperature=0.7, effort="medium"):
    start_time = time.time()
    try:
        content = _query_model(model_name, messages, temperature, effort)
        elapsed = time.time() - start_time
        return model_name, content, None, elapsed
    except Exception as e:
        elapsed = time.time() - start_time
        return model_name, None, str(e), elapsed

def _query_model_with_fallback_and_timing(model_name, messages, temperature=0.7, excluded_models=None, effort="medium"):
    if excluded_models is None:
        excluded_models = set()
    start_time = time.time()
    
    # We will try the primary model first, and then fallback to other free models if it fails.
    attempts = [model_name]
    
    # Dynamic multi-provider free backup pool across OpenRouter, Google Gemini, NVIDIA NIM, and OpenAI
    fallbacks = [
        "google/gemma-2-9b-it:free",
    ]
    if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
        fallbacks.extend(["gemini-2.5-flash", "gemini-2.0-flash"])
    if os.getenv("ZAI_API_KEY") or os.getenv("ZHIPUAI_API_KEY"):
        fallbacks.extend(["glm-4.5-flash"])  # glm-4-flash removed upstream
    if os.getenv("NVAPI_KEY") or os.getenv("NVIDIA_API_KEY"):
        fallbacks.extend(["meta/llama-3.1-8b-instruct"])
    fallbacks.extend([
        "qwen/qwen-2.5-72b-instruct:free",
        "meta-llama/llama-3.1-8b-instruct:free",
        "mistralai/mistral-7b-instruct:free",
        "microsoft/phi-3-mini-128k-instruct:free",
    ])
    
    for f in fallbacks:
        if f not in attempts and f not in excluded_models:
            attempts.append(f)
            
    last_err = None
    failed_attempts = []
    
    for attempt in attempts:
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            f = pool.submit(_query_model, attempt, messages, temperature, effort)
            content = f.result(timeout=35.0)
            try:
                pool.shutdown(wait=False, cancel_futures=True)
            except TypeError:
                pool.shutdown(wait=False)
            elapsed = time.time() - start_time
            return attempt, content, None, elapsed, failed_attempts
        except concurrent.futures.TimeoutError:
            try:
                pool.shutdown(wait=False, cancel_futures=True)
            except TypeError:
                pool.shutdown(wait=False)
            failed_attempts.append((attempt, f"Model froze (>35s timeout) -> auto-replacing"))
            last_err = TimeoutError(f"Model {attempt} timed out after 35.0s")
            continue
        except Exception as e:
            try:
                pool.shutdown(wait=False, cancel_futures=True)
            except TypeError:
                pool.shutdown(wait=False)
            failed_attempts.append((attempt, str(e)))
            last_err = e
            continue
            
    elapsed = time.time() - start_time
    return model_name, None, str(last_err), elapsed, failed_attempts

def _check_user_interrupt():
    """Checks if user typed /exit, /stop, or /cancel on stdin during a running query."""
    try:
        import select
        if sys.stdin and select.select([sys.stdin], [], [], 0)[0]:
            line = sys.stdin.readline()
            if line and line.strip().lower() in ("/exit", "/quit", "/stop", "/cancel", "exit", "quit"):
                return True
    except Exception:
        pass
    return False

def run_council(prompt, use_deep_context=False):
    """Executes Mythos-inspired LLM Council deliberation protocol:
    
    MoE-style expert selection: Route to specialist models based on task domain.
    ACT-inspired effort: Dynamic reasoning effort for council members.
    Convergence detection: Stop early when answers stabilize.
    
    Stage 1: Parallel opinions from 3 specialist council members.
    Stage 2: Parallel peer critique and scoring (1-10).
    Stage 3: Synthesis by the Chairman model.
    """
    import concurrent.futures
    import urllib.request
    
    # Classify task for MoE-style expert selection
    task_type = classify_task(prompt)
    effort = select_reasoning_effort(prompt, task_type)
    
    print(f"\033[94m[MoE] Task type: {task_type}, Effort: {effort}\033[0m")
    
    # Fetch live models from OpenRouter registry to prevent static model rot
    models_list = None
    try:
        url = "https://openrouter.ai/api/v1/models"
        req = urllib.request.Request(url, headers={"User-Agent": "RoutingMagic/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            models_list = json.loads(resp.read())["data"]
            print("\033[92m[LLM Council] Successfully fetched live model registry from OpenRouter.\033[0m")
    except Exception as e:
        print(f"\033[93m[LLM Council] Warning: Live registry fetch failed ({e}). Using hardcoded model defaults.\033[0m")

    # MoE-style expert selection based on task type
    def select_expert_for_task(models, task_type, excluded_set):
        """Select specialist model based on task domain (MoE-style routing)."""
        
        # Task-specific model preferences (MoE-style: sparse expert activation)
        # Updated July 2026 - current free models on OpenRouter
        task_model_preferences = {
            "reasoning": {
                "keywords": ["reasoning", "reason", "thinking", "thought", "oss"],
                "fallback": "openai/gpt-oss-120b:free"
            },
            "coding": {
                "keywords": ["coder", "code", "qwen"],
                "fallback": "qwen/qwen3-coder:free"
            },
            "agentic": {
                "keywords": ["tool", "function", "structured", "llama"],
                "fallback": "meta-llama/llama-3.3-70b-instruct:free"
            },
            "analysis": {
                "keywords": ["analysis", "summarize", "gemma", "nemotron"],
                "fallback": "google/gemma-4-31b-it:free"
            },
            "general": {
                "keywords": ["gemma", "llama", "nemotron"],
                "fallback": "google/gemma-4-31b-it:free"
            }
        }
        
        preferences = task_model_preferences.get(task_type, task_model_preferences["general"])
        
        # Try to find a specialist model with reasoning support
        if models:
            for m in models:
                m_id = m.get("id", "").lower()
                if m_id in excluded_set:
                    continue
                    
                sp = set(m.get("supported_parameters", []) or [])
                
                # For high-effort tasks, prefer models with reasoning support
                if effort == "high" and "reasoning" in sp:
                    if avg_price_per_m(m) == 0.0:
                        # Check if model matches task domain
                        for keyword in preferences["keywords"]:
                            if keyword in m_id:
                                return m["id"]
                
                # For medium-effort tasks, prefer task-specific models
                for keyword in preferences["keywords"]:
                    if keyword in m_id:
                        if avg_price_per_m(m) == 0.0:
                            return m["id"]
        
        # Fallback to default for this task type
        return preferences["fallback"]

    FAST_FREE_PREFIXES = ("google/", "qwen/", "meta-llama/", "microsoft/", "nvidia/")

    def _multi_provider_fallback(default_or, alt_gemini="gemini-2.5-flash", alt_nvidia="nvidia/nemotron-4-340b-instruct"):
        if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
            return alt_gemini
        if os.getenv("NVAPI_KEY") or os.getenv("NVIDIA_API_KEY"):
            return alt_nvidia
        return default_or

    def select_coder(models, excluded_set):
        for prefix in FAST_FREE_PREFIXES:
            for m in models:
                m_id = m.get("id", "").lower()
                if m_id in excluded_set or not m_id.startswith(prefix):
                    continue
                if "coder" in m_id or "code" in m_id or "qwen" in m_id:
                    if avg_price_per_m(m) == 0.0:
                        return m["id"]
        return _multi_provider_fallback("qwen/qwen-2.5-coder-32b-instruct:free", "gemini-2.5-flash", "nvidia/nemotron-4-340b-instruct")

    def select_reasoning(models, excluded_set):
        for prefix in FAST_FREE_PREFIXES:
            for m in models:
                m_id = m.get("id", "").lower()
                if m_id in excluded_set or not m_id.startswith(prefix):
                    continue
                if avg_price_per_m(m) == 0.0:
                    return m["id"]
        return _multi_provider_fallback("meta-llama/llama-3.3-70b-instruct:free", "gemini-2.5-flash", "nvidia/nemotron-4-340b-instruct")

    def select_agentic(models, excluded_set):
        for prefix in FAST_FREE_PREFIXES:
            for m in models:
                m_id = m.get("id", "").lower()
                if m_id in excluded_set or not m_id.startswith(prefix):
                    continue
                if avg_price_per_m(m) == 0.0:
                    return m["id"]
        return _multi_provider_fallback("google/gemma-4-31b-it:free", "gemini-2.5-flash", "meta/llama-3.3-70b-instruct")

    def select_general(models, excluded_set):
        for prefix in FAST_FREE_PREFIXES:
            for m in models:
                m_id = m.get("id", "").lower()
                if m_id in excluded_set or not m_id.startswith(prefix):
                    continue
                if avg_price_per_m(m) == 0.0:
                    return m["id"]
        return _multi_provider_fallback("google/gemma-4-31b-it:free", "gemini-2.0-flash", "meta/llama-3.3-70b-instruct")

    # ── Multi-Provider Council Selection ──────────────────────────────
    # DESIGN INVARIANT: Spread council members across DIFFERENT providers
    # so that rate limits, outages, and 404s on one provider cannot
    # compromise multiple council members simultaneously.
    #
    # Selection strategy: Randomly pick 3 models from different providers
    # Priority: NIM direct, OpenRouter free, direct providers (Gemini, Z.ai)
    # ─────────────────────────────────────────────────────────────────
    import random
    
    has_gem = bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
    has_zai = bool(os.getenv("ZAI_API_KEY") or os.getenv("ZHIPUAI_API_KEY"))
    has_or = bool(os.getenv("OPENROUTER_API_KEY"))
    has_nv = bool(os.getenv("NVAPI_KEY") or os.getenv("NVIDIA_API_KEY"))
    
    # Load registry for dynamic model selection
    council_models = []
    try:
        repo_registry = Path(__file__).parent / "registry"
        home_registry = Path.home() / ".routingmagic" / "registry"
        registry_dir = repo_registry if repo_registry.exists() else home_registry
        
        registry = load_registry(registry_dir)
        all_models = registry.nim_models + registry.openrouter_models + registry.opencode_models
        
        # Filter out degraded models
        now = datetime.now(timezone.utc)
        healthy_models = [
            m for m in all_models
            if not m.degraded_until or datetime.fromisoformat(m.degraded_until.replace("Z", "+00:00")) < now
        ]
        
        if healthy_models:
            # Group by source for provider diversity
            by_source = {"nim": [], "openrouter": [], "opencode": []}
            for m in healthy_models:
                if m.source in by_source:
                    by_source[m.source].append(m)
            
            # Score and sort within each source
            for src in by_source:
                by_source[src].sort(key=lambda x: x.score, reverse=True)
            
            # Randomly select from top 5 of each source for diversity
            # NOTE: normalize to string IDs — ModelInfo dataclass objects are
            # unhashable, so set()/dict-key ops downstream (e.g. set(council_models))
            # crash if an object is passed instead of its .id string.
            candidates = []
            for src in ["nim", "openrouter", "opencode"]:
                top_models = by_source[src][:5]
                if top_models:
                    candidates.append(random.choice(top_models).id)
            
            # Add direct provider models if keys available
            if has_gem:
                candidates.append("gemini-2.5-flash")  # Direct Google
            if has_zai:
                candidates.append("glm-4.5-flash")     # Direct Z.ai
            
            # Shuffle and pick up to 3 ensuring provider diversity
            random.shuffle(candidates)
            selected = []
            seen_sources = set()
            
            for c in candidates:
                if len(selected) >= 3:
                    break
                src = "direct"
                if c in [m.id for m in healthy_models if m.source == "nim"]:
                    src = "nim"
                elif c in [m.id for m in healthy_models if m.source == "openrouter"]:
                    src = "openrouter"
                elif c in [m.id for m in healthy_models if m.source == "opencode"]:
                    src = "opencode"
                elif c == "gemini-2.5-flash":
                    src = "google"
                elif c == "glm-4.5-flash":
                    src = "zai"
                
                if src not in seen_sources:
                    selected.append(c)
                    seen_sources.add(src)
            
            # If we have less than 3, fill from fallback chain
            if len(selected) < 3:
                fallback_chain = _get_council_fallback_models()
                for fb in fallback_chain:
                    if len(selected) >= 3:
                        break
                    if fb not in selected:
                        selected.append(fb)
            
            council_models = selected[:3]
    
    except Exception as e:
        print(f"[Council] Registry selection failed ({e}), using fallback chain")
        fallback_chain = _get_council_fallback_models()
        council_models = fallback_chain[:3]
    
    # Safety net: always have at least 1 model
    if not council_models:
        fallback_chain = _get_council_fallback_models()
        council_models = fallback_chain[:3]
    
    # Ensure exactly 3 models (pad if needed)
    while len(council_models) < 3:
        fallback_chain = _get_council_fallback_models()
        for fb in fallback_chain:
            if fb not in council_models:
                council_models.append(fb)
                break
        if len(council_models) >= 3:
            break

    context_str = get_deep_context() if use_deep_context else get_instant_context()
    system_instruction = (
        "You are a rigorous analytical assistant trained on Charlie Munger's mental models. "
        "1. INVERSION: Identify failure paths and how to avoid them.\n"
        "2. FIRST PRINCIPLES: Strip away assumptions; answer from the irreducible truth.\n"
        "3. NO FLUFF: Avoid generic advice. Give clear, specific, actionable insights.\n"
        "4. SPEED & DENSITY: Be extremely concise, direct, and rigorous. Keep your opinion under 250 words so deliberation completes rapidly.\n"
        f"Context:\n{context_str}"
    )
    
    # Select Chairman based on regex heuristics (supports trade-offs with hyphens)
    is_high_reasoning = bool(re.search(
        r'\b(math|financial analysis|deep reasoning|o1|complex logic|tradeoffs|trade-offs|step-by-step|chain of thought|deep analysis|critically audit|audit|algorithm|proof|prove|equation|derivation)\b',
        prompt.lower()
    ))
    
    if is_high_reasoning:
        # Dynamically choose the latest paid reasoning model under $3.00/M tokens ceiling
        chairman_model = get_dynamic_model(models_list, free=False, price_ceiling=3.0, required_params=["reasoning"],
                                           fallback_default="openai/o3-mini")
        reasoning_reason = f"high reasoning required (regex matched) -> selected latest {chairman_model}"
    else:
        # Dynamically choose the latest free flagship model
        chairman_model = get_dynamic_model(models_list, free=True, fallback_default="google/gemma-4-31b-it:free")
        reasoning_reason = f"general query -> selected latest {chairman_model}"
        
    print("\n\033[95m[LLM Council] Starting deliberation...\033[0m")
    print(f"\033[94m[Stage 1] Querying 3 council members {council_models} for opinions in parallel...\033[0m")
    
    stage1_start = time.time()
    opinions = {}
    
    specialist_roles = [
        ("Architect & First-Principles Specialist", "Focus on structural simplicity, long-term correctness, clean architecture, and first-principles truth."),
        ("Implementation & Feasibility Specialist", "Focus on practical implementation cost, operational friction, testability, and edge cases."),
        ("Contrarian Red-Team Specialist", "Focus on inversion analysis: identify failure paths, security/performance risks, and challenge hidden assumptions.")
    ]

    def _build_stage1_messages(idx, m):
        role_title, role_desc = specialist_roles[idx % len(specialist_roles)]
        role_system = (
            f"{system_instruction}\n\n"
            f"COUNCIL MEMBER ROLE #{idx+1}: {role_title}\n"
            f"Your Mandate: {role_desc}\n\n"
            "Provide a dense, structured analytical report answering the user prompt.\n"
            "Format your answer strictly with these concise headings (keep total response under 250 words for speed):\n"
            "1. Evidence/Assumptions\n"
            "2. Baseline/Current State\n"
            "3. Evaluated Alternative\n"
            "4. Correctness Risks & Failure Modes\n"
            "5. Implementation Complexity\n"
            "6. Recommendation (Keep / Pursue Alternative / Hybrid)\n"
            "7. Confidence (1-10) & Unknowns"
        )
        return [
            {"role": "system", "content": role_system},
            {"role": "user", "content": prompt}
        ]
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(council_models)) as executor:
        futures = {}
        for idx, m in enumerate(council_models):
            msgs = _build_stage1_messages(idx, m)
            f = executor.submit(_query_model_with_fallback_and_timing, m, msgs, 0.7, set(council_models), effort)
            futures[f] = m
        completed_futures = set()
        slot_status = {m: "⏳ running" for m in council_models}
        while len(completed_futures) < len(futures):
            if _check_user_interrupt():
                sys.stdout.write("\r\033[K")
                print("\n\033[91m🛑 [Interrupted] User typed /exit -> stopping Stage 1 deliberation cleanly.\033[0m")
                try:
                    executor.shutdown(wait=False, cancel_futures=True)
                except TypeError:
                    executor.shutdown(wait=False)
                return
            for future, orig_model in list(futures.items()):
                if future in completed_futures:
                    continue
                if future.done():
                    completed_futures.add(future)
                    sys.stdout.write("\r\033[K")
                    sys.stdout.flush()
                    succeeded_model, content, err, elapsed, failed_attempts = future.result()
                    for failed_m, failed_e in failed_attempts:
                        print(f"  \033[93m⚡ [{orig_model}] auto-replaced {failed_m} -> {failed_e}\033[0m")
                    if err:
                        print(f"  \033[91m✗ [{orig_model}] All fallbacks failed [{elapsed:.1f}s]\033[0m")
                        slot_status[orig_model] = "✗ failed"
                    else:
                        if succeeded_model != orig_model:
                            print(f"  \033[92m✓ [{orig_model} -> {succeeded_model}] completed [{elapsed:.1f}s]\033[0m")
                        else:
                            print(f"  \033[92m✓ [{succeeded_model}] completed [{elapsed:.1f}s]\033[0m")
                        opinions[succeeded_model] = content
                        lines = [l.strip() for l in content.strip().split("\n") if l.strip()]
                        preview = " / ".join(lines[:2])
                        if len(preview) > 120:
                            preview = preview[:117] + "..."
                        print(f"    \033[36m└─ Key takeaway: {preview}\033[0m")
                        slot_status[orig_model] = "✓ done"
            if len(completed_futures) < len(futures):
                elapsed_stage = time.time() - stage1_start
                status_parts = [f"{m.split('/')[-1].split(':')[0]}: {status}" for m, status in slot_status.items()]
                status_line = f"\r\033[K\033[96m[Stage 1 Deliberation • {elapsed_stage:.1f}s]\033[0m " + " | ".join(status_parts)
                sys.stdout.write(status_line)
                sys.stdout.flush()
                if (len(opinions) >= 2 and elapsed_stage > 45.0) or (len(opinions) >= 1 and elapsed_stage > 75.0) or elapsed_stage > 120.0:
                    sys.stdout.write("\r\033[K")
                    print(f"\n\033[93m⚡ [Fast Quorum Reached • {elapsed_stage:.1f}s] Proceeding with {len(opinions)} completed council member(s).\033[0m")
                    # Report cancelled models
                    for _f, _m in list(futures.items()):
                        if _f not in completed_futures:
                            print(f"  \033[90m⊘ [{_m}] cancelled (quorum reached)\033[0m")
                    try:
                        executor.shutdown(wait=False, cancel_futures=True)
                    except TypeError:
                        executor.shutdown(wait=False)
                    break
                time.sleep(0.15)
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()
        # Record stage duration INSIDE the with block before __exit__ blocks on stragglers
        stage1_duration = time.time() - stage1_start
                
    print(f"\033[94m[Stage 1] Completed in {stage1_duration:.2f}s\033[0m\n")
    
    if not opinions:
        print("\033[91m[LLM Council] Warning: All council models failed in Stage 1. Falling back to direct Chairman query.\033[0m")
        # Direct Chairman query fallback
        chairman_fallbacks = [
            chairman_model,
            "openai/o3-mini",
            "google/gemma-4-31b-it:free",
            "meta-llama/llama-3.3-70b-instruct:free",
            "nvidia/nemotron-3-super-120b-a12b:free"
        ]
        resp = None
        target_model = None
        for attempt in chairman_fallbacks:
            try:
                client, target_model = get_client_and_model(attempt)
                kwargs = {
                    "model": target_model,
                    "messages": [
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": prompt}
                    ],
                    "stream": True
                }
                base_model_id = target_model.split("/")[-1].split(":")[0]
                if base_model_id not in NO_TEMPERATURE_MODELS:
                    kwargs["temperature"] = 0.7
                
                extra_body = {}
                if "nemotron-3-ultra" in target_model:
                    extra_body = {"chat_template_kwargs": {"enable_thinking": True}, "reasoning_budget": 4096}
                elif "deepseek-v4-flash" in target_model:
                    extra_body = {"chat_template_kwargs": {"thinking": True, "reasoning_effort": "high"}}
                if extra_body:
                    kwargs["extra_body"] = extra_body
                    
                resp = client.chat.completions.create(**kwargs)
                break
            except Exception as e:
                print(f"\033[91mChairman fallback attempt {attempt} failed to start: {e}. Trying fallback...\033[0m")
                continue
                
        if not resp:
            raise RuntimeError("All Chairman fallback attempts failed to start.")
            
        print(f"\033[96m🤖 Chairman ({target_model}):\033[0m\n", end="", flush=True)
        assistant_reply = ""
        was_reasoning = False
        reasoning_start_time = None
        accumulated_reasoning = ""
        for chunk in resp:
            if not getattr(chunk, "choices", None) or len(chunk.choices) == 0:
                continue
            delta = chunk.choices[0].delta
            
            reasoning = getattr(delta, "reasoning_content", None)
            if reasoning:
                if not was_reasoning:
                    was_reasoning = True
                    reasoning_start_time = time.time()
                    accumulated_reasoning = ""
                accumulated_reasoning += reasoning
                elapsed = time.time() - reasoning_start_time
                snippet = accumulated_reasoning.replace("\n", " ").replace("\r", " ")
                if len(snippet) > 60:
                    snippet = "..." + snippet[-57:]
                sys.stdout.write(f"\r\033[K\033[90m[Thinking {elapsed:.1f}s] {snippet}\033[0m")
                sys.stdout.flush()
                
            content = getattr(delta, "content", None)
            if content:
                if was_reasoning:
                    sys.stdout.write("\r\033[K")
                    sys.stdout.flush()
                    was_reasoning = False
                print(content, end="", flush=True)
                assistant_reply += content
                
        if was_reasoning:
            sys.stdout.write("\r\033[K")
            sys.stdout.flush()
        print()
        return assistant_reply

    # Stage 2: Peer Review
    print("\033[94m[Stage 2] Running anonymized peer reviews & scoring in parallel...\033[0m")
    stage2_start = time.time()
    
    letters = ["A", "B", "C", "D", "E"]
    anonymized_opinions = []
    response_to_model = {}
    for i, (model_name, content) in enumerate(opinions.items()):
        label = f"Proposal {letters[i % len(letters)]}"
        anonymized_opinions.append((label, content))
        response_to_model[label] = model_name
        
    opinions_block = ""
    for label, content in anonymized_opinions:
        opinions_block += f"=== {label} ===\n{content}\n\n"
        
    peer_review_user_prompt = (
        f"You are conducting a Blind Cross-Critique on competing council proposals for: \"{prompt}\".\n\n"
        "Here are the independent specialist proposals (anonymized):\n\n"
        f"{opinions_block}"
        "Please critically evaluate each proposal without bandwagon bias. For each proposal, provide concisely (under 150 words total):\n"
        "1. Pros: What it gets right or where it is stronger than alternatives.\n"
        "2. Cons & Hidden Assumptions: Risks, edge cases, failure paths, or implementation flaws.\n"
        "3. Revised Assessment & Score: Quantitative score (1-10) based on architectural soundness and evidence quality.\n\n"
        "Reference proposals strictly by neutral label (Proposal A, Proposal B, etc.)."
    )
    
    peer_review_messages = [
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": peer_review_user_prompt}
    ]
    
    reviews = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(opinions)) as executor:
        futures = {executor.submit(_query_model_with_fallback_and_timing, m, peer_review_messages, 0.7, set(opinions.keys()), effort): m for m in opinions.keys()}
        completed_futures = set()
        slot_status = {m: "⏳ running" for m in opinions.keys()}
        while len(completed_futures) < len(futures):
            if _check_user_interrupt():
                sys.stdout.write("\r\033[K")
                print("\n\033[91m🛑 [Interrupted] User typed /exit -> stopping Stage 2 peer review cleanly.\033[0m")
                try:
                    executor.shutdown(wait=False, cancel_futures=True)
                except TypeError:
                    executor.shutdown(wait=False)
                return
            for future, orig_model in list(futures.items()):
                if future in completed_futures:
                    continue
                if future.done():
                    completed_futures.add(future)
                    sys.stdout.write("\r\033[K")
                    sys.stdout.flush()
                    succeeded_model, content, err, elapsed, failed_attempts = future.result()
                    for failed_m, failed_e in failed_attempts:
                        print(f"  \033[93m⚡ [{orig_model}] auto-replaced {failed_m} -> {failed_e}\033[0m")
                    if err:
                        print(f"  \033[91m✗ [{orig_model}] All fallbacks failed [{elapsed:.1f}s]\033[0m")
                        slot_status[orig_model] = "✗ failed"
                    else:
                        if succeeded_model != orig_model:
                            print(f"  \033[92m✓ [{orig_model} -> {succeeded_model}] review completed [{elapsed:.1f}s]\033[0m")
                        else:
                            print(f"  \033[92m✓ [{succeeded_model}] review completed [{elapsed:.1f}s]\033[0m")
                        reviews[succeeded_model] = content
                        lines = [l.strip() for l in content.strip().split("\n") if l.strip()]
                        preview = " / ".join(lines[:2])
                        if len(preview) > 120:
                            preview = preview[:117] + "..."
                        print(f"    \033[33m└─ Critique & Score: {preview}\033[0m")
                        slot_status[orig_model] = "✓ done"
            if len(completed_futures) < len(futures):
                elapsed_stage = time.time() - stage2_start
                status_parts = [f"{m.split('/')[-1].split(':')[0]}: {status}" for m, status in slot_status.items()]
                status_line = f"\r\033[K\033[94m[Stage 2 Peer Review • {elapsed_stage:.1f}s]\033[0m " + " | ".join(status_parts)
                sys.stdout.write(status_line)
                sys.stdout.flush()
                if (len(reviews) >= 2 and elapsed_stage > 45.0) or (len(reviews) >= 1 and elapsed_stage > 75.0) or elapsed_stage > 120.0:
                    sys.stdout.write("\r\033[K")
                    print(f"\n\033[93m⚡ [Fast Quorum Reached • {elapsed_stage:.1f}s] Proceeding with {len(reviews)} completed review(s).\033[0m")
                    # Report cancelled reviewers
                    for _f, _m in list(futures.items()):
                        if _f not in completed_futures:
                            print(f"  \033[90m⊘ [{_m}] cancelled (quorum reached)\033[0m")
                    try:
                        executor.shutdown(wait=False, cancel_futures=True)
                    except TypeError:
                        executor.shutdown(wait=False)
                    break
                time.sleep(0.15)
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()
        # Record stage duration INSIDE the with block before __exit__ blocks on stragglers
        stage2_duration = time.time() - stage2_start
                
    print(f"\033[94m[Stage 2] Completed in {stage2_duration:.2f}s\033[0m\n")
    
    # Stage 3: Synthesis by Chairman
    print(f"\033[94m[Stage 3] Synthesizing final response via Chairman: {chairman_model} ({reasoning_reason})...\033[0m\n")
    
    council_deliberation_content = ""
    for label, content in anonymized_opinions:
        model_name = response_to_model[label]
        review_text = reviews.get(model_name, "No review available.")
        council_deliberation_content += f"=== Council Member: {model_name} (Anonymized as {label}) ===\n"
        council_deliberation_content += f"Original Response:\n{content}\n\n"
        council_deliberation_content += f"Peer Critique provided by this member:\n{review_text}\n\n"
        council_deliberation_content += "=" * 40 + "\n\n"
        
    chairman_user_prompt = (
        f"You are the Chairman of the LLM Council. Your mandate is to synthesize the final executive recommendation answering the user's prompt based on specialist council deliberation.\n\n"
        f"User Prompt: \"{prompt}\"\n\n"
        "Here are the specialist reports and blind peer critiques from the council members:\n\n"
        f"{council_deliberation_content}"
        "Compare the proposals by evidence quality and architectural soundness (not vote count). Produce an Executive Decision Memo structured with exactly these headings:\n\n"
        "## Recommendation\n"
        "[1-2 direct sentences stating the definitive decision/answer.]\n\n"
        "## Consensus vs. Disagreements\n"
        "- [Where specialist authors converged]\n"
        "- [Key divergence or strongest objection raised]\n\n"
        "## Why This Option Wins\n"
        "- [First-principles and evidence-grounded reasons]\n\n"
        "## Tradeoffs and Risks\n"
        "- [Material risks, edge cases, or caveats]\n\n"
        "## Action Plan\n"
        "[Concrete next steps for execution.]"
    )
    
    chairman_fallbacks = [
        chairman_model,
        "openai/o3-mini",
        "google/gemma-4-31b-it:free",
        "meta-llama/llama-3.3-70b-instruct:free",
        "nvidia/nemotron-3-super-120b-a12b:free"
    ]
    resp = None
    target_model = None
    for attempt in chairman_fallbacks:
        try:
            client, target_model = get_client_and_model(attempt)
            kwargs = {
                "model": target_model,
                "messages": [
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": chairman_user_prompt}
                ],
                "stream": True
            }
            base_model_id = target_model.split("/")[-1].split(":")[0]
            supports_temperature = base_model_id not in NO_TEMPERATURE_MODELS
            if supports_temperature:
                kwargs["temperature"] = 0.7
                
            extra_body = {}
            if "nemotron-3-ultra" in target_model:
                extra_body = {"chat_template_kwargs": {"enable_thinking": True}, "reasoning_budget": 4096}
            elif "deepseek-v4-flash" in target_model:
                extra_body = {"chat_template_kwargs": {"thinking": True, "reasoning_effort": "high"}}
            if extra_body:
                kwargs["extra_body"] = extra_body
                
            resp = client.chat.completions.create(**kwargs)
            break
        except Exception as e:
            print(f"\033[91mChairman model attempt {attempt} failed to start: {e}. Trying fallback...\033[0m")
            continue
            
    if not resp:
        raise RuntimeError("All Chairman fallback attempts failed to start.")
        
    print(f"\033[96m🤖 Chairman ({target_model}):\033[0m\n", end="", flush=True)
    
    assistant_reply = ""
    was_reasoning = False
    reasoning_start_time = None
    accumulated_reasoning = ""
    for chunk in resp:
        if _check_user_interrupt():
            sys.stdout.write("\r\033[K")
            print("\n\033[91m🛑 [Interrupted] User typed /exit -> stopping Chairman synthesis cleanly.\033[0m")
            try:
                resp.close()
            except Exception:
                pass
            return
        if not getattr(chunk, "choices", None) or len(chunk.choices) == 0:
            continue
        delta = chunk.choices[0].delta
        
        reasoning = getattr(delta, "reasoning_content", None)
        if reasoning:
            if not was_reasoning:
                was_reasoning = True
                reasoning_start_time = time.time()
                accumulated_reasoning = ""
            accumulated_reasoning += reasoning
            elapsed = time.time() - reasoning_start_time
            snippet = accumulated_reasoning.replace("\n", " ").replace("\r", " ")
            if len(snippet) > 60:
                snippet = "..." + snippet[-57:]
            sys.stdout.write(f"\r\033[K\033[90m[Thinking {elapsed:.1f}s] {snippet}\033[0m")
            sys.stdout.flush()
            
        content = getattr(delta, "content", None)
        if content:
            if was_reasoning:
                sys.stdout.write("\r\033[K")
                sys.stdout.flush()
                was_reasoning = False
                
            print(content, end="", flush=True)
            assistant_reply += content
            
    if was_reasoning:
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()
    print()
    
    is_paid = "free" not in chairman_model.lower() and "nvidia" not in chairman_model.lower()
    if is_paid:
        approx_tokens = len(assistant_reply) / 4
        global SESSION_COST
        if "deepseek-r1" in target_model.lower():
            SESSION_COST += approx_tokens * 0.0000016
        else:
            SESSION_COST += approx_tokens * 0.00001
            
    return assistant_reply


def cleanup_terminal():
    sys.stdout.write("\033[?2004l")
    sys.stdout.flush()

atexit.register(cleanup_terminal)

def read_prompt(session_context=None):
    """Read a prompt from stdin using cbreak mode to prevent terminal freezes
    and handle large bracketed pastes of any size on macOS/Linux.
    """
    # Enable bracketed paste mode in terminal
    sys.stdout.write("\033[?2004h")
    sys.stdout.flush()

    fd = sys.stdin.fileno()
    
    # If not a TTY (piped input), read all of stdin
    if not os.isatty(fd):
        content = sys.stdin.read()
        cleanup_terminal()
        if not content:
            raise EOFError()
        return content.rstrip("\r\n")

    # Display prompt
    sys.stdout.write("\n\033[92m>>> \033[0m")
    sys.stdout.flush()

    old_settings = termios.tcgetattr(fd)
    try:
        # Set to cbreak mode, and disable ECHO
        tty.setcbreak(fd)
        new_settings = termios.tcgetattr(fd)
        new_settings[3] = new_settings[3] & ~termios.ECHO
        termios.tcsetattr(fd, termios.TCSADRAIN, new_settings)
        
        buffer = []
        
        while True:
            # Read 1 character
            char = sys.stdin.read(1)
            if not char:
                raise EOFError()
                
            is_paste_image = False
            pasted_text = ""
            
            # Handle Escape sequences (like arrow keys, bracketed paste)
            if char == "\x1b":
                # Check if more characters are available immediately
                seq = [char]
                while True:
                    # Sniff if more characters are available immediately
                    r, _, _ = select.select([sys.stdin], [], [], 0.05)
                    if not r:
                        break
                    next_c = sys.stdin.read(1)
                    seq.append(next_c)
                    seq_str = "".join(seq)
                    if seq_str == "\x1b[200~" or seq_str == "\x1b[201~":
                        break
                    if len(seq) >= 8:
                        break
                        
                seq_str = "".join(seq)
                if seq_str == "\x1b[200~":
                    # Paste start detected! Read until we see the paste end sequence \x1b[201~
                    paste_chars = []
                    while True:
                        c = sys.stdin.read(1)
                        if not c:
                            break
                        paste_chars.append(c)
                        if "".join(paste_chars[-6:]) == "\x1b[201~":
                            paste_chars = paste_chars[:-6]
                            break
                    pasted_text = "".join(paste_chars)
                    if (pasted_text == "" or pasted_text.isspace()) and check_clipboard_has_image():
                        is_paste_image = True
                    else:
                        buffer.extend(list(pasted_text))
                        sys.stdout.write(pasted_text)
                        sys.stdout.flush()
                        continue
                elif seq_str == "\x1b[201~":
                    # Ignore stray paste end codes
                    continue
                else:
                    # Ignore other escape sequences (like arrow keys)
                    continue
            
            # Handle Ctrl-V (macOS Clipboard Image Paste shortcut)
            elif char == "\x16":
                if check_clipboard_has_image():
                    is_paste_image = True
                else:
                    sys.stdout.write("\033[93m[Paste] No image found in macOS clipboard. Copy an image first.\033[0m\n>>> ")
                    sys.stdout.flush()
                    continue
            
            if is_paste_image:
                if session_context:
                    # Check maximum images (max 10)
                    if len(session_context.image_paths) >= 10:
                        sys.stdout.write("\n\033[91m[Paste] Maximum limit of 10 images reached. Cannot add more.\033[0m\n>>> ")
                        sys.stdout.flush()
                        continue
                        
                    sys.stdout.write("\n\033[92m[Paste] Detected image in macOS clipboard. Saving...\033[0m\n")
                    sys.stdout.flush()
                    
                    dest_path = session_context.add_image_from_clipboard()
                    if dest_path == "duplicate":
                        sys.stdout.write("\033[93m[Paste] Warning: Image already added to the queue (duplicate ignored).\033[0m\n>>> ")
                        sys.stdout.flush()
                    elif dest_path:
                        sys.stdout.write(f"\033[92m[Paste] Image {len(session_context.image_paths)} saved. Paste more, or type 'done' to process.\033[0m\n>>> ")
                        sys.stdout.flush()
                    else:
                        sys.stdout.write("\033[91m[Paste] Error saving image.\033[0m\n>>> ")
                        sys.stdout.flush()
                else:
                    sys.stdout.write("\n\033[91m[Paste] Clipboard image pasting is only supported inside an active REPL session.\033[0m\n>>> ")
                    sys.stdout.flush()
                continue

            # Handle Ctrl-D (EOF)
            if char == "\x04":
                if not buffer:
                    raise EOFError()
                continue
                
            # Handle Backspace / Delete
            if char in ("\x7f", "\b"):
                if buffer:
                    popped = buffer.pop()
                    if popped in ("\n", "\r"):
                        sys.stdout.write("\033[A")
                    else:
                        sys.stdout.write("\b \b")
                    sys.stdout.flush()
                continue
                
            # Handle Enter (Newline)
            if char in ("\n", "\r"):
                sys.stdout.write("\n")
                sys.stdout.flush()
                break
                
            # Normal character
            buffer.append(char)
            sys.stdout.write(char)
            sys.stdout.flush()
            
    finally:
        # Restore terminal settings
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        cleanup_terminal()
        
    typed_line = "".join(buffer).strip()
    if session_context and session_context.image_paths:
        if typed_line.lower() in ["/clear", "clear"]:
            session_context.clear()
            sys.stdout.write("\033[93m[Paste] Image queue cleared.\033[0m\n")
            sys.stdout.flush()
            return ""
            
        if typed_line.lower() in ["done", "/done"]:
            sys.stdout.write(f"\033[93mWhat would you like to do with these {len(session_context.image_paths)} images? (or press Enter for default summary): \033[0m")
            sys.stdout.flush()
            user_prompt = sys.stdin.readline().strip()
            
            if user_prompt.lower() in ["/clear", "clear"]:
                session_context.clear()
                sys.stdout.write("\033[93m[Paste] Image queue cleared.\033[0m\n")
                sys.stdout.flush()
                return ""
                
            if not user_prompt:
                user_prompt = "Describe these images in detail and summarize the key information shown."
            return f"/paste {user_prompt}"
        elif typed_line == "":
            sys.stdout.write(f"\033[93m[Paste] Queue contains {len(session_context.image_paths)} image(s). Paste more or type 'done' to process.\033[0m\n")
            sys.stdout.flush()
            return ""
        else:
            return f"/paste {typed_line}"
            
    return typed_line

def handle_exit(messages):
    print(f"\n\033[92mConversation saved to {TEMP_MEM_FILE}. Exiting.\033[0m")
    cleanup_terminal()

def repl(model, use_deep_context=False, session_context=None):
    global WORKSPACE, TEMP_MEM_FILE, SESSION_COST, daily_requests, request_timestamps
    
    # Early exit if no API access available
    if not _has_any_api_access():
        _check_api_keys()
        return
    
    if model != "smart" and model != "council":
        client, target_model = get_client_and_model(model)
        print(f"🦾 Universal Chat REPL — model: {model} (Target: {target_model})")
    elif model == "council":
        client, target_model = None, None
        print(f"🦾 LLM Council Deliberation REPL")
    else:
        client, target_model = None, None
        print(f"🧠 Smart Router REPL")
        
    print("Type your message. Exit with Ctrl-D or empty line.")
    print("\033[90m[Vision] Paste clipboard images directly with Ctrl+V (or Cmd+V if supported), or type /paste\033[0m\n")
    
    messages = load_temp_memory()
    if messages:
        print("\033[90m[Loaded previous session history. Type /clear to start fresh.]\033[0m")
        if model == "smart":
            target_model, task_type = smart_route(messages[-1]["content"] if len(messages)>1 else "resume")
            if target_model != "council":
                # Use fallback chain to find available model
                fallback_chain = [target_model] + _get_fallback_chain()
                seen = set()
                fallback_chain = [x for x in fallback_chain if not (x in seen or seen.add(x))]
                client = None
                for attempt_model in fallback_chain:
                    try:
                        client, target_model = get_client_and_model(attempt_model)
                        break
                    except Exception:
                        continue
                if client is None:
                    client, target_model = None, None
            else:
                client, target_model = None, None
            
    if not messages:
        if use_deep_context:
            context_str = get_deep_context()
        else:
            context_str = get_instant_context()
            
        caveman = get_caveman()
        compressed_ctx, ctx_stats = caveman.compress_context(context_str)
        if ctx_stats.get("input_savings_pct", 0) > 10:
            context_str = compressed_ctx
            print(f"\033[94m[Caveman] Context compressed: {ctx_stats['input_savings_pct']:.0f}% savings\033[0m")

        caveman_rules = caveman.get_system_prompt_injection()
        system_instruction = (
            "You are a rigorous analytical assistant trained on Charlie Munger's mental models. "
            "1. INVERSION: Identify failure paths and how to avoid them.\n"
            "2. FIRST PRINCIPLES: Strip away assumptions; answer from the irreducible truth.\n"
            "3. NO FLUFF: Avoid generic advice. Give clear, specific, actionable insights.\n"
            f"4. COMMUNICATION STYLE: {caveman_rules}\n"
            f"Context:\n{context_str}"
        )
        messages = [{"role": "system", "content": system_instruction}]

    if session_context is None:
        session_context = SessionContext()
    while True:
        try:
            line = read_prompt(session_context)
        except (EOFError, KeyboardInterrupt):
            session_context.cleanup()
            handle_exit(messages)
            break
            
        if not line.strip():
            continue
            
        line_stripped = line.strip().lower()
            
        if line_stripped in ["exit", "quit", "/exit", "/quit"]:
            session_context.cleanup()
            handle_exit(messages)
            break
            
        if line_stripped == "/clear":
            if os.path.exists(TEMP_MEM_FILE):
                os.remove(TEMP_MEM_FILE)
            system_instruction = (
                "You are a rigorous analytical assistant trained on Charlie Munger's mental models. "
                "1. INVERSION: Identify failure paths and how to avoid them.\n"
                "2. FIRST PRINCIPLES: Strip away assumptions; answer from the irreducible truth.\n"
                "3. NO FLUFF: Avoid generic advice. Give clear, specific, actionable insights.\n"
                f"Context:\n{get_instant_context()}"
            )
            messages = [{"role": "system", "content": system_instruction}]
            print("\033[93mConversation history cleared.\033[0m")
            continue
            
        # Clipboard Image Paste / Vision command
        if line_stripped.startswith(("/paste", "/image", "/img", "/v")) and not line_stripped.startswith("/workspace") and not line_stripped.startswith("/restore"):
            is_match = False
            for cmd_pref in ["/paste", "/image", "/img", "/v"]:
                if line_stripped.startswith(cmd_pref + " ") or line_stripped == cmd_pref:
                    is_match = True
                    break
            if is_match:
                parts = line.split(" ", 1)
                user_prompt = parts[1].strip() if len(parts) > 1 and parts[1].strip() else ""
                
                if session_context and session_context.image_paths:
                    print(f"\033[92m[Vision] Processing {len(session_context.image_paths)} image(s) from session queue.\033[0m")
                    print(f"\033[93m[Vision] Prompt: {user_prompt}\033[0m")
                    
                    image_paths_to_send = list(session_context.image_paths)
                    reply = run_vision_query(image_paths_to_send, user_prompt)
                    if reply:
                        messages.append({"role": "user", "content": f"[Image(s) attached] {user_prompt}"})
                        messages.append({"role": "assistant", "content": reply})
                        save_temp_memory(messages)
                    
                    session_context.clear()
                else:
                    # Parse files from prompt argument list (e.g. /v img1.png img2.png "compare")
                    args_list = parts[1].split(" ") if len(parts) > 1 else []
                    image_paths, prompt_from_args = parse_image_args(args_list)
                    if not prompt_from_args and not user_prompt:
                        prompt_from_args = "Describe this image in detail and summarize the key information shown."
                    elif not prompt_from_args:
                        prompt_from_args = user_prompt
                        
                    if image_paths:
                        if len(image_paths) > 10:
                            print("\033[91m[Vision] Error: Maximum of 10 images can be processed at once.\033[0m")
                            continue
                        total_size = sum(os.path.getsize(p) for p in image_paths)
                        if total_size > 15 * 1024 * 1024:
                            print("\033[91m[Vision] Error: Total image size exceeds the 15MB limit.\033[0m")
                            continue
                            
                        print(f"\033[92m[Vision] Processing {len(image_paths)} image(s) from files.\033[0m")
                        print(f"\033[93m[Vision] Prompt: {prompt_from_args}\033[0m")
                        reply = run_vision_query(image_paths, prompt_from_args)
                        if reply:
                            messages.append({"role": "user", "content": f"[Image(s) attached: {', '.join(image_paths)}] {prompt_from_args}"})
                            messages.append({"role": "assistant", "content": reply})
                            save_temp_memory(messages)
                    else:
                        if check_clipboard_has_image():
                            with tempfile.TemporaryDirectory(prefix="rm_one_shot_") as tmp_dir:
                                dest = os.path.join(tmp_dir, "clip_image.png")
                                ext = extract_clipboard_image(dest)
                                if ext:
                                    if ext != ".png":
                                        new_path = os.path.splitext(dest)[0] + ext
                                        try:
                                            os.rename(dest, new_path)
                                            dest = new_path
                                        except Exception:
                                            pass
                                    print(f"\033[92m[Vision] Extracted image from clipboard.\033[0m")
                                    print(f"\033[93m[Vision] Prompt: {user_prompt}\033[0m")
                                    reply = run_vision_query([dest], user_prompt)
                                    if reply:
                                        messages.append({"role": "user", "content": f"[Image attached: clipboard] {user_prompt}"})
                                        messages.append({"role": "assistant", "content": reply})
                                        save_temp_memory(messages)
                                else:
                                    print("\033[91m[Vision] Error extracting image from clipboard.\033[0m")
                        else:
                            clip_txt = get_clipboard_text()
                            if clip_txt:
                                print(f"\033[92m[Clipboard] Loaded {len(clip_txt):,} characters ({len(clip_txt.splitlines())} lines) of text.\033[0m")
                                full_prompt = f"{user_prompt}\n\n{clip_txt}".strip() if user_prompt else clip_txt
                                if model == "council":
                                    reply = run_council(full_prompt, use_deep_context=use_deep_context)
                                else:
                                    reply = chat_with_history(messages, model, full_prompt, use_deep_context=use_deep_context)
                                if reply:
                                    messages.append({"role": "user", "content": f"[Clipboard pasted] {user_prompt or ''}"})
                                    messages.append({"role": "assistant", "content": reply})
                                    save_temp_memory(messages)
                            else:
                                print("\033[91m[Clipboard] No image or text found in macOS clipboard. Copy something first (Command+C).\033[0m")
                continue

        # Council Deliberation Command
        if line_stripped.startswith(("/council ", "/mc ")) or line_stripped in ("/council", "/mc"):
            parts = line.split(" ", 1)
            if len(parts) > 1 and parts[1].strip():
                council_prompt = parts[1].strip()
                reply = run_council(council_prompt, use_deep_context=use_deep_context)
                messages.append({"role": "user", "content": line})
                messages.append({"role": "assistant", "content": reply})
                save_temp_memory(messages)
            else:
                print("\033[91mUsage: /council <prompt> or /MC <prompt>\033[0m")
            continue
            
        # 1. Context Pinning & Agent Workspaces
        if line_stripped.startswith("/workspace"):
            parts = line.split(" ", 1)
            if len(parts) > 1 and parts[1].strip():
                WORKSPACE = parts[1].strip()
                TEMP_MEM_FILE = f".rm_session_{WORKSPACE}.json"
                messages = load_temp_memory() or [{"role": "system", "content": f"You are a helpful assistant. Context:\n{get_instant_context()}"}]
                print(f"\033[92mSwitched to workspace: {WORKSPACE}\033[0m")
            else:
                print("\033[91mUsage: /workspace <name>\033[0m")
            continue
            
        if line_stripped.startswith("/pin"):
            parts = line.split(" ", 1)
            if len(parts) > 1 and parts[1].strip():
                filepath = parts[1].strip()
                # BUG-02 FIX: Restrict to files within the current working directory
                cwd = Path(os.getcwd()).resolve()
                resolved = (cwd / filepath).resolve()
                if not str(resolved).startswith(str(cwd)):
                    print(f"\033[91mBlocked: /pin only allows files inside the current project directory.\033[0m")
                    continue
                if resolved.exists():
                    with open(resolved, "r") as f:
                        content = f.read()
                    PINNED_CONTEXT.append({"role": "system", "content": f"[PINNED FILE: {filepath}]\\n{content}"})
                    print(f"\033[92mPinned {filepath} to context permanently.\033[0m")
                else:
                    print(f"\033[91mFile not found: {filepath}\033[0m")
            else:
                print("\033[91mUsage: /pin <filepath>\033[0m")
            continue
            
        # 2. Auto-Commit & Failsafe Restore
        if line_stripped == "/safe":
            print("\033[93mCreating failsafe snapshot...\033[0m")
            subprocess.run("git add . && git commit -m 'Auto-backup before AI changes'", shell=True)
            # Record the exact SHA so /restore can be precise
            try:
                global _SAFE_COMMIT_SHA
                _SAFE_COMMIT_SHA = subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], text=True
                ).strip()
                print(f"\033[92mSnapshot created! SHA: {_SAFE_COMMIT_SHA[:8]}. Type /restore to undo future changes.\033[0m")
            except Exception:
                print("\033[92mSnapshot created! Type /restore to undo future changes.\033[0m")
            continue
            
        if line_stripped == "/restore":
            if not _SAFE_COMMIT_SHA:
                print("\033[91mNo /safe snapshot found in this session. Run /safe first.\033[0m")
                continue
            print(f"\033[91mRestoring to /safe snapshot ({_SAFE_COMMIT_SHA[:8]})...\033[0m")
            subprocess.run(["git", "reset", "--hard", _SAFE_COMMIT_SHA])
            print("\033[92mRestored successfully.\033[0m")
            continue
            
        # 3. Global /save Hook
        if line_stripped == "/save":
            print("\033[93m[Global Hook] Triggering save_handler.py to update project memory...\033[0m")
            save_script = os.path.expanduser("~/Projects/RoutingMagic/save_handler.py")
            subprocess.run(f"python3 {save_script}", shell=True)
            continue
            
        # 4. Token Rate Limits & Cost Tracker
        if line_stripped == "/cost":
            rpm = len(request_timestamps)
            print(f"\033[96mSession Cost (Paid): \033[0m ${SESSION_COST:.4f} / ${MAX_BUDGET:.2f} max")
            print(f"\033[96mRate Limits (Free): \033[0m {rpm} RPM (Limit: ~40), {daily_requests} Requests today.")
            continue

        # Caveman & Savings Dashboard
        if line_stripped.startswith("/savings"):
            parts = line_stripped.split()
            subcmd = parts[1] if len(parts) > 1 else "total"
            if subcmd in ("total", "summary"):
                print(format_savings_dashboard(30))
            elif subcmd == "breakdown":
                print(json.dumps(get_savings_breakdown(), indent=2))
            elif subcmd == "models":
                print(json.dumps(get_model_efficiency_ranking(30), indent=2))
            elif subcmd == "export":
                print(export_savings_csv(30))
            elif subcmd == "session":
                print(get_current_session_savings("current"))
            else:
                print("Usage: /savings [total|breakdown|models|export|session]")
            continue

        # Unified Dashboard (multi-tool usage)
        if line_stripped.startswith("/dashboard"):
            parts = line_stripped.split()
            subcmd = parts[1] if len(parts) > 1 else "open"
            script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard_server.py")
            if subcmd == "scan":
                print("\033[96m[Dashboard] Scanning all sources...\033[0m")
                _sp.run([sys.executable, script, "scan"])
                print("\033[92m[Dashboard] Scan complete.\033[0m")
            elif subcmd in ("open", "start"):
                import webbrowser as _wb
                # Use ensure_dashboard_running to start daemon and get actual port
                from dashboard_server import ensure_dashboard_running
                port = ensure_dashboard_running()
                def _open_dash():
                    import time as _t
                    _t.sleep(1.5)
                    _wb.open(f"http://localhost:{port}")
                import threading as _th
                _th.Thread(target=_open_dash, daemon=True).start()
                print(f"\033[92m[Dashboard] Running at http://localhost:{port}\033[0m")
            elif subcmd == "stop":
                print("\033[93m[Dashboard] Kill with: pkill -f dashboard_server.py\033[0m")
            else:
                print("Usage: /dashboard [open|scan|stop]")
            continue

        if line_stripped.startswith("/caveman-feedback"):
            parts = line.split(" ", 1)
            feedback = parts[1].strip() if len(parts) > 1 else ""
            if feedback:
                qloop = get_quality_loop()
                qloop.record_explicit_feedback(feedback, line)
                print("\033[92m[Caveman] Feedback recorded. Use 'ask deep' if output was too terse.\033[0m")
            else:
                print("\033[93m[Caveman] Usage: /caveman-feedback <good|bad|terse|perfect|right>\033[0m")
            continue

        # 4. Context-Aware /model Switcher
        if line_stripped == "/model":
            last_msg = messages[-1]["content"] if len(messages) > 1 else "general"
            suggested_model, task_type = smart_route(last_msg)
            
            models_list = [
                ("smart", "Auto (Smart Router)"),
                ("google/gemma-4-31b-it:free", "Gemma-4 31B · OpenRouter (Best Free General)"),
                ("qwen/qwen3-coder:free", "Qwen3 Coder 480B · OpenRouter (Best Free Code)"),
                ("nvidia/nemotron-3-super-120b-a12b:free", "Nemotron 3 Super 120B · OpenRouter (Reasoning & 1M Context)"),
                ("deepseek/deepseek-r1", "DeepSeek R1 · OpenRouter (Paid Reasoning Anchor)"),
                ("meta-llama/llama-3.3-70b-instruct:free", "Llama-3.3 70B · OpenRouter (Tools/JSON)"),
                ("nvidia/llama-3.3-nemotron-super-49b-v1.5", "Nemotron Super 49B · NIM (Flagship)"),
                ("gemini-2.5-pro", "Gemini 2.5 Pro · Google (Paid Anchor)"),
                ("claude-3-7-sonnet-20250219", "Claude Sonnet 3.7 · Anthropic (Paid Anchor)")
            ]
            
            print("\n\033[96mInteractive Model Switcher\033[0m")
            print(f"Context detected: \033[93m{task_type}\033[0m")
            for i, (m_id, desc) in enumerate(models_list):
                prefix = "🌟 " if m_id == suggested_model else "   "
                if m_id == "smart": prefix = "   "
                print(f"{prefix}[{i}] {desc}")
                
            sys.stdout.write("Select model (0-5): ")
            sys.stdout.flush()
            choice = sys.stdin.readline().strip()
            try:
                idx = int(choice)
                if 0 <= idx < len(models_list):
                    model = models_list[idx][0]
                    if model == "smart":
                        client, target_model = None, None
                        print("\033[92mSwitched to Auto (Smart Router)\033[0m")
                    else:
                        client, target_model = get_client_and_model(model)
                        print(f"\033[92mSwitched to {model}\033[0m")
            except:
                print("Invalid choice, keeping current model.")
            continue
            
        # 5. Smart Error Interception & Auto-Testing
        if line.startswith("/run ") or line.startswith("!") or line.startswith("/test "):
            is_test = line.startswith("/test ")
            cmd = line[6:].strip() if is_test else (line[5:].strip() if line.startswith("/run ") else line[1:].strip())
            
            # BUG-01 FIX: Block shell injection metacharacters
            safe, reason = _sanitize_cmd(cmd)
            if not safe:
                print(f"\033[91m{reason}\033[0m")
                continue

            print(f"\033[93mRunning: {cmd}\033[0m")
            # shlex.split parses the command string into a proper argv list
            # so shell=False works correctly with multi-word commands like "npm start"
            try:
                cmd_list = shlex.split(cmd)
            except ValueError as e:
                print(f"\033[91mInvalid command syntax: {e}\033[0m")
                continue
            res = subprocess.run(cmd_list, shell=False, capture_output=True, text=True)
            if res.stdout:
                print(res.stdout)
                
            if res.returncode != 0:
                err = res.stderr or res.stdout
                print(f"\033[91mCommand failed! Error output captured.\033[0m")
                
                if is_test:
                    print("\033[93mAuto-correcting test failure...\033[0m")
                    line = f"The test `{cmd}` failed with this error:\\n```\\n{err[:2000]}\\n```\\nPlease explain the error and provide the corrected code."
                else:
                    sys.stdout.write("Would you like me to explain and fix this error? (y/N): ")
                    sys.stdout.flush()
                    ans = sys.stdin.readline().strip()
                    if ans.lower() == 'y':
                        line = f"I ran `{cmd}` and it failed with this error:\\n```\\n{err[:2000]}\\n```\\nPlease explain why and how to fix it."
                    else:
                        continue
            else:
                if is_test:
                    print("\033[92mTests passed!\033[0m")
                continue

        # Generate LLM response
        if model == "smart":
            target_model, task_type = smart_route(line)
            print(f"\033[94m[Smart Router] Selected '{target_model}' for task type: {task_type}\033[0m")
            
        # Caveman confusion detection — re-ask patterns signal compression may be too aggressive
        if any(p in line.lower() for p in _CONFUSION_PATTERNS):
            get_caveman().record_confusion_signal()
            get_quality_loop().record_confusion_signal(line)
            if get_caveman().session_stats.get("downgraded", False):
                print("\033[93m[Caveman] Auto-downgraded compression level (user confusion detected)\033[0m")

        messages.append({"role": "user", "content": line})
        
        # BUG-04 FIX: Only update target_model when the smart-routed model itself succeeds
        # Track the originally smart-routed model to avoid stale fallback bleeding
        smart_routed_model = target_model if model == "smart" else None

        # Dynamic Priority Fallback Chain based on available API keys
        fallback_chain = [target_model] + _get_fallback_chain()
        # Remove duplicates while preserving order
        seen = set()
        fallback_chain = [x for x in fallback_chain if not (x in seen or seen.add(x))]
        
        success = False
        assistant_reply = ""
        
        for attempt_model in fallback_chain:
            if attempt_model == "council":
                try:
                    print(f"\n\033[96m🤖 assistant (council):\033[0m\n", end="", flush=True)
                    assistant_reply = run_council(line, use_deep_context=use_deep_context)
                    success = True
                    # BUG-04 FIX: Only update target_model if this was the originally intended model
                    if model == "smart" and smart_routed_model and attempt_model == smart_routed_model:
                        target_model = "council"
                    elif model != "smart":
                        target_model = "council"
                    break
                except Exception as e:
                    print(f"\n\033[91m[Error with council] {e}\033[0m")
                    if attempt_model != fallback_chain[-1]:
                        print("\033[93mTrying fallback model...\033[0m")
                    continue

            is_paid = "free" not in attempt_model.lower() and "nvidia" not in attempt_model.lower()
            if is_paid and SESSION_COST >= MAX_BUDGET:
                print(f"\033[91mBudget cap (${MAX_BUDGET}) reached. Skipping paid fallback.\033[0m")
                continue
                
            try:
                temp_client, temp_target = get_client_and_model(attempt_model)
                extra_body = {}
                if "nemotron-3-ultra" in temp_target:
                    extra_body = {"chat_template_kwargs": {"enable_thinking": True}, "reasoning_budget": 4096}
                elif "deepseek-v4-flash" in temp_target:
                    extra_body = {"chat_template_kwargs": {"thinking": True, "reasoning_effort": "high"}}

                print(f"\n\033[96m🤖 assistant ({temp_target}):\033[0m\n", end="", flush=True)

                full_messages = PINNED_CONTEXT + messages

                # o3-mini and o1 family do NOT accept a temperature param — omit it for those
                base_model_id = temp_target.split("/")[-1].split(":")[0]  # e.g. "o3-mini"
                supports_temperature = base_model_id not in NO_TEMPERATURE_MODELS
                kwargs = {
                    "model": temp_target,
                    "messages": full_messages,
                    "stream": True
                }
                if supports_temperature:
                    kwargs["temperature"] = 0.7
                if extra_body:
                    kwargs["extra_body"] = extra_body

                resp = temp_client.chat.completions.create(**kwargs)
                
                now = time.time()
                request_timestamps = [t for t in request_timestamps if now - t < 60]
                request_timestamps.append(now)
                daily_requests += 1
                
                was_reasoning = False
                reasoning_start_time = None
                accumulated_reasoning = ""
                for chunk in resp:
                    if not getattr(chunk, "choices", None) or len(chunk.choices) == 0:
                        continue
                    delta = chunk.choices[0].delta
                    
                    reasoning = getattr(delta, "reasoning_content", None)
                    if reasoning:
                        if not was_reasoning:
                            was_reasoning = True
                            reasoning_start_time = time.time()
                            accumulated_reasoning = ""
                        accumulated_reasoning += reasoning
                        elapsed = time.time() - reasoning_start_time
                        snippet = accumulated_reasoning.replace("\n", " ").replace("\r", " ")
                        if len(snippet) > 60:
                            snippet = "..." + snippet[-57:]
                        sys.stdout.write(f"\r\033[K\033[90m[Thinking {elapsed:.1f}s] {snippet}\033[0m")
                        sys.stdout.flush()
                        
                    content = getattr(delta, "content", None)
                    if content:
                        if was_reasoning:
                            sys.stdout.write("\r\033[K")
                            sys.stdout.flush()
                            was_reasoning = False
                            
                        print(content, end="", flush=True)
                        assistant_reply += content
                if was_reasoning:
                    sys.stdout.write("\r\033[K")
                    sys.stdout.flush()
                print()
                
                if is_paid:
                    # Approximate tokens (1 token ≈ 4 chars) then apply per-model rate
                    approx_tokens = len(assistant_reply) / 4
                    if "deepseek-r1" in temp_target.lower():
                        SESSION_COST += approx_tokens * 0.0000016
                    else:
                        SESSION_COST += approx_tokens * 0.00001  # ~$10/M tokens
                    
                success = True
                # BUG-04 FIX: Only update target_model if this was the originally intended model
                if model == "smart" and smart_routed_model and attempt_model == smart_routed_model:
                    target_model = temp_target
                elif model != "smart":
                    target_model = temp_target
                break 
                
            except Exception as e:
                print(f"\n\033[91m[Error with {attempt_model}] {e}\033[0m")
                if attempt_model != fallback_chain[-1]:
                    print("\033[93mTrying fallback model...\033[0m")
                continue
                
        if not success:
            print("\033[91mAll models in the fallback chain failed.\033[0m")
            messages.pop()
            continue
            
        caveman = get_caveman()
        compressed_reply, out_stats = caveman.compress_response(assistant_reply)
        if out_stats.get("output_savings_pct", 0) > 0:
            messages.append({"role": "assistant", "content": compressed_reply})
        else:
            messages.append({"role": "assistant", "content": assistant_reply})
        save_temp_memory(messages)
        try:
            from metrics_collector import SessionMetrics, record_session
            record_session(SessionMetrics(
                session_id=f"repl_{int(time.time())}",
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                model_used=attempt_model,
                task_type=task_type if 'task_type' in locals() else "general",
                input_tokens=caveman.session_stats.get("original_tokens", 0),
                output_tokens=caveman.session_stats.get("compressed_tokens", 0),
                caveman_input_savings_pct=caveman.session_stats.get("input_savings_pct", 0),
                caveman_output_savings_pct=out_stats.get("output_savings_pct", 0),
                mythos_effort="medium",
                council_invoked=attempt_model == "council",
                fallback_tier=0,
                latency_ms=0,
                user_reasked=False,
                confusion_signals=caveman.session_stats.get("confusion_signals", 0),
                user_feedback=None,
                caveman_level=caveman.level,
                caveman_downgraded=caveman.session_stats.get("downgraded", False),
                reask_count=0,
                cost_usd=0.0
            ))
            if 'task_type' in locals():
                get_routing_learner().record_outcome(task_type, attempt_model, success=True, reask=False)
        except Exception:
            pass

        if len(messages) > 8:
            messages = compress_context(messages)
            save_temp_memory(messages)

def main():
    if len(sys.argv) < 2:
        sys.stderr.write("Usage: openai_wrapper.py <model_id|smart> [deep] [prompt...]\\n")
        sys.stderr.write("       openai_wrapper.py --setup    (configure API keys)\\n")
        sys.exit(1)
    
    # Handle --setup flag
    if sys.argv[1] == "--setup":
        setup_script = os.path.expanduser("~/Projects/RoutingMagic/setup_keys.py")
        if os.path.exists(setup_script):
            subprocess.run([sys.executable, setup_script])
        else:
            print(f"\033[91mSetup script not found: {setup_script}\033[0m")
        sys.exit(0)
        
    # Auto-update model registry on startup
    try:
        from model_registry_updater import auto_update_if_needed
        auto_update_if_needed()
    except Exception:
        pass
        
    model_id = sys.argv[1]
    args = sys.argv[2:]
    
    # Map 'smart council' argument structure to 'council' model mode
    if model_id == "smart" and args and args[0] in ["council", "MC", "mc"]:
        model_id = "council"
        args.pop(0)
        
    if model_id == "council" and args and args[0] in ["MC", "mc", "council"]:
        args.pop(0)

    # Map 'smart /paste' argument structure
    if model_id == "smart" and args and args[0] in ["/paste", "--paste", "-p", "/image", "/img", "/v"]:
        model_id = args[0]
        args.pop(0)
        
    use_paste = False
    if args and args[0] in ["--paste", "-p", "/paste"]:
        use_paste = True
        args.pop(0)
    elif model_id in ["--paste", "-p", "/paste"]:
        use_paste = True
        model_id = "smart"

    use_deep = False
    if args and args[0] in ["deep", "--deep"]:
        use_deep = True
        args.pop(0)

    if use_paste:
        clip_txt = get_clipboard_text()
        if clip_txt:
            print(f"\033[92m[Clipboard] Loaded {len(clip_txt):,} characters ({len(clip_txt.splitlines())} lines) of text from clipboard.\033[0m")
            extra_prompt = " ".join(args).strip()
            prompt = f"{extra_prompt}\n\n{clip_txt}".strip() if extra_prompt else clip_txt
            try:
                chat_oneshot(model_id, prompt, use_deep_context=use_deep)
            except KeyboardInterrupt:
                sys.stdout.write("\r\033[K")
                print("\n\033[91m🛑 [Interrupted] Process stopped by user (Ctrl+C). Exiting cleanly...\033[0m")
                sys.exit(130)
            sys.exit(0)

    if model_id in ["/image", "/img", "/v"]:
        image_paths, prompt = parse_image_args(args)
        if not prompt:
            prompt = "Describe this image in detail and summarize the key information shown." if len(image_paths) == 1 else "Describe these images in detail and summarize the key information shown."
            
        if image_paths:
            if len(image_paths) > 10:
                print("\033[91m[Vision] Error: Maximum of 10 images can be processed at once.\033[0m")
                sys.exit(1)
            total_size = sum(os.path.getsize(p) for p in image_paths)
            if total_size > 15 * 1024 * 1024:
                print("\033[91m[Vision] Error: Total image size exceeds the 15MB limit.\033[0m")
                sys.exit(1)
                
            print(f"\033[92m[Vision] Processing {len(image_paths)} image(s) from files.\033[0m")
            print(f"\033[93m[Vision] Prompt: {prompt}\033[0m")
            run_vision_query(image_paths, prompt)
        else:
            if check_clipboard_has_image():
                with tempfile.TemporaryDirectory(prefix="rm_one_shot_") as tmp_dir:
                    dest = os.path.join(tmp_dir, "clip_image.png")
                    ext = extract_clipboard_image(dest)
                    if ext:
                        if ext != ".png":
                            new_path = os.path.splitext(dest)[0] + ext
                            try:
                                os.rename(dest, new_path)
                                dest = new_path
                            except Exception:
                                pass
                        print(f"\033[92m[Vision] Extracted image from clipboard.\033[0m")
                        print(f"\033[93m[Vision] Prompt: {prompt}\033[0m")
                        run_vision_query([dest], prompt)
                    else:
                        print("\033[91m[Vision] Error extracting image from clipboard.\033[0m")
            else:
                print("\033[91m[Vision] No image found in macOS clipboard. Copy an image first (Command+C).\033[0m")
        sys.exit(0)
        
    use_deep = False
    if args and args[0] in ["deep", "--deep"]:
        use_deep = True
        args.pop(0)
        
    if "--resume" in args:
        if not os.path.exists(SESSION_DIR):
            print("No saved sessions found.")
            sys.exit(0)
        sessions = [d for d in os.listdir(SESSION_DIR) if os.path.isdir(os.path.join(SESSION_DIR, d))]
        if not sessions:
            print("No saved sessions found.")
            sys.exit(0)
            
        print("Available Sessions:")
        for i, s in enumerate(sessions):
            print(f"[{i}] {s}")
        
        try:
            sys.stdout.write("Select session to resume: ")
            sys.stdout.flush()
            choice = int(sys.stdin.readline().strip())
            if choice < 0 or choice >= len(sessions):
                raise IndexError("out of range")
            sel = sessions[choice]
            mem_path = os.path.join(SESSION_DIR, sel, "memory.md")
            # Convert the markdown file into a proper JSON messages array
            with open(mem_path, "r") as mf:
                md_content = mf.read()
            session_messages = [
                {"role": "system", "content": f"Resumed session context:\n{md_content}"}
            ]
            with open(TEMP_MEM_FILE, "w") as jf:
                json.dump(session_messages, jf)
            print(f"Loaded session {sel}.")
            with SessionContext() as session_context:
                repl(model_id, use_deep_context=use_deep, session_context=session_context)
        except (IndexError, ValueError):
            print("Invalid selection.")
        except Exception as e:
            print(f"Session load error: {e}")
        sys.exit(0)
        
    if len(args) == 0:
        with SessionContext() as session_context:
            repl(model_id, use_deep_context=use_deep, session_context=session_context)
    else:
        prompt = " ".join(args)
        try:
            chat_oneshot(model_id, prompt, use_deep_context=use_deep)
        except KeyboardInterrupt:
            sys.stdout.write("\r\033[K")
            print("\n\033[91m🛑 [Interrupted] Process stopped by user (Ctrl+C). Exiting cleanly...\033[0m")
            sys.exit(130)

if __name__ == "__main__":
    main()
