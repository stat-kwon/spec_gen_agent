"""품질 개선 피드백 추적 유틸리티."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from ..context import WorkflowContext


class FeedbackTracker:
    """품질 개선 피드백의 적용 상태를 추적합니다."""

    STORE_KEY = "applied_feedback"

    def __init__(self, context: WorkflowContext) -> None:
        self.context = context

    # ------------------------------------------------------------------ #
    # 상태 관리
    # ------------------------------------------------------------------ #

    @property
    def store(self) -> Dict[str, List[Dict[str, Any]]]:
        """컨텍스트에 저장된 피드백 상태 저장소를 반환합니다."""

        store = self.context.quality.get(self.STORE_KEY)
        if not isinstance(store, dict):
            store = {}
            self.context.quality[self.STORE_KEY] = store

        for doc, entries in list(store.items()):
            normalized: List[Dict[str, Any]] = []
            if isinstance(entries, list):
                source = entries
            elif isinstance(entries, (set, tuple)):
                source = list(entries)
            elif entries is None:
                source = []
            else:
                source = [entries]

            for item in source:
                if isinstance(item, dict):
                    note = item.get("note")
                    if not note:
                        continue
                    normalized.append(
                        {
                            "note": str(note),
                            "status": item.get("status", "verified"),
                            "iteration": item.get("iteration"),
                            "content_hash": item.get("content_hash"),
                        }
                    )
                else:
                    normalized.append({"note": str(item), "status": "verified"})

            store[doc] = normalized

        return store

    def mark_pending(
        self,
        document: str,
        notes: List[str],
        iteration: int,
        content_hash: str,
    ) -> None:
        """새로운 개선 요청을 pending 상태로 기록합니다."""

        store = self.store
        entries = store.setdefault(document, [])

        for note in notes:
            entries = [
                entry
                for entry in entries
                if not (
                    entry.get("note") == note and entry.get("status") != "verified"
                )
            ]
            entries.append(
                {
                    "note": note,
                    "status": "pending",
                    "iteration": iteration,
                    "content_hash": content_hash,
                }
            )

        store[document] = entries

    def update_with_feedback(
        self,
        feedback_by_doc: Dict[str, List[str]],
    ) -> None:
        """새로운 평가 결과에 맞춰 상태를 갱신합니다."""

        store = self.store

        for doc, entries in list(store.items()):
            remaining_notes = set(feedback_by_doc.get(doc, []) or [])
            updated: List[Dict[str, Any]] = []

            for entry in entries:
                note = entry.get("note")
                if not note:
                    continue

                status = entry.get("status", "pending")

                if status == "pending":
                    if note in remaining_notes:
                        updated.append(entry)
                    else:
                        entry["status"] = "verified"
                        updated.append(entry)
                elif status == "verified":
                    if note in remaining_notes:
                        entry["status"] = "pending"
                        continue
                    updated.append(entry)

            if updated:
                store[doc] = updated
            else:
                store.pop(doc, None)

    def filter_verified(
        self,
        feedback_by_doc: Dict[str, List[str]],
    ) -> Tuple[Dict[str, List[str]], Dict[str, List[str]]]:
        """이미 해결된 피드백을 제외하고 남은 항목과 건너뛴 항목을 반환합니다."""

        store = self.store
        filtered: Dict[str, List[str]] = {}
        skipped: Dict[str, List[str]] = {}

        for doc, notes in feedback_by_doc.items():
            verified_notes = {
                entry.get("note")
                for entry in store.get(doc, [])
                if entry.get("status") == "verified"
            }

            remaining = [note for note in notes if note not in verified_notes]
            removed = [note for note in notes if note in verified_notes]

            if remaining:
                filtered[doc] = remaining
            if removed:
                skipped[doc] = removed

        return filtered, skipped

    def verified_feedback(self) -> Dict[str, List[str]]:
        """검증 완료된 피드백 목록을 반환합니다."""

        store = self.store
        verified: Dict[str, List[str]] = {}

        for doc, entries in store.items():
            notes = [
                entry.get("note")
                for entry in entries
                if entry.get("status") == "verified"
            ]
            if notes:
                verified[doc] = notes

        return verified
