import os
import sys
from openai import OpenAI

# Use environment variables for safety; keep keys out of source control
base_url = os.getenv("NVAPI_BASE_URL", "https://integrate.api.nvidia.com/v1")
api_key = os.getenv("NVAPI_KEY")
if not api_key:
    print("Error: NVAPI_KEY not set in environment", file=sys.stderr)
    sys.exit(1)

client = OpenAI(base_url=base_url, api_key=api_key)

# Join all arguments as the user message
user_content = " ".join(sys.argv[1:])
if not user_content:
    print("Usage: glm5 <prompt>", file=sys.stderr)
    sys.exit(1)

completion = client.chat.completions.create(
    model="z-ai/glm-5.1",
    messages=[{"role": "user", "content": user_content}],
    temperature=1,
    top_p=1,
    max_tokens=16384,
    stream=True,
)

for chunk in completion:
    if not getattr(chunk, "choices", None):
        continue
    if not chunk.choices:
        continue
    delta = chunk.choices[0].delta
    if getattr(delta, "content", None) is not None:
        print(delta.content, end="")
