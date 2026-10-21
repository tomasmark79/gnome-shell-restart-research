#!/usr/bin/env python3
"""Find traced root paths to tagged retired UI in a SpiderMonkey heap dump.

This reads a private diagnostic artifact, never a running process. Weak-map
entries are not promoted to roots; results describe traced paths rather than
claiming that every edge is an independent semantic owner.
"""
import argparse
from collections import deque
import json
from pathlib import Path


def inspect_heap(path):
    nodes, edges, roots = {}, {}, {}
    current = None
    root_section = body = False
    with path.open() as stream:
        for raw in stream:
            line = raw.rstrip('\n')
            if line == '# Roots.':
                root_section = True
                continue
            if line == '# Weak maps.':
                root_section = False
                continue
            if line == '==========':
                body = True
                continue
            if line.startswith('#'):
                continue
            if line.startswith('> '):
                parts = line.split(' ', 3)
                if body and current:
                    edges.setdefault(current, []).append((parts[1], parts[3]))
            elif line.startswith('0x'):
                address, _color, label = line.split(' ', 2)
                if body:
                    nodes[address] = label
                    current = address
                elif root_section:
                    roots[address] = label
    parents = dict.fromkeys(roots)
    queue = deque(roots)
    while queue:
        node = queue.popleft()
        for child, label in edges.get(node, []):
            if child not in parents:
                parents[child] = node, label
                queue.append(child)
    results = []
    for node, children in edges.items():
        for child, label in children:
            if label != '_tgnomeRetirement':
                continue
            tag = nodes.get(child, '').split('> ')[-1]
            route, cursor = [], node
            while parents.get(cursor) is not None:
                previous, edge = parents[cursor]
                route.append({'node': nodes.get(cursor, cursor), 'edge': edge})
                cursor = previous
            results.append({'tag': tag, 'reachable': node in parents,
                            'root': {'address': cursor, 'kind': roots.get(cursor),
                                     'node': nodes.get(cursor),
                                     'scripts': [nodes.get(child) for child, edge
                                                 in edges.get(cursor, [])
                                                 if edge == 'JSFunction script'],
                                     'edges': [label for _, label in edges.get(cursor, [])]},
                            'path': list(reversed(route))})
    return {'nodes': len(nodes), 'edges': sum(map(len, edges.values())),
            'reachableNodes': len(parents), 'retiredUi': results}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('heap', type=Path)
    args = parser.parse_args()
    print(json.dumps(inspect_heap(args.heap), indent=2))
