#!/usr/bin/env python3
import os
import sys
import subprocess
import json
from dotenv import load_dotenv

# Ensure we can load openai_wrapper from its repository path
sys.path.append(os.path.expanduser("~/Projects/RoutingMagic"))
try:
    from openai_wrapper import get_client_and_model
except ImportError:
    # Fallback definition if import fails for some reason
    def get_client_and_model(model_name, is_summarizer=False):
        from openai import OpenAI
        api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("NVAPI_KEY")
        base_url = "https://openrouter.ai/api/v1" if "openrouter" in model_name else "https://integrate.api.nvidia.com/v1"
        return OpenAI(api_key=api_key, base_url=base_url), model_name

# Load API keys from user's own config (portable, no hardcoded paths)
load_dotenv(os.path.expanduser("~/.routingmagic/.env"))
load_dotenv(os.path.expanduser("~/global.env"))

FILES = ["memory.md", "progress.md", "scratchpad.md", "lessons.md"]

TEMPLATES = {
    "memory.md": """# Project Memory: {project_name}

## Tech Stack & Core Decisions
- Frameworks/dependencies: (e.g. Next.js, Python, FastAPI)
- Core architectural patterns:

## Durable Rules & Constraints
- Database/Storage patterns:
- Security/Authentication constraints:
""",
    "progress.md": """# Project Progress: {project_name}

## Chronological Log
- Initial project setup started.

## Backlog / Next Steps
- [ ] Define project requirements
- [ ] Implement initial structure
""",
    "scratchpad.md": """# Project Scratchpad: {project_name}

## Current Focus
- Initializing project documentation files

## Immediate TODOs
- [ ] Review templates
- [ ] Complete first codebase sweep
""",
    "lessons.md": """# Project Lessons: {project_name}

## Gotchas & Pitfalls
- (Add lessons learned here as you encounter bugs or architectural shifts)

## Best Practices
- (Document codebase rules and architecture constraints here)
"""
}

import re

def parse_llm_json(output: str):
    """Safely parse JSON from LLM output that might contain markdown blocks."""
    output = output.strip()
    match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', output, re.DOTALL)
    if match:
        output = match.group(1)
        
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return None


# ── Project layout ─────────────────────────────────────────────────────────────
# Legacy projects keep the four status files at the repo root. Projects that adopted a `pm/`
# folder (e.g. Investogram) keep them there, and their history files can be hundreds of KB.
# In pm-mode we NEVER send whole files to a model or write whole files back: the model returns
# only NEW entries, and we insert them at the top. A truncated model reply can then never wipe
# history, and nothing is ever created at the repo root.
PM_DIR = "pm"
PM_HEAD_CHARS = 4000          # context per file sent to the model in pm-mode
SCRATCHPAD_KEEP = 3           # rolling checkpoints kept in pm/scratchpad.md
_CHECKPOINT_RE = re.compile(r"^## (SESSION CHECKPOINT|Checkpoint)\b", re.M)


def detect_layout(root: str = ".") -> dict:
    """Return {'mode': 'pm'|'root', 'paths': {logical_name: path}}."""
    if os.path.isdir(os.path.join(root, PM_DIR)):
        return {"mode": "pm", "paths": {f: os.path.join(root, PM_DIR, f) for f in FILES}}
    return {"mode": "root", "paths": {f: os.path.join(root, f) for f in FILES}}


def insert_after_header(text: str, snippet: str) -> str:
    """Insert `snippet` after the file's leading title/blockquote block (before the first `## `)."""
    snippet = snippet.strip()
    if not snippet:
        return text
    m = re.search(r"^## ", text, re.M)
    if not m:
        return text.rstrip() + "\n\n" + snippet + "\n"
    return text[:m.start()] + snippet + "\n\n" + text[m.start():]


def insert_before_first(text: str, pattern: str, snippet: str) -> str:
    """Insert `snippet` before the first line matching `pattern` (regex); fall back to after-header."""
    snippet = snippet.strip()
    if not snippet:
        return text
    m = re.search(pattern, text, re.M)
    if not m:
        return insert_after_header(text, snippet)
    return text[:m.start()] + snippet + "\n\n" + text[m.start():]


def trim_checkpoints(text: str, keep: int = SCRATCHPAD_KEEP) -> str:
    """Keep only the newest `keep` checkpoint sections (they are newest-first)."""
    starts = [m.start() for m in _CHECKPOINT_RE.finditer(text)]
    if len(starts) <= keep:
        return text
    return text[:starts[keep]].rstrip() + "\n"


def apply_pm_entries(contents: dict, data: dict) -> dict:
    """Pure function: given current file texts and the model's new entries, return new texts.
    Only files that change are returned. Never shortens progress/memory/lessons."""
    out = {}
    plan = {
        "progress.md": ("progress_entry", lambda t, s: insert_after_header(t, s)),
        "memory.md": ("memory_facts", lambda t, s: insert_after_header(t, s)),
        "lessons.md": ("lessons_entry", lambda t, s: insert_before_first(t, r"^## L-\d+", s)),
        "scratchpad.md": ("scratchpad_checkpoint",
                          lambda t, s: trim_checkpoints(insert_after_header(t, s))),
    }
    for fname, (key, fn) in plan.items():
        snippet = (data.get(key) or "").strip()
        old = contents.get(fname, "")
        if not snippet or not old:
            continue
        new = fn(old, snippet)
        if fname != "scratchpad.md" and len(new) < len(old):
            continue  # safety: history files may only grow
        if new != old:
            out[fname] = new
    return out


def get_git_info(doc_paths=None):
    """Gathers status, recent commits, and diff from the workspace."""
    if not os.path.exists(".git"):
        return None, None, None
        
    try:
        status = subprocess.check_output(["git", "status", "-s"], stderr=subprocess.DEVNULL, text=True).strip()
        log = subprocess.check_output(["git", "log", "-n", "5", "--oneline"], stderr=subprocess.DEVNULL, text=True).strip()
        
        # BUG-06 FIX: Check BOTH uncommitted changes AND committed-but-undocumented changes.
        # git diff HEAD only catches uncommitted work. If user already committed,
        # we compare against HEAD~1 to capture recent commit content.
        diff = subprocess.check_output(["git", "diff", "HEAD"], stderr=subprocess.DEVNULL, text=True)
        if not diff.strip():
            # No uncommitted changes — check if latest commit is newer than the docs
            try:
                last_commit_ts = int(subprocess.check_output(
                    ["git", "log", "-1", "--format=%ct"], stderr=subprocess.DEVNULL, text=True
                ).strip())
                doc_files = list(doc_paths or FILES)
                docs_mtime = max(
                    (os.path.getmtime(f) for f in doc_files if os.path.exists(f)),
                    default=0
                )
                if last_commit_ts > docs_mtime:
                    # Docs are stale — get the diff from the last commit
                    diff = subprocess.check_output(
                        ["git", "diff", "HEAD~1", "HEAD"], stderr=subprocess.DEVNULL, text=True
                    )
                    print("\033[93m[Save] Detected committed changes not yet reflected in docs. Updating...\033[0m")
            except Exception:
                pass

        diff_str = diff[:8000].strip()
        return status, log, diff_str
    except Exception:
        return None, None, None


def initialize_files(project_name):
    initialized = []
    for f in FILES:
        if not os.path.exists(f):
            with open(f, "w") as fd:
                fd.write(TEMPLATES[f].format(project_name=project_name))
            initialized.append(f)
    return initialized


FALLBACK_CHAIN = ["google/gemma-4-31b-it:free", "nvidia/nemotron-3-super-120b-a12b:free",
                  "openai/gpt-oss-120b:free", "qwen/qwen3-coder:free"]


def _complete(prompt: str):
    """Run the prompt down the free-model chain; return the text or None."""
    for target_model in FALLBACK_CHAIN:
        try:
            client, model_id = get_client_and_model(target_model)
            resp = client.chat.completions.create(
                model=model_id, messages=[{"role": "user", "content": prompt}], temperature=0.3,
                response_format={"type": "json_object"},
            )
            content = resp.choices[0].message.content if resp and resp.choices else None
            if content:
                print(f"\033[92m[Save] Generated entries using {target_model}.\033[0m")
                return content.strip()
            raise RuntimeError("empty response")
        except Exception as e:
            print(f"\033[93m[Save] Model {target_model} failed: {e}. Trying fallback...\033[0m")
    return None


def main_pm(project_name: str, is_auto: bool, layout: dict):
    """pm-mode save: model writes only NEW entries; we insert them. Never creates root files."""
    paths = layout["paths"]
    missing = [p for p in paths.values() if not os.path.exists(p)]
    if missing:
        print(f"\033[91m[Save] pm/ layout is missing {missing}. Not creating anything; fix the layout first.\033[0m")
        return
    status, log, diff = get_git_info(list(paths.values()))
    if not status and not diff:
        print("\033[93m[Save] No active changes detected in git. Nothing to record.\033[0m")
        return
    contents = {f: open(p).read() for f, p in paths.items()}
    heads = {f: t[:PM_HEAD_CHARS] for f, t in contents.items()}
    prompt = f"""You are recording a work session for project '{project_name}'.
git status:
{status}
git log:
{log}
diff (truncated):
{diff}

The top of each status file (newest entries are at the top; match their style):
--- pm/progress.md ---
{heads['progress.md']}
--- pm/scratchpad.md ---
{heads['scratchpad.md']}
--- pm/memory.md ---
{heads['memory.md']}
--- pm/lessons.md ---
{heads['lessons.md']}

Return ONLY a JSON object with these keys. Each value is a NEW markdown section to insert at the
top of that file, or "" if nothing new. Never repeat existing content. Only state facts visible above.
{{
  "progress_entry": "## Session YYYY-MM-DD: <title>\\n- [x] ...",
  "scratchpad_checkpoint": "## SESSION CHECKPOINT — YYYY-MM-DD — RoutingMagic save\\n### Completed\\n...",
  "memory_facts": "## Recently Completed: <name> (YYYY-MM-DD)\\n- permanent fact ...  (or empty)",
  "lessons_entry": "## L-NNN — <title>\\n**What broke.** ... (or empty)",
  "diff_summary": "one short plain-English summary"
}}"""
    output = _complete(prompt)
    data = parse_llm_json(output) if output else None
    if not data:
        print("\033[91m[Save] No usable model output. Nothing written.\033[0m")
        return
    if not is_auto:
        print(f"\n{data.get('diff_summary', '')}\n")
        if input("Insert these entries into pm/? (y/N): ").strip().lower() not in ("y", "yes"):
            print("\033[91m[Save] Aborted by user.\033[0m")
            return
    updated = apply_pm_entries(contents, data)
    for fname, text in updated.items():
        with open(paths[fname], "w") as fd:
            fd.write(text)
    print(f"\033[92m[Save] Inserted entries into: {', '.join('pm/' + f for f in updated) or 'nothing'}\033[0m")


def main():
    cwd = os.getcwd()
    project_name = os.path.basename(cwd)
    is_auto = "--auto" in sys.argv

    layout = detect_layout(cwd)
    if layout["mode"] == "pm":
        return main_pm(project_name, is_auto, layout)
    
    # 1. Initialize files if they don't exist
    initialized = initialize_files(project_name)
    if initialized:
        print(f"\033[92m[Save] Initialized missing documentation files: {', '.join(initialized)}\033[0m")
        
    # If all files were just created, we don't need to summarize since there are no git changes yet
    if len(initialized) == len(FILES):
        print("\033[92m[Save] Initial setup complete. Type 'save' again after making changes to auto-update them!\033[0m")
        return
        
    # 2. Gather git history & diff
    status, log, diff = get_git_info()
    if not status and not diff:
        print("\033[93m[Save] No active changes detected in git. All documentation files are up-to-date.\033[0m")
        return

    # Read current file contents
    file_contents = {}
    for f in FILES:
        if os.path.exists(f):
            try:
                with open(f, "r") as fd:
                    file_contents[f] = fd.read().strip()
            except Exception:
                file_contents[f] = ""

    print("\033[94m[Save] Analyzing changes and generating plain English diff...\033[0m")
    
    # Select LLM fallback chain
    fallback_chain = ["google/gemma-4-31b-it:free", "nvidia/nemotron-3-super-120b-a12b:free", "openai/gpt-oss-120b:free", "qwen/qwen3-coder:free"]
    
    prompt = f"""You are an expert project chronicler and developer helper.
Your job is to update the four status files tracking the project '{project_name}' based on the recent changes.

Here is the current git status:
{status}

Here is the recent git log:
{log}

Here is a snippet of the git diff:
{diff}

Below are the current contents of the four files:
--- memory.md ---
{file_contents.get('memory.md', '')}

--- progress.md ---
{file_contents.get('progress.md', '')}

--- scratchpad.md ---
{file_contents.get('scratchpad.md', '')}

--- lessons.md ---
{file_contents.get('lessons.md', '')}

Your task:
1. Update 'progress.md' with a new dated entry describing what has been built/changed today. Keep previous entries intact.
2. Clean up completed items in 'scratchpad.md' (move them to progress if done) and list remaining or new TODOs.
3. Update 'lessons.md' if any gotchas were resolved or lessons learned.
4. Update 'memory.md' only if there are new structural decisions, configuration shifts, or packages added.

You must output ONLY a valid JSON object. Do not wrap in markdown quotes. The JSON keys must be exactly the four file names plus a "diff_summary" key:
{{
  "memory.md": "updated markdown content...",
  "progress.md": "updated markdown content...",
  "scratchpad.md": "updated markdown content...",
  "lessons.md": "updated markdown content...",
  "diff_summary": "A short, plain English summary of what has changed. Use color codes like \\033[92m for additions \\033[0m and \\033[91m for removals \\033[0m."
}}
"""

    try:
        output = None
        for target_model in fallback_chain:
            try:
                client, model_id = get_client_and_model(target_model)
                resp = client.chat.completions.create(
                    model=model_id,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    response_format={"type": "json_object"} if "glm-5.1" not in model_id else None
                )
                if resp is None:
                    raise RuntimeError("Response from API is None")
                choices = getattr(resp, "choices", None)
                if choices is None:
                    raise RuntimeError("Response choices field is None")
                if len(choices) == 0:
                    raise RuntimeError("Response choices list is empty")
                first_choice = choices[0]
                if first_choice is None:
                    raise RuntimeError("First choice is None")
                message = getattr(first_choice, "message", None)
                if message is None:
                    raise RuntimeError("Message in first choice is None")
                content = getattr(message, "content", None)
                if content is None:
                    raise RuntimeError("Content in message is None")
                output = content.strip()
                print(f"\033[92m[Save] Successfully generated diff using {target_model}.\033[0m")
                break
            except Exception as e:
                print(f"\033[93m[Save] Model {target_model} failed: {e}. Trying fallback...\033[0m")
                continue
                
        if not output:
            print("\033[91m[Save] All fallback models failed to generate a diff.\033[0m")
            return
        
        # Clean markdown if model wrapped the JSON
        data = parse_llm_json(output)
        if not data:
            print("\033[91m[Save] Failed to parse LLM response into JSON. Aborting.\033[0m")
            return
        
        # Interactive Grill Me
        if not is_auto and "diff_summary" in data:
            print("\n\033[96m================ HUMAN READABLE DIFF ================\033[0m")
            # Replace escaped color codes to actual print colors just in case
            summary = data["diff_summary"].replace("\\033", "\033")
            print(f"{summary}\n")
            print("\033[96m=====================================================\033[0m")
            ans = input("\nDo you approve saving these updates to the documentation? (y/N/edit): ").strip().lower()
            if ans not in ['y', 'yes', 'edit']:
                print("\033[91m[Save] Aborted by user.\033[0m")
                return
            if ans == 'edit':
                print("\033[93m[Save] Edit mode not fully implemented in CLI yet. Proceeding with save...\033[0m")
        
        # Write back updated files
        updated = []
        for f in FILES:
            if f in data and data[f].strip() and data[f] != file_contents.get(f, ""):
                with open(f, "w") as fd:
                    fd.write(data[f].strip() + "\n")
                updated.append(f)
                
        if updated:
            print(f"\033[92m[Save] Successfully updated status files: {', '.join(updated)}\033[0m")
        else:
            print("\033[92m[Save] Checked changes. No updates required for the documentation.\033[0m")
            
    except Exception as e:
        print(f"\033[91m[Save] Failed to update files via LLM: {e}\033[0m")

if __name__ == "__main__":
    main()
