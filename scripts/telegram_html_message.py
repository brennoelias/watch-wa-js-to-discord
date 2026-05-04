#!/usr/bin/env python3
"""Gera texto HTML para sendMessage do Telegram (parse_mode HTML)."""
from __future__ import annotations

import html
import json
import os
import re
import sys
from datetime import datetime, timezone

TG_MAX = 4096


def esc(s: str) -> str:
    return html.escape(s or "", quote=False)


def esc_attr(s: str) -> str:
    return html.escape(s or "", quote=True)


def replace_discord_timestamps(text: str) -> str:
    def repl(m: re.Match[str]) -> str:
        ts = int(m.group(1))
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    return re.sub(r"<t:(\d+):R>", repl, text)


def build_release() -> str:
    data = json.load(sys.stdin)
    tag = esc(data["tag"])
    name = esc(data["name"])
    pub = esc(data.get("pub") or "—")
    body = esc(data.get("body") or "")
    url = data.get("url") or ""
    href = esc_attr(url)
    parts = [
        f"🧩 <b>Nova versão</b> · <code>{tag}</code>",
        "",
        name,
        "",
        f'🔗 <a href="{href}">Abrir release no GitHub</a>',
        "",
        f"📅 <b>Publicado</b> · <i>{pub}</i>",
        "",
        "<b>Notas</b>",
        f"<pre>{body}</pre>",
    ]
    return "\n".join(parts)


def build_fixes(raw: str) -> str:
    raw = replace_discord_timestamps(raw)
    chunks = [p.strip() for p in re.split(r"\n{3,}", raw) if p.strip()]

    header = (
        "<b>🛠️ Fix commits na</b> <code>main</code>\n"
        "<i>wppconnect-team/wa-js</i>\n"
    )
    blocks: list[str] = []
    sha_line = re.compile(r"^-\s*`([0-9a-f]+)`\s*[—:]\s*(.*)$", re.IGNORECASE)

    for chunk in chunks:
        lines = chunk.split("\n")
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()

        m = sha_line.match(lines[0].strip()) if lines else None
        if m and len(lines) >= 3:
            sha, msg = m.group(1), m.group(2)
            meta = lines[1].strip() if len(lines) > 1 else ""
            url = lines[2].strip() if len(lines) > 2 else ""
            u = esc_attr(url) if url.startswith("http") else esc_attr("")
            link = f'<a href="{u}">Ver commit</a>' if url.startswith("http") else esc(url)
            blocks.append(
                "<blockquote>"
                f"<b><code>{esc(sha)}</code></b><br>"
                f"{esc(msg)}<br><br>"
                f"<i>{esc(meta)}</i><br>"
                f"{link}"
                "</blockquote>"
            )
        else:
            blocks.append(f"<pre>{esc(chunk)}</pre>")

    extra = os.environ.get("TG_EXTRA", "").strip()
    tail = ""
    if extra:
        tail = "\n\n" + f"<i>{esc(extra)}</i>"

    return header + "\n" + "\n".join(blocks) + tail


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "release":
        msg = build_release()
    elif mode == "fixes":
        msg = build_fixes(sys.stdin.read())
    else:
        print("Uso: telegram_html_message.py release|fixes", file=sys.stderr)
        sys.exit(1)

    if len(msg) > TG_MAX:
        msg = msg[: TG_MAX - 1] + "…"
    sys.stdout.write(msg)


if __name__ == "__main__":
    main()
