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

# Marcadores que sobrevivem a html.escape() e são trocados pelos trechos HTML finais.
_PH = "\ufffe{}\uffff"


def esc(s: str) -> str:
    return html.escape(s or "", quote=False)


def esc_attr(s: str) -> str:
    return html.escape(s or "", quote=True)


def replace_discord_timestamps(text: str) -> str:
    def repl(m: re.Match[str]) -> str:
        ts = int(m.group(1))
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    return re.sub(r"<t:(\d+):R>", repl, text)


def inline_format_line(s: str) -> str:
    """Markdown leve numa linha: `code`, **negrito**, [texto](url)."""
    slots: list[str] = []

    def put(html: str) -> str:
        slots.append(html)
        return _PH.format(len(slots) - 1)

    s = re.sub(r"`([^`]+)`", lambda m: put("<code>" + esc(m.group(1)) + "</code>"), s)
    s = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        lambda m: put(f'<a href="{esc_attr(m.group(2))}">{esc(m.group(1))}</a>'),
        s,
    )
    s = re.sub(r"\*\*([^*]+)\*\*", lambda m: put("<b>" + esc(m.group(1)) + "</b>"), s)
    s = esc(s)
    for i, h in enumerate(slots):
        s = s.replace(_PH.format(i), h)
    return s


def format_text_chunk(chunk: str) -> str:
    """Parágrafos / listas / títulos → HTML Telegram (sem <pre> no bloco todo)."""
    out: list[str] = []
    for line in chunk.split("\n"):
        raw = line.rstrip("\r")
        if not raw.strip():
            out.append("<br>")
            continue
        if re.match(r"^#{1,6}\s+", raw):
            rest = re.sub(r"^#{1,6}\s+", "", raw)
            out.append("<b>" + inline_format_line(rest) + "</b><br>")
        elif re.match(r"^[\*\-]\s+", raw):
            rest = re.sub(r"^[\*\-]\s+", "", raw)
            out.append("• " + inline_format_line(rest) + "<br>")
        elif re.match(r"^\d+\.\s+", raw):
            rest = re.sub(r"^\d+\.\s+", "", raw)
            out.append("• " + inline_format_line(rest) + "<br>")
        else:
            out.append(inline_format_line(raw) + "<br>")
    s = "".join(out)
    s = re.sub(r"(?:<br>)+$", "", s)
    return s


def changelog_to_telegram_html(body: str) -> str:
    """Notas de release: Markdown típico de changelog → subset HTML do Telegram."""
    body = (body or "").replace("\r\n", "\n").replace("\r", "\n")
    if not body.strip():
        return "<i>(sem notas)</i>"

    fence = re.compile(r"```[\w.-]*\s*\n(.*?)```", re.DOTALL)
    matches = list(fence.finditer(body))
    if not matches:
        return format_text_chunk(body)

    parts: list[str] = []
    pos = 0
    for m in matches:
        if m.start() > pos:
            parts.append(format_text_chunk(body[pos : m.start()]))
        parts.append("<pre>" + esc(m.group(1).rstrip("\n")) + "</pre>")
        pos = m.end()
    if pos < len(body):
        parts.append(format_text_chunk(body[pos:]))
    return "".join(parts)


def build_release() -> str:
    data = json.load(sys.stdin)
    tag_raw = (data.get("tag") or "").strip()
    name_raw = (data.get("name") or "").strip()
    tag = esc(tag_raw)
    name = esc(name_raw)
    pub = esc(data.get("pub") or "—")
    raw_body = data.get("body") or ""
    body_html = changelog_to_telegram_html(raw_body)
    url = data.get("url") or ""
    href = esc_attr(url)
    parts = [
        f"🧩 <b>Nova versão</b> · <code>{tag}</code>",
        "",
    ]
    if name_raw and name_raw != tag_raw:
        parts.extend([name, ""])
    parts.extend(
        [
            f'🔗 <a href="{href}">Abrir release no GitHub</a>',
            "",
            f"📅 <b>Publicado</b> · <i>{pub}</i>",
            "",
            "<b>Notas</b>",
            body_html,
        ]
    )
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
                f"{inline_format_line(msg)}<br><br>"
                f"<i>{esc(meta)}</i><br>"
                f"{link}"
                "</blockquote>"
            )
        else:
            blocks.append(changelog_to_telegram_html(chunk))

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
