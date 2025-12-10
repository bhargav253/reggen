# reggen

## Usage

```bash
python3 regtool.py --help
```

### Supported IP HJSON attributes (trimmed)
- Top-level IP: `name`, `clocking`, `bus_interfaces`, `registers`; optional `regwidth`, `param_list`, `scan`, `scan_reset`, `scan_en`
- Register: required `name`, `desc`, `fields`; optional `swaccess`, `hwaccess`, `hwext`, `hwqe`, `hwre`, `regwen`, `resval`, `tags`, `shadowed`, `writes_ignore_errors`
- Field: required `bits`; optional `name`, `desc`, `swaccess`, `hwaccess`, `hwqe`, `resval`, `enum`, `tags`, `mubi`, `auto_split`
- Windows/multiregs supported. Interrupts/alerts/countermeasures/features/RACL are removed in this lightweight fork.

### Common commands
- JSON (pretty): `python3 regtool.py -j examples/uart.hjson`
- RTL: `python3 regtool.py -r examples/uart.hjson --outdir build/rtl`
- UVM register model: `python3 regtool.py -s examples/uart.hjson --outdir build/uvm`
- C header: `python3 regtool.py -D examples/uart.hjson > build/uart_regs.h`
- Docs (AsciiDoc): `python3 regtool.py -d examples/uart.hjson > build/uart_regs.adoc`
- Docs (HTML): `python3 regtool.py --doc-html examples/uart.hjson > build/uart_regs.html`

### Top-level address collateral
Use the lightweight top-level generator:
```bash
python3 topgen/topgen.py examples/top_example.hjson --outdir build/top
```
Outputs:
- `top_base_addrs.h` (C defines for modules/memories)
- `top_base_addrs_pkg.sv` (SystemVerilog package)
- `toplevel_memory.ld` (linker stub)
- `top_addresses.md` / `top_addresses.html` (address map docs)
