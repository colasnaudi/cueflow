#!/usr/bin/env python3
"""Delegate simple tasks to the local Ollama model.

Examples:
    scripts/local-llm.py "Write a docstring for this function" -f app/foo.py
    scripts/local-llm.py "Generate 20 realistic tech house track names as JSON" -o data/seed.json --json
    git diff | scripts/local-llm.py "Write a one-line commit message for this diff"
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("LOCAL_LLM_MODEL", "gemma4:12b-it-qat")

SYSTEM = (
    "You are a precise senior software engineer assistant. "
    "Answer with the requested content only: no preamble, no closing remarks. "
    "When asked for code or a file, output only the raw content without markdown fences."
)


def strip_fences(text: str) -> str:
    match = re.fullmatch(r"\s*```[\w+-]*\n(.*?)\n```\s*", text, re.DOTALL)
    return match.group(1) + "\n" if match else text.strip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("prompt", help="Instruction for the model")
    parser.add_argument("-f", "--file", action="append", default=[], help="File to include as context (repeatable)")
    parser.add_argument("-o", "--output", help="Write the answer to this file instead of stdout")
    parser.add_argument("-m", "--model", default=DEFAULT_MODEL)
    parser.add_argument("--json", action="store_true", help="Force a JSON answer")
    parser.add_argument("--think", action="store_true", help="Enable reasoning mode (slower)")
    args = parser.parse_args()

    parts = [args.prompt]
    if not sys.stdin.isatty():
        piped = sys.stdin.read()
        if piped.strip():
            parts.append("INPUT:\n" + piped)
    for path in args.file:
        with open(path, encoding="utf-8") as fh:
            parts.append(f"FILE {path}:\n{fh.read()}")

    payload = {
        "model": args.model,
        "stream": False,
        "think": args.think,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": "\n\n".join(parts)},
        ],
        "options": {"temperature": 0.2, "num_ctx": 16384},
    }
    if args.json:
        payload["format"] = "json"

    request = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            answer = json.load(response)["message"]["content"]
    except urllib.error.URLError as exc:
        print(f"Ollama unreachable at {OLLAMA_URL}: {exc}", file=sys.stderr)
        return 1

    answer = strip_fences(answer)
    if args.output:
        os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(answer)
        print(f"wrote {args.output} ({len(answer.splitlines())} lines)")
    else:
        sys.stdout.write(answer)
    return 0


if __name__ == "__main__":
    sys.exit(main())
