"""Voice corpus: list, add, edit, delete, and bulk import past posts."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from postgen.store.corpus import Corpus
from postgen.web.routes.common import ctx, page, redirect

router = APIRouter()
MAX_UPLOAD_BYTES = 512 * 1024


def _corpus(request: Request) -> Corpus:
    return Corpus(ctx(request).settings.corpus_dir)


@router.get("/corpus", response_class=HTMLResponse)
def show_corpus(request: Request, imported: int | None = None) -> HTMLResponse:
    posts = _corpus(request).posts()
    posts.sort(key=lambda p: p.date or "", reverse=True)
    return page(request, "corpus.html", posts=posts, imported=imported)


@router.post("/corpus")
def add_post(
    request: Request, text: Annotated[str, Form()], topic: Annotated[str, Form()] = ""
) -> RedirectResponse:
    if not text.strip():
        raise HTTPException(400, "post text is required")
    _corpus(request).add(text, source="seed", topic=topic.strip() or None)
    return redirect("/corpus")


@router.post("/corpus/import")
async def import_posts(
    request: Request,
    text: Annotated[str, Form()] = "",
    files: Annotated[list[UploadFile], File()] = [],  # noqa: B006 (FastAPI default sentinel)
) -> RedirectResponse:
    corpus = _corpus(request)
    count = corpus.import_text(text) if text.strip() else 0
    for upload in files:
        if not upload.filename:
            continue
        raw = await upload.read(MAX_UPLOAD_BYTES + 1)
        if len(raw) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, f"{upload.filename} is larger than 512 KB")
        content = raw.decode("utf-8", errors="replace")
        if content.strip():
            corpus.import_file(upload.filename, content)
            count += 1
    if count == 0:
        raise HTTPException(400, "nothing to import: paste posts or choose files")
    return redirect(f"/corpus?imported={count}")


@router.post("/corpus/{slug}/edit")
def edit_post(
    request: Request,
    slug: str,
    text: Annotated[str, Form()],
    topic: Annotated[str, Form()] = "",
) -> RedirectResponse:
    if not text.strip():
        raise HTTPException(400, "post text is required")
    try:
        _corpus(request).update(slug, text, topic.strip() or None)
    except KeyError as exc:
        raise HTTPException(404) from exc
    return redirect("/corpus")


@router.post("/corpus/{slug}/delete")
def delete_post(request: Request, slug: str) -> RedirectResponse:
    if not _corpus(request).delete(slug):
        raise HTTPException(404)
    return redirect("/corpus")
