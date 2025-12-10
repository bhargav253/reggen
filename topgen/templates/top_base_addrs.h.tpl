#ifndef ${guard}
#define ${guard}

/* Auto-generated base addresses */
% for name, addr, target in mods:
#define TOP_${name.upper()}_BASE_ADDR 0x${"%08x" % addr}
% endfor
% for name, addr, size in mems:
#define TOP_${name.upper()}_BASE_ADDR 0x${"%08x" % addr}
#define TOP_${name.upper()}_SIZE      0x${"%08x" % size}
% endfor

#endif /* ${guard} */
