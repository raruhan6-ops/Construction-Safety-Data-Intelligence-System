# Inter-coder reliability files

These files let readers recompute the agreement between the two independent coders of the 2025 coverage matrix and see how each disagreement was resolved. Coder names have been removed. The coders are labelled A and B, as in the codebook.

| File | Contents |
| --- | --- |
| `coding_coder_A.csv` | Coder A's classification of all 148 hazard–system rows before adjudication. For the 32 rows decided at adjudication, the class, scope and rationale are coder A's values taken from the adjudication record. The other 116 rows were not changed at adjudication, so their values are taken from the final matrix. `matched_functions` and `coder_confidence` come from the final matrix for every row. The `source` column says which applies. |
| `coding_coder_B_revised.csv` | Coder B's independent sheet as returned, in its revised version (see below). |
| `adjudication_record.csv` | The 32 adjudicated rows (29 disagreements and 3 rows affected by rule changes), with both coders' classes and rationales, the written proposal, the decision and the final class. The adjudicator's name has been replaced with "Coders A and B (consensus)". |

## Which version of coder B's sheet this is

Coder B returned the sheet on 17 November 2026 and later re-saved it with notes on the VSS camera locations. Coder B made that revision after seeing the first comparison, so the paper reports agreement for the first version only. The first version was not kept. The file here is the revised version.

The two versions agree with coder A on the same number of rows. Only the agreement expected by chance, and therefore κ, differs slightly:

| | Rows agreeing | κ, first version (reported in the paper) | κ, revised version (this file) |
| --- | --- | --- | --- |
| All rows | 122/148 (82.4%) | 0.670 | 0.673 |
| HK 4S | 54/74 (73.0%) | 0.570 | 0.570 |
| SG VSS | 68/74 (91.9%) | 0.635 | 0.651 |

Scope agreement where both coders chose Direct is 24/27 in both versions.

## Recomputing the agreement

From the project root:

```
python tools/compare_coding.py reliability/coding_coder_A.csv reliability/coding_coder_B_revised.csv --out disagreements.csv
```

This prints the agreement figures above for the revised version and writes the 29 disagreements. The final classes are in `CSDIS_Coverage_Matrix_2025.csv`, and the coding rules are in `CSDIS_Coverage_Codebook_v1.2.md`.
