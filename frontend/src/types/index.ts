// ─── Connection ───────────────────────────────────────────────────────────────

export type DatabaseDialect = 'postgresql' | 'mysql' | 'sqlite' | 'mssql' | 'duckdb'

export interface ConnectionConfig {
  id: string
  name: string
  dialect: DatabaseDialect
  host?: string
  port?: number
  database: string
  username?: string
  ssl_mode?: string
}

export interface ConnectionTestResult {
  success: boolean
  latency_ms?: number
  server_version?: string
  error?: string
}

// ─── Schema ───────────────────────────────────────────────────────────────────

export type ColumnType =
  | 'integer' | 'bigint' | 'float' | 'decimal'
  | 'varchar' | 'text' | 'boolean'
  | 'date' | 'timestamp' | 'json' | 'uuid' | 'bytes' | 'other'

export interface ColumnProfile {
  name: string
  raw_type: string
  normalized_type: ColumnType
  is_nullable: boolean
  is_primary_key: boolean
  is_foreign_key: boolean
  referenced_table?: string
  referenced_column?: string
  has_index: boolean
  row_count?: number
  null_count?: number
  distinct_count?: number
  sample_values: string[]
  analyst_note?: string
  null_rate?: number
  selectivity?: number
}

export interface ForeignKeyConstraint {
  constrained_columns: string[]
  referred_schema?: string
  referred_table: string
  referred_columns: string[]
  name?: string
}

export interface TableProfile {
  name: string
  schema_name?: string
  row_count?: number
  columns: ColumnProfile[]
  primary_keys: string[]
  foreign_key_constraints: ForeignKeyConstraint[]
  index_names: string[]
  analyst_note?: string
  analyst_tags: string[]
}

export interface SchemaSnapshot {
  id: string
  connection_id: string
  project_id: string
  captured_at: string
  version: number
  tables: TableProfile[]
  notes?: string
}

// ─── Relationships ────────────────────────────────────────────────────────────

// ─── Column Search ───────────────────────────────────────────────────────────

export interface ColumnMatch {
  table: string
  column: string
  raw_type: string
  score: number
  reasons: string[]
}

export interface TermSearchResult {
  term: string
  matches: ColumnMatch[]
}

// ─── Manual & LLM Relationships ──────────────────────────────────────────────

export interface ManualRelationshipRequest {
  source_table: string
  source_column: string
  target_table: string
  target_column: string
  relationship_type: 'many-to-one' | 'one-to-one' | 'many-to-many'
  reason?: string
}

export interface SuggestedJoin {
  source_table: string
  source_column: string
  target_table: string
  target_column: string
  relationship_type: string
  reasoning: string
  confidence: string
}

export interface SuggestResponse {
  suggestions: SuggestedJoin[]
  llm_summary: string
  model_used: string
}

// ─── Relationships ────────────────────────────────────────────────────────────

export type SignalType = 'structural' | 'lexical' | 'statistical' | 'semantic' | 'llm' | 'manual'

export type ConfidenceTier = 'certain' | 'high' | 'medium' | 'low' | 'speculative'

export interface SignalEvidence {
  signal_type: SignalType
  score: number
  weight: number
  reasoning: string
  details: Record<string, unknown>
}

export interface InferredRelationship {
  id: string
  source_table: string
  source_column: string
  target_table: string
  target_column: string
  composite_score: number
  confidence: ConfidenceTier
  evidence: SignalEvidence[]
  relationship_type: string
  inferred_at: string
  snapshot_id?: string
}

export type ValidationStatus = 'pending' | 'confirmed' | 'rejected' | 'deferred'

export interface ValidationDecision {
  id: string
  project_id: string
  relationship_id: string
  status: ValidationStatus
  decided_at: string
  analyst_notes?: string
  corrected_source_column?: string
  corrected_target_table?: string
  corrected_target_column?: string
}

// ─── Memory ───────────────────────────────────────────────────────────────────

export type AnnotationTarget = 'table' | 'column' | 'relationship'
export type AnnotationType = 'description' | 'warning' | 'context' | 'assumption' | 'grain'

export interface SemanticAnnotation {
  id: string
  project_id: string
  target_type: AnnotationTarget
  target_identifier: string
  annotation_type: AnnotationType
  text: string
  created_at: string
  updated_at: string
}

export interface Project {
  id: string
  name: string
  description?: string
  connection_id: string
  created_at: string
  updated_at: string
  status: string
  latest_snapshot_id?: string
  validated_relationship_count: number
  confirmed_relationship_count: number
}

export interface ProjectMemorySummary {
  project_id: string
  table_count: number
  total_inferred_relationships: number
  confirmed_relationships: number
  rejected_relationships: number
  pending_relationships: number
  annotation_count: number
  last_crawl_at?: string
  last_validation_at?: string
  analyst_notes?: string
}

// ─── Dataset ──────────────────────────────────────────────────────────────────

export type JoinType = 'INNER' | 'LEFT' | 'RIGHT' | 'FULL'

export interface JoinClause {
  join_type: JoinType
  left_table: string
  left_column: string
  right_table: string
  right_column: string
  relationship_id?: string
  confidence: number
  reasoning: string
}

export interface ColumnSelection {
  table: string
  column: string
  alias?: string
  transformation?: string
  notes?: string
}

export interface FilterCondition {
  table: string
  column: string
  operator: string
  value: unknown
  reasoning?: string
}

export type DatasetPlanStatus = 'draft' | 'verified' | 'deprecated'

export interface DatasetPlan {
  id: string
  project_id: string
  name: string
  description: string
  base_table: string
  joins: JoinClause[]
  selected_columns: ColumnSelection[]
  filters: FilterCondition[]
  assumptions: string[]
  warnings: string[]
  grain_description?: string
  status: DatasetPlanStatus
  created_at: string
  updated_at: string
  generated_sql?: string
  sql_generated_at?: string
}

// ─── Graph (React Flow format) ────────────────────────────────────────────────

export interface SchemaGraphNode {
  id: string
  type: 'tableNode'
  data: {
    label: string
    rowCount?: number
    columnCount: number
    primaryKeys: string[]
    analystNote?: string
  }
  position: { x: number; y: number }
}

export interface SchemaGraphEdge {
  id: string
  source: string
  target: string
  type: 'relationshipEdge'
  data: {
    sourceColumn: string
    targetColumn: string
    compositeScore: number
    confidence: ConfidenceTier
    validationStatus: ValidationStatus
    relationshipType: string
  }
}

export interface SchemaGraphData {
  nodes: SchemaGraphNode[]
  edges: SchemaGraphEdge[]
}

// ─── Validation queue ─────────────────────────────────────────────────────────

export interface ValidationQueueProgress {
  total: number
  decided: number
  pending: number
  confirmed: number
  rejected: number
  completion_pct: number
}

export interface ValidationQueueResponse {
  batch: InferredRelationship[]
  progress: ValidationQueueProgress
}
