"""Database analyzer — static detection of engine, ORM, migrations, and
schema (ARCHITECTURE.md §11; product spec §11 "Database Intelligence").

V1 scope, honestly stated:

- **Engine** and **ORM/ODM** identity come from dependency-name
  heuristics, reusing the Dependency list the Discovery Engine already
  parsed — no extra file reads needed for that part.
- **Migrations** reuse the Discovery Engine's priority plan
  (``migrations`` bucket) plus an explicit check for ``alembic.ini``.
- **Table/column schema** is extracted for two unambiguous, line-oriented
  declarative formats: SQLAlchemy-style declarative model classes
  (``class X(Base): __tablename__ = ...`` / ``mapped_column`` or
  ``Column`` assignments) and Prisma schema files (``model X { ... }``).
  Django ORM models, Mongoose schemas, and raw SQL migrations are
  identified (engine/ORM) but their columns are **not** parsed in this
  pass — that is a real gap, not a guess, and surfaces honestly via
  ``codeatlas.knowledge.gaps`` when no tables were found.
- The SQLAlchemy detector only recognizes a base class literally named
  ``Base`` or an attribute access ending in ``db.Model`` (Flask-SQLAlchemy).
  A differently-named declarative base will not be detected. This is a
  known heuristic limitation, not a bug.

Nothing here calls an LLM — every finding is CONFIRMED or INFERRED from a
directly observable, static source.
"""

from __future__ import annotations

import itertools
import re

from codeatlas.discovery.engine import DiscoveryContext
from codeatlas.evidence.schema import Evidence, SourceLocation, VerificationStatus
from codeatlas.knowledge.schema import ColumnInfo, DatabaseModel, Finding, TableInfo

_ENGINE_BY_DEPENDENCY = {
    # Python
    "psycopg2": "PostgreSQL",
    "psycopg2-binary": "PostgreSQL",
    "psycopg": "PostgreSQL",
    "asyncpg": "PostgreSQL",
    "pymysql": "MySQL",
    "mysqlclient": "MySQL",
    "mysql-connector-python": "MySQL",
    "pymongo": "MongoDB",
    "mongoengine": "MongoDB",
    "motor": "MongoDB",
    "redis": "Redis",
    # Node
    "pg": "PostgreSQL",
    "mysql2": "MySQL",
    "mysql": "MySQL",
    "mongodb": "MongoDB",
    "mongoose": "MongoDB",
    "ioredis": "Redis",
    "better-sqlite3": "SQLite",
    "sqlite3": "SQLite",
}

_ORM_BY_DEPENDENCY = {
    "sqlalchemy": "SQLAlchemy",
    "peewee": "Peewee",
    "tortoise-orm": "Tortoise ORM",
    "mongoengine": "MongoEngine",
    "mongoose": "Mongoose",
    "typeorm": "TypeORM",
    "sequelize": "Sequelize",
    "prisma": "Prisma",
    "@prisma/client": "Prisma",
}

_MAX_FILES_SCANNED = 300

_SQLALCHEMY_CLASS = re.compile(r"^\s*class\s+(\w+)\s*\(([^)]*)\)\s*:")
_SQLALCHEMY_TABLENAME = re.compile(r"""__tablename__\s*=\s*['"](\w+)['"]""")
_SQLALCHEMY_COLUMN = re.compile(
    r"^\s*(\w+)\s*(?::\s*([\w\[\]\.\"']+))?\s*=\s*(?:mapped_column|Column)\(\s*([^)]*)\)"
)

_PRISMA_MODEL_BLOCK = re.compile(r"model\s+(\w+)\s*\{([^}]*)\}", re.DOTALL)
_PRISMA_FIELD = re.compile(r"^\s*(\w+)\s+([\w\[\]\?]+)(.*)$")


def analyze_database(ctx: DiscoveryContext, walker) -> tuple[DatabaseModel, list[Evidence]]:
    evidence: list[Evidence] = []

    engine = _detect_engine(ctx, evidence)
    orm = _detect_orm(ctx, evidence)
    migrations = _detect_migrations(ctx, evidence)
    tables = _detect_sqlalchemy_tables(ctx, walker, evidence)
    tables += _detect_prisma_tables(ctx, walker, evidence)

    return (
        DatabaseModel(engine=engine, orm=orm, migrations_found=migrations, tables=tables),
        evidence,
    )


def _detect_engine(ctx: DiscoveryContext, evidence: list[Evidence]) -> Finding | None:
    matches: dict[str, object] = {}
    for dep in ctx.result.dependencies:
        engine_name = _ENGINE_BY_DEPENDENCY.get(dep.name.lower())
        if engine_name and engine_name not in matches:
            matches[engine_name] = dep

    if not matches:
        return None

    for engine_name, dep in matches.items():
        evidence.append(
            Evidence(
                finding_id="database:engine",
                source_file=dep.source_file,
                excerpt=f"dependency '{dep.name}' declared",
                reasoning=f"'{dep.name}' is a declared dependency, identifying {engine_name} as a database engine in use.",
                confidence=0.85,
                verification_status=VerificationStatus.CONFIRMED,
                discovered_by="static",
            )
        )

    names = sorted(matches.keys())
    return Finding(
        value=", ".join(names),
        confidence=0.85,
        status=VerificationStatus.CONFIRMED,
        reasoning=f"Identified from database client dependency/dependencies: {', '.join(d.name for d in matches.values())}.",
    )


def _detect_orm(ctx: DiscoveryContext, evidence: list[Evidence]) -> Finding | None:
    dep_by_name = {d.name.lower(): d for d in ctx.result.dependencies}

    for key, orm_name in _ORM_BY_DEPENDENCY.items():
        dep = dep_by_name.get(key)
        if dep is None:
            continue
        ev = Evidence(
            finding_id="database:orm",
            source_file=dep.source_file,
            excerpt=f"dependency '{dep.name}' declared",
            reasoning=f"'{dep.name}' is a declared dependency, identifying {orm_name} as the ORM/ODM in use.",
            confidence=0.85,
            verification_status=VerificationStatus.CONFIRMED,
            discovered_by="static",
        )
        evidence.append(ev)
        return Finding(value=orm_name, confidence=0.85, status=VerificationStatus.CONFIRMED, reasoning=ev.reasoning)

    tech_names = {t.name for t in ctx.result.technology_items}
    if "Django" in tech_names and ctx.priority_plan.migrations:
        migration_file = ctx.priority_plan.migrations[0]
        ev = Evidence(
            finding_id="database:orm",
            source_file=migration_file,
            excerpt="migrations directory present alongside Django",
            reasoning=(
                "Django was detected as the web framework and a migrations directory is "
                "present, which is how Django's built-in ORM manages schema changes. "
                "Inferred, not confirmed: the migrations directory could in principle "
                "belong to a different tool."
            ),
            confidence=0.7,
            verification_status=VerificationStatus.INFERRED,
            discovered_by="static",
        )
        evidence.append(ev)
        return Finding(value="Django ORM", confidence=0.7, status=VerificationStatus.INFERRED, reasoning=ev.reasoning)

    return None


def _detect_migrations(ctx: DiscoveryContext, evidence: list[Evidence]) -> list[str]:
    migration_paths = list(ctx.priority_plan.migrations)
    alembic_ini = next(
        (f.relative_path for f in ctx.tree.files if not f.excluded and f.relative_path.rsplit("/", 1)[-1] == "alembic.ini"),
        None,
    )
    if alembic_ini and alembic_ini not in migration_paths:
        migration_paths.append(alembic_ini)

    if migration_paths:
        evidence.append(
            Evidence(
                finding_id="database:migrations",
                source_file=migration_paths[0],
                excerpt=f"{len(migration_paths)} migration-related file(s) found",
                reasoning=f"Found {len(migration_paths)} file(s) matching migration directory / Alembic config naming conventions.",
                confidence=0.85,
                verification_status=VerificationStatus.CONFIRMED,
                discovered_by="static",
            )
        )
    return migration_paths


def _looks_like_orm_base(bases: str) -> bool:
    return bool(re.search(r"\bBase\b", bases)) or "db.Model" in bases


def _detect_sqlalchemy_tables(ctx: DiscoveryContext, walker, evidence: list[Evidence]) -> list[TableInfo]:
    tables: list[TableInfo] = []
    py_files = (f for f in ctx.tree.readable_files if f.relative_path.endswith(".py"))

    for f in itertools.islice(py_files, _MAX_FILES_SCANNED):
        try:
            text = walker.read_text(f)
        except Exception:
            continue
        lines = text.splitlines()
        i = 0
        while i < len(lines):
            m = _SQLALCHEMY_CLASS.match(lines[i])
            if not m or not _looks_like_orm_base(m.group(2)):
                i += 1
                continue

            class_name = m.group(1)
            class_line = i + 1
            body: list[tuple[int, str]] = []
            indent: int | None = None
            j = i + 1
            while j < len(lines):
                line = lines[j]
                if not line.strip():
                    j += 1
                    continue
                cur_indent = len(line) - len(line.lstrip())
                if indent is None:
                    indent = cur_indent
                if cur_indent < indent:
                    break
                body.append((j + 1, line))
                j += 1

            tablename = class_name.lower()
            columns: list[ColumnInfo] = []
            for lineno, line in body:
                tn = _SQLALCHEMY_TABLENAME.search(line)
                if tn:
                    tablename = tn.group(1)
                col = _SQLALCHEMY_COLUMN.match(line)
                if not col:
                    continue
                col_name, annotation, col_args = col.group(1), col.group(2), col.group(3)
                pk = bool(re.search(r"primary_key\s*=\s*True", col_args))
                fk = re.search(r"ForeignKey\(\s*['\"]([^'\"]+)['\"]", col_args)
                if annotation:
                    col_type = annotation
                else:
                    type_token = re.match(r"^([\w.]+)", col_args)
                    col_type = type_token.group(1) if type_token else None
                columns.append(
                    ColumnInfo(name=col_name, type=col_type, primary_key=pk, foreign_key_to=fk.group(1) if fk else None)
                )

            finding_id = f"database:table:{tablename}:{f.relative_path}"
            status = VerificationStatus.CONFIRMED if columns else VerificationStatus.INFERRED
            evidence.append(
                Evidence(
                    finding_id=finding_id,
                    source_file=f.relative_path,
                    location=SourceLocation(file=f.relative_path, line_start=class_line, symbol=class_name),
                    excerpt=lines[i].strip()[:160],
                    reasoning=(
                        f"SQLAlchemy declarative model class '{class_name}' maps to table "
                        f"'{tablename}' with {len(columns)} column(s) detected."
                    ),
                    confidence=0.9 if columns else 0.55,
                    verification_status=status,
                    discovered_by="static",
                )
            )
            tables.append(TableInfo(name=tablename, columns=columns, source_file=f.relative_path, status=status))
            i = j

    return tables


def _detect_prisma_tables(ctx: DiscoveryContext, walker, evidence: list[Evidence]) -> list[TableInfo]:
    tables: list[TableInfo] = []
    prisma_files = [f for f in ctx.tree.readable_files if f.relative_path.endswith("schema.prisma")]

    for f in prisma_files:
        try:
            text = walker.read_text(f)
        except Exception:
            continue
        for m in _PRISMA_MODEL_BLOCK.finditer(text):
            model_name, body = m.group(1), m.group(2)
            line_start = text[: m.start()].count("\n") + 1

            raw_fields: list[tuple[str, str, str]] = []
            for raw_line in body.splitlines():
                line = raw_line.strip()
                if not line or line.startswith("//") or line.startswith("@@"):
                    continue
                fm = _PRISMA_FIELD.match(line)
                if fm:
                    raw_fields.append((fm.group(1), fm.group(2), fm.group(3)))

            # A `@relation(fields: [x], references: [y])` attribute lives on the
            # virtual relation accessor field (e.g. `author User @relation(...)`),
            # but the real foreign-key *column* is the scalar field named in
            # `fields: [x]` (e.g. `authorId Int`). Map local-field -> target
            # here, then attach it to the scalar column below, not to the
            # virtual accessor itself.
            fk_target_by_local_field: dict[str, str] = {}
            relation_accessor_names: set[str] = set()
            for field_name, field_type, rest in raw_fields:
                rel = re.search(r"@relation\([^)]*fields:\s*\[(\w+)\][^)]*references:\s*\[(\w+)\]", rest)
                if rel:
                    local_field, referenced_field = rel.group(1), rel.group(2)
                    target_model = field_type.rstrip("?[]")
                    fk_target_by_local_field[local_field] = f"{target_model}.{referenced_field}"
                    relation_accessor_names.add(field_name)

            columns: list[ColumnInfo] = []
            for field_name, field_type, rest in raw_fields:
                if field_name in relation_accessor_names or field_type.endswith("[]"):
                    # Virtual relation accessor (owning side) or back-relation
                    # list (inverse side) — neither is a real table column.
                    continue
                columns.append(
                    ColumnInfo(
                        name=field_name,
                        type=field_type,
                        primary_key="@id" in rest,
                        nullable="?" in field_type,
                        foreign_key_to=fk_target_by_local_field.get(field_name),
                    )
                )

            finding_id = f"database:table:{model_name}:{f.relative_path}"
            evidence.append(
                Evidence(
                    finding_id=finding_id,
                    source_file=f.relative_path,
                    location=SourceLocation(file=f.relative_path, line_start=line_start, symbol=model_name),
                    excerpt=f"model {model_name} {{ ... }}",
                    reasoning=f"Prisma schema declares model '{model_name}' with {len(columns)} field(s).",
                    confidence=0.95,
                    verification_status=VerificationStatus.CONFIRMED,
                    discovered_by="static",
                )
            )
            tables.append(
                TableInfo(name=model_name, columns=columns, source_file=f.relative_path, status=VerificationStatus.CONFIRMED)
            )

    return tables
