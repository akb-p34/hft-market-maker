# Redactions

This repository is a public copy of the team's 2025 Stevens High Frequency Trading Competition code, taken from a
private course folder. This file lists every change made for the public release and every file that was left out.

## What was changed, in short

Nothing inside the code was edited. `avellaneda_stoikov.py` and `run.py` are byte-for-byte copies of the originals
(sha256 below), so every line number matches the original files.

| File | sha256 (original and this copy, identical) |
|---|---|
| `avellaneda_stoikov.py` | `9237bfa6e9948bcc80fb619bb8af9d88cd2f72d1538bd4d3a4b167137712d67d` |
| `run.py` | `c6c7e214e3b8644a54ffd79b9a2db69c7bc8712ed79eacc83711a7829a6be5ed` |

## Login details

`run.py` never held a password. It reads the SHIFT username, password and connection file from a local `config.ini`
(`run.py` lines 509-517). That `config.ini` was not in the source folder and is not in this repository.
`config.example.ini` is new: it lists the same keys with placeholder values, and `.gitignore` excludes `config.ini`
so a real one can't be committed by accident.

## Files left out

| Left out | Why |
|---|---|
| `goodcbfs.py` | SHIFT callback helpers (print trades, order reports, portfolio updates). `run.py` never imports it, and it appears to be SHIFT's example code rather than the team's own work. |
| `config.ini` | Never in the source folder. It would hold a personal SHIFT login. |
| Logs the bot writes at runtime (`market_log6.csv`, `backtest15_order_logs.csv`) | None were in the source folder. `.gitignore` excludes `*.csv` so they stay out. |
| The QF 302 course files (`HFTCadapted.py`, `qf_302_project_part_1.py`, `qf_302_project_part_2.py`, the `GDC` folder, the final deck) | A different team's course project. The README mentions it in one paragraph and names nobody from that team. |

## Scan

Before the commit, the whole tree was searched, case-insensitively, for `passw`, `secret`, `token`, `api_key`,
`api-key`, `username`, `login`, `@stevens` and `@gmail`, plus every `.cfg`, `.ini` and `.json` file. The remaining hits
are:

- `run.py` lines 513, 517 and 519: `config["username"]`, `config["password"]` and `shift.IncorrectPasswordError`.
  These are the names of settings and of an error type. No value is stored.
- `config.example.ini`: the placeholders `YOUR_SHIFT_USERNAME` and `YOUR_SHIFT_PASSWORD`, and comments about them.
- This file and `README.md`, which describe the scan and the login setup.

No email address, server address or IP address appears anywhere in the tree.
