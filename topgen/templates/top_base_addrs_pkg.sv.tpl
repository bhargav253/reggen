// Auto-generated base addresses
package ${pkg_name};
  // Module base addresses
% for name, addr, target in mods:
  localparam int unsigned ${name}_base_addr = 32'h${"%08x" % addr};
% endfor
  // Memory regions
% for name, addr, size in mems:
  localparam int unsigned ${name}_base_addr = 32'h${"%08x" % addr};
  localparam int unsigned ${name}_size      = 32'h${"%08x" % size};
% endfor
endpackage : ${pkg_name}
