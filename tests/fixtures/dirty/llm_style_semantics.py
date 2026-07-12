from typing import TypedDict


class NodeData(TypedDict, total=False):
    id: str
    active: bool
    metrics: dict[str, float]


def process_telemetry(
    payload: list[NodeData],
    strict: bool,
    bounds: tuple[float, float, float]
) -> dict[str, list[str]]:
    return {
        node['id']: [
            k for k, v in node.get('metrics', {}).items()
            if (v > bounds[0] if k.startswith('tx_') else (v < bounds[1] if strict else v == bounds[2]))
        ]
        for node in payload
        if 'id' in node and (not strict or node.get('active', False))
    }
