'use client';

import type { JsonRecord } from '@/types/api';

export function GraphView({ value, onSelect }: { value: JsonRecord; onSelect: (entity: string) => void }) {
  const nodes = Array.isArray(value.nodes) ? value.nodes as JsonRecord[] : [];
  const edges = Array.isArray(value.edges) ? value.edges as JsonRecord[] : [];
  const positions = new Map(nodes.map((node, index) => [String(node.id), { x: 90 + (index % 4) * 180, y: 70 + Math.floor(index / 4) * 115 }]));
  return <div className="graph-view" aria-label="Evidence relationship graph">
    <svg viewBox="0 0 720 420" role="img">
      {edges.map((edge, index) => { const start = positions.get(String(edge.source_entity_id)); const end = positions.get(String(edge.target_entity_id)); if (!start || !end) return null; return <g key={`${String(edge.id)}-${index}`}><line x1={start.x} y1={start.y} x2={end.x} y2={end.y} stroke="#466183" strokeWidth="2" /><text x={(start.x + end.x) / 2} y={(start.y + end.y) / 2 - 5} fill="#9db0ca" fontSize="9" textAnchor="middle">{String(edge.relationship_type ?? 'related')}</text></g>; })}
      {nodes.map((node, index) => { const point = positions.get(String(node.id)) ?? { x: 90 + index * 40, y: 60 }; return <g key={String(node.id)} className="graph-node" onClick={() => onSelect(String(node.source_id ?? node.id))} tabIndex={0} role="button"><circle cx={point.x} cy={point.y} r="28" fill="#182f50" stroke="#71a9ff" /><text x={point.x} y={point.y - 3} fill="#edf4ff" fontSize="10" textAnchor="middle">{String(node.source_id ?? node.id).slice(0, 14)}</text><text x={point.x} y={point.y + 11} fill="#9db0ca" fontSize="8" textAnchor="middle">{String(node.entity_type ?? '')}</text></g>; })}
    </svg>
    <p className="muted">Click a node to inspect its stored provenance. Edges are rendered only when present in the generated graph artifact.</p>
  </div>;
}
