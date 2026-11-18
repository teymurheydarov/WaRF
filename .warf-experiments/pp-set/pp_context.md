PPSSPP: a C++17 PSP emulator. CI builds Release only: Windows MSVC (x64, ARM64, UWP, libretro x64/x86), Linux gcc/clang (x86-64, arm64, Alpine; armhf, riscv64, loongarch64 under qemu), macOS, iOS, tvOS, Android (arm64, armv7, x86_64).
Warnings never fail the build: gcc/clang -Wall with only -Werror=return-type; MSVC /W3, no /WX.
No CI build defines _DEBUG: _dbg_assert_ and _dbg_assert_msg_ expand to nothing (condition not evaluated); _assert_ and _assert_msg_ stay and crash.
Sources are listed by hand in CMake, Windows and UWP .vcxproj and .filters, android/jni/Android.mk and libretro/Makefile.common; a file missing in one breaks that build.
Tests: PPSSPPUnitTest ALL and pspautotests (software renderer), on Linux under all four CPU backends (jit, jit-ir, ir, interpreter). No sanitizers.
