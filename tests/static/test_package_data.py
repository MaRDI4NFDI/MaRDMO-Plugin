'''The wheel ships every file MaRDMO needs besides its Python modules (package-data in pyproject.toml).

The tests run from the repository, where every file is at hand; a data,
query or template file the package data does not name is missing only
from the installed MaRDMO.  So every file under MaRDMO/ that is not Python
must match a pattern, and every pattern must match a file (a pattern left
from a moved folder would match none).
'''
import tomllib
from pathlib import Path

PACKAGE = Path(__file__).parents[2] / 'MaRDMO'
PATTERNS = tomllib.loads((PACKAGE.parent / 'pyproject.toml').read_text(encoding='utf-8'))[
    'tool']['setuptools']['package-data']['MaRDMO']
# Files for the developers only, not needed by the installed MaRDMO
NOT_SHIPPED = {'model/queries/split/README.md'}


def files():
    '''The files under MaRDMO/ that are not Python, relative to it (hidden files left out).'''
    return {str(path.relative_to(PACKAGE)) for path in PACKAGE.rglob('*')
            if path.is_file() and path.suffix not in ('.py', '.pyc')
            and not any(part.startswith('.') or part == '__pycache__' for part in path.relative_to(PACKAGE).parts)}


def shipped(pattern):
    return {str(path.relative_to(PACKAGE)) for path in PACKAGE.glob(pattern) if path.is_file()}


def test_every_file_is_shipped():
    covered = set().union(*map(shipped, PATTERNS))
    assert sorted(files() - covered - NOT_SHIPPED) == []


def test_every_pattern_names_files():
    assert [pattern for pattern in PATTERNS if not shipped(pattern)] == []


def test_the_files_not_shipped_exist():
    '''An entry of NOT_SHIPPED whose file is gone belongs out of the list.'''
    assert sorted(NOT_SHIPPED - files()) == []
