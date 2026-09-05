"""Фабрики настоящих моделей ядра.

Двойников здесь намеренно нет. Сервисы работают с `SubmissionBundle` и
`Rubric` — теми самыми классами, что отдаёт ingest и читает API, — поэтому
тесты строят их же. Если контракт разъедется, тесты сломаются сразу, а не на
интеграции; двойник в этом месте только маскировал бы расхождение.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from avito_reviewer.ai.content import ArtifactText, build_texts
from avito_reviewer.ai.rubric import Criterion, LatePolicy, Rubric, Scale
from avito_reviewer.distribution import DistributionItem, Reviewer, WorkProfile
from avito_reviewer.ingest import (
    Artifact,
    ArtifactRole,
    ChangeStatus,
    LineRange,
    RepoContext,
    Revision,
    StudentRef,
    SubmissionBundle,
    SubmissionSource,
)

NOW = datetime(2026, 2, 8, 20, 0, tzinfo=UTC)

GO_MAIN = """package main

import (
\t"log"
\t"net/http"
\t"os/signal"
)

func main() {
\tr := chi.NewRouter()
\tr.Get("/ping", handlePing)
\tr.Head("/healthcheck", handleHealth)

\tsignal.Notify(stop, syscall.SIGINT, syscall.SIGTERM)
\t<-stop
\tlog.Println("Shutting down service-courier")
}

func handlePing(w http.ResponseWriter, r *http.Request) {
\tw.WriteHeader(http.StatusOK)
\tw.Write([]byte(`{"message":"pong"}`))
}
"""


def added_diff(text: str) -> str:
    """Дифф файла, добавленного целиком, — ровно то, что отдаёт GitHub на новый файл."""
    lines = text.splitlines()
    return f"@@ -0,0 +1,{len(lines)} @@\n" + "".join(f"+{line}\n" for line in lines)


def artifact(
    path: str,
    *,
    text: str | None = None,
    diff: str | None = None,
    role: ArtifactRole = ArtifactRole.SOLUTION,
    status: ChangeStatus = ChangeStatus.ADDED,
    lang: str | None = "go",
    size_bytes: int | None = None,
    changed: list[tuple[int, int]] | None = None,
    is_binary: bool = False,
) -> Artifact:
    """Артефакт с телом (`excerpt`) или без него — как их отдаёт ingest."""
    body_size = size_bytes if size_bytes is not None else len((text or "").encode())
    return Artifact(
        path=path,
        status=status,
        role=role,
        lang=lang,
        is_binary=is_binary,
        size_bytes=body_size,
        line_count=text.count("\n") + 1 if text else None,
        changed_ranges=[LineRange(start=a, end=b) for a, b in (changed or [])],
        diff=diff if diff is not None else (added_diff(text) if text else None),
        excerpt=text,
        content_ref=f"github:acme/courier@head:{path}",
    )


def partial_artifact(path: str, *, size_bytes: int = 40_000) -> Artifact:
    """Крупный изменённый файл: тела нет, дифф покрывает только ханк.

    Тот самый случай, ради которого существует флаг `partial`: по такому файлу
    нельзя утверждать, что чего-то в нём нет.
    """
    return Artifact(
        path=path,
        status=ChangeStatus.MODIFIED,
        role=ArtifactRole.SOLUTION,
        lang="go",
        size_bytes=size_bytes,
        changed_ranges=[LineRange(start=41, end=42)],
        diff=(
            "@@ -40,3 +40,4 @@ func (s *Store) Get() {\n"
            " \tctx := context.Background()\n"
            "-\told()\n"
            "+\trows, err := s.db.Query(ctx, q)\n"
            "+\tif err != nil {\n"
            " \treturn nil, err\n"
        ),
        content_ref=f"github:acme/courier@head:{path}",
    )


def revision(
    *, minutes_ago: int, added: int, removed: int = 0, ident: str = "c"
) -> Revision:
    return Revision(
        id=f"{ident}{minutes_ago}",
        authored_at=NOW - timedelta(minutes=minutes_ago),
        author_hash="author1",
        summary="work",
        added_lines=added,
        removed_lines=removed,
    )


def go_bundle(**kwargs) -> SubmissionBundle:
    defaults = dict(
        source=SubmissionSource.GITHUB_PR,
        origin_url="https://github.com/acme/courier/pull/7",
        retrieved_at=NOW,
        student_ref=StudentRef(internal_id="stu-1", external_handles={"github": "octocat"}),
        submitted_at=NOW,
        deadline_at=NOW + timedelta(days=1),
        base_ref="b" * 40,
        head_ref="h" * 40,
        artifacts=[artifact("cmd/main.go", text=GO_MAIN, changed=[(1, 24)])],
        revisions=[revision(minutes_ago=90, added=12), revision(minutes_ago=30, added=40)],
        repo=RepoContext(
            root="acme/courier",
            default_branch="main",
            total_files=4,
            files=["cmd/main.go", "go.mod"],
        ),
    )
    defaults.update(kwargs)
    return SubmissionBundle(**defaults)


def go_rubric(**kwargs) -> Rubric:
    defaults = dict(
        assignment_id="go-task1",
        title="Boilerplate сервиса на Go",
        course="Разработка микросервисов на Go",
        scale=Scale(total_max=6, pass_threshold=4, step=0.5),
        late_policy=LatePolicy(grace_days=1, penalty_per_grace_day=1, after_grace="zero"),
        criteria=[
            Criterion(
                id="c1",
                title="Структура проекта",
                max_score=2,
                min_score_for_pass=1,
                checks=["код разделён на cmd/ и internal/"],
            ),
            Criterion(
                id="c2",
                title="Тестовые эндпоинты",
                max_score=2,
                min_score_for_pass=1,
                checks=["GET /ping возвращает 200", "HEAD /healthcheck возвращает 204"],
            ),
            Criterion(
                id="c3",
                title="Корректное завершение",
                max_score=2,
                checks=["в лог пишется Shutting down service-courier"],
            ),
        ],
    )
    defaults.update(kwargs)
    return Rubric(**defaults)


def reviewer(reviewer_id: str = "c-one", **kwargs) -> Reviewer:
    defaults = dict(
        id=reviewer_id,
        name="Антон Круглов",
        skills=["go", "бэкенд"],
        capacity_minutes=600,
        median_minutes_per_work=20.0,
        source="анкета куратора, 02.2026",
    )
    defaults.update(kwargs)
    return Reviewer(**defaults)


def work_profile(**kwargs) -> WorkProfile:
    defaults = dict(
        topics=["gRPC", "graceful shutdown"],
        stack=["go", "docker"],
        complexity=0.4,
        est_review_minutes=30,
    )
    defaults.update(kwargs)
    return WorkProfile(**defaults)


def item(item_id: str = "s1", **kwargs) -> DistributionItem:
    defaults = dict(item_id=item_id, est_review_minutes=30, course_id="go")
    defaults.update(kwargs)
    return DistributionItem(**defaults)


def atext(path: str = "a.go", *, text: str = "", **kwargs) -> ArtifactText:
    """Текст артефакта, доступного целиком, — без похода в резолвер."""
    from avito_reviewer.ai.content import from_artifact

    built = from_artifact(artifact(path, text=text, **kwargs))
    assert built is not None
    return built


def texts_of(bundle: SubmissionBundle, resolver=None) -> list[ArtifactText]:
    """Тексты сдачи тем же путём, которым их получает приложение."""
    return asyncio.run(build_texts(bundle, resolver))
