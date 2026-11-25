from datetime import datetime, timezone


def utcnow() -> datetime:
    """Return a naive UTC datetime for compatibility with the existing Prisma DateTime columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
