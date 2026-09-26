"""Parse and harden AI-generated T-SQL before execution.

The AI SQL assistant is a knowledge base over committed warehouse tables
(dbo.Dim* / dbo.Fact*). Staging and reporting views are not allowed here;
report writing uses staging separately.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NoReturn

import sqlglot
from fastapi import HTTPException
from sqlglot import exp

from backend.app.core.settings import get_settings

ALLOWED_FUNCTIONS: frozenset[str] = frozenset(
    {
        "coalesce",
        "nullif",
        "sum",
        "avg",
        "count",
        "min",
        "max",
        "isnull",
        "cast",
        "convert",
        "round",
        "abs",
        "upper",
        "lower",
        "len",
        "substring",
        "datepart",
        "year",
        "month",
    }
)

# sqlglot models AND/OR/CASE (and similar) as Func subclasses — expressions, not calls.
_OPERATOR_FUNC_TYPES: tuple[type, ...] = tuple(
    t
    for t in (
        getattr(exp, "And", None),
        getattr(exp, "Or", None),
        getattr(exp, "Xor", None),
        getattr(exp, "Connector", None),
        getattr(exp, "Case", None),
        getattr(exp, "If", None),
    )
    if t is not None
)

_OPERATOR_FUNC_NAMES: frozenset[str] = frozenset({"and", "or", "xor", "not", "case", "if"})


@dataclass(frozen=True)
class GuardedSql:
    """SQL text approved by the AI SQL guard, plus whether TOP was capped."""

    sql: str
    truncated: bool


def _reject(detail: str) -> NoReturn:
    raise HTTPException(status_code=400, detail=detail)


def _normalize_ref(schema: str | None, name: str | None) -> str | None:
    if not name:
        return None
    table = name.strip().strip("[]").lower()
    if not table:
        return None
    schema_part = (schema or "dbo").strip().strip("[]").lower() or "dbo"
    return f"{schema_part}.{table}"


def is_allowed_warehouse_table(schema: str | None, name: str | None) -> bool:
    """Allow only dbo.Dim* and dbo.Fact* (case-insensitive; includes fact*)."""
    ref = _normalize_ref(schema, name)
    if ref is None:
        return False
    schema_part, _, table = ref.partition(".")
    if schema_part != "dbo":
        return False
    return table.startswith("dim") or table.startswith("fact")


def _cte_names(tree: exp.Expression) -> set[str]:
    names: set[str] = set()
    for cte in tree.find_all(exp.CTE):
        alias = cte.alias
        if alias:
            names.add(str(alias).strip().strip("[]").lower())
        elif cte.alias_or_name:
            names.add(str(cte.alias_or_name).strip().strip("[]").lower())
    return names


def _function_name(node: exp.Func) -> str:
    this = getattr(node, "this", None)
    if isinstance(this, exp.Identifier):
        return str(this.name)
    if isinstance(this, str):
        return this
    sql_name = getattr(node, "sql_name", None)
    if callable(sql_name):
        try:
            return str(sql_name())
        except Exception:
            pass
    return str(node.__class__.__name__)


def _is_sql_function_call(node: exp.Func) -> bool:
    """True for real function calls (SUM, OPENROWSET); False for AND/OR operators."""
    if isinstance(node, _OPERATOR_FUNC_TYPES):
        return False
    name = _function_name(node).lower()
    if name in _OPERATOR_FUNC_NAMES:
        return False
    return True


def _limit_value(select: exp.Select) -> int | None:
    limit = select.args.get("limit")
    if limit is None:
        return None
    expression = limit.args.get("expression") if isinstance(limit, exp.Expression) else None
    if expression is None:
        return None
    try:
        return int(expression.this)
    except (TypeError, ValueError, AttributeError):
        return None


def _apply_top_cap(select: exp.Select, max_rows: int) -> bool:
    """Ensure SELECT has TOP <= max_rows. Returns True if capped/injected."""
    current = _limit_value(select)
    if current is None:
        select.set("limit", exp.Limit(expression=exp.Literal.number(max_rows)))
        return True
    if current > max_rows:
        select.set("limit", exp.Limit(expression=exp.Literal.number(max_rows)))
        return True
    return False


def guard_ai_sql(sql: str, *, max_rows: int | None = None) -> GuardedSql:
    """
    Validate AI SQL as a single Dim/Fact SELECT and inject TOP max_rows when needed.
    """
    cleaned = (sql or "").strip().rstrip(";").strip()
    if not cleaned:
        _reject("Generated SQL is empty.")

    cap = max_rows if max_rows is not None else get_settings().ai_sql_max_rows
    if cap < 1:
        _reject("AI SQL max rows must be at least 1.")

    try:
        trees = sqlglot.parse(cleaned, dialect="tsql")
    except sqlglot.errors.ParseError as exc:
        _reject(f"Generated SQL could not be parsed: {exc}")

    trees = [t for t in trees if t is not None]
    if len(trees) != 1:
        _reject("Only a single SQL statement is allowed.")

    tree = trees[0]
    if not isinstance(tree, exp.Select):
        _reject("Generated SQL must be a SELECT (or WITH ... SELECT) statement.")

    select_tree: exp.Select = tree

    if select_tree.args.get("into") is not None or list(select_tree.find_all(exp.Into)):
        _reject("SELECT INTO is not allowed.")

    for node in select_tree.walk():
        if isinstance(
            node,
            (
                exp.Insert,
                exp.Update,
                exp.Delete,
                exp.Drop,
                exp.Create,
                exp.Alter,
                exp.Command,
                exp.Merge,
                exp.TruncateTable,
            ),
        ):
            _reject("Generated SQL contains a forbidden statement type.")

    for func in select_tree.find_all(exp.Func):
        if not _is_sql_function_call(func):
            continue
        name = _function_name(func).lower()
        if name not in ALLOWED_FUNCTIONS:
            _reject(f"Function '{name}' is not allowed.")

    cte_aliases = _cte_names(select_tree)
    for table in select_tree.find_all(exp.Table):
        raw_name = (table.name or "").strip().strip("[]")
        if not raw_name:
            _reject("Generated SQL references an unsupported table expression.")
        name_l = raw_name.lower()
        if name_l in cte_aliases:
            continue
        if not is_allowed_warehouse_table(table.db, raw_name):
            _reject(
                "Generated SQL may only reference committed warehouse tables "
                "(dbo.Dim* and dbo.Fact*). Staging tables and other objects are not allowed."
            )

    truncated = _apply_top_cap(select_tree, cap)
    guarded = select_tree.sql(dialect="tsql")
    return GuardedSql(sql=guarded, truncated=truncated)
