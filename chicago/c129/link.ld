/* C129 mipsel harness: one flat image at 0x80010000 (mipsrun loads the objcopy'd binary there). */
ENTRY(_start)
SECTIONS {
    . = 0x80010000;
    .text : { *(.text.start) *(.text*) }
    .rodata : { *(.rodata*) }
    .data : { *(.data*) *(.sdata*) }
    . = ALIGN(4);
    __bss_start = .;
    .bss : { *(.sbss*) *(.bss*) *(COMMON) }
    . = ALIGN(4);
    __bss_end = .;
    /DISCARD/ : { *(.comment) *(.MIPS.abiflags) *(.reginfo) *(.pdr) *(.gnu.attributes) *(.eh_frame*) }
}
