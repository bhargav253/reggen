/* Auto-generated linker script stub */
MEMORY
{
% for name, addr, size in mems:
  ${name.upper()} (rxw) : ORIGIN = 0x${"%08x" % addr}, LENGTH = 0x${"%08x" % size}
% endfor
}

SECTIONS
{
  /* TODO: Place sections into the appropriate MEMORY regions */
}
