PPSSPP defect profile (40 past defects). Check a diff for:
- Wrong operand/operator (8): EBOOT.OLD for altBootNames[i], width for height, == for =, >= for !=, inverted iFpsLimit/60, &flag to value overload, full pixel for alpha byte, extra format args.
- Arithmetic/bounds (8): > vs >= size, inclusive scissor edge, unsigned a-b underflow, byte count on s16*, address missing row y, 1/128 vs 1/256, float[3] for float[4] in savestate, one-sided margins.
- JIT/HLE contracts (8): regcache pair check mr[i] vs mr[i+1], MAP_NOINIT on dest aliasing source, SUBF operand order, size 4 to PrepareRead/Write, JAL for J, getter NID bound to setter, extra Wrap arg, stub returns 1.
- Lifetime/threads/null (6): freeing/reusing what queued work uses (Vulkan allocator, XAudio2 buffer), loader task racing release, inverted wait predicate, new[] leak, null deref (gpuDebug, audioBuf after loadstate).
- Stale state/order (5): result left in unstored local (fullhash), raw glEnable/glBlendFunc bypassing glstate cache, framebuffer re-picked from gstate, Reset moved after Init, later match overwrites best.
- Platform/paths (5): struct/class forward-decl mismatch (MSVC), glClearDepth on GLES2, Win32-only header change breaks Linux/Android, realpath drops trailing slash, bare name vs disc-relative path.
