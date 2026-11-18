Apache Arrow C++: libraries for the Arrow columnar in-memory format, IPC and Parquet (C++20); CI on Linux x86-64/ARM64, macOS, Windows (MSVC, MinGW).
GCC, Clang, MSVC. BUILD_WARNING_LEVEL=CHECKIN (default unless Release): -Wall (Clang also -Wextra -Wshorten-64-to-32), MSVC /W3, -Werror or /WX in Debug; most CI builds are Debug, so warnings fail CI.
Under NDEBUG (Release) DCHECK* compile out, arguments unevaluated, except DCHECK_OK; ARROW_CHECK* is fatal in all builds.
CI builds optional parts (Parquet, Dataset, Flight, Gandiva, filesystems) and runs unit tests per platform, ASAN+UBSAN with fuzz regressions, and Python, R, GLib/Ruby, MATLAB builds.
Buffers are reference-counted for zero-copy sharing; CI tests use ARROW_DEBUG_MEMORY_POOL=trap to catch overruns and wrong-size frees.
