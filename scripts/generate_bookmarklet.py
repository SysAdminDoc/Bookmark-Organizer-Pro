#!/usr/bin/env python3
"""Generate a bookmarklet URL that saves the current page to BOP.

Usage:
    python scripts/generate_bookmarklet.py [--port 8765]

Reads the API token from ~/.bookmark_organizer/api_token.txt and prints
a `javascript:` URL you can drag to your browser's bookmark bar.
"""

import argparse
import sys
import urllib.parse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Generate BOP bookmarklet")
    parser.add_argument("--port", type=int, default=8765, help="API port (default: 8765)")
    args = parser.parse_args()

    token_file = Path.home() / ".bookmark_organizer" / "api_token.txt"
    if not token_file.exists():
        print("Error: API token not found. Start the app once to generate it.", file=sys.stderr)
        print(f"Expected: {token_file}", file=sys.stderr)
        sys.exit(1)

    token = token_file.read_text(encoding="utf-8").strip()

    js = f"""(function(){{
var u=location.href,t=document.title,s=window.getSelection().toString().substring(0,500);
var x=new XMLHttpRequest();
x.open('POST','http://127.0.0.1:{args.port}/bookmarks',true);
x.setRequestHeader('Content-Type','application/json');
x.setRequestHeader('Authorization','Bearer {token}');
x.onload=function(){{
  if(x.status<300){{
    var b=document.createElement('div');
    b.textContent='Saved to BOP';
    b.style.cssText='position:fixed;top:12px;right:12px;z-index:999999;padding:10px 20px;background:#1a1a2e;color:#58a6ff;border-radius:8px;font:14px system-ui;box-shadow:0 4px 12px rgba(0,0,0,.3)';
    document.body.appendChild(b);
    setTimeout(function(){{b.remove()}},2000);
  }}else{{
    alert('BOP save failed: '+x.status);
  }}
}};
x.onerror=function(){{alert('Cannot reach BOP at 127.0.0.1:{args.port}. Is it running?')}};
x.send(JSON.stringify({{url:u,title:t,notes:s?'Selected: '+s:''}}));
}})();"""

    minified = " ".join(js.split())
    bookmarklet = "javascript:" + urllib.parse.quote(minified, safe="(){}:;,.'\"=+!?/&*")

    print("Drag this URL to your bookmark bar:\n")
    print(bookmarklet)
    print(f"\nPort: {args.port}")
    print(f"Token: {token[:8]}...")


if __name__ == "__main__":
    main()
