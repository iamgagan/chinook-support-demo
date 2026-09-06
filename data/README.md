# Pinned Chinook data

`Chinook_Sqlite.sql` is the unmodified SQL downloaded from:

https://raw.githubusercontent.com/lerocha/chinook-database/master/ChinookDatabase/DataSources/Chinook_Sqlite.sql

SHA-256: `caf31d698a4a79c628215b552dfe6575e71be052ae02b8f18e763498f55f5d44`

The upstream MIT license is included as `LICENSE.md`. The SQL identifies itself as Chinook 1.4.5.

`uv run python -m chinook_support.db` builds the ignored `chinook.sqlite` from this source and initializes a separate ignored `support.sqlite` for thread ownership and demo tickets. Normal setup does not reset either database.
