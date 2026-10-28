from __future__ import annotations

import re
from dataclasses import dataclass
from functools import total_ordering

_VERSION_RE = re.compile(
    r"^(?P<major>\d+)\.(?P<minor>\d+)(?:\.(?P<patch>\d+))?"
    r"(?:(?P<pre>alpha|beta|rc)(?P<pre_num>\d+))?$"
)

_PRE_RANK = {"alpha": 1, "beta": 2, "rc": 3, None: 4}


@total_ordering
@dataclass(frozen=True)
class Version:
    major: int
    minor: int
    patch: int = 0
    pre: str | None = None
    pre_num: int = 0

    @property
    def is_prerelease(self) -> bool:
        return self.pre is not None

    @property
    def major_line(self) -> str:
        return str(self.major)

    def _key(self) -> tuple[int, int, int, int, int]:
        return (self.major, self.minor, self.patch, _PRE_RANK[self.pre], self.pre_num)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return self._key() == other._key()

    def __lt__(self, other: "Version") -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return self._key() < other._key()

    def __str__(self) -> str:
        text = f"{self.major}.{self.minor}"
        if self.patch or (self.minor == 0 and self.major >= 7):
            text += f".{self.patch}"
        if self.pre:
            text += f"{self.pre}{self.pre_num}"
        return text


def parse(value: str | None) -> Version | None:
    """Acepta '7.16.2', '7.16.2 (stable)', '7.26beta4', ' 6.49.23 '."""
    if not value:
        return None
    cleaned = value.strip().split("(")[0].strip().lower().replace(" ", "")
    match = _VERSION_RE.match(cleaned)
    if not match:
        return None
    return Version(
        major=int(match.group("major")),
        minor=int(match.group("minor")),
        patch=int(match.group("patch") or 0),
        pre=match.group("pre"),
        pre_num=int(match.group("pre_num") or 0),
    )


def is_newer(candidate: str | None, reference: str | None) -> bool:
    a, b = parse(candidate), parse(reference)
    if a is None or b is None:
        return False
    return a > b
