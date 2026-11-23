'''SPARQL queries of MaRDMO: the query files (#198).

The queries live as ``.sparql`` files in the packages that use them
(``model/queries/``, ``publication/queries/``, ...); a query too slow for the
portal as one exists only as its parts (``.../split/``).
'''
import os
import re
from functools import lru_cache

# The MaRDMO package: the query files' paths are relative to it
PACKAGE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@lru_cache(maxsize=None)
def get_sparql_query(file_name):
    '''Load and return the contents of a SPARQL query file.

    Result is cached indefinitely after the first read.

    Args:
        file_name: Path relative to the package directory (e.g.
                   ``"model/queries/field.sparql"``).

    Returns:
        Query string (may contain ``{}`` format placeholders).
    '''
    path = os.path.join(PACKAGE_DIR, file_name)
    with open(path, "r", encoding="utf-8") as sparql_file:
        return sparql_file.read()


@lru_cache(maxsize=None)
def get_sparql_query_optional(file_name):
    '''Load a SPARQL query file, returning ``None`` if the file does not exist.

    Result is cached indefinitely after the first read.

    Args:
        file_name: Path relative to the package directory.

    Returns:
        Query string on success; ``None`` when the file is absent.
    '''
    path = os.path.join(PACKAGE_DIR, file_name)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as sparql_file:
        return sparql_file.read()


@lru_cache(maxsize=None)
def get_sparql_query_parts(file_name):
    '''Load the split parts of a SPARQL query file, or return ``None`` if it has none.

    The parts of ``model/queries/task_mardi.sparql`` are
    ``model/queries/split/task_mardi_1.sparql``, ``..._2.sparql`` and so on;
    the query itself exists only as these parts.  Each part has only a few
    OPTIONAL blocks, which the portal answers much faster than one query
    with all of them (see ``model/queries/split/README.md``).
    Result is cached indefinitely after the first read.

    Args:
        file_name: Path of the query relative to the package directory.

    Returns:
        Tuple of query strings in part order, or ``None``.
    '''
    folder, name = os.path.split(file_name)
    stem = os.path.splitext(name)[0]
    split_dir = os.path.join(PACKAGE_DIR, folder, 'split')
    if not os.path.isdir(split_dir):
        return None
    pattern = re.compile(rf'{re.escape(stem)}_(\d+)\.sparql')
    numbers = sorted(
        int(match.group(1))
        for match in map(pattern.fullmatch, os.listdir(split_dir))
        if match
    )
    if not numbers:
        return None
    parts = []
    for number in numbers:
        path = os.path.join(split_dir, f'{stem}_{number}.sparql')
        with open(path, "r", encoding="utf-8") as sparql_file:
            parts.append(sparql_file.read())
    return tuple(parts)
