"""Source-evidence graph traversal for the REFERENCE UI audit."""
from collections import defaultdict, deque
from collections.abc import Iterable, Mapping


def reachable_windows(
    edges: Iterable[Mapping[str, str]], candidates: Iterable[str], roots: Iterable[str],
) -> set[str]:
    """Follow verified source transitions, including cycles, from the supplied roots."""
    candidates = set(candidates)
    graph: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        if edge['status'] == 'verified_cpp' and edge['source_window'] in candidates:
            graph[edge['source_window']].add(edge['target_window'])
    reached = set(roots)
    queue = deque(reached)
    while queue:
        for target in graph.get(queue.popleft(), ()):
            if target not in reached:
                reached.add(target)
                queue.append(target)
    return reached
