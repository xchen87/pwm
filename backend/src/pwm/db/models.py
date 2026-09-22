"""Relational source of truth.

Every row carries `user_id`. Sources are immutable. Assertions are append-only in
content: the only fields that ever change are `review` (user actions only),
`superseded_by_id`, and a commitment's `status`. Deleting a source cascades through
everything derived from it.
"""

from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSON, list[Any]: JSON}


def _id() -> Mapped[UUID]:
    return mapped_column(primary_key=True, default=uuid4)


def _user() -> Mapped[UUID]:
    return mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)


def _now() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = _id()
    email: Mapped[str] = mapped_column(String(320), unique=True)
    name: Mapped[str | None] = mapped_column(String(200))
    # Google's stable account id. Email can change; this cannot.
    google_sub: Mapped[str | None] = mapped_column(String(64), unique=True)
    # Consent, as given at sign-up: which terms, when, and that they attested to being old enough.
    terms_version: Mapped[str | None] = mapped_column(String(32))
    terms_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    age_attested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # "What changed" is measured from the previous visit, not this one.
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    previous_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _now()


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (UniqueConstraint("user_id", "external_id"),)

    id: Mapped[UUID] = _id()
    user_id: Mapped[UUID] = _user()
    external_id: Mapped[str] = mapped_column(String(200))
    # Which connection brought this in, so disconnecting can remove exactly its data.
    connector: Mapped[str] = mapped_column(String(32), default="manual", index=True)
    kind: Mapped[str] = mapped_column(String(32))
    thread_id: Mapped[str | None] = mapped_column(String(200), index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # The normalized record exactly as the connector produced it. With the mock connector
    # this includes the body; Slice 4 replaces stored bodies with on-demand re-fetching.
    record: Mapped[dict[str, Any]]
    route: Mapped[str | None] = mapped_column(String(32))
    suspicious: Mapped[bool] = mapped_column(default=False)
    processed_with: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = _now()


class Person(Base):
    __tablename__ = "people"

    id: Mapped[UUID] = _id()
    user_id: Mapped[UUID] = _user()
    display_name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = _now()

    identifiers: Mapped[list["PersonIdentifier"]] = relationship(
        back_populates="person", cascade="all, delete-orphan"
    )


class PersonIdentifier(Base):
    __tablename__ = "person_identifiers"
    __table_args__ = (UniqueConstraint("user_id", "kind", "value"),)

    id: Mapped[UUID] = _id()
    user_id: Mapped[UUID] = _user()
    person_id: Mapped[UUID] = mapped_column(ForeignKey("people.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32), default="email")
    value: Mapped[str] = mapped_column(String(320))
    # "exact" when the address itself was seen; "inferred" when code linked it to this
    # person; "user" when the user merged or split it, which code never overrides.
    link: Mapped[str] = mapped_column(String(16), default="exact")

    person: Mapped[Person] = relationship(back_populates="identifiers")


class Assertion(Base):
    __tablename__ = "assertions"
    __table_args__ = (
        Index("ix_assertions_user_kind_review", "user_id", "kind", "review"),
        # Identity is where the fact was found, not which extractor found it: a new model or
        # prompt version must meet the user's earlier decision, not create a fresh copy.
        UniqueConstraint(
            "source_id", "kind", "quote_hash", "ordinal", name="uq_assertions_identity"
        ),
    )

    id: Mapped[UUID] = _id()
    user_id: Mapped[UUID] = _user()
    source_id: Mapped[UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(32))
    subject: Mapped[str] = mapped_column(Text)
    predicate: Mapped[str] = mapped_column(String(64))
    value: Mapped[str] = mapped_column(Text)
    evidence_quote: Mapped[str] = mapped_column(Text)
    quote_hash: Mapped[str] = mapped_column(String(64))
    # Distinguishes several facts supported by the same sentence.
    ordinal: Mapped[int] = mapped_column(default=0)
    extraction_method: Mapped[str] = mapped_column(String(64))
    prompt_version: Mapped[str] = mapped_column(String(64))

    origin: Mapped[str] = mapped_column(String(32))
    review: Mapped[str] = mapped_column(String(32), default="unreviewed")
    confidence: Mapped[str] = mapped_column(String(16))

    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = _now()
    superseded_by_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("assertions.id", ondelete="SET NULL")
    )

    commitment_type: Mapped[str | None] = mapped_column(String(16))
    direction: Mapped[str | None] = mapped_column(String(16))
    committed_by: Mapped[str | None] = mapped_column(String(200))
    committed_to: Mapped[str | None] = mapped_column(String(200))
    due: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str | None] = mapped_column(String(16))

    source: Mapped[Source] = relationship()


class AssertionRelation(Base):
    __tablename__ = "assertion_relations"
    __table_args__ = (UniqueConstraint("type", "from_id", "to_id"),)

    id: Mapped[UUID] = _id()
    user_id: Mapped[UUID] = _user()
    type: Mapped[str] = mapped_column(String(16))
    from_id: Mapped[UUID] = mapped_column(ForeignKey("assertions.id", ondelete="CASCADE"))
    to_id: Mapped[UUID] = mapped_column(ForeignKey("assertions.id", ondelete="CASCADE"))
    # "pipeline" relations are rebuilt on every run; "user" relations (corrections) are kept.
    made_by: Mapped[str] = mapped_column(String(16), default="pipeline")


class ReviewEvent(Base):
    """Audit trail of user decisions. The only writer of `Assertion.review`."""

    __tablename__ = "review_events"

    id: Mapped[UUID] = _id()
    user_id: Mapped[UUID] = _user()
    assertion_id: Mapped[UUID] = mapped_column(ForeignKey("assertions.id", ondelete="CASCADE"))
    action: Mapped[str] = mapped_column(String(32))
    detail: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_at: Mapped[datetime] = _now()


class ModelCall(Base):
    """Audit trail of model usage. Token counts and versions only: never content."""

    __tablename__ = "model_calls"

    id: Mapped[UUID] = _id()
    user_id: Mapped[UUID] = _user()
    source_id: Mapped[UUID | None] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))
    stage: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(64))
    prompt_version: Mapped[str] = mapped_column(String(64))
    input_tokens: Mapped[int] = mapped_column(default=0)
    output_tokens: Mapped[int] = mapped_column(default=0)
    cache_read_input_tokens: Mapped[int] = mapped_column(default=0)
    cache_creation_input_tokens: Mapped[int] = mapped_column(default=0)
    cost_usd: Mapped[float] = mapped_column(default=0.0)
    created_at: Mapped[datetime] = _now()


class StageResult(Base):
    """Stored output of a model stage, so re-running the pipeline never re-pays for a call.

    Keyed by source, stage, and prompt version: a new prompt version is a new result.
    """

    __tablename__ = "stage_results"
    __table_args__ = (UniqueConstraint("source_id", "stage", "version"),)

    id: Mapped[UUID] = _id()
    user_id: Mapped[UUID] = _user()
    source_id: Mapped[UUID] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))
    stage: Mapped[str] = mapped_column(String(32))
    version: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict[str, Any]]
    created_at: Mapped[datetime] = _now()


class Job(Base):
    """Work queue, claimed with FOR UPDATE SKIP LOCKED. At most one pending job per user is
    enqueued; processing itself is idempotent and serialized per user."""

    __tablename__ = "jobs"

    id: Mapped[UUID] = _id()
    user_id: Mapped[UUID] = _user()
    kind: Mapped[str] = mapped_column(String(32))
    key: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(default=0)
    run_after: Mapped[datetime] = _now()
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _now()


class Brief(Base):
    """A generated World Brief. Items reference assertions by id; deleting the user removes it."""

    __tablename__ = "briefs"

    id: Mapped[UUID] = _id()
    user_id: Mapped[UUID] = _user()
    period: Mapped[str] = mapped_column(String(16))
    covers_since: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    writer_version: Mapped[str] = mapped_column(String(64))
    items: Mapped[list[Any]]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Notification(Base):
    """In-app inbox and the record of what was pushed. Bodies are generic by rule (threat T8)."""

    __tablename__ = "notifications"

    id: Mapped[UUID] = _id()
    user_id: Mapped[UUID] = _user()
    title: Mapped[str] = mapped_column(String(120))
    deep_link: Mapped[str] = mapped_column(String(200))
    channel: Mapped[str] = mapped_column(String(16))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Insertion order, for "newest first" when timestamps tie (a pinned demo clock does that).
    sequence: Mapped[int] = mapped_column(Integer, Identity(), unique=True)


class ProductEvent(Base):
    """Usage measurement (opened, useful, dismissed...). Names and ids only: never content."""

    __tablename__ = "product_events"

    id: Mapped[UUID] = _id()
    user_id: Mapped[UUID] = _user()
    name: Mapped[str] = mapped_column(String(48), index=True)
    subject_id: Mapped[UUID | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Connection(Base):
    """A data source the user has connected. Disconnecting deletes what it brought in."""

    __tablename__ = "connections"
    __table_args__ = (UniqueConstraint("user_id", "connector"),)

    id: Mapped[UUID] = _id()
    user_id: Mapped[UUID] = _user()
    connector: Mapped[str] = mapped_column(String(32))
    label: Mapped[str] = mapped_column(String(120))
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Opaque to everything but the connector: a timestamp, a Gmail history id, a Calendar
    # sync token, or a backfill page marker.
    cursor: Mapped[str | None] = mapped_column(Text)
    # "ok", "syncing", "needs_reconnect" (the grant was revoked or expired), or "error".
    status: Mapped[str] = mapped_column(String(24), default="ok")
    # Exception class name only, never provider text.
    last_error: Mapped[str | None] = mapped_column(String(64))
    # Pages read so far in a multi-page first read; 0 once caught up.
    pages_synced: Mapped[int] = mapped_column(default=0)
    # Records ingested since the world was last rebuilt from them.
    unprocessed: Mapped[int] = mapped_column(default=0)


class OAuthToken(Base):
    """A Google refresh token, encrypted with the application data key. Never leaves the server."""

    __tablename__ = "oauth_tokens"
    __table_args__ = (UniqueConstraint("user_id", "provider"),)

    id: Mapped[UUID] = _id()
    user_id: Mapped[UUID] = _user()
    provider: Mapped[str] = mapped_column(String(32))
    refresh_token_encrypted: Mapped[str] = mapped_column(Text)
    scopes: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OAuthState(Base):
    """One sign-in attempt in flight. `app_challenge` is the hash of a secret only the app
    that started it holds; it is what ties the end of the flow back to its beginning."""

    __tablename__ = "oauth_states"

    state: Mapped[str] = mapped_column(String(64), primary_key=True)
    code_verifier: Mapped[str] = mapped_column(String(128))
    app_redirect: Mapped[str] = mapped_column(String(300))
    app_challenge: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LoginCode(Base):
    """A single-use, short-lived code handed to the app after sign-in and exchanged for a
    session, so the session token itself never appears in a URL."""

    __tablename__ = "login_codes"

    code_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[UUID] = _user()
    # Redeemable only by whoever holds the secret whose hash this is.
    app_challenge: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ExportCode(Base):
    """A single-use, short-lived code that lets a browser download the user's export without
    a bearer token in the URL."""

    __tablename__ = "export_codes"

    code_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[UUID] = _user()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuthSession(Base):
    """A signed-in device. Only the hash of its token is stored."""

    __tablename__ = "sessions"

    id: Mapped[UUID] = _id()
    user_id: Mapped[UUID] = _user()
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Device(Base):
    """A phone that can receive push. The token is Expo's; it addresses the device, not the
    person, and is dropped the moment Expo reports it dead."""

    __tablename__ = "devices"
    __table_args__ = (UniqueConstraint("user_id", "push_token"),)

    id: Mapped[UUID] = _id()
    user_id: Mapped[UUID] = _user()
    push_token: Mapped[str] = mapped_column(String(200))
    platform: Mapped[str] = mapped_column(String(16))
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
