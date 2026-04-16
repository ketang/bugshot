"""Issue tracker adapters for bugshot workflows."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
MINIMUM_SEARCH_TOKEN_LENGTH = 3
INITIAL_ISSUE_IDENTIFIER = 1


class AttachmentNotSupportedError(RuntimeError):
    """Raised when a tracker backend cannot attach files to issues."""


@dataclass
class TrackerIssue:
    """Represents a tracker issue used for duplicate checks and creation."""

    id: int
    title: str
    body: str
    attachments: list[str]


class IssueTracker:
    """Minimal tracker contract for the standalone CLI."""

    def search_issues(self, query: str) -> list[TrackerIssue]:
        raise NotImplementedError

    def create_issue(self, title: str, body: str) -> TrackerIssue:
        raise NotImplementedError

    def attach_file(self, issue_id: int, file_path: str) -> None:
        raise NotImplementedError


class MockIssueTracker(IssueTracker):
    """File-backed mock tracker for deterministic local runs and tests."""

    def __init__(self, state_path: str):
        self.state_path = state_path
        self.state = self._load_state()

    def search_issues(self, query: str) -> list[TrackerIssue]:
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        matches = []
        for issue in self.state["issues"]:
            haystack = f"{issue['title']} {issue['body']}"
            issue_tokens = self._tokenize(haystack)
            if query_tokens & issue_tokens:
                matches.append(self._to_issue(issue))
        return matches

    def create_issue(self, title: str, body: str) -> TrackerIssue:
        next_issue_id = self._next_issue_id()
        issue = {
            "id": next_issue_id,
            "title": title,
            "body": body,
            "attachments": [],
        }
        self.state["issues"].append(issue)
        self._save_state()
        return self._to_issue(issue)

    def attach_file(self, issue_id: int, file_path: str) -> None:
        if not self.state.get("supports_attachments", True):
            raise AttachmentNotSupportedError("attachments are disabled")

        for issue in self.state["issues"]:
            if issue["id"] == issue_id:
                issue["attachments"].append(os.path.basename(file_path))
                self._save_state()
                return
        raise KeyError(f"issue not found: {issue_id}")

    def _load_state(self) -> dict[str, object]:
        if not os.path.exists(self.state_path):
            return {
                "supports_attachments": True,
                "issues": [],
            }
        with open(self.state_path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    def _save_state(self) -> None:
        with open(self.state_path, "w", encoding="utf-8") as handle:
            json.dump(self.state, handle, indent=2)

    def _next_issue_id(self) -> int:
        if not self.state["issues"]:
            return INITIAL_ISSUE_IDENTIFIER
        return max(issue["id"] for issue in self.state["issues"]) + 1

    def _to_issue(self, issue: dict[str, object]) -> TrackerIssue:
        return TrackerIssue(
            id=issue["id"],
            title=issue["title"],
            body=issue["body"],
            attachments=list(issue.get("attachments", [])),
        )

    def _tokenize(self, text: str) -> set[str]:
        lowered_text = text.lower()
        return {
            token
            for token in TOKEN_PATTERN.findall(lowered_text)
            if len(token) >= MINIMUM_SEARCH_TOKEN_LENGTH
        }

