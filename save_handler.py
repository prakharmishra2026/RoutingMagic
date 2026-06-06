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

# Load API keys
load_dotenv(os.path.expanduser("~/Projects/investogram/.env"))
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
- (Document patterns that work well for this specific codebase)
"""
}

def get_git_info():
    """Gathers status, recent commits, and diff from the workspace."""
    if not os.path.exists(".git"):
        return None, None, None
        
    try:
        status = subprocess.check_output(["git", "status", "-s"], stderr=subprocess.DEVNULL, text=True).strip()
        log = subprocess.check_output(["git", "log", "-n", "5", "--oneline"], stderr=subprocess.DEVNULL, text=True).strip()
        diff = subprocess.check_output(["git", "diff", "HEAD"], stderr=subprocess.DEVNULL, text=True)
        # Limit diff size to prevent token blowups
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

def main():
    cwd = os.getcwd()
    project_name = os.path.basename(cwd)
    is_auto = "--auto" in sys.argv
    
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
    
    # Select LLM
    client, target_model = get_client_and_model("nvidia/z-ai/glm-5.1")
    
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
        resp = client.chat.completions.create(
            model=target_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            response_format={"type": "json_object"} if "glm-5.1" not in target_model else None
        )
        output = resp.choices[0].message.content.strip()
        
        # Clean markdown code block wraps if LLM added them
        if output.startswith("```"):
            lines = output.splitlines()
            if lines[0].startswith("```json") or lines[0].startswith("```"):
                lines = lines[1:]
            if lines[-1].startswith("```"):
                lines = lines[:-1]
            output = "\n".join(lines).strip()
            
        data = json.loads(output)
        
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
