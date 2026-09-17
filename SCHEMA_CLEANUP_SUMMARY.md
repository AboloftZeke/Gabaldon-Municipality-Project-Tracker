# Schema cleanup summary

The earlier legacy-table migration plan has been superseded by the clean schema
baseline on `feature/publication-approval-workflow`.

See [Schema naming and database rebuild](SCHEMA_NAMING.md) for the complete rename
map, removed and retained models, migration reset instructions, and verification
commands. Use a new empty development database; do not fake these migrations over
the old migration history. Earlier versions of this document remain in Git history.
