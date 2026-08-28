# Unified Token Dashboard — Final Implementation Plan (Adaptive Discovery)

## Core Philosophy
> **Auto-discover what's available → Deep-track only active tools → Graceful degradation for missing tools**

The dashboard adapts to the user's actual setup. No hard dependencies. If Ollama isn't running, don't show Ollama panel. If Antigravity CLI isn't installed, skip it. User sees only what's relevant.

---

## Architecture: Adaptive Adapter System

```
┌─────────────────────────────────────────────────────────────────┐
│                    ADAPTIVE SCANNER                             │
│  1. Scan known paths for each adapter                           │
│  2. Probe health (CLI exists? API responds? DB readable?)       │
│  3. Load ONLY healthy adapters                                  │
│  4. Deep-track active, surface-track inactive                   │
└────────────────────────────┬────────────────────────────────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
    ┌───────────────┐ ┌─────────────┐ ┌─────────────┐
    │ ACTIVE (Deep) │ │ INACTIVE    │ │ MISSING     │
    │ • Full history│ │ • Last seen │ │ • Not shown │
    │ • Real-time   │ │ • Config    │ │ • Install   │
    │ • Quotas      │ │   hint      │ │   hint      │
    │ • Alerts      │ │ • Shallow   │ │             │
    │ • Projections │ │   scan      │ │             │
    └───────────────┘ └─────────────┘ └─────────────┘
```

### Adapter States
| State | Criteria | Tracking Depth | UI Presence |
|-------|----------|----------------|-------------|
| **ACTIVE** | DB exists + readable + recent data (< 24h) | Full (history, quotas, alerts, projections) | Full panel + charts |
| **STALE** | DB exists but no recent data (> 24h) | Last session only + config hint | Collapsed panel + "Last used: 3 days ago" |
| **CONFIGURED** | No DB but adapter configured in YAML | Config hint + install guide | Minimal row in Sources list |
| **MISSING** | Not installed, not configured | None | Hidden (unless "Show all" toggled) |

---

## Adapter Registry (Auto-Discovery)

### Known Tool Paths
```python
ADAPTER_PROBES = {
    "claude": {
        "paths": [
            "~/.claude/usage.db",
            "~/.claude/projects/",
        ],
        "cli_check": ["claude", "--version"],
        "api_check": None,
    },
    "opencode": {
        "paths": ["~/.local/share/opencode/opencode.db"],
        "cli_check": ["opencode", "--version"],
        "api_check": None,
    },
    "codex": {
        "paths": ["~/.codex/state_5.sqlite"],
        "cli_check": ["codex", "--version"],
        "api_check": None,
    },
    "9router": {
        "paths": ["~/.9router/db/data.sqlite"],
        "cli_check": ["9router", "--version"],
        "api_check": "http://localhost:20128/health",
    },
    "hermes": {
        "paths": ["~/.hermes/state.db"],
        "cli_check": ["hermes", "--version"],
        "api_check": None,
    },
    "routingmagic": {
        "paths": ["~/.routingmagic/metrics/token_metrics.db"],
        "cli_check": None,  # Internal
        "api_check": None,
    },
    "ollama": {
        "paths": ["~/.ollama/"],
        "cli_check": ["ollama", "list"],
        "api_check": "http://localhost:11434/api/tags",
        "proxy_path": "~/.routingmagic/metrics/ollama_usage.db",
    },
    "antigravity": {
        "paths": [
            "~/Library/Application Support/Antigravity/",
            "~/Library/Application Support/Antigravity IDE/",
        ],
        "cli_check": ["agy", "/usage", "--json"],  # Test JSON output
        "api_check": None,  # Requires Google auth
    },
    "chatgpt": {
        "paths": [],  # No local DB - uses OpenAI API directly
        "cli_check": None,
        "api_check": "https://api.openai.com/v1/usage",  # Requires API key
    },
    "gemini": {
        "paths": [],  # Google AI Studio - no local DB
        "cli_check": None,
        "api_check": "https://generativelanguage.googleapis.com/v1beta/models",  # Requires API key
    },
}
```

### Discovery Logic
```python
def discover_adapters() -> Dict[str, AdapterStatus]:
    """Run on every scan. Returns {adapter_name: AdapterStatus}."""
    results = {}
    
    for name, probe in ADAPTER_PROBES.items():
        # 1. Check paths exist
        paths_exist = any(Path(p).expanduser().exists() for p in probe["paths"])
        
        # 2. Check CLI available
        cli_ok = False
        if probe["cli_check"]:
            try:
                subprocess.run(probe["cli_check"], capture_output=True, timeout=3)
                cli_ok = True
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass
        
        # 3. Check API responsive
        api_ok = False
        if probe["api_check"]:
            try:
                urllib.request.urlopen(probe["api_check"], timeout=3)
                api_ok = True
            except Exception:
                pass
        
        # 4. Determine state
        if paths_exist and (cli_ok or api_ok):
            state = "ACTIVE"
        elif paths_exist:
            state = "STALE"
        elif name in get_configured_adapters():  # From quotas.yaml
            state = "CONFIGURED"
        else:
            state = "MISSING"
        
        results[name] = AdapterStatus(name, state, paths_exist, cli_ok, api_ok)
    
    return results
```

---

## Quota System: Finite Token Budget Awareness

You emphasized: **"token consumption is finite"** - the dashboard must make this visible.

### Quota Config (`~/.routingmagic/quotas.yaml`)
```yaml
# User's finite budgets
budgets:
  # Hard limits (enforced alerts)
  monthly_usd: 50.00           # Total monthly spend cap
  daily_tokens: 2000000        # Daily token ceiling
  
  # Per-provider (from their plans)
  providers:
    anthropic:
      type: subscription
      plan: max                # max|pro|api|free
      # Auto-detected: 1M tokens / 5hr window
      # User can override:
      # periodic_tokens: 1000000
      # refresh_hours: 5
      
    openrouter:
      type: credits
      balance_usd: 10.00       # User updates manually or via API
      auto_refresh: false
      
    nvidia_nim:
      type: rate_limit
      rpm: 40
      tpm: 200000
      
    openai:
      type: credits
      balance_usd: 5.00
      
    google_vertex:
      type: rate_limit
      rpm: 60
      project_id: "my-project"
      
    ollama:
      type: custom_cap
      daily_tokens: 1000000    # Self-imposed limit
      weekly_tokens: 5000000
      
    antigravity:
      type: subscription
      plan: ultra              # ultra|pro|free
      # Baseline from Google AI Ultra: highest quota, 5hr refresh
      # G1 Credits for overages:
      credits_usd: 50.00
      
    chatgpt:
      type: credits
      balance_usd: 20.00       # OpenAI API credits
      
    gemini:
      type: credits
      balance_usd: 10.00       # Google AI Studio credits

# Alert thresholds
alerts:
  warning_pct: 80
  critical_pct: 90
  exhausted_pct: 100
  notify_desktop: true
```

### Quota Dashboard Panel (Always Visible for Active Tools)
```
┌────────────────────────────────────────────────────────────────────────┐
│ 💰 TOKEN BUDGET STATUS                                    [🔄 Refresh]  │
├────────────────────────────────────────────────────────────────────────┤
│ Monthly Budget: $50.00  │  Spent: $12.40 (25%)  │  Remaining: $37.60  │
│ Daily Cap: 2.0M tokens  │  Used: 450K (23%)     │  Remaining: 1.55M   │
├──────────────┬──────────────┬──────────┬───────────┬────────┬─────────┤
│ Provider     │ Model        │ Used     │ Remaining │ % Used │ Status  │
├──────────────┼──────────────┼──────────┼───────────┼────────┼─────────┤
│ Anthropic    │ Sonnet 4.6   │ 234K/1M  │ 766K      │ 23%    │ ████░░  │
│              │ 5hr window   │          │ (4.2hr)   │        │ OK      │
├──────────────┼──────────────┼──────────┼───────────┼────────┼─────────┤
│ OpenRouter   │ Nemotron 3   │ $3.20/$10│ $6.80     │ 32%    │ █████░  │
│              │ credits      │          │           │        │ OK      │
├──────────────┼──────────────┼──────────┼───────────┼────────┼─────────┤
│ NVIDIA NIM   │ Nemotron 3   │ 38/40 RPM│ 2 RPM     │ 95%    │ ████████████ WARN │
│              │ rate limit   │          │           │        │         │
├──────────────┼──────────────┼──────────┼───────────┼────────┼─────────┤
│ Ollama       │ Qwen3:8b     │ 450K/1M  │ 550K      │ 45%    │ ██████░ │
│              │ local cap    │          │           │        │ OK      │
├──────────────┼──────────────┼──────────┼───────────┼────────┼─────────┤
│ Antigravity  │ Gemini 3.5   │ 1.2M/5M  │ 3.8M      │ 24%    │ ████░░  │
│ (Ultra)      │ 5hr window   │          │ (3.8hr)   │        │ OK      │
├──────────────┼──────────────┼──────────┼───────────┼────────┼─────────┤
│ Antigravity  │ G1 Credits   │ $45/$50  │ $5        │ 90%    │ ████████████ CRIT │
│              │ overage      │          │           │        │         │
├──────────────┼──────────────┼──────────┼───────────┼────────┼─────────┤
│ ChatGPT      │ GPT-4o       │ $12/$20  │ $8        │ 60%    │ ████████░ │
│              │ API credits  │          │           │        │ OK      │
├──────────────┼──────────────┼──────────┼───────────┼────────┼─────────┤
│ Gemini       │ 2.5 Pro      │ $3/$10   │ $7        │ 30%    │ █████░░ │
│              │ API credits  │          │           │        │ OK      │
└──────────────┴──────────────┴──────────┴───────────┴────────┴─────────┘
│ 🔴 CRITICAL: Antigravity G1 Credits at 90% - 5 hours until refresh │
│ 🟡 WARNING: NVIDIA NIM at 95% RPM - consider fallback to OpenRouter │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Core Infrastructure (Week 1)

### 1.1 Adaptive Scanner (`adaptive_scanner.py` - NEW)
```python
class AdaptiveScanner:
    def __init__(self):
        self.adapter_status = {}
        self.active_adapters = []
        self.stale_adapters = []
    
    def discover(self) -> Dict[str, AdapterStatus]:
        """Run discovery probes, return status map."""
        
    def scan(self, verbose=True) -> ScanResult:
        """Only scan ACTIVE adapters. Update STALE with shallow scan."""
        # 1. Discover current state
        self.adapter_status = self.discover()
        self.active_adapters = [n for n,s in self.adapter_status.items() if s.state == "ACTIVE"]
        self.stale_adapters = [n for n,s in self.adapter_status.items() if s.state == "STALE"]
        
        # 2. Deep scan active
        for name in self.active_adapters:
            rows = ADAPTERS[name]()
            self._upsert_deep(name, rows)
        
        # 3. Shallow scan stale (just update last_seen)
        for name in self.stale_adapters:
            self._upsert_shallow(name)
        
        # 4. Record discovery state
        self._record_discovery_state()
        
        return ScanResult(...)
```

### 1.2 Port Auto-Discovery & Daemon
```python
# dashboard_server.py
def find_free_port(start=9898, max_tries=100):
    for port in range(start, start + max_tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('localhost', port)) != 0:
                return port
    raise RuntimeError("No free ports in range")

def run_as_daemon():
    # Double-fork
    # Write PID to ~/.routingmagic/dashboard.pid
    # Logs to ~/.routingmagic/dashboard.log (rotating)
```

### 1.3 Extended Schema (`unified_scanner.py`)
```sql
-- Adapter discovery state
CREATE TABLE IF NOT EXISTS adapter_state (
    name        TEXT PRIMARY KEY,
    state       TEXT,          -- ACTIVE, STALE, CONFIGURED, MISSING
    last_seen   TEXT,          -- Last successful deep scan
    last_shallow TEXT,        -- Last shallow scan
    cli_ok      INTEGER,       -- 0/1
    api_ok      INTEGER,       -- 0/1
    paths_found TEXT,          -- JSON array
    error_msg   TEXT
);

-- Quota budgets (from YAML)
CREATE TABLE IF NOT EXISTS quota_budgets (
    provider    TEXT PRIMARY KEY,
    budget_type TEXT,          -- subscription, credits, rate_limit, custom_cap
    config_json TEXT,
    updated_at  TEXT
);

-- Quota snapshots (computed per scan)
CREATE TABLE IF NOT EXISTS quota_snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    provider    TEXT,
    model       TEXT,
    timestamp   TEXT,
    consumed    INTEGER,
    remaining   INTEGER,
    limit_value INTEGER,
    pct_used    REAL,
    window_start TEXT,        -- For subscription types
    window_end   TEXT
);

-- Budget alerts
CREATE TABLE IF NOT EXISTS budget_alerts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    provider    TEXT,
    model       TEXT,
    timestamp   TEXT,
    level       TEXT,          -- WARNING, CRITICAL, EXHAUSTED
    message     TEXT,
    pct_used    REAL,
    acknowledged INTEGER DEFAULT 0
);
```

---

## Phase 2: Adapters (Week 1-2)

### 2.1 Active Tool Adapters (Deep Tracking)
| Tool | Adapter | Data Source | Quota Source |
|------|---------|-------------|--------------|
| **Claude Code** | ✅ `scan_claude` | `~/.claude/usage.db` | Plan (Max/Pro) + API credits |
| **OpenCode** | ✅ `scan_opencode` | `~/.local/share/opencode/opencode.db` | Built-in |
| **Codex** | ✅ `scan_codex` | `~/.codex/state_5.sqlite` | OpenAI API |
| **9router** | ✅ `scan_9router` | `~/.9router/db/data.sqlite` | OpenRouter credits |
| **Hermes** | ✅ `scan_hermes` | `~/.hermes/state.db` | Custom |
| **RoutingMagic** | ✅ `scan_routingmagic` | `~/.routingmagic/metrics/token_metrics.db` | NIM RPM + OR free |

### 2.2 Your Current Tools (Priority Deep)
| Tool | Adapter | Data Source | Quota Source | Notes |
|------|---------|-------------|--------------|-------|
| **Ollama** | 🔲 `scan_ollama` | **Proxy DB** (`ollama_usage.db`) | Custom cap (YAML) | **Needs `ollama-proxy`** |
| **Antigravity** | 🔲 `scan_antigravity` | **CLI parse** (`agy /usage --json`) | Plan (Ultra/Pro) + G1 Credits | Check JSON flag |
| **ChatGPT** | 🔲 `scan_chatgpt` | **OpenAI API** (`/v1/usage`) | API credits | Requires `OPENAI_API_KEY` |

### 2.3 Competitor Adapters (Pluggable, Auto-Discovered)
```python
# These load automatically IF installed
COMPETITOR_ADAPTERS = {
    "cursor": {"paths": ["~/.cursor/"], "cli": ["cursor", "--version"]},
    "windsurf": {"paths": ["~/.windsurf/"], "cli": ["windsurf", "--version"]},
    "continue": {"paths": ["~/.continue/"], "cli": ["continue", "--version"]},
    "aider": {"paths": ["~/.aider/"], "cli": ["aider", "--version"]},
    "sourcegraph": {"paths": [], "api": "https://api.sourcegraph.com/"},
    "copilot": {"paths": [], "api": "https://api.github.com/copilot/usage"},
    "tabnine": {"paths": ["~/.tabnine/"], "cli": ["tabnine", "--version"]},
    "codeium": {"paths": ["~/.codeium/"], "cli": ["codeium", "--version"]},
    "deepseek": {"paths": [], "api": "https://api.deepseek.com/usage"},
    "anthropic_api": {"paths": [], "api": "https://api.anthropic.com/v1/usage"},
    "groq": {"paths": [], "api": "https://api.groq.com/openai/v1/usage"},
    "together": {"paths": [], "api": "https://api.together.xyz/usage"},
    "perplexity": {"paths": [], "api": "https://api.perplexity.ai/usage"},
}
```

### 2.4 Ollama Proxy (Required for Deep Tracking)
```python
# ollama_proxy.py - Runs as `ollama-proxy serve`
# Proxies localhost:11435 → localhost:11434
# Logs ALL requests to SQLite with token counts

class OllamaProxy:
    def __init__(self):
        self.listen_port = 11435
        self.target_port = 11434
        self.db = Path.home() / ".routingmagic" / "metrics" / "ollama_usage.db"
    
    async def handle_request(self, request):
        # Forward to real Ollama
        response = await forward(request)
        
        # Extract tokens from response
        prompt_tokens = response.get("prompt_eval_count", 0)
        completion_tokens = response.get("eval_count", 0)
        
        # Log to DB
        self.log_usage(
            model=request.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            duration=response.get("total_duration"),
        )
        
        return response
```

### 2.5 Antigravity Adapter
```python
# adapters/antigravity.py
def scan_antigravity() -> List[Dict]:
    """Parse `agy /usage --json` and `agy /credits --json`."""
    # Test if JSON flag works
    usage_json = run_cli_json(["agy", "/usage", "--json"])
    credits_json = run_cli_json(["agy", "/credits", "--json"])
    
    if not usage_json:
        # Fallback: parse TUI text output (brittle)
        return parse_antigravity_tui(run_cli_text(["agy", "/usage"]))
    
    # Parse quota data
    rows = []
    for model_quota in usage_json.get("models", []):
        rows.append({
            "source": "antigravity",
            "session_id": f"ag-{model_quota['model']}-{datetime.now().date()}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "model": model_quota["model"],
            "input_tokens": model_quota.get("input_tokens_used", 0),
            "output_tokens": model_quota.get("output_tokens_used", 0),
            "cache_read": 0,
            "cache_write": 0,
            "reasoning_tokens": 0,
            "cost": 0.0,  # Baseline quota = free
            "project": "antigravity",
            "source_metadata": json.dumps({
                "quota_limit": model_quota.get("limit"),
                "quota_remaining": model_quota.get("remaining"),
                "refresh_window_hours": 5,
                "plan": "ultra",  # From credits_json
            }),
        })
    
    # Add G1 Credits as separate "model"
    if credits_json:
        rows.append({
            "source": "antigravity",
            "session_id": f"ag-credits-{datetime.now().date()}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "model": "G1 Credits (overage)",
            "input_tokens": 0,
            "output_tokens": 0,
            "cost": credits_json.get("spent_usd", 0),
            "source_metadata": json.dumps({
                "credits_total": credits_json.get("total_usd"),
                "credits_remaining": credits_json.get("remaining_usd"),
                "credits_spent": credits_json.get("spent_usd"),
            }),
        })
    
    return rows
```

---

## Phase 3: Quota Engine (Week 2)

### 3.1 Quota Calculation (`quota_engine.py`)
```python
class QuotaEngine:
    def __init__(self):
        self.budgets = load_quota_budgets()  # From YAML
    
    def compute_all(self, db) -> List[QuotaSnapshot]:
        snapshots = []
        
        for provider, budget in self.budgets.items():
            if budget.type == "subscription":
                snapshots.extend(self._compute_subscription(provider, budget, db))
            elif budget.type == "credits":
                snapshots.extend(self._compute_credits(provider, budget, db))
            elif budget.type == "rate_limit":
                snapshots.extend(self._compute_rate_limit(provider, budget, db))
            elif budget.type == "custom_cap":
                snapshots.extend(self._compute_custom_cap(provider, budget, db))
        
        return snapshots
    
    def _compute_subscription(self, provider, budget, db):
        # Get window start (e.g., 5-hour rolling for Anthropic)
        window_start = self._get_window_start(budget.refresh_hours)
        
        # Query tokens in current window
        used = db.query("""
            SELECT model, SUM(input_tokens + output_tokens) as used
            FROM unified_turns
            WHERE source = ? AND timestamp >= ?
            GROUP BY model
        """, (provider, window_start))
        
        for row in used:
            limit = budget.get_model_limit(row.model)
            remaining = max(0, limit - row.used)
            pct = (row.used / limit * 100) if limit else 0
            
            yield QuotaSnapshot(
                provider=provider,
                model=row.model,
                consumed=row.used,
                remaining=remaining,
                limit_value=limit,
                pct_used=pct,
                window_start=window_start,
                window_end=window_start + timedelta(hours=budget.refresh_hours),
            )
    
    def _compute_credits(self, provider, budget, db):
        # Convert token usage to USD cost
        spent_usd = db.query("""
            SELECT SUM(cost) FROM unified_turns WHERE source = ?
        """, (provider,)) or 0
        
        remaining_usd = budget.balance_usd - spent_usd
        
        yield QuotaSnapshot(
            provider=provider,
            model=f"{provider} credits",
            consumed=int(spent_usd * 1_000_000 / avg_cost_per_million(provider)),
            remaining=int(max(0, remaining_usd) * 1_000_000 / avg_cost_per_million(provider)),
            limit_value=int(budget.balance_usd * 1_000_000 / avg_cost_per_million(provider)),
            pct_used=(spent_usd / budget.balance_usd * 100) if budget.balance_usd else 0,
        )
```

### 3.2 Background Monitor (in `dashboard_server.py`)
```python
def start_quota_monitor():
    """Background thread: runs every 60s."""
    def loop():
        while True:
            try:
                snapshots = quota_engine.compute_all(get_db())
                save_snapshots(snapshots)
                
                # Check alerts
                for snap in snapshots:
                    if snap.pct_used >= 100:
                        create_alert(snap, "EXHAUSTED")
                    elif snap.pct_used >= 90:
                        create_alert(snap, "CRITICAL")
                    elif snap.pct_used >= 80:
                        create_alert(snap, "WARNING")
                
                # Broadcast via WebSocket
                broadcast_alerts()
                
            except Exception as e:
                log.error(f"Quota monitor error: {e}")
            
            time.sleep(60)
    
    threading.Thread(target=loop, daemon=True).start()
```

---

## Phase 4: Dashboard UI (Week 2-3)

### 4.1 Adaptive Source Filter Bar
```html
<!-- Only shows ACTIVE + STALE sources. CONFIGURED hidden unless "Show All" -->
<div class="source-filter">
  <button class="source-chip active" data-source="claude">
    <span class="dot" style="background: #d97757"></span>
    Claude Code <span class="count">1.2M</span>
    <span class="badge">ACTIVE</span>
  </button>
  <button class="source-chip active" data-source="ollama">
    <span class="dot" style="background: #74C991"></span>
    Ollama <span class="count">450K</span>
    <span class="badge">ACTIVE</span>
  </button>
  <button class="source-chip stale" data-source="codex">
    <span class="dot" style="background: #D9A84E"></span>
    Codex <span class="count">0</span>
    <span class="badge">STALE</span>
  </button>
  <button class="source-chip configured" data-source="windsurf" style="display:none">
    <span class="dot" style="background: #666"></span>
    Windsurf (configured, not installed)
  </button>
  <button id="show-all-toggle" onclick="toggleShowAll()">Show All (12)</button>
</div>
```

### 4.2 Budget Status Header (Always Visible)
```html
<div class="budget-header">
  <div class="budget-item">
    <span class="label">Monthly Budget</span>
    <span class="value">$12.40 / $50.00</span>
    <span class="pct">25%</span>
    <div class="bar"><div class="fill" style="width: 25%"></div></div>
  </div>
  <div class="budget-item">
    <span class="label">Daily Cap</span>
    <span class="value">450K / 2.0M</span>
    <span class="pct">23%</span>
    <div class="bar"><div class="fill" style="width: 23%"></div></div>
  </div>
  <div class="alert-banner critical">
    🔴 Antigravity G1 Credits: 90% used ($5 remaining)
  </div>
</div>
```

### 4.3 WebSocket for Real-time Alerts
```javascript
// dashboard HTML
const ws = new WebSocket(`ws://${location.host}/ws`);
ws.onmessage = (e) => {
    const alert = JSON.parse(e.data);
    if (alert.level === 'EXHAUSTED') {
        showDesktopNotification(`🚨 ${alert.provider} ${alert.model} EXHAUSTED`);
        flashRow(alert.provider, alert.model, 'critical');
    } else if (alert.level === 'CRITICAL') {
        showDesktopNotification(`⚠️ ${alert.provider} ${alert.model} at ${alert.pct_used}%`);
        flashRow(alert.provider, alert.model, 'warning');
    }
    updateQuotaPanel(); // Re-fetch /api/quotas
};
```

---

## Phase 5: Packaging (Week 3)

### 5.1 Standalone Package: `routingmagic-dashboard`
```toml
# pyproject.toml
[project]
name = "routingmagic-dashboard"
version = "1.0.0"
description = "Adaptive universal AI token usage dashboard"
requires-python = ">=3.10"
dependencies = []

[project.optional-dependencies]
dev = ["pytest", "pytest-asyncio"]

[project.entry-points]
console_scripts = [
    "rm-dashboard = routingmagic_dashboard.cli:main",
    "ollama-proxy = routingmagic_dashboard.ollama_proxy:main",
]

[project.entry-points."routingmagic.dashboard.adapters"]
# Built-in
claude = "routingmagic_dashboard.adapters.claude:scan_claude"
opencode = "routingmagic_dashboard.adapters.opencode:scan_opencode"
codex = "routingmagic_dashboard.adapters.codex:scan_codex"
nine_router = "routingmagic_dashboard.adapters.nine_router:scan_9router"
hermes = "routingmagic_dashboard.adapters.hermes:scan_hermes"
routingmagic = "routingmagic_dashboard.adapters.routingmagic:scan_routingmagic"
# Your tools
ollama = "routingmagic_dashboard.adapters.ollama:scan_ollama"
antigravity = "routingmagic_dashboard.adapters.antigravity:scan_antigravity"
chatgpt = "routingmagic_dashboard.adapters.chatgpt:scan_chatgpt"
gemini = "routingmagic_dashboard.adapters.gemini:scan_gemini"
# Competitors (auto-load if installed)
cursor = "routingmagic_dashboard.adapters.cursor:scan_cursor"
windsurf = "routingmagic_dashboard.adapters.windsurf:scan_windsurf"
# ... etc
```

### 5.2 Installation
```bash
# Standalone
pipx install routingmagic-dashboard
rm-dashboard scan
rm-dashboard dashboard
ollama-proxy serve  # Run in background for Ollama tracking

# In RoutingMagic
python3 dashboard_server.py scan
python3 dashboard_server.py
```

---

## Phase 6: RoutingMagic Integration (Week 3)

### 6.1 Auto-Start Daemon
```python
# openai_wrapper.py - in repl() startup
def _ensure_dashboard_running():
    pid_file = Path.home() / ".routingmagic" / "dashboard.pid"
    if pid_file.exists():
        pid = int(pid_file.read_text().strip())
        if is_process_alive(pid):
            return
    
    subprocess.Popen([
        sys.executable, 
        str(Path(__file__).parent / "dashboard_server.py")
    ], start_new_session=True,
       stdout=open(log_file, 'a'), stderr=subprocess.STDOUT)
```

### 6.2 REPL Commands
```python
# In repl() loop
if line_stripped == "/dashboard":
    import webbrowser
    webbrowser.open("http://localhost:9898")
    continue

if line_stripped == "/quota":
    print(format_terminal_quota_status())
    continue

if line_stripped == "/sources":
    print(format_adapter_status())  # Shows ACTIVE/STALE/CONFIGURED
    continue
```

### 6.3 RoutingMagic Deep Metrics
- Caveman compression savings %
- Mythos effort distribution
- Council invocation rate
- Smart router accuracy
- Fallback tier usage

---

## File Summary

### Modified
1. `dashboard_server.py` → Adaptive discovery, daemon, WebSocket, quota API
2. `unified_scanner.py` → Extended schema (adapter_state, quota_budgets, quota_snapshots, budget_alerts)
3. `dashboard_adapters.py` → Refactored to `adapters/` package with entry points
4. `metrics_collector.py` → Already pushes to unified DB ✅

### New
1. `adaptive_scanner.py` - Discovery + state-aware scanning
2. `quota_engine.py` - QuotaEngine, budgets, alerts, projections
3. `adapters/ollama.py` - Reads from Ollama proxy DB
4. `adapters/antigravity.py` - Parses `agy /usage --json`
5. `adapters/chatgpt.py` - OpenAI API usage endpoint
6. `adapters/gemini.py` - Google AI Studio API
7. `adapters/competitors/*.py` - 10+ competitor adapters (pluggable)
8. `ollama_proxy.py` - Middleware server + CLI
9. `quota_config.yaml` - User budgets (created on first run)
10. `routingmagic_dashboard/` - Standalone package

---

## Success Criteria

| Criterion | Test |
|-----------|------|
| **Adaptive discovery** | `rm-dashboard scan` only loads adapters for tools actually installed |
| **Deep tracking active** | Claude, Ollama, Antigravity show full history + quotas + alerts |
| **Graceful degradation** | Missing tools hidden; stale tools show "Last used: X days ago" |
| **Finite budget visibility** | Budget header shows $ spent/remaining, daily token cap, per-provider quotas |
| **Real-time alerts** | Desktop notification at 80%/90%/100% thresholds |
| **Auto-port** | `rm-dashboard dashboard` finds free port 9898→9899→... |
| **Daemon mode** | Survives terminal close, auto-starts with RoutingMagic REPL |
| **Standalone install** | `pipx install routingmagic-dashboard` works on clean machine |
| **Ollama tracking** | `ollama-proxy serve` enables full Ollama token history |

---

## Next Steps

1. **Verify Antigravity CLI JSON**: Run `agy /usage --json` and `agy /credits --json` - do they output valid JSON?
2. **Test Ollama Proxy**: Confirm `ollama-proxy serve` works and logs tokens correctly
3. **Confirm Budget Defaults**: Review `quota_config.yaml` values match your actual plans
4. **Begin Phase 1**: `adaptive_scanner.py` + schema extensions + daemon mode

Ready to implement when you confirm the Antigravity JSON output and Ollama proxy approach.
