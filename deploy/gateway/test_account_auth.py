"""Account bearer attribution: anonymous-compatible and ambiguity-safe."""
import asyncio

from account_auth import (AccountContextMiddleware, account_key_context,
                          current_account_key)


def test_context_binding_is_request_local_and_resets():
    assert current_account_key() is None
    with account_key_context("acct_test_secret"):
        assert current_account_key() == "acct_test_secret"
    assert current_account_key() is None


def _run(headers):
    observed = []

    async def app(scope, receive, send):
        observed.append(current_account_key())

    async def scenario():
        await AccountContextMiddleware(app)(
            {"type": "http", "headers": headers}, lambda: None, lambda _: None)

    asyncio.run(scenario())
    return observed[0]


def test_valid_bearer_is_attributed_without_touching_payload():
    assert _run([(b"authorization", b"Bearer acct_live_abc")]) == "acct_live_abc"


def test_absent_malformed_and_duplicate_headers_stay_anonymous():
    assert _run([]) is None
    assert _run([(b"authorization", b"Basic abc")]) is None
    assert _run([(b"authorization", b"Bearer " + b"x" * 257)]) is None
    assert _run([(b"authorization", b"Bearer key\x00bad")]) is None
    assert _run([(b"authorization", b"Bearer one"),
                 (b"authorization", b"Bearer two")]) is None


def test_concurrent_requests_cannot_leak_bearer_context():
    observed = {}
    both_entered = asyncio.Event()
    entered = 0
    entered_lock = asyncio.Lock()

    async def app(scope, receive, send):
        nonlocal entered
        async with entered_lock:
            entered += 1
            if entered == 2:
                both_entered.set()
        await both_entered.wait()
        await asyncio.sleep(0)
        observed[scope["path"]] = current_account_key()

    middleware = AccountContextMiddleware(app)

    async def request(path, token):
        await middleware(
            {"type": "http", "path": path,
             "headers": [(b"authorization", f"Bearer {token}".encode())]},
            lambda: None, lambda _: None)

    async def scenario():
        await asyncio.gather(request("/one", "key-one"),
                             request("/two", "key-two"))

    asyncio.run(scenario())
    assert observed == {"/one": "key-one", "/two": "key-two"}
    assert current_account_key() is None
