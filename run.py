"""ArisuAgentIntegration --- one-click launcher for the AI core.

This script starts the FastAPI + Gradio server (ai_core).
All channel processes (QQ bot, Bilibili stream, Unity desktop pet)
are managed through the Channels tab in the Gradio admin UI at /admin.
"""

from __future__ import annotations

import os
import sys
import traceback


def main() -> None:
    ai_core = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ai_core")
    sys.path.insert(0, ai_core)
    os.chdir(ai_core)

    try:
        import uvicorn
    except ImportError as e:
        print(f"[ERROR] Missing dependency: {e}")
        print(f"  Python: {sys.executable}")
        print(f"  Run: pip install -r requirements.txt")
        if sys.platform == "win32":
            input("Press Enter to exit...")
        sys.exit(1)

    try:
        from main import app  # type: ignore
    except Exception:
        print("[ERROR] Failed to import ai_core.main:")
        traceback.print_exc()
        if sys.platform == "win32":
            input("Press Enter to exit...")
        sys.exit(1)

    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))

    print("=" * 48)
    print(f"  ArisuAgentIntegration AI Core")
    print(f"  http://{host}:{port}")
    print(f"  Admin UI:  http://localhost:{port}/admin")
    print(f"  API Docs:  http://localhost:{port}/docs")
    print("=" * 48)
    print()
    print("Channels are managed from the Admin UI (Channels tab).")
    print()

    try:
        uvicorn.run(app, host=host, port=port, workers=1)
    except KeyboardInterrupt:
        print("\nShutting down...")
    except Exception:
        traceback.print_exc()
        if sys.platform == "win32":
            input("Press Enter to exit...")
        sys.exit(1)


if __name__ == "__main__":
    main()
