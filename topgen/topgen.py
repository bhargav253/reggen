#!/usr/bin/env python3
# Lightweight top-level generator focused on address collateral only.
# Reads a top-level HJSON with `module` and `memory` lists and emits:
#   - C header with base addresses for modules and memories
#   - SystemVerilog package with base address parameters
#   - Minimal linker script stub with MEMORY regions
#
# Expected HJSON snippets:
# {
#   module: [
#     { name: "uart0", base_addr: "0x40000000" }
#     // or base_addr: { hart: "0x40000000" }
#   ],
#   memory: [
#     { name: "rom", base_addr: "0x0", size: "0x1000", type: "rom" }
#   ]
# }

import argparse
import os
from pathlib import Path
from typing import Dict, List, Tuple

import hjson  # type: ignore
from mako.template import Template


def _as_int(val: object, what: str) -> int:
    if isinstance(val, int):
        return val
    if isinstance(val, str):
        try:
            return int(val, 0)
        except ValueError as err:
            raise ValueError(f"{what} is not a valid int: {val}") from err
    raise ValueError(f"{what} must be int or str, got {type(val)}")


def _get_base_addr(entry: Dict, what: str) -> int:
    if "base_addr" not in entry:
        raise ValueError(f"{what} is missing base_addr")
    ba = entry["base_addr"]
    if isinstance(ba, dict):
        # pick the first value if multiple domains are listed
        if not ba:
            raise ValueError(f"{what} has empty base_addr map")
        ba_val = next(iter(ba.values()))
        return _as_int(ba_val, f"{what} base_addr value")
    return _as_int(ba, f"{what} base_addr")


def parse_top(top_path: Path) -> Tuple[List[Tuple[str, int, str]], List[Tuple[str, int, int]]]:
    with open(top_path, "r", encoding="utf-8") as f:
        data = hjson.load(f)

    mods = []
    for m in data.get("module", []):
        name = m.get("name")
        if not name:
            raise ValueError("Module entry missing name")
        target = name.rstrip("0123456789") or name
        ip_hjson = m.get("ip_hjson")
        if ip_hjson:
            target = Path(ip_hjson).stem
        mods.append((name, _get_base_addr(m, f"module {name}"), target))

    mems = []
    for mem in data.get("memory", []):
        name = mem.get("name")
        if not name:
            raise ValueError("Memory entry missing name")
        base = _get_base_addr(mem, f"memory {name}")
        size = _as_int(mem.get("size"), f"memory {name} size")
        mems.append((name, base, size))

    return mods, mems


def emit_cheader(mods: List[Tuple[str, int, str]], mems: List[Tuple[str, int, int]], out: Path) -> None:
    tpl_path = Path(__file__).with_name("templates").joinpath("top_base_addrs.h.tpl")
    guard = out.stem.upper() + "_"
    tpl = Template(tpl_path.read_text())
    out.write_text(tpl.render(guard=guard, mods=mods, mems=mems), encoding="utf-8")


def emit_sv_pkg(mods: List[Tuple[str, int, str]], mems: List[Tuple[str, int, int]], out: Path) -> None:
    tpl_path = Path(__file__).with_name("templates").joinpath("top_base_addrs_pkg.sv.tpl")
    tpl = Template(tpl_path.read_text())
    out.write_text(tpl.render(pkg_name=out.stem, mods=mods, mems=mems), encoding="utf-8")


def emit_linker(mems: List[Tuple[str, int, int]], out: Path) -> None:
    tpl_path = Path(__file__).with_name("templates").joinpath("toplevel_memory.ld.tpl")
    tpl = Template(tpl_path.read_text())
    out.write_text(tpl.render(mems=mems), encoding="utf-8")


def emit_docs(mods: List[Tuple[str, int, str]], mems: List[Tuple[str, int, int]], out_md: Path) -> None:
    tpl_path = Path(__file__).with_name("templates").joinpath("top_addresses.md.tpl")
    tpl = Template(tpl_path.read_text())
    out_md.write_text(tpl.render(mods=mods, mems=mems), encoding="utf-8")


def emit_ral_pkg(mods: List[Tuple[str, int, str]], out: Path) -> None:
    tpl_path = Path(__file__).with_name("templates").joinpath("top_ral_pkg.sv.tpl")
    tpl = Template(tpl_path.read_text())
    out.write_text(tpl.render(mods=mods, pkg_name=out.stem), encoding="utf-8")


def wrap_html(md_content: str) -> str:
    import re
    lines = ["<html><body>"]
    in_table = False
    header_expected = False
    link_re = re.compile(r"<<([A-Za-z0-9_]+),\\s*([^>]+)>>")

    def fmt_cell(text: str) -> str:
        if text.startswith("<<") and text.endswith(">>") and "," in text:
            inner = text[2:-2]
            tgt, label = inner.split(",", 1)
            return f'<a href="{tgt.strip()}.html">{label.strip()}</a>'
        return link_re.sub(lambda m: f'<a href=\"{m.group(1)}.html\">{m.group(2)}</a>', text)

    for line in md_content.splitlines():
        if line.startswith("[cols"):
            continue
        if line.startswith("|==="):
            if not in_table:
                lines.append("<table border=\"1\" cellspacing=\"0\" cellpadding=\"4\">")
                in_table = True
                header_expected = True
            else:
                lines.append("</table>")
                in_table = False
            continue
        if in_table and line.startswith("| "):
            cols = [fmt_cell(c.strip()) for c in line.split("|")[1:] if c.strip()]
            tag = "th" if header_expected else "td"
            header_expected = False
            lines.append("<tr>" + "".join(f"<{tag}>{c}</{tag}>" for c in cols) + "</tr>")
            continue
        if line.startswith("= "):
            lines.append(f"<h1>{line[2:].strip()}</h1>")
        elif line.startswith("== "):
            lines.append(f"<h2>{line[3:].strip()}</h2>")
        elif line.strip():
            lines.append(f"<p>{fmt_cell(line.strip())}</p>")
    lines.append("</body></html>")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Lightweight top-level address generator")
    ap.add_argument("topcfg", type=Path, help="Top-level HJSON describing modules/memory")
    ap.add_argument("--outdir", type=Path, default=Path("build/toplite"),
                    help="Output directory (default: build/toplite)")
    args = ap.parse_args()

    mods, mems = parse_top(args.topcfg)
    args.outdir.mkdir(parents=True, exist_ok=True)

    emit_cheader(mods, mems, args.outdir / "top_base_addrs.h")
    emit_sv_pkg(mods, mems, args.outdir / "top_base_addrs_pkg.sv")
    emit_linker(mems, args.outdir / "toplevel_memory.ld")
    emit_ral_pkg(mods, args.outdir / "top_ral_pkg.sv")
    # Docs
    md_path = args.outdir / "top_addresses.md"
    emit_docs(mods, mems, md_path)
    (args.outdir / "top_addresses.html").write_text(
        wrap_html(md_path.read_text(encoding="utf-8")),
        encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
