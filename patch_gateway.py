import os
import sys

filepath = "/usr/local/lib/python3.11/site-packages/gateway/run.py"

if not os.path.exists(filepath):
    print(f"ERROR: {filepath} not found.")
    sys.exit(1)

with open(filepath, "r") as f:
    content = f.read()

target = "    from cron.scheduler_provider import resolve_cron_scheduler"

replacement = """    print("[GATEWAY-DEBUG] CWD:", os.getcwd(), flush=True)
    print("[GATEWAY-DEBUG] sys.path:", sys.path, flush=True)
    import traceback
    try:
        from cron.scheduler_provider import resolve_cron_scheduler
        print("[GATEWAY-DEBUG] Import cron.scheduler_provider: SUCCESS", flush=True)
    except Exception as e:
        print("[GATEWAY-DEBUG] Import cron.scheduler_provider: FAILED:", e, flush=True)
        traceback.print_exc()
        raise"""

if target in content:
    content = content.replace(target, replacement)
    with open(filepath, "w") as f:
        f.write(content)
    print("SUCCESS: gateway/run.py patched successfully!")
else:
    # Try finding it with different indentation or look for it generally
    print("WARNING: Target code not found in gateway/run.py.")
