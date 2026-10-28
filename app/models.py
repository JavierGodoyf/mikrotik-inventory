from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .config import utcnow
from .db import Base


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    host: Mapped[str] = mapped_column(String(255))
    port: Mapped[int] = mapped_column(Integer, default=8728)
    transport: Mapped[str] = mapped_column(String(16), default="api")  # api | api_ssl
    username: Mapped[str] = mapped_column(String(64), default="panel")
    secret: Mapped[str] = mapped_column(String(512))
    verify_tls: Mapped[bool] = mapped_column(Boolean, default=False)

    network: Mapped[str] = mapped_column(String(16), default="lan")  # lan | public
    channel: Mapped[str] = mapped_column(String(16), default="stable")  # stable | long-term
    site: Mapped[str] = mapped_column(String(120), default="")
    tags: Mapped[str] = mapped_column(String(255), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    checks: Mapped[list["Check"]] = relationship(
        back_populates="device",
        cascade="all, delete-orphan",
        order_by="Check.started_at.desc()",
    )


class Check(Base):
    __tablename__ = "checks"

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)

    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    ok: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    identity: Mapped[str | None] = mapped_column(String(120), nullable=True)
    installed_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    architecture: Mapped[str | None] = mapped_column(String(40), nullable=True)
    board_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    platform_name: Mapped[str | None] = mapped_column(String(60), nullable=True)
    channel: Mapped[str | None] = mapped_column(String(20), nullable=True)
    latest_reported: Mapped[str | None] = mapped_column(String(40), nullable=True)

    routerboot_current: Mapped[str | None] = mapped_column(String(40), nullable=True)
    routerboot_upgrade: Mapped[str | None] = mapped_column(String(40), nullable=True)
    firmware_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    free_hdd_kb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uptime: Mapped[str | None] = mapped_column(String(60), nullable=True)

    status: Mapped[str] = mapped_column(String(32), default="unknown", index=True)
    target_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    target_source: Mapped[str | None] = mapped_column(String(20), nullable=True)  # upstream | router
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    routerboot_outdated: Mapped[bool] = mapped_column(Boolean, default=False)

    raw_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    device: Mapped[Device] = relationship(back_populates="checks")


class LatestCache(Base):
    """Última versión publicada por MikroTik para una rama y un canal."""

    __tablename__ = "latest_cache"
    __table_args__ = (UniqueConstraint("line", "channel", name="uq_latest_line_channel"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    line: Mapped[str] = mapped_column(String(4))  # "6" | "7"
    channel: Mapped[str] = mapped_column(String(20))  # stable | long-term
    version: Mapped[str] = mapped_column(String(40))
    released_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
