from __future__ import annotations

import io
import threading
from pathlib import Path

import pytest

from src.inbox.accounts import AccountError, AccountRepository
from src.inbox.app import create_app
from src.inbox.claims import (
    OUTCOME_ALREADY_YOURS,
    OUTCOME_CLAIMED,
    OUTCOME_NOT_ASSIGNED,
    OUTCOME_NOT_YOURS,
    OUTCOME_RELEASED,
    OUTCOME_TAKEN,
    ClaimRepository,
)
from src.inbox.models import InboxQuery
from src.inbox.query import InboxRepository
from src.inbox.users import main as users_main
from src.sios.storage import Storage
from tests.test_inbox_query import eko_card, sios_card

PASSWORD = "correct horse"


def seeded_storage(path: Path) -> Storage:
    storage = Storage(path)
    storage.upsert_card(sios_card(1001))
    storage.upsert_card(eko_card("77888"))
    return storage


def two_users(storage: Storage):
    accounts = AccountRepository(storage.conn)
    ola = accounts.create_user("ola", "Ola Nowak", PASSWORD)
    jan = accounts.create_user("jan", "Jan Kowalski", PASSWORD)
    return accounts, ola, jan


def signed_in_client(app, username: str):
    client = app.test_client()
    response = client.post(
        "/login", data={"username": username, "password": PASSWORD, "next": "/"}
    )
    assert response.status_code == 302
    return client


def make_app(path: Path):
    storage = seeded_storage(path)
    two_users(storage)
    app = create_app(storage=storage)
    app.config["TESTING"] = True
    return app


def test_account_validation_and_authentication(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "sios.sqlite")
    accounts = AccountRepository(storage.conn)
    user = accounts.create_user("  Ola ", "  Ola   Nowak ", PASSWORD)
    assert user.username == "ola"
    assert user.display_name == "Ola Nowak"
    assert accounts.authenticate("ola", PASSWORD).id == user.id
    assert accounts.authenticate("ola", "wrong password") is None
    assert accounts.authenticate("nobody", PASSWORD) is None
    stored = storage.conn.execute("SELECT password_hash FROM users").fetchone()[0]
    assert PASSWORD not in stored

    with pytest.raises(AccountError):
        accounts.create_user("ola", "Someone Else", PASSWORD)
    with pytest.raises(AccountError):
        accounts.create_user("ola2", "ola nowak", PASSWORD)
    with pytest.raises(AccountError):
        accounts.create_user("x", "Short Username", PASSWORD)
    with pytest.raises(AccountError):
        accounts.create_user("ola3", "", PASSWORD)
    with pytest.raises(AccountError):
        accounts.create_user("ola4", "Weak Password", "short")


def test_users_cli_creates_account_from_stdin(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    db = tmp_path / "sios.sqlite"
    monkeypatch.setattr("sys.stdin", io.StringIO(PASSWORD + "\n"))
    code = users_main(
        [
            "--db", str(db), "create", "ola",
            "--display-name", "Ola Nowak", "--password-stdin",
        ]
    )
    assert code == 0
    assert users_main(["--db", str(db), "list"]) == 0
    assert "ola\tOla Nowak\tactive" in capsys.readouterr().out
    storage = Storage(db)
    assert AccountRepository(storage.conn).authenticate("ola", PASSWORD)
    assert users_main(["--db", str(db), "deactivate", "missing"]) == 1


def test_claim_release_and_single_assignee(tmp_path: Path) -> None:
    storage = seeded_storage(tmp_path / "sios.sqlite")
    _accounts, ola, jan = two_users(storage)
    claims = ClaimRepository(storage.conn)
    inbox = InboxRepository(storage)

    assert inbox.get_card("sios", "1001").assignee_name is None
    first = claims.claim("sios", "1001", ola.id)
    assert first.outcome == OUTCOME_CLAIMED
    assert claims.claim("sios", "1001", ola.id).outcome == OUTCOME_ALREADY_YOURS
    taken = claims.claim("sios", "1001", jan.id)
    assert taken.outcome == OUTCOME_TAKEN
    assert taken.assignee.display_name == "Ola Nowak"
    assert inbox.get_card("sios", "1001").assignee_name == "Ola Nowak"

    refused = claims.release("sios", "1001", jan.id)
    assert refused.outcome == OUTCOME_NOT_YOURS
    assert inbox.get_card("sios", "1001").assignee_user_id == ola.id

    assert claims.release("sios", "1001", ola.id).outcome == OUTCOME_RELEASED
    assert inbox.get_card("sios", "1001").assignee_name is None
    assert claims.release("sios", "1001", ola.id).outcome == OUTCOME_NOT_ASSIGNED
    assert claims.claim("sios", "1001", jan.id).outcome == OUTCOME_CLAIMED

    with pytest.raises(KeyError):
        claims.claim("sios", "9999", ola.id)


def test_claims_do_not_change_triage(tmp_path: Path) -> None:
    storage = seeded_storage(tmp_path / "sios.sqlite")
    _accounts, ola, _jan = two_users(storage)
    inbox = InboxRepository(storage)
    ClaimRepository(storage.conn).claim("sios", "1001", ola.id)

    assert storage.conn.execute("SELECT COUNT(*) FROM card_reviews").fetchone()[0] == 0
    card = inbox.get_card("sios", "1001")
    assert card.review_status == "NEW"
    assert card.reviewed_at is None
    new_page = inbox.search(InboxQuery())
    assert new_page.total == 2
    assert {c.assignee_name for c in new_page.items} == {"Ola Nowak", None}
    assert inbox.metrics().total_new == 2
    inbox.set_status("sios", "1001", "MONITOR")
    assert inbox.get_card("sios", "1001").assignee_name == "Ola Nowak"


def test_deactivating_user_frees_claims(tmp_path: Path) -> None:
    storage = seeded_storage(tmp_path / "sios.sqlite")
    accounts, ola, jan = two_users(storage)
    claims = ClaimRepository(storage.conn)
    claims.claim("sios", "1001", ola.id)
    accounts.set_active("ola", False)
    assert claims.get_assignee("sios", "1001") is None
    assert accounts.authenticate("ola", PASSWORD) is None
    assert claims.claim("sios", "1001", jan.id).outcome == OUTCOME_CLAIMED


def test_concurrent_claims_have_exactly_one_winner(tmp_path: Path) -> None:
    path = tmp_path / "sios.sqlite"
    setup = seeded_storage(path)
    accounts = AccountRepository(setup.conn)
    users = [
        accounts.create_user("user{}".format(i), "User {}".format(i), PASSWORD)
        for i in range(8)
    ]
    for round_number in range(5):
        native_id = "1001"
        setup.conn.execute("DELETE FROM card_claims")
        setup.conn.commit()
        barrier = threading.Barrier(len(users))
        outcomes = {}
        errors = []

        def worker(user) -> None:
            storage = Storage(path)
            try:
                claims = ClaimRepository(storage.conn)
                barrier.wait()
                outcomes[user.id] = claims.claim("sios", native_id, user.id)
            except Exception as exc:  # pragma: no cover - surfaced below
                errors.append(exc)
            finally:
                storage.close()

        threads = [threading.Thread(target=worker, args=(u,)) for u in users]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert not errors
        winners = [u for u in users if outcomes[u.id].outcome == OUTCOME_CLAIMED]
        assert len(winners) == 1, round_number
        for user in users:
            result = outcomes[user.id]
            assert result.assignee.user_id == winners[0].id
            if user is not winners[0]:
                assert result.outcome == OUTCOME_TAKEN
        rows = setup.conn.execute("SELECT user_id FROM card_claims").fetchall()
        assert [row[0] for row in rows] == [winners[0].id]


def test_card_claims_primary_key_blocks_a_second_row(tmp_path: Path) -> None:
    storage = seeded_storage(tmp_path / "sios.sqlite")
    _accounts, ola, jan = two_users(storage)
    storage.conn.execute(
        "INSERT INTO card_claims VALUES ('sios', '1001', ?, 'now')", (ola.id,)
    )
    with pytest.raises(Exception):
        storage.conn.execute(
            "INSERT INTO card_claims VALUES ('sios', '1001', ?, 'now')", (jan.id,)
        )


def test_anonymous_claim_requires_sign_in(tmp_path: Path) -> None:
    app = make_app(tmp_path / "sios.sqlite")
    client = app.test_client()
    page = client.get("/")
    html = page.get_data(as_text=True)
    assert "Claim task" in html
    assert "Sign in" in html
    response = client.post(
        "/cards/sios/1001/claim", data={"next": "/"}
    )
    assert response.status_code == 303
    assert "/login" in response.headers["Location"]
    detail = client.get("/cards/sios/1001").get_data(as_text=True)
    assert "Assigned to" not in detail


def test_login_rejects_bad_credentials_and_external_redirects(tmp_path: Path) -> None:
    app = make_app(tmp_path / "sios.sqlite")
    client = app.test_client()
    bad = client.post("/login", data={"username": "ola", "password": "nope"})
    assert bad.status_code == 401
    assert "not correct" in bad.get_data(as_text=True)
    good = client.post(
        "/login",
        data={"username": "ola", "password": PASSWORD, "next": "https://evil.test/"},
    )
    assert good.status_code == 302
    assert good.headers["Location"] == "/"
    protocol_relative = client.post(
        "/login",
        data={"username": "ola", "password": PASSWORD, "next": "//evil.test/"},
    )
    assert protocol_relative.headers["Location"] == "/"
    client.post("/logout")
    assert "Sign in" in client.get("/").get_data(as_text=True)


def test_claim_is_visible_to_everyone_and_release_is_assignee_only(
    tmp_path: Path,
) -> None:
    app = make_app(tmp_path / "sios.sqlite")
    ola = signed_in_client(app, "ola")
    jan = signed_in_client(app, "jan")
    anonymous = app.test_client()

    claimed = ola.post(
        "/cards/sios/1001/claim", data={"next": "/"}, follow_redirects=True
    )
    html = claimed.get_data(as_text=True)
    assert "You claimed this task." in html
    assert "Assigned to Ola Nowak" in html
    assert "Release task" in html

    for client in (jan, anonymous):
        listing = client.get("/").get_data(as_text=True)
        assert "Assigned to Ola Nowak" in listing
        assert "Release task" not in listing
        detail = client.get("/cards/sios/1001").get_data(as_text=True)
        assert "Assigned to Ola Nowak" in detail
        assert "Release task" not in detail
    # Only the unassigned EkoKarty card still offers a claim.
    assert jan.get("/").get_data(as_text=True).count("Claim task") == 1

    refused = jan.post(
        "/cards/sios/1001/release", data={"next": "/"}, follow_redirects=True
    )
    refused_html = refused.get_data(as_text=True)
    assert "Only Ola Nowak can release this task." in refused_html
    assert "Assigned to Ola Nowak" in refused_html

    released = ola.post(
        "/cards/sios/1001/release", data={"next": "/"}, follow_redirects=True
    )
    released_html = released.get_data(as_text=True)
    assert "You released this task." in released_html
    assert "Assigned to" not in released_html
    assert released_html.count("Claim task") == 2


def test_losing_claim_shows_error_and_current_assignee(tmp_path: Path) -> None:
    app = make_app(tmp_path / "sios.sqlite")
    ola = signed_in_client(app, "ola")
    jan = signed_in_client(app, "jan")
    jan_view = jan.get("/").get_data(as_text=True)
    assert "Claim task" in jan_view
    ola.post("/cards/sios/1001/claim", data={"next": "/"})

    # Jan's page was rendered before Ola claimed; his click now loses.
    lost = jan.post(
        "/cards/sios/1001/claim", data={"next": "/"}, follow_redirects=True
    )
    html = lost.get_data(as_text=True)
    assert "already claimed by Ola Nowak" in html
    assert "Assigned to Ola Nowak" in html
    assert "Assigned to Jan Kowalski" not in html
    detail = jan.get("/cards/sios/1001").get_data(as_text=True)
    assert "Assigned to Ola Nowak" in detail


def test_simultaneous_http_claims_leave_one_assignee(tmp_path: Path) -> None:
    path = tmp_path / "sios.sqlite"
    app_a = make_app(path)
    storage_b = Storage(path)
    app_b = create_app(storage=storage_b)
    app_b.config["TESTING"] = True
    clients = [signed_in_client(app_a, "ola"), signed_in_client(app_b, "jan")]
    barrier = threading.Barrier(2)
    responses = []

    def click(client) -> None:
        barrier.wait()
        responses.append(
            client.post("/cards/sios/1001/claim", data={"next": "/"})
        )

    threads = [threading.Thread(target=click, args=(c,)) for c in clients]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert [r.status_code for r in responses] == [303, 303]
    storage = Storage(path)
    rows = storage.conn.execute("SELECT user_id FROM card_claims").fetchall()
    assert len(rows) == 1
    for client in clients:
        html = client.get("/").get_data(as_text=True)
        assert html.count("Assigned to") == 1


def test_unknown_card_claim_is_404(tmp_path: Path) -> None:
    app = make_app(tmp_path / "sios.sqlite")
    ola = signed_in_client(app, "ola")
    assert ola.post("/cards/sios/404/claim").status_code == 404
    assert ola.post("/cards/sios/404/release").status_code == 404


def test_claim_ui_is_hidden_in_usability_mode(tmp_path: Path, monkeypatch) -> None:
    storage = seeded_storage(tmp_path / "usability.sqlite")
    monkeypatch.setenv("USABILITY_TEST_MODE", "1")
    monkeypatch.setenv("PARTICIPANT_ID", "P01")
    app = create_app(storage=storage)
    app.config["TESTING"] = True
    client = app.test_client()
    html = client.get("/").get_data(as_text=True)
    assert "Claim task" not in html
    assert client.post("/cards/sios/1001/claim").status_code == 404
