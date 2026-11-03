import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def pytest_sessionfinish(session, exitstatus):
    """При заданной ASTRA_VERIFY_REPORT записывает наибольшие расхождения с эталонами NASA в JSON."""
    import json
    import os
    out = os.environ.get("ASTRA_VERIFY_REPORT")
    if not out:
        return
    mod = sys.modules.get("test_nasa_reference")
    if mod is None:
        return
    rows = [{"test": t, "quantity": w, **d} for (t, w), d in sorted(mod.DEVIATIONS.items())]
    Path(out).write_text(json.dumps({"exitstatus": int(exitstatus), "rows": rows}, ensure_ascii=False, indent=1),
                         encoding="utf-8")
