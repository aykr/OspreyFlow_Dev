# The studio lane's L1.2a plants (rule 15)

Each script plants a change in the product or a fake, runs the named tests, prints the first
failing assertion, and restores the file, which it checks by md5. They are kept so every red in
`../L1.2a_RED_RECORD.md` can be run again. Run them only under the stack lease, from
`OspreyFlow_Build`, with the venv's Python. Pass the plants' letters as arguments.

- `plants.py`: a–d. Link withdrawal and the two old ledger reads, in `studio_publish.py`, and
  events taken by link, end to end. Takes the test paths as arguments.
- `plants2.py`: e, f, g. A count from other cases' loads, `withdrawn_before` without the case,
  and `withdrawn_row_keys_among` without the case.
- `plants3.py`: P, M, D, K, G, H, R, S (round 1's self-review).
- `plants4.py`: U, V, T, W, X, Y, Z, S1, S2, S3, F (Part A2).
