"""Cover synthesis.

Four genuinely different directions, generated as SVG from the title and genre:
typographic, illustrated, photographic-ish, and a deliberately conventional one
as a control. Bookit does not pick the winner — real readers do.
"""

from __future__ import annotations

import base64
from html import escape

SER = 'font-family="Georgia,serif"'
SAN = 'font-family="Helvetica,Arial,sans-serif"'
DIRECTIONS = ("A", "B", "C", "D")


def _split_title(title: str) -> tuple[str, str]:
    t = title[:24] + "…" if len(title) > 26 else title
    words = t.split()
    half = -(-len(words) // 2)  # ceil
    return escape(" ".join(words[:half])), escape(" ".join(words[half:]))


def _box(inner: str, bg: str) -> str:
    return (
        '<svg viewBox="0 0 300 450" xmlns="http://www.w3.org/2000/svg">'
        f'<rect width="300" height="450" fill="{bg}"/>{inner}</svg>'
    )


def cover_svg(kind: str, title: str, author: str) -> str:
    """Render one cover direction as a standalone SVG string."""
    l1, l2 = _split_title(title)
    au = escape(author)
    au_caps = escape(author.upper())

    if kind == "A":  # typographic
        return _box(f"""
    <line x1="34" y1="86" x2="266" y2="86" stroke="#1b1b1b" stroke-width="1"/>
    <line x1="34" y1="364" x2="266" y2="364" stroke="#1b1b1b" stroke-width="1"/>
    <text x="150" y="70" {SAN} font-size="9.5" letter-spacing="4" fill="#7a6f60" text-anchor="middle">A NOVEL</text>
    <text x="150" y="200" {SER} font-size="35" fill="#171717" text-anchor="middle">{l1}</text>
    <text x="150" y="240" {SER} font-size="35" fill="#171717" text-anchor="middle">{l2}</text>
    <text x="150" y="352" {SAN} font-size="11" letter-spacing="3" fill="#4a4238" text-anchor="middle">{au_caps}</text>""",
                    "#f3ece1")

    if kind == "B":  # the conventional control
        return _box(f"""
    <defs><linearGradient id="gb" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#3d6fb5"/><stop offset="1" stop-color="#8fb6dd"/></linearGradient></defs>
    <rect width="300" height="450" fill="url(#gb)"/>
    <circle cx="150" cy="168" r="52" fill="#fff" opacity=".26"/>
    <text x="150" y="262" {SAN} font-size="27" font-weight="bold" fill="#fff" text-anchor="middle">{l1}</text>
    <text x="150" y="292" {SAN} font-size="27" font-weight="bold" fill="#fff" text-anchor="middle">{l2}</text>
    <rect x="106" y="312" width="88" height="2" fill="#fff" opacity=".7"/>
    <text x="150" y="338" {SAN} font-size="12" fill="#eef4fa" text-anchor="middle">{au}</text>""",
                    "#3d6fb5")

    if kind == "C":  # illustrated
        return _box(f"""
    <rect width="300" height="450" fill="#f6efe3"/>
    <circle cx="150" cy="132" r="46" fill="#e0a84a"/>
    <path d="M0 330 L74 214 L134 300 L196 190 L300 330 Z" fill="#2d4a42"/>
    <path d="M0 360 L96 258 L182 360 Z" fill="#1e3530" opacity=".9"/>
    <rect y="330" width="300" height="120" fill="#1e3530"/>
    <text x="150" y="378" {SER} font-size="27" fill="#f6efe3" text-anchor="middle">{l1}</text>
    <text x="150" y="406" {SER} font-size="27" fill="#f6efe3" text-anchor="middle">{l2}</text>
    <text x="150" y="430" {SAN} font-size="9.5" letter-spacing="3" fill="#c9b48d" text-anchor="middle">{au_caps}</text>""",
                    "#f6efe3")

    return _box(f"""
    <defs><linearGradient id="gd" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#14100c"/><stop offset=".55" stop-color="#2b1d12"/>
      <stop offset="1" stop-color="#0c0a08"/></linearGradient></defs>
    <rect width="300" height="450" fill="url(#gd)"/>
    <g opacity=".5"><circle cx="60" cy="60" r="1.4" fill="#e9cf9a"/><circle cx="240" cy="96" r="1.1" fill="#e9cf9a"/>
      <circle cx="196" cy="44" r="1" fill="#e9cf9a"/><circle cx="96" cy="120" r="1.2" fill="#e9cf9a"/>
      <circle cx="268" cy="176" r="1" fill="#e9cf9a"/><circle cx="34" cy="200" r="1.1" fill="#e9cf9a"/></g>
    <circle cx="150" cy="176" r="58" fill="none" stroke="#d9b26a" stroke-width="1.2"/>
    <circle cx="150" cy="176" r="46" fill="none" stroke="#d9b26a" stroke-width=".6" opacity=".65"/>
    <path d="M150 138 L162 170 L196 176 L162 182 L150 214 L138 182 L104 176 L138 170 Z" fill="#e3c485"/>
    <text x="150" y="306" {SER} font-size="32" fill="#f0e2c4" text-anchor="middle" letter-spacing="1">{l1}</text>
    <text x="150" y="342" {SER} font-size="32" fill="#f0e2c4" text-anchor="middle" letter-spacing="1">{l2}</text>
    <line x1="112" y1="366" x2="188" y2="366" stroke="#d9b26a" stroke-width=".8"/>
    <text x="150" y="392" {SAN} font-size="10.5" letter-spacing="3.5" fill="#c9a976" text-anchor="middle">{au_caps}</text>""",
                "#14100c")


def cover_data_uri(kind: str, title: str, author: str) -> str:
    """The same cover, encoded for an <img> tag."""
    svg = cover_svg(kind, title, author)
    b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"
