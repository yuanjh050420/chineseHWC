#!/usr/bin/env python3
"""Safely set the ANTHROPIC_API_KEY in .env — no text editor needed.

Prompts for your key with hidden input (it is NOT echoed to the screen and NOT
saved to shell history), strips stray spaces/quotes, validates the shape, and
writes it into .env (creating .env from .env.example if needed) while preserving
every other line. Use this instead of editing .env by hand in TextEdit.

    python3 set_key.py
"""
import getpass, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV = ROOT / ".env"
EXAMPLE = ROOT / ".env.example"

def main():
    key = getpass.getpass("Paste your Anthropic API key (input hidden), then press Enter:\n> ").strip()
    # strip accidental wrapping quotes / whitespace
    key = key.strip().strip('"').strip("'").strip()

    if not key:
        sys.exit("No key entered. Nothing changed.")
    if not key.startswith("sk-ant-"):
        sys.exit(f"That doesn't look like an Anthropic key (should start with 'sk-ant-'; got '{key[:8]}...'). Nothing changed.")
    if len(key) < 50:
        sys.exit(f"That key is only {len(key)} characters — far too short (a real key is ~100+). "
                 "You likely copied a truncated/placeholder value. Nothing changed.")

    # start from existing .env, else the example template, else a minimal file
    if ENV.exists():
        lines = ENV.read_text().splitlines()
    elif EXAMPLE.exists():
        lines = EXAMPLE.read_text().splitlines()
    else:
        lines = ["ANTHROPIC_API_KEY="]

    out, replaced = [], False
    for ln in lines:
        if re.match(r"\s*ANTHROPIC_API_KEY\s*=", ln):
            out.append(f"ANTHROPIC_API_KEY={key}")
            replaced = True
        else:
            out.append(ln)
    if not replaced:
        out.insert(0, f"ANTHROPIC_API_KEY={key}")

    ENV.write_text("\n".join(out) + "\n")
    print(f"\nWrote key to {ENV}")
    print(f"  key length: {len(key)} chars | starts: {key[:14]} | ends: {key[-6:]}")
    print("Now run:  python run_weekly.py --with-search")

if __name__ == "__main__":
    main()
