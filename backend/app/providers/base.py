"""Provider abstraction (SPEC §2, §4). Domain code never sees SDK-specific types."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


class ProviderError(Exception):
    """category: transient | quota | invalid_output | permanent"""

    def __init__(self, category: str, message_vi: str, user_action_required: str | None = None):
        super().__init__(message_vi)
        self.category = category
        self.message_vi = message_vi
        self.user_action_required = user_action_required


@dataclass
class ImagePart:
    label: str  # shown to the model right before the image, e.g. "FRAME FR12 (TARGET)"
    path: Path


@dataclass
class ProviderRequest:
    stage: str
    model: str
    system: str
    user_text: str
    images: list[ImagePart] = field(default_factory=list)
    # previous attempts in this conversation: (model_output, feedback) pairs
    history: list[tuple[str, str]] = field(default_factory=list)


class AnalysisProvider(Protocol):
    name: str

    def generate(self, req: ProviderRequest) -> str:
        """Return the raw model text (expected to be JSON). Raise ProviderError on failure."""
        ...
