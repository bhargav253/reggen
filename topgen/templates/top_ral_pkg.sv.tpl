// Auto-generated top-level RAL aggregator
package ${pkg_name};

  import uvm_pkg::*;
% for name, addr, target in mods:
  import ${target}_ral_pkg::*;
% endfor

  class top_ral extends uvm_reg_block;
% for name, addr, target in mods:
    rand ${target}_ral_block ${name};
% endfor
    uvm_reg_map default_map;

    function new(string name="top_ral");
      super.new(name, .has_coverage(UVM_NO_COVERAGE));
    endfunction

    virtual function void build();
      default_map = create_map("default_map", 0, 4, UVM_LITTLE_ENDIAN);
% for name, addr, target in mods:
      ${name} = ${target}_ral_block::type_id::create("${name}", , get_full_name());
      ${name}.build();
      ${name}.lock_model();
      default_map.add_submap(${name}.default_map, 32'h${"%08x" % addr});
% endfor
    endfunction
  endclass

endpackage : ${pkg_name}
