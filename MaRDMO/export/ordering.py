'''Order of the items of an export: dependency graphs and their cycles.'''
from collections import defaultdict, deque


def topological_order(direct_dependencies: dict[str, set[str]]) -> list[str]:
    '''Return nodes of a dependency graph in topological (creation) order.

    Uses Kahn's algorithm.  Nodes with no dependencies come first; nodes
    that depend on others follow after all their dependencies have been
    emitted.

    Args:
        direct_dependencies: Mapping ``{node: set_of_nodes_it_depends_on}``.

    Returns:
        Ordered list of node names.  If the graph is acyclic the list
        contains every node exactly once.
    '''
    dependents = defaultdict(set)
    in_degree = {}
    for item, deps in direct_dependencies.items():
        in_degree[item] = len(deps)
        for dep in deps:
            dependents[dep].add(item)
    queue = deque(item for item, deg in in_degree.items() if deg == 0)
    order = []
    while queue:
        item = queue.popleft()
        order.append(item)

        for dependent in dependents[item]:
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)
    return order

def cycle_groups(dependencies: dict[str, set[str]]) -> list[list[str]]:
    '''The groups of nodes that depend on each other in a cycle, each sorted, sorted by first node (#164).

    The strongly connected components with more than one node (Tarjan's
    algorithm, iterative: a cycle of thousands of items does not reach the
    recursion limit).  A node that depends on itself is not a group; edges
    to nodes not in *dependencies* are left out.

    Args:
        dependencies: Mapping ``{node: set_of_nodes_it_depends_on}``.
    '''
    index, low, on_stack, stack, groups = {}, {}, set(), [], []
    successors = {node: sorted(dep for dep in deps if dep in dependencies and dep != node)
                  for node, deps in dependencies.items()}
    for root in sorted(dependencies):
        if root in index:
            continue
        work = [(root, 0)]
        while work:
            node, position = work.pop()
            if position == 0:
                index[node] = low[node] = len(index)
                stack.append(node)
                on_stack.add(node)
            if position < len(successors[node]):
                work.append((node, position + 1))
                successor = successors[node][position]
                if successor not in index:
                    work.append((successor, 0))
                elif successor in on_stack:
                    low[node] = min(low[node], index[successor])
                continue
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index[node]:
                group = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    group.append(member)
                    if member == node:
                        break
                if len(group) > 1:
                    groups.append(sorted(group))
    return sorted(groups)


def is_cyclic(dependencies: dict[str, set[str]]) -> bool:
    '''Return ``True`` if the dependency graph contains a cycle (Kahn's algorithm).

    Args:
        dependencies: Mapping ``{node: set_of_nodes_it_depends_on}``.

    Returns:
        ``True`` if a cycle is detected, ``False`` if the graph is a DAG.
    '''
    dependents = defaultdict(set)
    in_degree = {}
    # Build in-degree and reverse edges
    for item, deps in dependencies.items():
        in_degree[item] = len(deps)
        for dep in deps:
            dependents[dep].add(item)
    # Nodes without dependencies
    queue = deque(item for item, deg in in_degree.items() if deg == 0)
    processed = 0
    while queue:
        item = queue.popleft()
        processed += 1
        for dependent in dependents[item]:
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)
    # If not all items were processed → cycle exists
    return processed != len(dependencies)
