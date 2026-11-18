"""Retrieved declarations for the DuckDB set (development, git only): ../../real-set/jev-narrow/context/
build_context.py pointed at DuckDB, as ../../pooled-dev/decl/build_decl.py did for RocksDB. Same procedure
(identifiers on the changed lines -> git grep at the item's own commit -> declaration-like hits, nearest scope
first -> snippets up to 6000 characters), no labels or defect text used. Changes: the repository, the search
path (all C++ files outside third_party/ instead of src/) and a DuckDB stoplist of very common names.

    python build_decl_ddb.py      # writes decl_items.jsonl"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent.parent
sys.path.insert(0, str(EXP / "real-set" / "jev-narrow" / "context"))
import build_context as bc  # noqa: E402

bc.GISMO6 = r"C:\workdir\warf\repos\duckdb"
bc.COMMON |= set("""duckdb idx_t Vector DataChunk LogicalType LogicalTypeId PhysicalType ClientContext Value
unique_ptr make_uniq make_shared_ptr shared_ptr vector string D_ASSERT InternalException NotImplementedException
BinderException InvalidInputException ConversionException Exception optional_ptr reference count result input
state context type types data size_t int64_t int32_t uint64_t uint32_t uint8_t hugeint_t string_t SelectionVector
ValidityMask FlatVector ConstantVector Cast GetType ToString Copy Reset Initialize Append Scan Get Set Add Bind
expression expr child children names name column columns info bind_data Allocator BufferManager move std
""".split())
_git = bc.git


def git(*args):
    if args and args[-1] == "src":           # the builder searches src/ of gismo6: here all C++ files
        args = (*args[:-1], "*.hpp", "*.cpp", "*.h", "*.cc", ":(exclude)third_party")
    return _git(*args)


bc.git = git
bc.ITEMS = EXP / "ddb-set" / "items.jsonl"
bc.OUT = HERE / "decl_items.jsonl"

if __name__ == "__main__":
    sys.argv = [sys.argv[0]]
    bc.main()
