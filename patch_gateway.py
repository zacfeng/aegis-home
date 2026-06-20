import os
import sys
import gateway

filepath = os.path.join(os.path.dirname(gateway.__file__), "run.py")

if not os.path.exists(filepath):
    print(f"ERROR: {filepath} not found.")
    sys.exit(1)

with open(filepath, "r") as f:
    content = f.read()

target = "    from cron.scheduler_provider import resolve_cron_scheduler"

replacement = """    # TEMPORARY WORKAROUND: Remove plugins directory from sys.path to prevent plugins/cron from shadowing core cron package
    import sys
    _orig_path = list(sys.path)
    sys.path = [p for p in sys.path if not p.endswith('/plugins') and not p.endswith('\\\\plugins')]
    try:
        from cron.scheduler_provider import resolve_cron_scheduler
    finally:
        sys.path = _orig_path"""

if target in content:
    content = content.replace(target, replacement)
    with open(filepath, "w") as f:
        f.write(content)
    print("SUCCESS: gateway/run.py patched successfully!")
else:
    print("WARNING: Target code not found in gateway/run.py.")
