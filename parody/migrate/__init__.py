"""Migration toolkit: meta-book (System B) repos -> parody content repos.

Consolidates the per-book migrate_from_meta.py scripts that diverged across
the math, engineering-computing, and system-dynamics migrations (each grew
strictly more capable). Book repos keep a thin scripts/migrate_from_meta.py
wrapper plus their re-hash loser list; everything generic lives here.
"""

from .meta_book import MetaBookMigrator, migrate_meta_book
from .rehash import rehash_duplicates

__all__ = ["MetaBookMigrator", "migrate_meta_book", "rehash_duplicates"]
