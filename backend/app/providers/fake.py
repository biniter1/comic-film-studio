"""Deterministic provider for tests: responses come from a callable or a queue per stage."""

from collections.abc import Callable

from app.providers.base import ProviderRequest


class FakeProvider:
    name = "fake"

    def __init__(self, respond: Callable[[ProviderRequest], str]):
        self.respond = respond
        self.calls: list[ProviderRequest] = []

    def generate(self, req: ProviderRequest) -> str:
        self.calls.append(req)
        return self.respond(req)
