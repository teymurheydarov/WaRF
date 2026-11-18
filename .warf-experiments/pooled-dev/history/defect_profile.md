RocksDB defect profile (37 past defects). Check a diff for:
- Build breaks on one compiler or config (about 17 of 37), mostly -Werror on clang/macOS or MSVC /WX. Integer types: size_t/uint64_t into int/uint32_t/uint16_t, signed/unsigned compares (also ASSERT_EQ), %d/%lu for size_t/uint64_t, int for an enum. Also class/struct forward-decl mismatch, inconsistent missing override, fields unused under ROCKSDB_LITE, #ifdef in macro arguments, capturing lambda as C fn pointer, include not via "rocksdb/...", nonexistent enumerator.
- Lifetime/memory (about 8): pointer into a buffer or Version freed while still used; statics used during static init/exit; ownership change callers ignore (leak); buffer smaller than the length passed; array shrunk without its count; deref of an empty handle.
- Logic edge cases (about 8): inverted condition or assert, option set to 0, empty key vs empty initial sentinel, off-by-one substr, stale iterator state across files, error status lost on refresh, partial Windows error mapping.
- Concurrency (about 3): shared state read without the mutex or while it is released.
- Debug vs release (2): side effect inside assert(); variable used only in assert.
