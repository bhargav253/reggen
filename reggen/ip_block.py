# Copyright lowRISC contributors (OpenTitan project).
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
'''Code representing an IP block for reggen'''

import logging as log
from typing import Optional
from dataclasses import dataclass, field

import hjson  # type: ignore
from reggen.bus_interfaces import BusInterfaces
from reggen.clocking import Clocking, ClockingItem
from reggen.lib import (check_bool, check_int, check_keys, check_name)
from reggen.params import ReggenParams
from reggen.reg_block import RegBlock

try:
    from semantic_version import Version  # type: ignore
except ModuleNotFoundError:
    class Version(str):
        """Fallback version representation when semantic_version is absent."""

        def __new__(cls, value: str = '0.0.0') -> 'Version':
            return str.__new__(cls, value)

# Known unique comportable IP names and associated CIP_IDs.
REQUIRED_ALIAS_FIELDS = {
    'alias_impl': ['s', "identifier for this alias implementation"],
    'alias_target': ['s', "name of the component to apply the alias file to"],
    'registers': ['l', "list of alias register definition groups"],
    'bus_interfaces': ['l', "bus interfaces for the device"],
}

OPTIONAL_ALIAS_FIELDS: dict[str, list[str]] = {}

REQUIRED_FIELDS = {
    'name': ['s', "name of the component"],
    'clocking': ['l', "clocking for the device"],
    'bus_interfaces': ['l', "bus interfaces for the device"],
    'registers':
    ['l', "list of register definition groups and "
     "offset control groups"]
}

OPTIONAL_FIELDS = {
    'human_name': ['s', "human-readable name of the component"],
    'one_line_desc': ['s', "one-line description of the component"],
    'one_paragraph_desc': ['s', "one-paragraph description of the component"],
    'design_spec':
    ['s', "path to the design specification, relative to repo root"],
    'dv_doc': ['s', "path to the DV document, relative to repo root"],
    'hw_checklist': ['s', "path to the hw_checklist, relative to repo root"],
    'sw_checklist': ['s', "path to the sw_checklist, relative to repo root"],
    'design_stage': ['s', "design stage of module"],
    'dif_stage': ['s', 'DIF stage of module'],
    'verification_stage': ['s', "verification stage of module"],
    'notes': ['s', "random notes"],
    'version': ['s', "module version"],
    'life_stage': ['s', "life stage of module"],
    'commit_id': ['s', "commit ID of last stage sign-off"],
    'param_list': ['lp', "list of parameters of the IP"],
    'regwidth': ['d', "width of registers in bits (default 32)"],
    'scan': ['pb', 'Indicates the module have `scanmode_i`'],
    'scan_reset': ['pb', 'Indicates the module have `scan_rst_ni`'],
    'scan_en': ['pb', 'Indicates the module has `scan_en_i`'],
    'SPDX-License-Identifier': [
        's', "License identifier (if using pure json) "
        "Only use this if unable to put this "
        "information in a comment at the top of the "
        "file."
    ],
}

# Note that the revisions list may be deprecated in the future.
REQUIRED_REVISIONS_FIELDS = {
    'design_stage': ['s', "design stage of module"],
    'verification_stage': ['s', "verification stage of module"],
    'version': ['s', "semantic module version in the format x.y.z[+res#]"],
    'life_stage': ['s', "life stage of module"],
}

OPTIONAL_REVISIONS_FIELDS = {
    'dif_stage': ['s', 'DIF stage of module'],
    'commit_id': ['s', "commit ID of last stage sign-off"],
    'notes': ['s', "random notes"],
}


@dataclass
class IpBlock:
    name: str
    regwidth: int
    params: ReggenParams
    reg_blocks: dict[str | None, RegBlock]
    bus_interfaces: BusInterfaces
    clocking: Clocking
    version: Version = Version('0.0.0')
    scan: bool = False
    scan_reset: bool = False
    scan_en: bool = False
    node: str = ''
    alias_impl: str | None = None

    def __post_init__(self) -> None:
        assert self.reg_blocks

        # Filter the interfaces and reg_blocks if request to build only for a
        # specific reg_block node.
        dev_if_names: list[str | None] = []
        if self.node:
            dev_if_names += [
                i for i in self.bus_interfaces.named_devices if i == self.node
            ]
            self.reg_blocks = {k: v for k, v in self.reg_blocks.items()
                               if k == self.node}
        else:
            dev_if_names += self.bus_interfaces.named_devices

        # Check that register blocks are in bijection with device interfaces
        reg_block_names = self.reg_blocks.keys()
        if self.bus_interfaces.has_unnamed_device:
            dev_if_names.append(None)
        assert set(reg_block_names) == set(dev_if_names)

    @staticmethod
    def from_raw(param_defaults: list[tuple[str, str]],
                 raw: object,
                 where: str,
                 node: str = '') -> 'IpBlock':

        rd = check_keys(raw, 'block at ' + where, list(REQUIRED_FIELDS.keys()),
                        list(OPTIONAL_FIELDS.keys()))

        name = check_name(rd['name'], 'name of block at ' + where)
        what = '{} block at {}'.format(name, where)

        r_regwidth = rd.get('regwidth')
        if r_regwidth is None:
            regwidth = 32
        else:
            regwidth = check_int(r_regwidth, 'regwidth field of ' + what)
            if regwidth <= 0:
                raise ValueError('Invalid regwidth field for {}: '
                                 '{} is not positive.'.format(what, regwidth))

        params = ReggenParams.from_raw('parameter list for ' + what,
                                       rd.get('param_list', []))
        try:
            params.apply_defaults(param_defaults)
        except (ValueError, KeyError) as err:
            raise ValueError(
                'Failed to apply defaults to params: {}'.format(err)) from None

        init_block = RegBlock(regwidth, params)

        scan = check_bool(rd.get('scan', False), 'scan field of ' + what)

        bus_interfaces = (BusInterfaces.from_raw(
            rd['bus_interfaces'], 'bus_interfaces field of ' + where))

        clocking = Clocking.from_raw(rd['clocking'],
                                     'clocking field of ' + what)

        reg_blocks = RegBlock.build_blocks(init_block, rd['registers'],
                                           bus_interfaces, clocking, False)

        scan_reset = check_bool(rd.get('scan_reset', False),
                                'scan_reset field of ' + what)
        scan_en = check_bool(rd.get('scan_en', False),
                             'scan_en field of ' + what)

        version = Version(rd.get('version', '0.0.0'))
        # Check that register blocks are in bijection with device interfaces
        reg_block_names = reg_blocks.keys()
        dev_if_names: list[str | None] = []
        dev_if_names += bus_interfaces.named_devices
        if bus_interfaces.has_unnamed_device:
            dev_if_names.append(None)
        if set(reg_block_names) != set(dev_if_names):
            raise ValueError("IP block {} defines device interfaces, named {} "
                             "but its registers don't match (they are keyed "
                             "by {}).".format(name, dev_if_names,
                                              list(reg_block_names)))

        return IpBlock(name=name,
                       regwidth=regwidth,
                       params=params,
                       reg_blocks=reg_blocks,
                       bus_interfaces=bus_interfaces,
                       clocking=clocking,
                       version=version,
                       scan=scan,
                       scan_reset=scan_reset,
                       scan_en=scan_en,
                       node=node)

    @staticmethod
    def from_text(txt: str,
                  param_defaults: list[tuple[str, str]],
                  where: str,
                  node: str = '') -> 'IpBlock':
        '''Load an IpBlock from an hjson description in txt'''
        return IpBlock.from_raw(param_defaults,
                                hjson.loads(txt, use_decimal=True), where,
                                node)

    @staticmethod
    def from_path(path: str,
                  param_defaults: list[tuple[str, str]]) -> 'IpBlock':
        '''Load an IpBlock from an hjson description in a file at path'''
        with open(path, 'r', encoding='utf-8') as handle:
            return IpBlock.from_text(handle.read(), param_defaults,
                                     'file at {!r}'.format(path))

    def alias_from_raw(self, scrub: bool, raw: object, where: str) -> None:
        '''Parses and validates an alias reg block and adds it to this IpBlock.

        The alias register definitions are compared with the corresponding
        generic register definitions in self.reg_blocks to ensure that the
        register and field structure is the same. Only a subset of register
        and field attributes may differ and all other attributes must be
        identical. The overridable attributes are defined in register.py and
        field.py, but typically comprise attributes like 'name', 'desc',
        'resval' and 'tags'.

        The alias register information is then applied to the self.reg_blocks
        datastructure. Generic register descriptions with no associated alias
        register definition just remain unmodified, meaning that the user can
        choose to only provide alias overrides for a subset of all registers.
        The resulting "augmented" register block is therefore always guaranteed
        to be structurally identical to the unmodified generic register block.

        Note that the alias register definition also overrides the hier_path
        variable associated with the corresponding bus interfaces.

        Setting the scrub argument to True will scrub sensitive fields in the
        alias definition and replace the entire register block of the target
        interface with the scrubbed alias reg block. This is helpful to create
        the generic CSR structure matching the alias definition automatically.
        '''
        rd = check_keys(raw, 'block at ' + where,
                        list(REQUIRED_ALIAS_FIELDS.keys()),
                        list(OPTIONAL_ALIAS_FIELDS.keys()))

        alias_bus_interfaces = (BusInterfaces.from_raw(
            rd['bus_interfaces'], 'bus_interfaces of block at ' + where))
        if ((alias_bus_interfaces.has_unnamed_host or
             alias_bus_interfaces.named_hosts)):
            raise ValueError("Alias registers cannot be defined for host "
                             "interfaces (in block at {}).".format(where))
        # Alias register definitions are only compatible with named devices.
        if ((alias_bus_interfaces.has_unnamed_device or
             self.bus_interfaces.has_unnamed_device)):
            raise ValueError("Alias registers must use named devices "
                             "(in block at {}).".format(where))

        # Check that the device interface names are
        # a subset of the already defined register blocks
        bus_device_names = set(self.bus_interfaces.named_devices)
        alias_bus_device_names = set(alias_bus_interfaces.named_devices)
        if not alias_bus_device_names.issubset(bus_device_names):
            raise ValueError("Alias file {} refers to device names {} that "
                             "do not map to device names in {}.".format(
                                 where, list(alias_bus_device_names),
                                 self.name))

        self.alias_impl = check_name(rd['alias_impl'],
                                     'alias_impl of block at ' + where)

        alias_target = check_name(rd['alias_target'],
                                  'alias_target of block at ' + where)

        if alias_target != self.name:
            raise ValueError("Alias target block name {} in {} "
                             "does not match block name {}.".format(
                                 alias_target, where, self.name))

        init_block = RegBlock(self.regwidth, self.params)

        alias_reg_blocks = RegBlock.build_blocks(init_block, rd['registers'],
                                                 self.bus_interfaces,
                                                 self.clocking, True)

        # Check that alias register block names are
        # a subset of the already defined register blocks
        alias_reg_block_names = set(alias_reg_blocks.keys())

        if not alias_reg_block_names.issubset(set(self.reg_blocks.keys())):
            raise ValueError("Alias file {} refers to register blocks {} that "
                             "do not map to register blocks in {}.".format(
                                 where, list(alias_reg_block_names),
                                 self.name))

        # Check that the alias bus interface names and register blocks match
        if alias_reg_block_names != alias_bus_device_names:
            raise ValueError("Interface and register block names do not match "
                             "in {}.".format(where))

        # Validate alias registers against the generic reg blocks,
        # and enhance the information in the existing datastructures.
        for block_key, alias_block in alias_reg_blocks.items():
            # Double check the interface definition options
            if self.bus_interfaces.device_async:
                if not alias_bus_interfaces.device_async:
                    raise ValueError('Missing device_async key in alias '
                                     'interface {} in {}'.format(
                                         block_key, where))
                if ((alias_bus_interfaces.device_async[block_key] !=
                     self.bus_interfaces.device_async[block_key])):
                    raise ValueError('Inconsistent configuration of interface '
                                     '{} in {}'.format(block_key, where))

            if scrub:
                # scrub alias definitions and replace the entire block.
                alias_block.scrub_alias(where)
                self.reg_blocks[block_key] = alias_block
            else:
                # Override hier path of aliased interface
                hier_path = alias_bus_interfaces.device_hier_paths[block_key]
                self.bus_interfaces.device_hier_paths[block_key] = hier_path

                # Validate and apply alias definitions
                self.reg_blocks[block_key].apply_alias(alias_block, where)

    def alias_from_text(self, scrub: bool, txt: str, where: str) -> None:
        '''Load alias regblocks from an hjson description in txt'''
        self.alias_from_raw(scrub, hjson.loads(txt, use_decimal=True), where)

    def alias_from_path(self, scrub: bool, path: str) -> None:
        '''Load alias regblocks from an hjson description in a file at path'''
        with open(path, 'r', encoding='utf-8') as handle:
            self.alias_from_text(scrub, handle.read(),
                                 'alias file at {!r}'.format(path))

    def _asdict(self) -> dict[str, object]:
        ret = {'name': self.name, 'regwidth': self.regwidth}
        if len(self.reg_blocks) == 1 and None in self.reg_blocks:
            ret['registers'] = self.reg_blocks[None].as_dicts()
        else:
            ret['registers'] = {
                k: v.as_dicts()
                for k, v in self.reg_blocks.items()
            }

        ret['param_list'] = self.params.as_dicts()
        ret['version'] = str(self.version)
        ret['bus_interfaces'] = self.bus_interfaces.as_dicts()
        ret['clocking'] = self.clocking.items
        ret['scan'] = self.scan
        ret['scan_reset'] = self.scan_reset
        ret['scan_en'] = self.scan_en

        return ret

    def get_rnames(self) -> set[str]:
        ret = set()  # type: set[str]
        for rb in self.reg_blocks.values():
            ret = ret.union(set(rb.name_to_offset.keys()))
        return ret

    def has_shadowed_reg(self) -> bool:
        '''Return boolean indication whether reg block contains shadowed registers'''

        for rb in self.reg_blocks.values():
            if rb.has_shadowed_reg():
                return True

        # if we are here, then no one has a shadowed register
        return False

    def get_primary_clock(self) -> ClockingItem:
        '''Return primary clock of an block'''

        return self.clocking.primary

    def check_regwens(self) -> bool:
        """Checks all regwens are used in at least one other CSR

        This relies on the regwen having the string "REGWEN" in its name.
        The uses should be in the "regwen" field of a CSR.
        """
        log.debug(f"Checking regwens for IP {self.name}")
        status: bool = True
        for rb in self.reg_blocks.values():
            rb_name = rb.name if rb.name else "default"
            log.debug(f"Register block: {rb_name}")
            regwen_names: list[str] = [
                reg.name for reg in rb.registers if "REGWEN" in reg.name
            ]
            unused_regwens: list[str] = []
            for regwen in regwen_names:
                regwen_users = []
                for reg in rb.registers:
                    if reg.regwen == regwen:
                        regwen_users.append(reg)
                for multi_reg in rb.multiregs:
                    for reg in multi_reg.pregs:
                        if reg.regwen == regwen:
                            regwen_users.append(reg)
                if not regwen_users:
                    unused_regwens.append(regwen)
                else:
                    log.debug(
                        f"Regwen {regwen} in {self.name}'s {rb_name} register "
                        "block controls the following registers:")
                    for r in regwen_users:
                        log.debug(f"  {r.name}")
            if unused_regwens:
                log.error(f"Unused regwen(s) in {self.name} {rb_name} "
                          f"register block: {', '.join(unused_regwens)}")
                status = False
        return status
