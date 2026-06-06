#!/usr/bin/env python3
"""Universal Chat Wrapper & Smart Router

Supports:
  - NVIDIA NIM models (glm-5.1, deepseek-v4-flash, nemotron, etc.)
  - OpenAI models
  - OpenRouter / local 9Router models (free/paid)
  - Smart Routing: Auto-selects the best NVIDIA free model based on task.

Usage:
  ask "your prompt"          # Auto-routes to the best free model
  chat gpt-4o                # Start interactive REPL with a specific model
"""
import os
import sys
import socket
import re
from openai import OpenAI
from dotenv import load_dotenv

# Load the env file to ensure all keys are accessible
load_dotenv(os.path.expanduser("~/Projects/investogram/.env"))
load_dotenv(os.path.expanduser("~/global.env"))

# Mapping of NVIDIA NIM models to their specific API keys
NVIDIA_API_MAP = {
    "nvidia/nemotron-3-ultra-550b-a55b": "NVAPI_KEY_NEMOTRON_ULTRA_550B",
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

def is_port_open(ip, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.2)
    try:
        s.connect((ip, int(port)))
        s.close()
        return True
    except:
        return False

def smart_route(prompt):
    """Intelligently routes the prompt to the best available free model."""
    prompt_lower = prompt.lower()
    
    # Task 1: Deep Reasoning & Planning
    if re.search(r'\b(reason deeply|architecture|strategy|plan|tradeoffs|complex analysis|tool orchestration)\b', prompt_lower):
        return "nvidia/nemotron-3-ultra-550b-a55b", "deep_reasoning_planning"
        
    # Task 2: Fast Coding & Debugging
    if re.search(r'\b(code|fix bug|refactor|write function|regex|sql|snippet|debug|react|css|html)\b', prompt_lower):
        return "deepseek-ai/deepseek-v4-flash", "fast_coding"
        
    # Task 3: Long Horizon Agentic Coding
    if re.search(r'\b(large repo|multi-step coding|agent loop|tool use|long workflow|codebase reasoning)\b', prompt_lower):
        return "moonshotai/kimi-k2.6", "long_horizon_agentic_coding"
        
    # Task 4: Multimodal Reasoning (Fallback if triggered by text, though intended for images)
    if re.search(r'\b(image and text|video and text|multimodal reasoning)\b', prompt_lower):
        return "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning", "multimodal_reasoning"
        
    # Task 5: Safety Moderation
    if re.search(r'\b(moderation|toxicity|unsafe content|policy check|compliance screening)\b', prompt_lower):
        return "nvidia/nemotron-3.5-content-safety", "safety_moderation"
        
    # Task 6: Office Productivity
    if re.search(r'\b(office tasks|rewrite email|business drafting|document help)\b', prompt_lower):
        return "minimaxai/minimax-m2.7", "office_productivity"
        
    # Task 7: Budget Dense Reasoning
    if re.search(r'\b(small dense model|light reasoning|budget coding)\b', prompt_lower):
        return "google/gemma-4-31b-it", "budget_dense_reasoning"
        
    # Default: General Chat
    return "nvidia/z-ai/glm-5.1", "default_general"

def get_client_and_model(model_name):
    clean_model = model_name
    
    # 1. NVIDIA NIM Models
    if model_name in NVIDIA_API_MAP or "nvidia" in model_name or "glm" in model_name or "deepseek" in model_name or "kimi" in model_name or "mistral" in model_name or "minimax" in model_name or "gemma" in model_name:
        if model_name.startswith("nvidia/"):
            clean_model = model_name.replace("nvidia/", "")
        else:
            clean_model = model_name
            
        key_env_var = NVIDIA_API_MAP.get(model_name, "NVAPI_KEY")
        api_key = os.getenv(key_env_var) or os.getenv("NVAPI_KEY") or os.getenv("NVIDIA_API_KEY")
        base_url = "https://integrate.api.nvidia.com/v1"
        return OpenAI(api_key=api_key, base_url=base_url), clean_model
        
    # 2. OpenAI
    if model_name.startswith("openai/") or model_name.startswith("gpt-") or model_name.startswith("o1-") or model_name.startswith("o3-"):
        if model_name.startswith("openai/"):
            clean_model = model_name.replace("openai/", "")
        api_key = os.getenv("OPENAI_API_KEY")
        return OpenAI(api_key=api_key), clean_model

    # 3. Fallback to OpenRouter / 9Router
    if is_port_open("127.0.0.1", 20128):
        base_url = "http://127.0.0.1:20128/v1"
        api_key = "9router-local"
    else:
        base_url = "https://openrouter.ai/api/v1"
        api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("9ROUTER_API_KEY")
        
    return OpenAI(api_key=api_key, base_url=base_url), model_name

def chat_oneshot(model, prompt):
    if model == "smart":
        target_model, task_type = smart_route(prompt)
        print(f"\033[94m[Smart Router] Selected '{target_model}' for task type: {task_type}\033[0m")
    else:
        target_model = model

    client, final_model_id = get_client_and_model(target_model)
    
    # Some models need specific parameters
    extra_body = {}
    if "nemotron-3-ultra" in final_model_id:
        extra_body = {"chat_template_kwargs":{"enable_thinking":True},"reasoning_budget":4096}
    elif "deepseek-v4-flash" in final_model_id:
        extra_body = {"chat_template_kwargs":{"thinking":True,"reasoning_effort":"high"}}
    
    kwargs = {
        "model": final_model_id,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "stream": True
    }
    
    if extra_body:
        kwargs["extra_body"] = extra_body

    try:
        resp = client.chat.completions.create(**kwargs)
        for chunk in resp:
            if not getattr(chunk, "choices", None) or len(chunk.choices) == 0:
                continue
                
            delta = chunk.choices[0].delta
            
            # Print reasoning if available (DeepSeek/Nemotron)
            reasoning = getattr(delta, "reasoning_content", None)
            if reasoning:
                print(f"\033[90m{reasoning}\033[0m", end="", flush=True)
                
            if getattr(delta, "content", None):
                print(delta.content, end="", flush=True)
        print()
    except Exception as e:
        sys.stderr.write(f"Request failed: {e}\n")
        
        # Fallback handling
        if model == "smart":
            print(f"\033[91m[Smart Router] Request failed. Falling back to glm-5.1...\033[0m")
            chat_oneshot("nvidia/z-ai/glm-5.1", prompt)
        else:
            sys.exit(1)

def repl(model):
    client, target_model = get_client_and_model(model)
    print(f"🦾 Universal Chat REPL — model: {model} (Target: {target_model})")
    print("Type your message. Exit with Ctrl-D or empty line.\n")
    
    messages = []
    while True:
        try:
            line = input(">>> ")
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break
        if not line.strip():
            continue
            
        messages.append({"role": "user", "content": line})
        
        try:
            resp = client.chat.completions.create(
                model=target_model,
                messages=messages,
                temperature=0.7,
                stream=True
            )
            
            print("assistant: ", end="", flush=True)
            assistant_reply = ""
            for chunk in resp:
                if not getattr(chunk, "choices", None) or len(chunk.choices) == 0:
                    continue
                delta = chunk.choices[0].delta
                if getattr(delta, "content", None):
                    print(delta.content, end="", flush=True)
                    assistant_reply += delta.content
            print()
            
            messages.append({"role": "assistant", "content": assistant_reply})
            
        except Exception as e:
            sys.stderr.write(f"\nRequest failed: {e}\n")
            messages.pop()

def main():
    if len(sys.argv) < 2:
        sys.stderr.write("Usage: openai_wrapper.py <model_id|smart> [prompt...]\n")
        sys.exit(1)
    model_id = sys.argv[1]
    if len(sys.argv) == 2 and model_id != "smart":
        repl(model_id)
    else:
        if model_id == "smart" and len(sys.argv) == 2:
            sys.stderr.write("Usage: ask \"your prompt\"\n")
            sys.exit(1)
        prompt = " ".join(sys.argv[2:])
        chat_oneshot(model_id, prompt)

if __name__ == "__main__":
    main()
