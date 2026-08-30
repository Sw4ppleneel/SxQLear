import { useCallback, useMemo } from 'react'
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  type NodeTypes,
  type Node,
  type Edge,
  useNodesState,
  useEdgesState,
  BackgroundVariant,
  MarkerType,
} from 'reactflow'
import 'reactflow/dist/style.css'
import dagre from 'dagre'
import type { SchemaGraphData, SchemaGraphNode, SchemaGraphEdge, ConfidenceTier } from '@/types'
import { cn } from '@/lib/utils'

// ─── Custom Node: Table ───────────────────────────────────────────────────────

interface TableNodeData {
  label: string
  rowCount?: number
  columnCount: number
  primaryKeys: string[]
  analystNote?: string
  isSelected?: boolean
}

function TableNode({ data }: { data: TableNodeData }) {
  return (
    <div
      className={cn(
        'min-w-[140px] rounded border bg-surface-elevated',
        data.isSelected ? 'border-accent shadow-lg shadow-accent/20' : 'border-surface-border'
      )}
    >
      <div className="border-b border-surface-border px-3 py-1.5">
        <p className="font-mono text-xs font-semibold text-text-primary">{data.label}</p>
        {data.rowCount != null && (
          <p className="text-2xs text-text-muted">
            {data.rowCount.toLocaleString()} rows · {data.columnCount} cols
          </p>
        )}
      </div>
      {data.primaryKeys.length > 0 && (
        <div className="px-3 py-1">
          {data.primaryKeys.map((pk) => (
            <p key={pk} className="text-2xs font-mono text-accent/70">
              🔑 {pk}
            </p>
          ))}
        </div>
      )}
    </div>
  )
}

// ─── Custom Edge: Relationship ────────────────────────────────────────────────

const CONFIDENCE_EDGE_COLORS: Record<ConfidenceTier, string> = {
  certain: '#22c55e',
  high: '#14b8a6',
  medium: '#f59e0b',
  low: '#f97316',
  speculative: '#ef4444',
}

// ─── Schema Graph ─────────────────────────────────────────────────────────────

const NODE_TYPES: NodeTypes = { tableNode: TableNode }

const NODE_WIDTH = 180
const NODE_HEIGHT = 70

/**
 * Hierarchical layout via dagre, keyed off actual FK/relationship edges so the
 * graph reads as a join map rather than an arbitrary grid. Falls back to a
 * grid when there are no edges (e.g. a fresh crawl with no inferred
 * relationships yet), since dagre has nothing to hierarchy-sort in that case.
 */
function layoutNodes(nodes: Node[], edges: Edge[]): Node[] {
  if (edges.length === 0) {
    const COLS = Math.max(1, Math.ceil(Math.sqrt(nodes.length)))
    return nodes.map((node, i) => ({
      ...node,
      position: {
        x: (i % COLS) * (NODE_WIDTH + 60) + 20,
        y: Math.floor(i / COLS) * (NODE_HEIGHT + 90) + 20,
      },
    }))
  }

  const g = new dagre.graphlib.Graph()
  g.setGraph({ rankdir: 'LR', nodesep: 50, ranksep: 110 })
  g.setDefaultEdgeLabel(() => ({}))

  for (const node of nodes) {
    g.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT })
  }
  for (const edge of edges) {
    if (g.hasNode(edge.source) && g.hasNode(edge.target)) {
      g.setEdge(edge.source, edge.target)
    }
  }

  dagre.layout(g)

  return nodes.map((node) => {
    const pos = g.node(node.id)
    if (!pos) return node
    return {
      ...node,
      position: { x: pos.x - NODE_WIDTH / 2, y: pos.y - NODE_HEIGHT / 2 },
    }
  })
}

interface SchemaGraphProps {
  data: SchemaGraphData
  selectedTable?: string | null
  onTableSelect?: (tableName: string) => void
  onRelationshipSelect?: (relationshipId: string) => void
}

export function SchemaGraph({
  data,
  selectedTable,
  onTableSelect,
  onRelationshipSelect,
}: SchemaGraphProps) {
  const baseNodes: Node[] = useMemo(
    () =>
      data.nodes.map((n: SchemaGraphNode) => ({
        id: n.id,
        type: 'tableNode',
        position: n.position,
        data: {
          ...n.data,
          isSelected: n.id === selectedTable,
        },
      })),
    [data.nodes, selectedTable]
  )

  const rfEdges: Edge[] = useMemo(
    () =>
      data.edges.map((e: SchemaGraphEdge) => {
        const color = CONFIDENCE_EDGE_COLORS[e.data.confidence] ?? '#555'
        return {
          id: e.id,
          source: e.source,
          target: e.target,
          animated: e.data.validationStatus === 'pending',
          style: { stroke: color, strokeWidth: e.data.validationStatus === 'confirmed' ? 2 : 1 },
          markerEnd: { type: MarkerType.ArrowClosed, color },
          label: `${e.data.sourceColumn} → ${e.data.targetColumn}`,
          labelStyle: { fontSize: 9, fill: '#888' },
          labelBgStyle: { fill: '#1a1a1a', fillOpacity: 0.85 },
        }
      }),
    [data.edges]
  )

  const rfNodes: Node[] = useMemo(
    () => layoutNodes(baseNodes, rfEdges),
    [baseNodes, rfEdges]
  )

  const [nodes, , onNodesChange] = useNodesState(rfNodes)
  const [edges, , onEdgesChange] = useEdgesState(rfEdges)

  const onNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      onTableSelect?.(node.id)
    },
    [onTableSelect]
  )

  const onEdgeClick = useCallback(
    (_: React.MouseEvent, edge: Edge) => {
      onRelationshipSelect?.(edge.id)
    },
    [onRelationshipSelect]
  )

  if (data.nodes.length === 0) {
    return (
      <div className="flex h-full items-center justify-center text-text-secondary text-sm">
        No schema data yet. Run a crawl to populate the graph.
      </div>
    )
  }

  const isLargeGraph = data.nodes.length > 75

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      onNodeClick={onNodeClick}
      onEdgeClick={onEdgeClick}
      nodeTypes={NODE_TYPES}
      onlyRenderVisibleElements={isLargeGraph}
      fitView
      fitViewOptions={{ padding: 0.2 }}
      className="bg-surface"
    >
      <Background
        variant={BackgroundVariant.Dots}
        gap={20}
        size={1}
        color="#2a2a2a"
      />
      <Controls
        className="!bg-surface-elevated !border-surface-border !text-text-secondary"
      />
      {!isLargeGraph && (
        <MiniMap
          nodeColor="#1a1a1a"
          maskColor="rgba(0,0,0,0.6)"
          style={{ background: '#111', border: '1px solid #2a2a2a' }}
        />
      )}
    </ReactFlow>
  )
}
