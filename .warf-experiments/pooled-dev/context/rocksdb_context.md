RocksDB: a C++ embedded key-value storage library (LSM tree), used on Linux, macOS, Windows and 32-bit platforms.
Build: gcc and clang with -W -Wextra -Wall -Wsign-compare -Wshadow and -Werror; MSVC with /W4 /WX. Any new compiler warning on any supported compiler breaks the build.
Release builds define NDEBUG, so expressions inside assert() are not evaluated there.
Unit tests, the db_stress tool, db_bench, the Java (JNI) bindings, the C API and optional build variants are compiled on every supported platform and must keep building.
Many structures are shared between threads and guarded by the DB mutex.
