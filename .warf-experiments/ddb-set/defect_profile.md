DuckDB defect profile (40 past defects). Check a diff for:
- Index/offset slips (~9): selection vector skipped (RowIsValid(i) vs sel idx) or applied twice; offsets dropped or swapped (result_offset, ValidityMask::Slice); index advanced before use (lhs_idx, current_segment_idx); unsigned underflow; Child(1) vs a one-child grammar rule.
- Build breaks (~8): default argument repeated (MSVC); incomplete type/name clash (amalgamation); MinGW under #ifdef _WIN32; template without definition (link); Python 2/3 APIs; py::list returning py::none().
- CSV reader (~7): error line set on one path only; LineInfo state across threads (wrong line, CanItGetLine spin); option names read_csv rejects (skip_rows); SetReadOption fed options it lacks; single-column files; wrong error_handler.
- Optimizer/planner logic (~6): inverted condition; children swapped ignoring join type; any vs every window partition; struct indexes reversed; parameter shadows member; lock_configuration rejecting every RESET.
- Asserts/tests failing on valid input (~5): D_ASSERT on legal states; parenthesis moved by a cast; uninitialized test variables; tests ignoring concurrent inserts.
- Memory/races (~5): data left pinned on handoff; malloc'ed buffer leaked; pointer into a by-value copy; unlocked shared statistics.
