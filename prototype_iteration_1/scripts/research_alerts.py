"""Local observation notices and reconstruction drafts; no outbound delivery."""

import hashlib
import json
from pathlib import Path
import sqlite3


def notice_key(kind, incident, region, horizon=None):
    return hashlib.sha256(
        json.dumps(
            [kind, str(incident), str(region), horizon], separators=(",", ":")
        ).encode()
    ).hexdigest()[:24]


def save_notices(path, notices, seen_at):
    if len({n["id"] for n in notices}) != len(notices):
        raise ValueError("Duplicate incoming notice identity")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS notices (id TEXT PRIMARY KEY, revision TEXT NOT NULL, body TEXT NOT NULL, first_seen TEXT NOT NULL, last_seen TEXT NOT NULL)"
        )
        for notice in notices:
            if (
                notice.get("actionable") is not False
                or notice.get("delivery") != "local_only"
            ):
                raise ValueError(
                    "This store accepts only non-actionable local research notices"
                )
            body = json.dumps(
                notice, sort_keys=True, allow_nan=False, separators=(",", ":")
            )
            revision = hashlib.sha256(body.encode()).hexdigest()
            db.execute(
                "INSERT INTO notices VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,body=excluded.body,last_seen=excluded.last_seen",
                (notice["id"], revision, body, seen_at, seen_at),
            )
        # This response is the current snapshot, not every old notice in the ledger.
        if not notices:
            return []
        result = []
        for notice in notices:
            row = db.execute(
                "SELECT revision,body,first_seen,last_seen FROM notices WHERE id=?",
                (notice["id"],),
            ).fetchone()
            result.append(
                {
                    **json.loads(row[1]),
                    "revision": row[0],
                    "first_seen_utc": row[2],
                    "last_seen_utc": row[3],
                }
            )
        return result
