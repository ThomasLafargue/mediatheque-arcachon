# Message à envoyer au support Turso

Dashboard → bouton **Support** (ou support@turso.tech).

**Objet :**

```
All queries failing (502 / "unexpected EOF during chunk size line") — mediatheque-arcachon
```

**Corps du message (à copier tel quel) :**

```
Hello,

Since 2026-07-26 my database has become progressively unusable, and since
2026-07-27 ~09:00 UTC every single query fails, including the simplest one.

DATABASE
  Name    : mediatheque-arcachon-thomaslafargue
  URL     : libsql://mediatheque-arcachon-thomaslafargue.aws-eu-west-1.turso.io
  Region  : aws-eu-west-1
  Plan    : Free
  Size    : 54.06 MB, ~44,000 rows in the main table
  Status shown in the dashboard: Active

CLIENT
  Python 3.10, libsql 0.1.11, macOS

WHAT FAILS
  Every query, including:

      SELECT COUNT(*) FROM notice

  Two errors alternate:

    ValueError: Hrana: `cursor error: `cursor error: `error reading a body
    from connection: unexpected EOF during chunk size line``

    ValueError: Hrana: `api error: `status=502 Bad Gateway,
    body={"error":"upstream forward failed"}``

  I ran a script of 8 escalating test queries (COUNT, 10 rows, 300 rows,
  ORDER BY, JOIN) three times over one hour: 8/8 failed every time, in
  0.3 to 4 seconds. Failures are immediate, not timeouts.

TIMELINE
  2026-07-26  large SELECTs (~4,300 rows with text columns) started failing
              with "unexpected EOF during chunk size line". Small queries
              still worked.
  2026-07-27  ~09:00 UTC onwards: everything fails, including COUNT(*).

WHAT I HAVE ALREADY RULED OUT
  - Quota: 44,009,044 rows read and 2,233,186 written this month, against
    the 500M / 10M free-tier limits. Storage 54 MB of 5 GB. Also, quota
    exhaustion returns BLOCKED, not 502.
  - Concurrency: I stopped my only background job. The database has had no
    other client for over an hour and still fails.
  - Network / TLS: the dashboard loads fine from the same machine, and TLS
    errors would surface differently.
  - My queries: SELECT COUNT(*) FROM notice cannot be the problem.

The 502 "upstream forward failed" comes from your edge, which suggests the
database instance itself is not reachable behind the gateway even though the
dashboard reports it as Active.

Could you check the health of this instance? This database powers the public
catalogue tool of a French public library (Médiathèque d'Arcachon), so I would
be grateful for a look as soon as you can.

Thank you,
Thomas Lafargue
thomaslafargue@me.com
```

---

## Si le support demande plus

- Sortie brute du diagnostic : `diagnostic.txt` (8 tests, 8 échecs)
- Script reproductible : `_diag_turso.py`
- Aucun jeton d'authentification n'est communiqué dans ce message — ne jamais
  le coller dans un ticket.
