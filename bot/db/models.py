from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class GuildSettings(Base):
    __tablename__ = "guild_settings"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    default_volume: Mapped[int] = mapped_column(Integer, default=75)
    dj_role_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    music_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    vote_skip_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    twenty_four_seven: Mapped[bool] = mapped_column(Boolean, default=False)
    prefix_note: Mapped[str | None] = mapped_column(String(255), nullable=True)
