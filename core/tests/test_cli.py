"""Tests for the CLI entry point."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from numislens_core import cli, melt

REPO_ROOT = Path(__file__).resolve().parents[2]
PEACE_MANIFEST = REPO_ROOT / "core" / "sets" / "peace-dollars-1921-1935.json"


def test_init_creates_db(tmp_path, capsys):
    db = tmp_path / "cli.db"
    rc = cli.main(["--db", str(db), "init"])
    assert rc == 0
    assert db.exists()
    out, _ = capsys.readouterr()
    assert "initialized" in out


def test_add_show_move_roundtrip(tmp_path, capsys):
    db = tmp_path / "cli.db"
    cli.main(["--db", str(db), "init"])
    capsys.readouterr()

    rc = cli.main(["--db", str(db), "loc", "add", "cabinet", "A"])
    assert rc == 0
    out, _ = capsys.readouterr()
    loc1 = out.strip()
    assert loc1 == "1"

    rc = cli.main(["--db", str(db), "loc", "add", "cabinet", "B"])
    assert rc == 0
    out, _ = capsys.readouterr()
    loc2 = out.strip()
    assert loc2 == "2"

    rc = cli.main(
        [
            "--db",
            str(db),
            "add",
            "--series",
            "Peace Dollar",
            "--year",
            "1921",
            "--mint",
            "P",
            "--location",
            loc1,
        ]
    )
    assert rc == 0
    out, _ = capsys.readouterr()
    assert "NL-000001" in out

    rc = cli.main(["--db", str(db), "move", "NL-000001", loc2])
    assert rc == 0
    capsys.readouterr()

    rc = cli.main(["--db", str(db), "show", "NL-000001"])
    assert rc == 0
    out, _ = capsys.readouterr()
    assert "Peace Dollar" in out
    assert "1921" in out
    assert "B" in out


def test_show_json_parses(tmp_path, capsys):
    db = tmp_path / "cli.db"
    cli.main(["--db", str(db), "init"])
    capsys.readouterr()
    cli.main(
        [
            "--db",
            str(db),
            "add",
            "--series",
            "Peace Dollar",
            "--year",
            "1921",
            "--mint",
            "P",
        ]
    )
    capsys.readouterr()

    rc = cli.main(["--db", str(db), "show", "NL-000001", "--json"])
    assert rc == 0
    out, _ = capsys.readouterr()
    data = json.loads(out)
    assert data["accession_no"] == "NL-000001"
    assert data["series"] == "Peace Dollar"


def test_find_json_parses(tmp_path, capsys):
    db = tmp_path / "cli.db"
    cli.main(["--db", str(db), "init"])
    capsys.readouterr()
    cli.main(["--db", str(db), "add", "--series", "Peace Dollar", "--year", "1921"])
    capsys.readouterr()
    cli.main(["--db", str(db), "add", "--series", "Peace Dollar", "--year", "1922"])
    capsys.readouterr()

    rc = cli.main(["--db", str(db), "find", "--series", "Peace Dollar", "--json"])
    assert rc == 0
    out, _ = capsys.readouterr()
    data = json.loads(out)
    assert isinstance(data, list)
    assert len(data) == 2


def test_set_load_and_gaps(tmp_path, capsys):
    db = tmp_path / "cli.db"
    cli.main(["--db", str(db), "init"])
    capsys.readouterr()

    rc = cli.main(["--db", str(db), "set", "load", str(PEACE_MANIFEST)])
    assert rc == 0
    capsys.readouterr()

    rc = cli.main(
        ["--db", str(db), "set", "gaps", "peace-dollars-1921-1935", "--json"]
    )
    assert rc == 0
    out, _ = capsys.readouterr()
    gaps = json.loads(out)
    assert isinstance(gaps, list)
    assert len(gaps) > 0

    rc = cli.main(["--db", str(db), "set", "status", "peace-dollars-1921-1935"])
    assert rc == 0
    out, _ = capsys.readouterr()
    assert "filled" in out


def test_bad_enum_exits_1(tmp_path, capsys):
    db = tmp_path / "cli.db"
    cli.main(["--db", str(db), "init"])
    capsys.readouterr()

    rc = cli.main(["--db", str(db), "add", "--value-basis", "gutfeel"])
    assert rc == 1
    _, err = capsys.readouterr()
    assert "error:" in err
    assert "value_basis" in err


def test_show_missing_coin_exits_1(tmp_path, capsys):
    db = tmp_path / "cli.db"
    cli.main(["--db", str(db), "init"])
    capsys.readouterr()

    rc = cli.main(["--db", str(db), "show", "NL-999999"])
    assert rc == 1
    _, err = capsys.readouterr()
    assert "not found" in err


def test_melt_update_with_monkeypatched_fetchers(tmp_path, capsys, monkeypatch):
    now = datetime.now(timezone.utc).isoformat()
    monkeypatch.setattr(melt, "_fetch_gold_api", lambda metal: (6001, now))
    monkeypatch.setattr(melt, "_fetch_yahoo", lambda metal: 6010)

    db = tmp_path / "cli.db"
    cli.main(["--db", str(db), "init"])
    capsys.readouterr()

    conn = sqlite3.connect(str(db))
    cid = conn.execute(
        "SELECT id FROM compositions WHERE name='90% silver dollar'"
    ).fetchone()[0]
    conn.close()

    rc = cli.main(
        ["--db", str(db), "add", "--composition", str(cid), "--value-basis", "melt"]
    )
    assert rc == 0
    capsys.readouterr()

    rc = cli.main(["--db", str(db), "melt", "update"])
    assert rc == 0
    out, _ = capsys.readouterr()
    assert "recorded" in out
    assert "updated 1 melt-basis coin" in out

    rc = cli.main(["--db", str(db), "melt", "status", "--json"])
    assert rc == 0
    out, _ = capsys.readouterr()
    data = json.loads(out)
    assert data["portfolio"]["total_cents"] > 0
    assert data["spots"]["XAG"]["price_usd_cents"] == 6001


def test_melt_update_reports_failure_exit_1(tmp_path, capsys, monkeypatch):
    def raise_down(metal):
        raise melt.SpotFetchError("down")

    monkeypatch.setattr(melt, "_fetch_gold_api", raise_down)

    db = tmp_path / "cli.db"
    cli.main(["--db", str(db), "init"])
    capsys.readouterr()

    rc = cli.main(["--db", str(db), "melt", "update"])
    assert rc == 1
    _, err = capsys.readouterr()
    assert "ERROR" in err


def test_watch_mark_and_stale(tmp_path, capsys):
    db = tmp_path / "cli.db"
    cli.main(["--db", str(db), "init"])
    capsys.readouterr()

    cli.main(["--db", str(db), "add", "--series", "Morgan Dollar", "--year", "1921"])
    capsys.readouterr()

    rc = cli.main(
        ["--db", str(db), "watch", "mark", "--series", "Morgan Dollar",
         "--reason", "silver news"]
    )
    assert rc == 0
    out, _ = capsys.readouterr()
    assert "marked 1" in out

    rc = cli.main(["--db", str(db), "watch", "stale", "--json"])
    assert rc == 0
    out, _ = capsys.readouterr()
    stale = json.loads(out)
    assert len(stale) == 1
    assert stale[0]["stale_reason"] == "silver news"


def test_watch_mark_unknown_series_fails(tmp_path, capsys):
    db = tmp_path / "cli.db"
    cli.main(["--db", str(db), "init"])
    capsys.readouterr()

    rc = cli.main(
        ["--db", str(db), "watch", "mark", "--series", "Nope", "--reason", "x"]
    )
    assert rc == 1
    _, err = capsys.readouterr()
    assert "unknown series" in err


def test_watch_status_json(tmp_path, capsys):
    db = tmp_path / "cli.db"
    cli.main(["--db", str(db), "init"])
    capsys.readouterr()
    cli.main(
        ["--db", str(db), "add", "--series", "Morgan Dollar", "--year", "1921",
         "--value", "50"]
    )
    capsys.readouterr()

    rc = cli.main(["--db", str(db), "watch", "status", "--json"])
    assert rc == 0
    out, _ = capsys.readouterr()
    data = json.loads(out)
    assert data["stale_count"] == 0
    assert len(data["watchlist"]) == 1
