#!/usr/bin/env python3
# Copyright lowRISC contributors (OpenTitan project).
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0
r"""Command-line tool to validate and convert register hjson

"""
import argparse
import logging as log
import re
import sys
from pathlib import Path
import os
import inspect

from reggen import (
    gen_cheader, gen_dv, gen_json, gen_md, gen_rtl, version,
)
# Optional generators (guard imports to avoid hard deps)
try:
    from reggen import gen_html  # type: ignore
except ImportError:  # pragma: no cover
    gen_html = None
try:
    from reggen import gen_selfdoc  # type: ignore
except ImportError:  # pragma: no cover
    gen_selfdoc = None
from reggen.ip_block import IpBlock

DESC = """regtool, generate register info from Hjson source"""

USAGE = '''
  regtool [options]
  regtool [options] <input>
  regtool (-h | --help)
  regtool (-V | --version)
'''

target_folder   = "/media/poseidon/HDD/projects/rtrial"
exclude_folders = ["/media/poseidon/HDD/projects/rtrial/myproject_env"]

def should_trace(filename):
    """Check if we should trace this file"""
    if not filename.endswith('.py'):
        return False
    
    abs_path = os.path.abspath(filename)
    
    # First check if file is in any excluded folder
    for exclude_folder in exclude_folders:
        exclude_abs = os.path.abspath(exclude_folder)
        if exclude_abs in abs_path:
            return False
    
    # Then check if file is in target folder
    target_abs = os.path.abspath(target_folder)
    return target_abs in abs_path


def trace_calls(frame, event, arg):
    if event == 'call':
        filename = frame.f_code.co_filename
        func_name = frame.f_code.co_name
        
        if should_trace(filename):
            # Get caller info
            caller_frame = frame.f_back
            if caller_frame:
                caller_file = os.path.basename(caller_frame.f_code.co_filename)
                caller_line = caller_frame.f_lineno
                caller_func = caller_frame.f_code.co_name
                print(f"→ {caller_file}:{caller_line} {caller_func}() -> {func_name}()")
            else:
                print(f"→ {func_name}() (entry point)")
    
    return trace_calls

def main():

    verbose = 0

    parser = argparse.ArgumentParser(
        prog="regtool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        usage=USAGE,
        description=DESC)
    parser.add_argument('input',
                        nargs='?',
                        metavar='file',
                        type=argparse.FileType('r'),
                        default=sys.stdin,
                        help='input file in Hjson type')
    parser.add_argument('-d',
                        action='store_true',
                        help='Output register documentation (markdown)')
    parser.add_argument('--doc-html',
                        action='store_true',
                        help='Output register documentation as simple HTML')
    parser.add_argument('--doc-html-old',
                        action='store_true',
                        help='Output html documentation (deprecated)')
    parser.add_argument('--adoc',
                        action='store_true',
                        help='Output register documentation (asciidoc)')
    parser.add_argument('--doc',
                        action='store_true',
                        help='Output source file documentation (markdown)')
    parser.add_argument('-a',
                        '--alias',
                        type=Path,
                        default=None,
                        help='Alias register file in Hjson type')
    parser.add_argument('-S',
                        '--scrub',
                        default=False,
                        action='store_true',
                        help='Scrub alias register definition')
    parser.add_argument('--cdefines',
                        '-D',
                        action='store_true',
                        help='Output C defines header')
    parser.add_argument('-j',
                        action='store_true',
                        help='Output as formatted JSON')
    parser.add_argument('-c', action='store_true', help='Output as JSON')
    parser.add_argument('-r',
                        action='store_true',
                        help='Output as SystemVerilog RTL')
    parser.add_argument('-s',
                        action='store_true',
                        help='Output as UVM Register class')
    parser.add_argument('--outdir',
                        '-t',
                        help='Target directory for generated RTL; '
                        'tool uses ../rtl if blank.')
    parser.add_argument(
        '--dv-base-names',
        nargs="+",
        help='Names or prefix for the DV register classes from which '
        'the register models are derived.')
    parser.add_argument('--outfile',
                        '-o',
                        type=argparse.FileType('w'),
                        default=sys.stdout,
                        help='Target filename for json, html, gfm.')
    parser.add_argument('--verbose',
                        '-v',
                        action='store_true',
                        help='Verbose and run validate twice')
    parser.add_argument('--quiet',
                        '-q',
                        action='store_true',
                        help='Log only errors, not warnings')
    parser.add_argument('--param',
                        '-p',
                        type=str,
                        default="",
                        help='''Change the Parameter values.
                                Only integer value is supported.
                                You can add multiple param arguments.

                                  Format: ParamA=ValA;ParamB=ValB
                                  ''')
    parser.add_argument('--version',
                        '-V',
                        action='store_true',
                        help='Show version')
    parser.add_argument('--novalidate',
                        action='store_true',
                        help='Skip validate, just output json')
    parser.add_argument('--node',
                        '-n',
                        type=str,
                        default="",
                        help='''Regblock node to generate.
                                By default, generate for all nodes.
                                ''')
    parser.add_argument(
        '--version-stamp',
        type=str,
        default=None,
        help=
        'If version stamping, the location of workspace version stamp file.')

    args = parser.parse_args()

    if args.version:
        version.show_and_exit(__file__, ["Hjson", "Mako"])

    log_format = "%(filename)s:%(lineno)d: %(levelname)s: %(message)s"
    verbose = args.verbose
    if verbose:
        log.basicConfig(format=log_format, level=log.DEBUG)
    elif args.quiet:
        log.basicConfig(format=log_format, level=log.ERROR)
    else:
        log.basicConfig(format=log_format)

    # Entries are triples of the form (arg, (fmt, dirspec)).
    #
    # arg is the name of the argument that selects the format. fmt is the
    # name of the format. dirspec is None if the output is a single file; if
    # the output needs a directory, it is a default path relative to the source
    # file (used when --outdir is not given).
    arg_to_format = [('j', ('json', None)), ('c', ('compact', None)),
                     ('r', ('rtl', 'rtl')), ('s', ('dv', 'dv')),
                     ('cdefines', ('cdh', None)),
                     ('d', ('registers', None)),
                     ('doc', ('doc', None)),
                     ('doc_html', ('doc_html', None)),
                     ('doc_html_old', ('doc_html', None)),
                     ('adoc', ('adoc', None))]
    fmt = None
    dirspec = None
    for arg_name, spec in arg_to_format:
        if getattr(args, arg_name):
            if fmt is not None:
                log.error('Multiple output formats specified on '
                          'command line ({} and {}).'.format(fmt, spec[0]))
                sys.exit(1)
            fmt, dirspec = spec
    if fmt is None:
        fmt = 'hjson'

    infile = args.input

    # Split parameters into key=value pairs.
    raw_params = args.param.split(';') if args.param else []
    params = []
    for idx, raw_param in enumerate(raw_params):
        tokens = raw_param.split('=')
        if len(tokens) != 2:
            raise ValueError('Entry {} in list of parameter defaults to '
                             'apply is {!r}, which is not of the form '
                             'param=value.'.format(idx, raw_param))
        params.append((tokens[0], tokens[1]))

    # Define either outfile or outdir (but not both), depending on the output
    # format.
    outfile = None
    outdir = None
    if dirspec is None:
        if args.outdir is not None:
            log.error('The {} format expects an output file, '
                      'not an output directory.'.format(fmt))
            sys.exit(1)

        outfile = args.outfile
    else:
        if args.outfile is not sys.stdout:
            log.error('The {} format expects an output directory, '
                      'not an output file.'.format(fmt))
            sys.exit(1)

        if args.outdir is not None:
            outdir = args.outdir
        elif infile is not sys.stdin:
            outdir = str(Path(infile.name).parents[1].joinpath(dirspec))
        else:
            # We're using sys.stdin, so can't infer an output directory name
            log.error(
                'The {} format writes to an output directory, which '
                'cannot be inferred automatically if the input comes '
                'from stdin. Use --outdir to specify it manually.'.format(
                    fmt))
            sys.exit(1)

    srcfull = infile.read()

    try:
        obj = IpBlock.from_text(srcfull, params, infile.name, args.node)
    except ValueError as err:
        log.error(str(err))
        exit(1)

    # Parse and validate alias register definitions (this ensures that the
    # structure of the original register node and the alias register file is
    # identical).
    if args.alias is not None:
        try:
            obj.alias_from_path(args.scrub, args.alias)
        except ValueError as err:
            log.error(str(err))
            exit(1)
    else:
        if args.scrub:
            raise ValueError('The --scrub argument is only meaningful in '
                             'combination with the --alias argument')

    if args.novalidate:
        with outfile:
            gen_json.gen_json(obj, outfile, fmt)
            outfile.write('\n')
    else:
        if fmt == 'rtl':
            return gen_rtl.gen_rtl(obj, outdir)
        if fmt == 'dv':
            return gen_dv.gen_dv(obj, args.dv_base_names, outdir)
        if fmt == 'doc':
            if gen_selfdoc is None:
                raise RuntimeError("gen_selfdoc not available (missing dependency)")
            with outfile:
                gen_selfdoc.document(outfile)
            return 0
        if fmt in ('registers', 'doc_html', 'doc_html_old', 'adoc'):
            # Custom doc rendering (roughly OT style).
            def _render_table(rows, headers):
                lines = []
                lines.append("|===\n| " + " | ".join(headers))
                for r in rows:
                    lines.append("| " + " | ".join(r))
                lines.append("|===")
                return "\n".join(lines)

            def render_block_adoc(block: IpBlock) -> str:
                lines = []
                lines.append(f"= {block.name} Register Map\n")
                # Summary
                rows = []
                for reg in block.reg_blocks[None].flat_regs:
                    rows.append([
                        f"<<{reg.name.lower()}, {reg.name}>>",
                        f"0x{reg.offset:04x}",
                        f"{block.regwidth // 8}",
                        reg.desc.splitlines()[0] if reg.desc else ""
                    ])
                lines.append("[cols=\"3,2,2,5\",options=\"header\"]")
                lines.append(_render_table(rows, ["Name", "Offset", "Length (bytes)", "Description"]))
                lines.append("")
                # Registers
                for reg in block.reg_blocks[None].flat_regs:
                    lines.append(f"[[{reg.name.lower()}]]")
                    lines.append(f"== {reg.name}")
                    if reg.desc:
                        lines.append(reg.desc)
                    lines.append(f"* Offset: `0x{reg.offset:04x}`")
                    lines.append(f"* Reset default: `0x{reg.resval:x}`")
                    lines.append("")
                    # Fields
                    field_rows = []
                    for f in reg.fields:
                        bits = f"{f.bits.msb}:{f.bits.lsb}" if f.bits.width() > 1 else str(f.bits.lsb)
                        desc = f.desc or ""
                        field_rows.append([bits, f.name, desc])
                    lines.append("[cols=\"2,3,7\",options=\"header\"]")
                    lines.append(_render_table(field_rows, ["Bits", "Name", "Description"]))
                    lines.append("")
                return "\n".join(lines)

            def adoc_to_html(adoc: str) -> str:
                import re
                link_re = re.compile(r"<<([A-Za-z0-9_]+),\\s*([^>]+)>>")

                def fmt_cell(text: str) -> str:
                    if text.startswith("<<") and text.endswith(">>") and "," in text:
                        inner = text[2:-2]
                        tgt, label = inner.split(",", 1)
                        return f'<a href="#{tgt.strip()}">{label.strip()}</a>'
                    return link_re.sub(lambda m: f'<a href="#{m.group(1)}">{m.group(2)}</a>', text)

                html_lines = ["<html><body>"]
                in_table = False
                header_expected = False
                for line in adoc.splitlines():
                    if line.startswith("[cols"):
                        continue
                    if line.startswith("|==="):
                        if not in_table:
                            html_lines.append("<table border=\"1\" cellspacing=\"0\" cellpadding=\"4\">")
                            in_table = True
                            header_expected = True
                        else:
                            html_lines.append("</table>")
                            in_table = False
                        continue
                    if in_table and line.startswith("| "):
                        cols = [fmt_cell(c.strip()) for c in line.split("|")[1:] if c.strip()]
                        tag = "th" if header_expected else "td"
                        header_expected = False
                        html_lines.append("<tr>" + "".join(f"<{tag}>{c}</{tag}>" for c in cols) + "</tr>")
                        continue
                    if line.startswith("= "):
                        html_lines.append(f"<h1>{line[2:].strip()}</h1>")
                    elif line.startswith("== "):
                        html_lines.append(f"<h2 id=\"{line[3:].strip().lower()}\">{line[3:].strip()}</h2>")
                    elif line.startswith("[[") and line.endswith("]]"):
                        # Anchor already handled via ID on heading
                        continue
                    elif line.strip():
                        html_lines.append(f"<p>{fmt_cell(line.strip())}</p>")
                html_lines.append("</body></html>")
                return "\n".join(html_lines)

            adoc_text = render_block_adoc(obj)
            if fmt == 'registers':
                outfile.write(adoc_text)
                return 0
            if fmt == 'adoc':
                outfile.write(adoc_text)
                return 0
            html = adoc_to_html(adoc_text)
            outfile.write(html)
            return 0
        src_lic = None
        src_copy = ''
        found_spdx = None
        found_lunder = None
        copy = re.compile(r'.*(copyright.*)|(.*\(c\).*)', re.IGNORECASE)
        spdx = re.compile(r'.*(SPDX-License-Identifier:.+)')
        lunder = re.compile(r'.*(Licensed under.+)', re.IGNORECASE)
        for line in srcfull.splitlines():
            mat = copy.match(line)
            if mat is not None:
                src_copy += mat.group(1)
            mat = spdx.match(line)
            if mat is not None:
                found_spdx = mat.group(1)
            mat = lunder.match(line)
            if mat is not None:
                found_lunder = mat.group(1)
        if found_lunder:
            src_lic = found_lunder
        if found_spdx:
            src_lic += '\n' + found_spdx

        with outfile:
            if fmt == 'cdh':
                return gen_cheader.gen_cdefines(obj, outfile, src_lic,
                                                src_copy)
            else:
                return gen_json.gen_json(obj, outfile, fmt)

            outfile.write('\n')


if __name__ == '__main__':
    sys.settrace(trace_calls)
    sys.exit(main())
