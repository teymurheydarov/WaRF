DuckDB: in-process analytical SQL database in C++17 for Linux (glibc, musl), macOS, Windows (also MinGW, arm64), Wasm, Android.
CI compilers: mostly Clang (clang-cl on Windows), also GCC 11+. -Werror only in the Linux relassert and OSX Debug jobs, with -Wall -Wunused -Wnarrowing -pedantic; no /WX on Windows.
Release: NDEBUG. Debug: DEBUG (enables #ifdef DEBUG verifiers), ASan/UBSan. D_ASSERT is a no-op unless DEBUG or FORCE_ASSERT (then throws InternalException); duckdb::vector/unique_ptr keep bounds/null checks in release.
CI: format, clang-tidy, up-to-date generated files, sqllogictest/C++ tests in relassert (sanitizers) and release, TSan, extensions, CLI, Wasm, Swift, vector size 2, no-RTTI.
Clang builds fail on violated thread-safety annotations (DUCKDB_GUARDED_BY, DUCKDB_REQUIRES).
