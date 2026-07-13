"""Album / coin-folder photo-import endpoints.

Thin HTTP layer over ``numislens_core.albums`` (a pure connection-based module).
The album lifecycle is: create an import -> upload page photos -> a vision pass
POSTs per-page analysis (or a human does) -> review the merged slots against the
matched set manifests -> commit into a real set + coin rows. Vision NEVER
auto-commits; a human drives the commit.

Error mapping is handled inline (AlbumUncertain -> 409, AlbumNotFound -> 404,
other AlbumError -> 422), mirroring the rolls router, because AlbumError is not a
LedgerError subclass. ManifestError/ValueError still map via the shared handlers.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Annotated, Literal, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from numislens_core import Ledger, albums
from numislens_core.albums import AlbumError, AlbumNotFound, AlbumUncertain
from pydantic import BaseModel, ConfigDict, Field

from ..deps import get_ledger

router = APIRouter()

LedgerDep = Annotated[Ledger, Depends(get_ledger)]

_CONTENT_TYPE_EXT = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}


# ---------------------------------------------------------------------------
# request bodies
# ---------------------------------------------------------------------------

class ImportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Optional[str] = None


class SlotAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slot_index: int
    label_text: str = ""
    year: Optional[int] = None
    mint: Optional[str] = None
    note: Optional[str] = None
    fill_state: Literal["filled", "empty", "uncertain"]
    confidence: Optional[float] = None


class PageAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page_title: Optional[str] = None
    page_type: Literal["page", "not_a_page"]
    slots: list[SlotAnalysis] = Field(default_factory=list)


class SlotPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fill_state: Literal["filled", "empty", "uncertain"]


class CommitBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    manifest_id: Optional[str] = None
    custom_name: Optional[str] = None
    create_coins: bool = True
    location_label: Optional[str] = None
    uncertain_policy: Literal["block", "empty"] = "block"


# ---------------------------------------------------------------------------
# serialization helpers
# ---------------------------------------------------------------------------

def _import_row(ldb: Ledger, import_id: int):
    row = ldb.conn.execute(
        "SELECT id, name, status, set_id, created_at FROM album_imports WHERE id = ?",
        (import_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"album import not found: {import_id}")
    return row


def _page_slots(ldb: Ledger, page_id: int) -> list[dict]:
    rows = ldb.conn.execute(
        """
        SELECT id, slot_index, label_text, year, mint, note, fill_state,
               confidence, source
        FROM album_page_slots WHERE page_id = ? ORDER BY slot_index
        """,
        (page_id,),
    ).fetchall()
    return [
        {
            "slot_id": r["id"],
            "slot_index": r["slot_index"],
            "label_text": r["label_text"],
            "year": r["year"],
            "mint": r["mint"],
            "note": r["note"],
            "fill_state": r["fill_state"],
            "confidence": r["confidence"],
            "source": r["source"],
        }
        for r in rows
    ]


def _pages(ldb: Ledger, import_id: int, *, with_slots: bool = True) -> list[dict]:
    rows = ldb.conn.execute(
        """
        SELECT id, seq, content_hash, page_title, page_type, analyzed_at
        FROM album_pages WHERE import_id = ? ORDER BY seq
        """,
        (import_id,),
    ).fetchall()
    out: list[dict] = []
    for r in rows:
        page = {
            "page_id": r["id"],
            "seq": r["seq"],
            "content_hash": r["content_hash"],
            "page_title": r["page_title"],
            "page_type": r["page_type"],
            "analyzed_at": r["analyzed_at"],
        }
        if with_slots:
            page["slots"] = _page_slots(ldb, r["id"])
        out.append(page)
    return out


# ---------------------------------------------------------------------------
# imports
# ---------------------------------------------------------------------------

@router.post("/albums/imports", status_code=status.HTTP_201_CREATED, tags=["albums"])
def create_import(body: ImportCreate, ldb: LedgerDep) -> dict:
    now = albums._utcnow()
    with ldb.conn:
        ldb.conn.execute("PRAGMA foreign_keys = ON")
        cur = ldb.conn.execute(
            "INSERT INTO album_imports (name, status, created_at) VALUES (?, 'pending', ?)",
            (body.name, now),
        )
        import_id = cur.lastrowid
        ldb.conn.execute(
            "INSERT INTO events (coin_id, event_type, at, detail) VALUES (NULL, 'album:created', ?, ?)",
            (now, _detail(import_id, name=body.name)),
        )
    return {
        "import_id": import_id,
        "name": body.name,
        "status": "pending",
        "created_at": now,
    }


@router.get("/albums/imports", tags=["albums"])
def list_imports(ldb: LedgerDep) -> list[dict]:
    rows = ldb.conn.execute(
        """
        SELECT i.id, i.name, i.status, i.created_at,
               (SELECT COUNT(*) FROM album_pages p WHERE p.import_id = i.id) AS page_count
        FROM album_imports i
        ORDER BY i.id
        """
    ).fetchall()
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "status": r["status"],
            "created_at": r["created_at"],
            "page_count": r["page_count"],
        }
        for r in rows
    ]


@router.get("/albums/imports/{import_id}", tags=["albums"])
def get_import(import_id: int, ldb: LedgerDep) -> dict:
    row = _import_row(ldb, import_id)
    pages = _pages(ldb, import_id)
    merged = albums.merge_page_slots(ldb.conn, import_id)
    candidates = albums.match_manifests(merged, albums.load_manifests())
    return {
        "id": row["id"],
        "name": row["name"],
        "status": row["status"],
        "set_id": row["set_id"],
        "created_at": row["created_at"],
        "pages": pages,
        "merged_slots": merged,
        "match_candidates": candidates,
    }


@router.delete("/albums/imports/{import_id}", tags=["albums"])
def discard_import(import_id: int, ldb: LedgerDep) -> dict:
    row = _import_row(ldb, import_id)
    now = albums._utcnow()
    with ldb.conn:
        ldb.conn.execute("PRAGMA foreign_keys = ON")
        ldb.conn.execute(
            "UPDATE album_imports SET status = 'discarded' WHERE id = ?", (import_id,)
        )
        ldb.conn.execute(
            "INSERT INTO events (coin_id, event_type, at, detail) VALUES (NULL, 'album:discarded', ?, ?)",
            (now, _detail(import_id)),
        )
    return {"import_id": import_id, "status": "discarded"}


# ---------------------------------------------------------------------------
# pages: upload + serve image
# ---------------------------------------------------------------------------

@router.post("/albums/imports/{import_id}/pages", tags=["albums"])
def upload_pages(
    import_id: int,
    request: Request,
    ldb: LedgerDep,
    pages: list[UploadFile] = File(...),
) -> dict:
    row = _import_row(ldb, import_id)
    if row["status"] in ("committed", "discarded"):
        raise HTTPException(
            status_code=409,
            detail=f"cannot add pages to a {row['status']} import",
        )

    dest_dir = Path(request.app.state.images_dir) / "albums" / str(import_id)
    dest_dir.mkdir(parents=True, exist_ok=True)

    seq_row = ldb.conn.execute(
        "SELECT COALESCE(MAX(seq), 0) AS m FROM album_pages WHERE import_id = ?",
        (import_id,),
    ).fetchone()
    next_seq = seq_row["m"] + 1

    added: list[dict] = []
    duplicates: list[str] = []
    for upload in pages:
        if upload.content_type is None or not upload.content_type.startswith("image/"):
            raise HTTPException(
                status_code=422,
                detail=f"not an image content-type: {upload.content_type}",
            )
        data = upload.file.read()
        digest = hashlib.sha256(data).hexdigest()
        existing = ldb.conn.execute(
            "SELECT id FROM album_pages WHERE import_id = ? AND content_hash = ?",
            (import_id, digest),
        ).fetchone()
        if existing is not None:
            duplicates.append(digest)
            continue
        ext = _CONTENT_TYPE_EXT.get(
            upload.content_type, upload.content_type.split("/")[-1]
        )
        path = dest_dir / f"{digest}.{ext}"
        if not path.exists():
            path.write_bytes(data)
        with ldb.conn:
            ldb.conn.execute("PRAGMA foreign_keys = ON")
            cur = ldb.conn.execute(
                """
                INSERT INTO album_pages (import_id, seq, content_hash, path)
                VALUES (?, ?, ?, ?)
                """,
                (import_id, next_seq, digest, str(path)),
            )
            page_id = cur.lastrowid
        added.append({"page_id": page_id, "seq": next_seq, "content_hash": digest})
        next_seq += 1

    return {"added": added, "duplicates": duplicates}


@router.get("/albums/imports/{import_id}/pages/{page_id}/image", tags=["albums"])
def get_page_image(import_id: int, page_id: int, ldb: LedgerDep) -> FileResponse:
    row = ldb.conn.execute(
        "SELECT path FROM album_pages WHERE id = ? AND import_id = ?",
        (page_id, import_id),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"page not found: {page_id}")
    path = Path(row["path"])
    if not path.is_file():
        raise HTTPException(status_code=404, detail="page image file missing on disk")
    return FileResponse(path)


# ---------------------------------------------------------------------------
# analysis + human review
# ---------------------------------------------------------------------------

@router.post("/albums/imports/{import_id}/pages/{page_id}/analysis", tags=["albums"])
def post_analysis(
    import_id: int, page_id: int, body: PageAnalysis, ldb: LedgerDep
) -> dict:
    page = ldb.conn.execute(
        "SELECT id FROM album_pages WHERE id = ? AND import_id = ?",
        (page_id, import_id),
    ).fetchone()
    if page is None:
        raise HTTPException(status_code=404, detail=f"page not found: {page_id}")

    century_hint = albums.extract_century_hint(body.page_title or "")
    now = albums._utcnow()
    with ldb.conn:
        ldb.conn.execute("PRAGMA foreign_keys = ON")
        # Idempotent re-analysis: this analysis REPLACES the page's slots.
        ldb.conn.execute("DELETE FROM album_page_slots WHERE page_id = ?", (page_id,))
        for s in body.slots:
            year = s.year
            mint = s.mint
            note = s.note or ""
            # Server-side parse whenever the analyzer left the year null and a
            # label was read -- the analyzer reads text, the server canonicalizes.
            if year is None and s.label_text.strip():
                py, pm, pnote = albums.parse_slot_label(s.label_text, century_hint)
                year, mint = py, pm
                if not note:
                    note = pnote
            ldb.conn.execute(
                """
                INSERT INTO album_page_slots
                    (page_id, slot_index, label_text, year, mint, note,
                     fill_state, confidence, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'vision')
                """,
                (
                    page_id,
                    s.slot_index,
                    s.label_text,
                    year,
                    mint,
                    note,
                    s.fill_state,
                    s.confidence,
                ),
            )
        ldb.conn.execute(
            "UPDATE album_pages SET page_title = ?, page_type = ?, analyzed_at = ? WHERE id = ?",
            (body.page_title, body.page_type, now, page_id),
        )
        ldb.conn.execute(
            """
            UPDATE album_imports SET status = 'analyzed'
            WHERE id = ? AND status IN ('pending', 'analyzed')
            """,
            (import_id,),
        )

    return {
        "page_id": page_id,
        "page_title": body.page_title,
        "page_type": body.page_type,
        "slots": _page_slots(ldb, page_id),
    }


@router.patch("/albums/imports/{import_id}/slots/{slot_id}", tags=["albums"])
def patch_slot(
    import_id: int, slot_id: int, body: SlotPatch, ldb: LedgerDep
) -> dict:
    row = ldb.conn.execute(
        """
        SELECT s.id FROM album_page_slots s
        JOIN album_pages p ON s.page_id = p.id
        WHERE s.id = ? AND p.import_id = ?
        """,
        (slot_id, import_id),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"slot not found: {slot_id}")
    with ldb.conn:
        ldb.conn.execute("PRAGMA foreign_keys = ON")
        ldb.conn.execute(
            "UPDATE album_page_slots SET fill_state = ?, source = 'human' WHERE id = ?",
            (body.fill_state, slot_id),
        )
    slot = ldb.conn.execute(
        """
        SELECT id, slot_index, label_text, year, mint, note, fill_state,
               confidence, source
        FROM album_page_slots WHERE id = ?
        """,
        (slot_id,),
    ).fetchone()
    return {
        "slot_id": slot["id"],
        "slot_index": slot["slot_index"],
        "label_text": slot["label_text"],
        "year": slot["year"],
        "mint": slot["mint"],
        "note": slot["note"],
        "fill_state": slot["fill_state"],
        "confidence": slot["confidence"],
        "source": slot["source"],
    }


# ---------------------------------------------------------------------------
# commit
# ---------------------------------------------------------------------------

@router.post("/albums/imports/{import_id}/commit", tags=["albums"])
def commit_import(import_id: int, body: CommitBody, ldb: LedgerDep) -> dict:
    if (body.manifest_id is None) == (body.custom_name is None):
        raise HTTPException(
            status_code=422,
            detail="provide exactly one of manifest_id or custom_name",
        )
    try:
        return albums.commit_import(
            ldb.conn,
            import_id,
            manifest_id=body.manifest_id,
            custom_name=body.custom_name,
            create_coins=body.create_coins,
            location_label=body.location_label,
            uncertain_policy=body.uncertain_policy,
        )
    except AlbumUncertain as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except AlbumNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AlbumError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _detail(import_id: int, **extra) -> str:
    import json

    payload = {"import_id": import_id}
    payload.update({k: v for k, v in extra.items() if v is not None})
    return json.dumps(payload)
