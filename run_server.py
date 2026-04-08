# backend/run_server.py
"""
Entry point for PyInstaller-bundled backend.
Starts the FastAPI server via uvicorn programmatically.
Also serves the frontend static files so the whole app runs from one exe.
"""
import os
import sys
import webbrowser
import threading

if getattr(sys, 'frozen', False):
    bundle_dir = sys._MEIPASS
    exe_dir = os.path.dirname(sys.executable)
    os.chdir(exe_dir)
    sys.path.insert(0, bundle_dir)
    env_path = os.path.join(exe_dir, '.env')
    if os.path.exists(env_path):
        from dotenv import load_dotenv
        load_dotenv(env_path)
    if not os.getenv('SENTRIBID_DB_URL'):
        db_path = os.path.join(exe_dir, 'sentribid.db')
        os.environ['SENTRIBID_DB_URL'] = f'sqlite:///{db_path}'
    if not os.getenv('SENTRIBID_UPLOAD_DIR'):
        os.environ['SENTRIBID_UPLOAD_DIR'] = os.path.join(exe_dir, 'uploads')
else:
    from dotenv import load_dotenv
    load_dotenv()

import uvicorn

def open_browser(port):
    import time
    time.sleep(2.5)
    url = f"http://127.0.0.1:{port}"
    print(f"[SentriBiD] Opening browser: {url}")
    webbrowser.open(url)

if __name__ == '__main__':
    port = int(os.getenv('SENTRIBID_PORT', '8099'))
    claude_ok = bool(os.getenv('CLAUDE_API_KEY') or os.getenv('ANTHROPIC_API_KEY'))
    print("=" * 55)
    print("  SentriBiD v0.7.0 - Gov Bid Intelligence")
    print("  AI-Powered Discovery | Bid Analysis | Proposals")
    print("  Claude AI Copilot | Subcontract Scout")
    print("=" * 55)
    print(f"  Server:    http://127.0.0.1:{port}")
    print(f"  Working:   {os.getcwd()}")
    print(f"  Database:  {os.getenv('SENTRIBID_DB_URL', 'default')}")
    print(f"  Claude AI: {'Configured' if claude_ok else 'Not set - add CLAUDE_API_KEY or ANTHROPIC_API_KEY to .env'}")
    print(f"  OpenAI:    {'Configured' if os.getenv('OPENAI_API_KEY') else 'Not set'}")
    print(f"  Gemini:    {'Configured' if os.getenv('GEMINI_API_KEY') else 'Not set'}")
    print()
    print("  DO NOT CLOSE THIS WINDOW while using SentriBiD!")
    print("  The app runs in your browser.")
    print("=" * 55)
    print()
    threading.Thread(target=open_browser, args=(port,), daemon=True).start()
    uvicorn.run("app.main:app", host="127.0.0.1", port=port, log_level="info")
