"""Regression tests for concurrent lazy initialization of the Gemini client.

The consensus tool dispatches all consultations concurrently via
``asyncio.to_thread`` against ONE cached ``GeminiModelProvider`` (the registry
caches one instance per provider type). If the first-ever Gemini use is a
concurrent panel, every worker thread sees ``_client is None`` and constructs
its own ``genai.Client``, each assignment overwriting the last. An overwritten
wrapper loses its final reference as soon as the winning thread resolves
``.models``, so CPython refcount-GC runs ``genai.Client.__del__`` — which
closes that wrapper's httpx transport while a sibling request is still
in flight on it. The sibling then fails with:

    Cannot send a request, as the client has been closed.

Observed live on 2026-07-20: a 4-model consensus panel with three Gemini
models returned that error for two of them while the third succeeded.
"""

import threading

from providers.gemini import GeminiModelProvider


def test_concurrent_first_client_access_constructs_one_client(monkeypatch):
    """Concurrent first access to ``.client`` must construct exactly one genai.Client."""
    from providers import gemini as gemini_module

    real_client_cls = gemini_module.genai.Client
    constructions = []
    n_workers = 3  # mirrors the observed 3-Gemini consensus panel

    class SlowInitClient(real_client_cls):
        """Real client whose construction is slow enough to expose the race window."""

        def __init__(self, *args, **kwargs):
            constructions.append(None)  # sentinel only: a self-ref would defeat GC
            threading.Event().wait(0.25)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(gemini_module.genai, "Client", SlowInitClient)

    provider = GeminiModelProvider("test-key")
    start = threading.Barrier(n_workers)
    results = [None] * n_workers

    def worker(i):
        start.wait()
        # Mirrors generate_content's access pattern: the Client wrapper
        # reference is transient; only the Models module is retained.
        results[i] = provider.client.models

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert len(constructions) == 1, (
        f"{len(constructions)} genai.Client instances constructed under concurrent "
        "first access; overwritten instances are GC'd and their __del__ closes the "
        "httpx transport out from under sibling in-flight requests"
    )

    # Every worker must hold the same, still-open transport.
    transports = {id(m._api_client._httpx_client) for m in results}
    assert len(transports) == 1
    assert not results[0]._api_client._httpx_client.is_closed
