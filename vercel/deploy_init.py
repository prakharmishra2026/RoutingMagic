"""Initialize database for Vercel deployment by copying from local."""
import shutil
from pathlib import Path

src_db = Path.home() / ".routingmagic" / "metrics" / "usage_unified.db"
dst_db = Path("/tmp/usage_unified.db")
dst_registry = Path("/tmp/registry")
src_registry = Path.home() / ".routingmagic" / "registry"

print(f"Copying {src_db} -> {dst_db}")
dst_db.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(src_db, dst_db)
print(f"DB size: {dst_db.stat().st_size:,} bytes")

print(f"Copying registry {src_registry} -> {dst_registry}")
dst_registry.mkdir(parents=True, exist_ok=True)
for f in src_registry.glob("*"):
    shutil.copy2(f, dst_registry / f.name)
    print(f"  Copied {f.name}")

print("Initialization complete")
