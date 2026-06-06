# RoutingMagic 🪄

**Your Smart AI Assistant & Codebase Router**

RoutingMagic is a tool that sits on your system and helps you talk to AI models instantly and intelligently. It automatically knows which project you are working on, routes your questions to the best free or paid AI models, protects you from rate limits, and automatically maintains your project's developer status files.

---

## 🚀 The Core Commands (How to use it)

You can run these commands from **any** folder or project on your computer using your standard terminal, VS Code terminal, or Antigravity IDE terminal.

### 1. `ask "your question"`
This is your fast, daily assistant. Type `ask` followed by what you want to know. 
*   **Example:** `ask "How do I connect to Supabase?"`
*   **How it works:** It instantly sniffs out the folder you are in, detects your project stack (like Next.js or Python), and gets you a contextual answer in milliseconds.
*   **Interactive Chat:** Type `ask` with nothing after it to enter a continuous chat room. Type `exit` or `quit` to leave, and it will ask you if you want to save the chat memory or discard it.

### 2. `ask --deep "your question"`
Use this for big architectural questions when you want the AI to understand your entire project.
*   **Example:** `ask --deep "Is my mutual funds page effective?"`
*   **How it works:** It looks for your core project status files (`memory.md`, `progress.md`, `scratchpad.md`, `lessons.md`). If they are there, it reads them instantly (saving you tokens). If not, it does a full scan of your project files and summarizes the architecture first.

### 3. `save` (Intelligent Codebase Auto-Saver)
This command keeps your project documentation up-to-date automatically using AI.
*   **Example:** Just type `save` in your project folder.
*   **How it works:**
    *   **First time:** It automatically creates 4 essential tracking files: `memory.md`, `progress.md`, `scratchpad.md`, and `lessons.md`.
    *   **Subsequent times:** It reads your recent Git changes (your code edits, commits, and status) and uses the AI to update your progress log, clean up completed tasks in your scratchpad, and log any new bugs or lessons learned.

### 4. `cc-route "your task"`
Routes your task to the best Claude Code model configuration.
*   **Example:** `cc-route "fix the auth bug on production"` (automatically routes to paid Sonnet 4.6 because it's critical production work).

---

## 🛠️ The 4 Documentation Files (Auto-managed by `save`)

Whenever you run `save`, RoutingMagic creates or updates these files in your folder. They follow industry best practices:

1.  **`memory.md` (The Brain):** Stores long-term structural decisions, tech stack configuration, and rules.
2.  **`progress.md` (The Timeline):** A chronological log of what has been built and a list of future features.
3.  **`scratchpad.md` (The Agenda):** What you are working on *right now* and immediate TODOs. Running `save` moves completed items from here to `progress.md`.
4.  **`lessons.md` (The Shield):** A record of gotchas, tricky bugs, and rules to prevent making the same mistake twice.

---

## 🔑 Where do my API keys go?

No need to configure keys for every single project:
*   **Global Keys:** Put your AI provider keys (like OpenRouter, OpenAI, or NVIDIA NIM keys) in `~/global.env`.
*   **Project Keys:** Put project-specific keys (like database passwords, Stripe webhooks, or telegram bots for `investogram`) in that project's `.env` file (e.g. `~/Projects/investogram/.env`).
*   RoutingMagic automatically merges both files together when you run a command.

---

## 📦 How to Setup

Open your terminal and run these commands to install RoutingMagic:

```bash
git clone https://github.com/prakharmishra2026/RoutingMagic.git ~/Projects/RoutingMagic
cd ~/Projects/RoutingMagic
./install.sh
```

**What the installer does:**
1. Registers the commands globally.
2. Connects RoutingMagic to Claude Code.

*To reload your terminal after installation, close and reopen it, or run:* `source ~/.zshrc`.
