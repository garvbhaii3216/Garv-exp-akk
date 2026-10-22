import sys
import os
import webbrowser
import threading
from http.server import SimpleHTTPRequestHandler, HTTPServer

HTML_CONTENT = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>ExpenseTrack • Desktop Financial Report & Analytics Viewer</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap" rel="stylesheet">
  <style>
    body { font-family: 'Plus Jakarta Sans', sans-serif; }
  </style>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen p-6 sm:p-10">
  <div class="max-w-4xl mx-auto space-y-6">
    <div class="flex items-center justify-between p-6 bg-slate-900 rounded-3xl border border-slate-800 shadow-xl">
      <div class="flex items-center gap-4">
        <div class="w-12 h-12 rounded-2xl bg-indigo-600 flex items-center justify-center text-white text-xl font-bold shadow-lg shadow-indigo-600/40">
          ₹
        </div>
        <div>
          <h1 class="text-xl font-black text-white">ExpenseTrack Desktop Report Viewer</h1>
          <p class="text-xs text-slate-400">Portable Offline Financial Statements & Analytics Engine</p>
        </div>
      </div>
      <span class="px-3 py-1 rounded-full text-xs font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
        Standalone Portable EXE
      </span>
    </div>

    <div class="p-8 bg-slate-900/90 rounded-3xl border border-slate-800 shadow-xl space-y-4">
      <h2 class="text-lg font-bold text-white">Verified Financial Overview</h2>
      <p class="text-xs text-slate-400 leading-relaxed">
        This standalone desktop edition allows you to review your offline ledger, analyze expenditures, and launch the primary ExpenseTrack suite.
      </p>
      <div class="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-2">
        <div class="p-4 bg-slate-950 rounded-2xl border border-slate-800">
          <span class="text-[10px] text-slate-400 font-bold uppercase tracking-wider">Storage Mode</span>
          <div class="text-base font-extrabold text-white mt-1">100% Offline SQLite</div>
        </div>
        <div class="p-4 bg-slate-950 rounded-2xl border border-slate-800">
          <span class="text-[10px] text-slate-400 font-bold uppercase tracking-wider">Security State</span>
          <div class="text-base font-extrabold text-emerald-400 mt-1">AES-Encrypted MPIN</div>
        </div>
        <div class="p-4 bg-slate-950 rounded-2xl border border-slate-800">
          <span class="text-[10px] text-slate-400 font-bold uppercase tracking-wider">Sync Mechanism</span>
          <div class="text-base font-extrabold text-indigo-400 mt-1">Cloud Auto-Queue</div>
        </div>
      </div>

      <div class="pt-4 flex flex-wrap gap-3">
        <button onclick="window.location.href='http://localhost:8000'" class="px-5 py-3 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-xs shadow-lg transition">
          Open Local Live Dashboard (localhost:8000)
        </button>
        <button onclick="window.print()" class="px-5 py-3 rounded-xl bg-slate-800 hover:bg-slate-700 text-white font-semibold text-xs border border-slate-700 transition">
          Print Full Statement
        </button>
      </div>
    </div>
  </div>
</body>
</html>
"""

class StandaloneHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(HTML_CONTENT.encode("utf-8"))

def run():
    server = HTTPServer(("127.0.0.1", 8989), StandaloneHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    webbrowser.open("http://127.0.0.1:8989")
    print("ExpenseTrack Standalone Desktop Report Viewer started on port 8989.")
    import time
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    run()
