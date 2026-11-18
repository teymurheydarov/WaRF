"""Retrieved declarations for the RocksDB matched set (development): ../../real-set/jev-narrow/context/build_context.py
pointed at RocksDB. Same procedure (identifiers on the changed lines -> git grep at the item's own commit ->
declaration-like hits, nearest scope first -> snippets up to 6000 characters), no labels or defect text used.
Changes: the repository, the search path (all C++ files instead of src/) and a RocksDB stoplist of very common
names.

    python build_decl.py      # writes decl_items.jsonl"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent.parent
sys.path.insert(0, str(EXP / "real-set" / "jev-narrow" / "context"))
import build_context as bc  # noqa: E402

bc.GISMO6 = r"C:\workdir\warf\repos\rocksdb"
bc.COMMON |= set("""rocksdb ROCKSDB_NAMESPACE Status Slice ok ToString IsNotFound OK NotFound Corruption NotSupported
InvalidArgument IOError ASSERT_OK ASSERT_NOK ASSERT_EQ ASSERT_NE ASSERT_TRUE ASSERT_FALSE ASSERT_LT ASSERT_LE ASSERT_GT
ASSERT_GE EXPECT_EQ EXPECT_TRUE EXPECT_FALSE EXPECT_OK TEST TEST_F TEST_P Options DBOptions ColumnFamilyOptions
ReadOptions WriteOptions DB db_ dbfull options env_ Env uint64_t uint32_t uint16_t uint8_t int64_t int32_t size_t
string vector map set unordered_map unique_ptr shared_ptr make_unique make_shared reset release get Put Get Delete
Merge Flush Open Close Reopen DestroyAndReopen Next Prev Seek SeekToFirst SeekToLast Valid key value status mutex_
Lock Unlock InstrumentedMutexLock MutexLock fprintf snprintf printf PRIu64 nullptr""".split())
_git = bc.git


def git(*args):
    if args and args[-1] == "src":           # the builder searches src/ of gismo6: here all C++ files
        args = (*args[:-1], "*.h", "*.cc", "*.cpp", "*.hpp")
    return _git(*args)


bc.git = git
bc.ITEMS = EXP / "rdb-set" / "items.jsonl"
bc.OUT = HERE / "decl_items.jsonl"

if __name__ == "__main__":
    sys.argv = [sys.argv[0]]
    bc.main()
