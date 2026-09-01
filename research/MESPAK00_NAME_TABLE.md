# MESPAK00 name table

Canonical workflow input: [`tables/namesMESPAK00.tbl`](tables/namesMESPAK00.tbl).

This user-supplied table contains **2,294** mappings from a four-digit hex
token to a fixed two-character output. It is the reference table for
table-driven review/import of Digimon name data from `MSG/MESPAK00.PAK`.

It is an **encoding table**, not a translation list. It helps tooling decode,
validate, and round-trip name records; contributors must still provide an
approved Japanese-to-English name mapping before a ROM build changes text.

## Use policy

1. Use this table when inspecting/exporting MESPAK00 name records.
2. Keep canonical English spellings in a separate reviewed CSV/JSON mapping.
3. Reject an import when a token is absent from this table or when an edited
   record cannot round-trip through the same encoding.
4. Preserve string indices and archive pointers; name work must not alter
   unrelated MESPAK00 strings.

The table is safe to publish because it contains codec mappings only—no ROM,
save state, or extracted game archive.
