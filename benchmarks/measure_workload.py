"""Measure the offline workload from the checkout on PYTHONPATH, with SQL call counts."""

import json
import os
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg

from scripts import benchmark_memory as benchmark

_original_database = benchmark.database
_database_calls: dict[str, int] = {}


@contextmanager
def _measured_database(url: str) -> Iterator[tuple[str, str]]:
    with _original_database(url) as (service, api):
        with psycopg.connect(service, autocommit=True) as stats:
            row = stats.execute(
                "select oid from pg_database where datname = current_database()"
            ).fetchone()
            assert row is not None
            database_id = row[0]
        yield service, api
        with psycopg.connect(url, autocommit=True) as admin:
            row = admin.execute(
                "select coalesce(sum(calls), 0), coalesce(sum(calls) filter"
                " (where query ilike 'insert into public.events%%'), 0)"
                " from pg_stat_statements where dbid = %s",
                (database_id,),
            ).fetchone()
            assert row is not None
            _database_calls.update(db_statements=int(row[0]), event_insert_statements=int(row[1]))


def main() -> None:
    url = os.environ["SOMNIA_BENCH_DATABASE_URL"]
    benchmark.database = _measured_database
    for size in (100, 1000, 10000):
        metrics = benchmark.run_case(url, benchmark.history(size), "offline")
        print(json.dumps({"events": size, **metrics, **_database_calls}), flush=True)


if __name__ == "__main__":
    main()
