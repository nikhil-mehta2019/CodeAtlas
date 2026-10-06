"""Authentication & authorization analyzer — static detection of auth
mechanism, password handling, and authorization model (ARCHITECTURE.md
§12; product spec §12 "Authentication and Authorization Understanding").

V1 scope, honestly stated:

- **Mechanism** (JWT / OAuth2 / session) comes from two independent static
  signals: declared dependency names (reusing the Discovery Engine's
  already-parsed Dependency list, same pattern as
  ``codeatlas.analysis.database``), and a direct code scan for JWT
  encode/decode/sign/verify calls in the files the Discovery Engine's
  priority plan already flagged as auth-related. A dependency-only
  session-management signal (e.g. ``express-session``) is weaker evidence
  that it's the *authentication* mechanism specifically (it could be used
  for CSRF tokens or flash messages only), so it is marked INFERRED unless
  a stronger JWT/OAuth2 signal is also present.
- **Password handling** comes from declared hashing-library dependencies
  or direct calls to well-known hashing functions
  (``generate_password_hash``, ``bcrypt.hash*``, ``argon2.*``).
- **Authorization model** comes from role/permission-check decorators and
  calls found in the same auth-related/controller files. Named roles
  found in those checks imply RBAC (INFERRED, not CONFIRMED — the checks
  are directly observed, but "this constitutes RBAC as a design" is an
  interpretation); unnamed login/permission checks without role names are
  reported as "ad-hoc authorization checks" at UNVERIFIED, which is
  intentionally the weakest status this analyzer ever emits for a
  non-empty finding.
- This is understanding only, matching the spec's explicit V1 scope — no
  active security testing of any kind is performed.

Nothing here calls an LLM. No mechanism/model found → the corresponding
field stays ``None``, which ``codeatlas.knowledge.gaps`` already reports
as an explicit Unknown rather than a guess.
"""

from __future__ import annotations

import itertools
import re

from codeatlas.discovery.engine import DiscoveryContext
from codeatlas.evidence.schema import Evidence, SourceLocation, VerificationStatus
from codeatlas.knowledge.schema import AuthenticationModel, AuthorizationModel, Finding

_MAX_FILES_SCANNED = 200

_JWT_DEPENDENCIES = {
    "pyjwt": "PyJWT",
    "python-jose": "python-jose",
    "jsonwebtoken": "jsonwebtoken",
    "jose": "jose",
    "djangorestframework-simplejwt": "djangorestframework-simplejwt",
    "fastapi-jwt-auth": "fastapi-jwt-auth",
}
_OAUTH_DEPENDENCIES = {
    "authlib": "Authlib",
    "requests-oauthlib": "requests-oauthlib",
    "django-allauth": "django-allauth",
    "passport": "Passport.js",
    "passport-oauth2": "passport-oauth2",
    "next-auth": "NextAuth.js",
}
_SESSION_DEPENDENCIES = {
    "flask-session": "Flask-Session",
    "express-session": "express-session",
    "flask-login": "Flask-Login",
}
_PASSWORD_HASH_DEPENDENCIES = {
    "bcrypt": "bcrypt",
    "bcryptjs": "bcryptjs",
    "passlib": "passlib",
    "argon2-cffi": "argon2",
    "argon2": "argon2",
}

_JWT_CALL_PATTERN = re.compile(r"\bjwt\.(encode|decode|sign|verify)\s*\(")
_PASSWORD_HASH_CALL_PATTERN = re.compile(
    r"\b(generate_password_hash|check_password_hash|bcrypt\.hash(?:Sync)?|"
    r"bcrypt\.compare(?:Sync)?|bcrypt\.hashpw|bcrypt\.checkpw|argon2\.hash|argon2\.verify)\s*\("
)
_PY_ROLE_DECORATOR = re.compile(
    r"@(login_required|role_required|requires_role|roles_allowed|permission_required)"
    r"(?:\(\s*['\"]([\w\-]+)['\"]\s*\))?"
)
_JS_ROLE_CHECK = re.compile(r"(?:requireRole|checkRole|hasRole)\(\s*['\"](\w+)['\"]\s*\)")


def analyze_authentication(
    ctx: DiscoveryContext, walker
) -> tuple[AuthenticationModel, AuthorizationModel, list[Evidence]]:
    evidence: list[Evidence] = []

    categories: set[str] = set()
    categories |= _match_dependency_categories(ctx, _JWT_DEPENDENCIES, "JWT", evidence)
    categories |= _match_dependency_categories(ctx, _OAUTH_DEPENDENCIES, "OAuth2", evidence)
    categories |= _match_dependency_categories(ctx, _SESSION_DEPENDENCIES, "Session", evidence)

    for path, lineno, line in _scan_candidate_files(ctx, walker, _JWT_CALL_PATTERN):
        categories.add("JWT")
        evidence.append(
            Evidence(
                finding_id="authentication:mechanism",
                source_file=path,
                location=SourceLocation(file=path, line_start=lineno, line_end=lineno),
                excerpt=line.strip()[:160],
                reasoning=f"JWT encode/decode/sign/verify call found at {path}:{lineno}.",
                confidence=0.85,
                verification_status=VerificationStatus.CONFIRMED,
                discovered_by="static",
            )
        )

    mechanism = _build_mechanism_finding(categories)
    password_handling, pw_evidence = _detect_password_handling(ctx, walker)
    evidence += pw_evidence

    token_handling = None
    if "JWT" in categories:
        token_handling = (
            "JWT-based tokens observed (see authentication:mechanism evidence); "
            "expiry/refresh/signing-key behavior was not independently verified in this pass."
        )

    authentication = AuthenticationModel(
        mechanism=mechanism,
        token_handling=token_handling,
        password_handling=password_handling,
    )

    authorization, authz_evidence = _detect_authorization(ctx, walker)
    evidence += authz_evidence

    return authentication, authorization, evidence


def _match_dependency_categories(
    ctx: DiscoveryContext, dep_map: dict[str, str], category_label: str, evidence: list[Evidence]
) -> set[str]:
    found: set[str] = set()
    for dep in ctx.result.dependencies:
        lib_name = dep_map.get(dep.name.lower())
        if lib_name is None:
            continue
        found.add(category_label)
        evidence.append(
            Evidence(
                finding_id="authentication:mechanism",
                source_file=dep.source_file,
                excerpt=f"dependency '{dep.name}' declared",
                reasoning=f"'{dep.name}' is a declared dependency, identifying {category_label}-based authentication ({lib_name}).",
                confidence=0.85,
                verification_status=VerificationStatus.CONFIRMED,
                discovered_by="static",
            )
        )
    return found


def _build_mechanism_finding(categories: set[str]) -> Finding | None:
    if not categories:
        return None
    strong_signal = bool(categories & {"JWT", "OAuth2"})
    status = VerificationStatus.CONFIRMED if strong_signal else VerificationStatus.INFERRED
    confidence = 0.85 if strong_signal else 0.6
    reasoning = (
        f"Identified from {', '.join(sorted(categories))}-related dependency and/or code signals."
        if strong_signal
        else (
            f"Only a session-management dependency signal was found ({', '.join(sorted(categories))}); "
            "this is weaker evidence than a JWT/OAuth2 library because session middleware can be used "
            "for things other than authentication (e.g. CSRF tokens, flash messages)."
        )
    )
    return Finding(value=", ".join(sorted(categories)), confidence=confidence, status=status, reasoning=reasoning)


def _detect_password_handling(ctx: DiscoveryContext, walker) -> tuple[str | None, list[Evidence]]:
    evidence: list[Evidence] = []
    for dep in ctx.result.dependencies:
        lib_name = _PASSWORD_HASH_DEPENDENCIES.get(dep.name.lower())
        if lib_name is None:
            continue
        evidence.append(
            Evidence(
                finding_id="authentication:password_handling",
                source_file=dep.source_file,
                excerpt=f"dependency '{dep.name}' declared",
                reasoning=f"'{dep.name}' is a declared dependency, indicating passwords are hashed with {lib_name}.",
                confidence=0.85,
                verification_status=VerificationStatus.CONFIRMED,
                discovered_by="static",
            )
        )
        return f"Hashed using {lib_name} (dependency declared in {dep.source_file}).", evidence

    hits = _scan_candidate_files(ctx, walker, _PASSWORD_HASH_CALL_PATTERN)
    if hits:
        path, lineno, line = hits[0]
        evidence.append(
            Evidence(
                finding_id="authentication:password_handling",
                source_file=path,
                location=SourceLocation(file=path, line_start=lineno, line_end=lineno),
                excerpt=line.strip()[:160],
                reasoning=f"Password hashing call found at {path}:{lineno}.",
                confidence=0.75,
                verification_status=VerificationStatus.CONFIRMED,
                discovered_by="static",
            )
        )
        return f"Hashing call observed at {path}:{lineno} (see evidence).", evidence

    return None, evidence


def _detect_authorization(ctx: DiscoveryContext, walker) -> tuple[AuthorizationModel, list[Evidence]]:
    evidence: list[Evidence] = []
    roles: set[str] = set()
    protected_endpoints: list[str] = []

    for path, lineno, line in _scan_candidate_lines(ctx, walker):
        py_match = _PY_ROLE_DECORATOR.search(line)
        js_match = _JS_ROLE_CHECK.search(line)
        if not py_match and not js_match:
            continue

        role_name = py_match.group(2) if py_match else js_match.group(1)
        if role_name:
            roles.add(role_name)
        location = f"{path}:{lineno}"
        protected_endpoints.append(location)
        evidence.append(
            Evidence(
                finding_id="authorization:model",
                source_file=path,
                location=SourceLocation(file=path, line_start=lineno, line_end=lineno),
                excerpt=line.strip()[:160],
                reasoning=(
                    f"Role/permission check found at {location}"
                    + (f" for role '{role_name}'" if role_name else " (no specific role named)")
                    + "."
                ),
                confidence=0.8 if role_name else 0.6,
                verification_status=VerificationStatus.CONFIRMED if role_name else VerificationStatus.INFERRED,
                discovered_by="static",
            )
        )

    model = None
    if roles:
        model = Finding(
            value="RBAC (role-based)",
            confidence=0.75,
            status=VerificationStatus.INFERRED,
            reasoning=(
                f"Found {len(roles)} distinct named role(s) referenced in permission checks: "
                f"{', '.join(sorted(roles))}. The checks themselves are directly observed; "
                "classifying this as an RBAC design is an interpretation, not a confirmed fact."
            ),
        )
    elif protected_endpoints:
        model = Finding(
            value="Ad-hoc authorization checks",
            confidence=0.5,
            status=VerificationStatus.UNVERIFIED,
            reasoning=(
                f"Found {len(protected_endpoints)} permission/login check(s) without a clearly named "
                "role model — too little signal to classify the authorization design with confidence."
            ),
        )

    return AuthorizationModel(model=model, roles=sorted(roles), protected_endpoints=protected_endpoints), evidence


def _candidate_auth_paths(ctx: DiscoveryContext) -> list[str]:
    seen: set[str] = set()
    paths: list[str] = []
    for p in itertools.chain(ctx.priority_plan.auth, ctx.priority_plan.controllers_routes, ctx.priority_plan.entry_points):
        if p not in seen:
            seen.add(p)
            paths.append(p)
    return paths


def _iter_candidate_lines(ctx: DiscoveryContext, walker):
    """Yield (relative_path, lineno, line) for every line in every
    auth/controller/entry-point candidate file, up to the scan cap."""
    files_by_path = {f.relative_path: f for f in ctx.tree.readable_files}

    for path in itertools.islice(_candidate_auth_paths(ctx), _MAX_FILES_SCANNED):
        f = files_by_path.get(path)
        if f is None or not f.relative_path.endswith((".py", ".js", ".ts")):
            continue
        try:
            text = walker.read_text(f)
        except Exception:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            yield f.relative_path, lineno, line


def _scan_candidate_files(ctx: DiscoveryContext, walker, pattern: re.Pattern) -> list[tuple[str, int, str]]:
    return [(p, n, line) for p, n, line in _iter_candidate_lines(ctx, walker) if pattern.search(line)]


def _scan_candidate_lines(ctx: DiscoveryContext, walker) -> list[tuple[str, int, str]]:
    return [
        (p, n, line)
        for p, n, line in _iter_candidate_lines(ctx, walker)
        if _PY_ROLE_DECORATOR.search(line) or _JS_ROLE_CHECK.search(line)
    ]
