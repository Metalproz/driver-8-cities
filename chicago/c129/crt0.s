# C129 mipsel harness entry: stack, clear .bss, call mips_main, stop with 'break' (mipsrun ends there; v0 = result).
    .set noreorder
    .section .text.start
    .globl _start
_start:
    lui   $sp, 0x801F
    ori   $sp, $sp, 0xFF00
    la    $t0, __bss_start
    la    $t1, __bss_end
1:  beq   $t0, $t1, 2f
    nop
    sw    $zero, 0($t0)
    b     1b
    addiu $t0, $t0, 4
2:  jal   mips_main
    nop
    break 0
    nop
