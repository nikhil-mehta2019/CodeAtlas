"""M7 sanity tests: database analyzer (engine, ORM, migrations, schema).

Covers the three required status behaviors per .claude/skills/build-analyzer:
  - a CONFIRMED finding backed by static evidence (SQLAlchemy/Prisma tables,
    engine/ORM from declared dependencies),
  - an ambiguous case that comes back INFERRED, not CONFIRMED (Django ORM
    guessed from framework + migrations dir, with no explicit ORM dependency),
  - no fabricated finding when there is no signal at all.
"""

from __future__ import annotations

from pathlib import Path

from codeatlas.analysis.database import analyze_database
from codeatlas.discovery.engine import DiscoveryContext, DiscoveryEngine
from codeatlas.evidence.schema import VerificationStatus
from codeatlas.repository.walker import RepositoryWalker

FIXTURES = Path(__file__).parent.parent / "fixtures" / "sample_repos"


def _discover(name: str) -> tuple[DiscoveryContext, RepositoryWalker]:
    ctx = DiscoveryEngine().discover(str(FIXTURES / name))
    walker = RepositoryWalker(FIXTURES / name)
    return ctx, walker


def test_sqlalchemy_tables_detected_as_confirmed_with_evidence():
    ctx, walker = _discover("python_fastapi")
    db_model, evidence = analyze_database(ctx, walker)

    table_names = {t.name for t in db_model.tables}
    assert {"users", "posts"} <= table_names

    users_table = next(t for t in db_model.tables if t.name == "users")
    assert users_table.status == VerificationStatus.CONFIRMED
    col_names = {c.name for c in users_table.columns}
    assert {"id", "email"} <= col_names
    id_col = next(c for c in users_table.columns if c.name == "id")
    assert id_col.primary_key is True

    posts_table = next(t for t in db_model.tables if t.name == "posts")
    author_col = next(c for c in posts_table.columns if c.name == "author_id")
    assert author_col.foreign_key_to == "users.id"

    # Every table-level finding must trace back to static evidence.
    table_evidence = [e for e in evidence if e.finding_id.startswith("database:table:")]
    assert table_evidence
    assert all(e.discovered_by == "static" for e in table_evidence)
    assert all(e.verification_status == VerificationStatus.CONFIRMED for e in table_evidence)


def test_sqlalchemy_engine_and_orm_confirmed_from_dependencies():
    ctx, walker = _discover("python_fastapi")
    db_model, evidence = analyze_database(ctx, walker)

    assert db_model.orm is not None
    assert db_model.orm.value == "SQLAlchemy"
    assert db_model.orm.status == VerificationStatus.CONFIRMED

    assert db_model.migrations_found  # alembic.ini + migrations/ dir
    migration_evidence = [e for e in evidence if e.finding_id == "database:migrations"]
    assert migration_evidence
    assert migration_evidence[0].verification_status == VerificationStatus.CONFIRMED


def test_prisma_schema_detected_as_confirmed():
    ctx, walker = _discover("node_express")
    db_model, evidence = analyze_database(ctx, walker)

    assert db_model.engine is not None
    assert "PostgreSQL" in db_model.engine.value
    assert db_model.engine.status == VerificationStatus.CONFIRMED

    assert db_model.orm is not None
    assert db_model.orm.value == "Prisma"

    table_names = {t.name for t in db_model.tables}
    assert {"User", "Post"} <= table_names

    user_table = next(t for t in db_model.tables if t.name == "User")
    assert not any(c.name == "posts" for c in user_table.columns)  # back-relation list excluded, not a column

    post_table = next(t for t in db_model.tables if t.name == "Post")
    assert not any(c.name == "author" for c in post_table.columns)  # virtual relation accessor excluded
    author_fk_col = next(c for c in post_table.columns if c.name == "authorId")
    assert author_fk_col.foreign_key_to == "User.id"  # resolved from @relation(fields: [authorId], references: [id])
    assert all(t.status == VerificationStatus.CONFIRMED for t in db_model.tables)


def test_no_fabricated_findings_when_no_signal(tmp_path):
    empty_repo = tmp_path / "empty_repo"
    (empty_repo / "src").mkdir(parents=True)
    (empty_repo / "src" / "util.py").write_text("def add(a, b):\n    return a + b\n")

    ctx = DiscoveryEngine().discover(str(empty_repo))
    walker = RepositoryWalker(empty_repo)
    db_model, evidence = analyze_database(ctx, walker)

    assert db_model.engine is None
    assert db_model.orm is None
    assert db_model.tables == []
    assert db_model.migrations_found == []
    assert evidence == []


def test_django_orm_inferred_not_confirmed_without_explicit_dependency():
    ctx, walker = _discover("python_fastapi")

    # Simulate a Django-flavored project signal (framework detected, migrations present,
    # no explicit ORM dependency) without needing a dedicated fixture repo.
    class _FakeTech:
        def __init__(self, name):
            self.name = name

    ctx.result.technology_items = [t for t in ctx.result.technology_items if t.name != "FastAPI"]
    ctx.result.technology_items.append(_FakeTech("Django"))
    ctx.result.dependencies = [d for d in ctx.result.dependencies if d.name != "sqlalchemy"]

    db_model, evidence = analyze_database(ctx, walker)

    assert db_model.orm is not None
    assert db_model.orm.value == "Django ORM"
    assert db_model.orm.status == VerificationStatus.INFERRED
    assert db_model.orm.confidence < 0.85  # lower confidence than an explicit dependency match
