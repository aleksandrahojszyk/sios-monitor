from __future__ import annotations

from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

from flask import Flask, abort, redirect, render_template, request, url_for

from src.sios.config import load_settings
from src.sios.storage import Storage

from .models import (
    DEFAULT_PAGE_SIZE,
    QUICK_ACTIONS,
    REVIEW_LABELS,
    REVIEW_NEW,
    REVIEW_STATUSES,
    SOURCE_LABELS,
    InboxQuery,
)
from .query import InboxRepository
from .usability import (
    finish_open_sessions,
    resolve_participant_id,
    start_or_resume_session,
    usability_mode_enabled,
    usability_sqlite_path,
    volunteer_sqlite_path,
)

HIDDEN_RAW_PREFIXES = ("_",)


def create_app(
    storage: Optional[Storage] = None,
    sqlite_path: Optional[Path] = None,
) -> Flask:
    here = Path(__file__).resolve().parent
    app = Flask(
        __name__,
        template_folder=str(here / "templates"),
        static_folder=str(here / "static"),
    )
    app.config["TEMPLATES_AUTO_RELOAD"] = True
    owns_storage = storage is None
    usability_mode = usability_mode_enabled()
    participant_id = None
    session_id = None
    if storage is None:
        if sqlite_path is None and usability_mode:
            sqlite_path = usability_sqlite_path()
            if not sqlite_path.exists():
                raise SystemExit(
                    "Usability dataset missing at {}. "
                    "Run: python -m src.inbox.prepare_usability_dataset".format(
                        sqlite_path
                    )
                )
        path = sqlite_path or load_settings().sqlite_path
        if usability_mode and path.resolve() == volunteer_sqlite_path():
            raise SystemExit(
                "USABILITY_TEST_MODE is on; refusing to open the volunteer "
                "database {}. Use data/usability/inbox.sqlite.".format(path)
            )
        storage = Storage(path)
    if usability_mode:
        participant_id = resolve_participant_id()
        session_id = start_or_resume_session(storage.conn, participant_id)
    repo = InboxRepository(
        storage,
        participant_id=participant_id,
        session_id=session_id,
    )
    app.config["INBOX_STORAGE"] = storage
    app.config["INBOX_REPO"] = repo
    app.config["INBOX_OWNS_STORAGE"] = owns_storage
    app.config["USABILITY_MODE"] = usability_mode
    app.config["PARTICIPANT_ID"] = participant_id
    app.config["USABILITY_SESSION_ID"] = session_id

    @app.teardown_appcontext
    def _close(_exc: Optional[BaseException]) -> None:
        return None

    @app.context_processor
    def _usability_context() -> dict:
        return {
            "usability_mode": usability_mode,
            "participant_id": participant_id,
        }

    def _query_from_request() -> InboxQuery:
        args = request.args
        status = args.get("status", REVIEW_NEW)
        if status in {"", "all"}:
            status = None
        try:
            page = int(args.get("page") or 1)
        except ValueError:
            page = 1
        try:
            page_size = int(args.get("page_size") or DEFAULT_PAGE_SIZE)
        except ValueError:
            page_size = DEFAULT_PAGE_SIZE
        return InboxQuery(
            status=status,
            source=args.get("source") or None,
            authority=args.get("authority") or None,
            document_type=args.get("document_type") or None,
            keyword=args.get("keyword") or None,
            voivodeship=args.get("voivodeship") or None,
            county=args.get("county") or None,
            date_from=args.get("date_from") or None,
            date_to=args.get("date_to") or None,
            q=(args.get("q") or "").strip() or None,
            page=page,
            page_size=page_size,
        )

    def _filter_qs(query: InboxQuery, **overrides: object) -> str:
        values = {
            "status": query.status if query.status is not None else "all",
            "source": query.source,
            "authority": query.authority,
            "document_type": query.document_type,
            "keyword": query.keyword,
            "voivodeship": query.voivodeship,
            "county": query.county,
            "date_from": query.date_from,
            "date_to": query.date_to,
            "q": query.q,
            "page": query.page,
            "page_size": query.page_size,
        }
        values.update(overrides)
        compact = {}
        for key, value in values.items():
            if value is None or value == "":
                continue
            if key == "page" and int(value) == 1:
                continue
            if key == "page_size" and int(value) == DEFAULT_PAGE_SIZE:
                continue
            if key == "status" and value == REVIEW_NEW:
                continue
            compact[key] = value
        return urlencode(compact, doseq=True)

    def _useful_raw(raw_fields: dict) -> list[tuple[str, object]]:
        items = []
        for key, value in raw_fields.items():
            if any(key.startswith(prefix) for prefix in HIDDEN_RAW_PREFIXES):
                continue
            if value in (None, "", [], {}):
                continue
            items.append((key, value))
        return items

    app.jinja_env.globals.update(
        review_labels=REVIEW_LABELS,
        review_statuses=REVIEW_STATUSES,
        quick_actions=QUICK_ACTIONS,
        source_labels=SOURCE_LABELS,
        useful_raw=_useful_raw,
        filter_qs=_filter_qs,
    )

    @app.route("/")
    def inbox():
        query = _query_from_request()
        page = repo.search(query)
        metrics = repo.metrics()
        facets = repo.facets()
        empty_kind = None
        if page.total == 0:
            if metrics.total_cards == 0:
                empty_kind = "none"
            elif query.q:
                empty_kind = "search"
            elif query.status == REVIEW_NEW and not any(
                [
                    query.source,
                    query.authority,
                    query.document_type,
                    query.keyword,
                    query.voivodeship,
                    query.county,
                    query.date_from,
                    query.date_to,
                ]
            ):
                empty_kind = "new"
            else:
                empty_kind = "filter"
        return render_template(
            "inbox.html",
            page=page,
            query=query,
            metrics=metrics,
            facets=facets,
            empty_kind=empty_kind,
        )

    @app.route("/cards/<source_system>/<native_record_id>")
    def card_detail(source_system: str, native_record_id: str):
        card = repo.get_card(source_system, native_record_id)
        if card is None:
            abort(404)
        repo.mark_viewed(source_system, native_record_id)
        query = _query_from_request()
        return render_template(
            "detail.html",
            card=card,
            query=query,
            fragment=False,
        )

    @app.route("/cards/<source_system>/<native_record_id>/fragment")
    def card_fragment(source_system: str, native_record_id: str):
        card = repo.get_card(source_system, native_record_id)
        if card is None:
            abort(404)
        repo.mark_viewed(source_system, native_record_id)
        query = _query_from_request()
        return render_template(
            "detail.html",
            card=card,
            query=query,
            fragment=True,
        )

    @app.route(
        "/cards/<source_system>/<native_record_id>/status",
        methods=["POST"],
    )
    def card_status(source_system: str, native_record_id: str):
        status = request.form.get("status")
        if status not in REVIEW_STATUSES:
            abort(400)
        try:
            repo.set_status(source_system, native_record_id, status)
        except KeyError:
            abort(404)
        next_url = request.form.get("next") or url_for("inbox")
        return redirect(next_url)

    @app.route(
        "/cards/<source_system>/<native_record_id>/note",
        methods=["POST"],
    )
    def card_note(source_system: str, native_record_id: str):
        note = request.form.get("note") or ""
        try:
            repo.set_note(source_system, native_record_id, note)
        except KeyError:
            abort(404)
        next_url = request.form.get("next") or url_for(
            "card_detail",
            source_system=source_system,
            native_record_id=native_record_id,
        )
        return redirect(next_url)

    @app.route("/cards/<source_system>/<native_record_id>/open-source")
    def open_source(source_system: str, native_record_id: str):
        card = repo.get_card(source_system, native_record_id)
        if card is None or not card.source_url:
            abort(404)
        repo.mark_source_opened(
            source_system,
            native_record_id,
            previous_status=card.review_status,
        )
        return redirect(card.source_url)

    if usability_mode:

        @app.route("/usability/finish", methods=["POST"])
        def finish_usability_session():
            finished = finish_open_sessions(
                storage.conn, participant_id=participant_id
            )
            return render_template(
                "usability_finished.html",
                participant_id=participant_id,
                sessions_finished=finished,
            )

    return app


def main() -> None:
    app = create_app()
    app.run(host="127.0.0.1", port=5050, debug=False)


if __name__ == "__main__":
    main()
