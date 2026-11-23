'''What the layers of MaRDMO promise beyond the contracts of lint-imports (docs: Concepts, Architecture).

lint-imports checks which layer uses which ([tool.importlinter] in
pyproject.toml) and that core/ uses neither RDMO nor requests; it cannot
forbid a part of an outside package, so core's database access is checked
here.
'''
import ast
from pathlib import Path

import MaRDMO

PACKAGE = Path(MaRDMO.__file__).parent


def imported(path):
    '''The modules *path* imports (absolute names; relative imports stay MaRDMO's own).'''
    for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            yield node.module


def test_core_uses_no_database():
    uses = sorted(f'{path.relative_to(PACKAGE)}: {module}'
                  for path in (PACKAGE / 'core').rglob('*.py')
                  for module in imported(path)
                  if module == 'django.db' or module.startswith('django.db.'))
    assert uses == []
