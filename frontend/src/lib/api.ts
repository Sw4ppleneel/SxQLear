import axios from 'axios'
import type {
  ColumnMatch,
  ConnectionTestResult,
  DatabaseDialect,
  DatasetPlan,
  InferredRelationship,
  ManualRelationshipRequest,
  Project,
  ProjectMemorySummary,
  SchemaGraphData,
  SchemaSnapshot,
  SemanticAnnotation,
  SuggestResponse,
  TermSearchResult,
  ValidationDecision,
  ValidationQueueResponse,
  ValidationStatus,
  AnnotationTarget,
  AnnotationType,
} from '@/types'

const api = axios.create({
  baseURL: '/api/v1',
  headers: { 'Content-Type': 'application/json' },
})

// ─── Connections ──────────────────────────────────────────────────────────────

export const testConnection = async (params: {
  name: string
  dialect: DatabaseDialect
  host?: string
  port?: number
  database: string
  username?: string
  password?: string
}): Promise<ConnectionTestResult> => {
  const { data } = await api.post('/connections/test', params)
  return data
}

// ─── Projects ─────────────────────────────────────────────────────────────────

export const createProject = async (params: {
  name: string
  description?: string
  dialect: DatabaseDialect
  host?: string
  port?: number
  database: string
  username?: string
  password?: string
}): Promise<Project> => {
  const { data } = await api.post('/projects', params)
  return data
}

export const listProjects = async (): Promise<Project[]> => {
  const { data } = await api.get('/projects')
  return data
}

export const getProject = async (projectId: string): Promise<Project> => {
  const { data } = await api.get(`/projects/${projectId}`)
  return data
}

export const getProjectConnection = async (projectId: string): Promise<Partial<ConnectionConfig> & { dialect: DatabaseDialect }> => {
  const { data } = await api.get(`/projects/${projectId}/connection`)
  return data
}

export const updateProject = async (
  projectId: string,
  params: {
    name?: string
    description?: string
    dialect?: DatabaseDialect
    host?: string
    port?: number
    database?: string
    username?: string
    password?: string
    ssl_mode?: string
  }
): Promise<Project> => {
  const { data } = await api.put(`/projects/${projectId}`, params)
  return data
}

export const deleteProject = async (projectId: string): Promise<void> => {
  await api.delete(`/projects/${projectId}`)
}

// ─── Schema ───────────────────────────────────────────────────────────────────

export const crawlSchema = async (
  projectId: string,
  options?: { mode?: 'full' | 'quick' }
): Promise<SchemaSnapshot> => {
  const { data } = await api.post(`/projects/${projectId}/crawl`, options ?? {})
  return data
}

export const cancelCrawl = async (projectId: string): Promise<void> => {
  await api.delete(`/projects/${projectId}/crawl`)
}

export const searchColumns = async (
  projectId: string,
  terms: string[],
  topK = 5,
): Promise<TermSearchResult[]> => {
  const { data } = await api.post(`/projects/${projectId}/columns/search`, {
    terms,
    top_k: topK,
  })
  return data
}

export const getLatestSnapshot = async (projectId: string): Promise<SchemaSnapshot> => {
  const { data } = await api.get(`/projects/${projectId}/snapshots/latest`)
  return data
}

export const getSchemaGraph = async (projectId: string): Promise<SchemaGraphData> => {
  const { data } = await api.get(`/projects/${projectId}/graph`)
  return data
}

// ─── Inference ────────────────────────────────────────────────────────────────

export const runInference = async (
  projectId: string,
  useStatistical = false
): Promise<InferredRelationship[]> => {
  const { data } = await api.post(
    `/projects/${projectId}/inference?use_statistical=${useStatistical}`
  )
  return data
}

export const getRelationships = async (projectId: string): Promise<InferredRelationship[]> => {
  const { data } = await api.get(`/projects/${projectId}/inference`)
  return data
}

export const createManualRelationship = async (
  projectId: string,
  req: ManualRelationshipRequest
): Promise<InferredRelationship> => {
  const { data } = await api.post(`/projects/${projectId}/inference/manual`, req)
  return data
}

export const suggestRelationships = async (
  projectId: string,
  intent: string,
  maxSuggestions = 8,
): Promise<SuggestResponse> => {
  const { data } = await api.post(`/projects/${projectId}/inference/suggest`, {
    intent,
    max_suggestions: maxSuggestions,
  })
  return data
}

// ─── Validation ───────────────────────────────────────────────────────────────

export const getValidationQueue = async (
  projectId: string,
  batchSize = 10
): Promise<ValidationQueueResponse> => {
  const { data } = await api.get(
    `/projects/${projectId}/validation/queue?batch_size=${batchSize}`
  )
  return data
}

export const recordDecision = async (
  projectId: string,
  params: {
    relationship_id: string
    status: ValidationStatus
    analyst_notes?: string
    correction?: Record<string, string>
  }
): Promise<ValidationDecision> => {
  const { data } = await api.post(`/projects/${projectId}/validation/decide`, params)
  return data
}

export const recordBulkDecisions = async (
  projectId: string,
  decisions: Array<{
    relationship_id: string
    status: ValidationStatus
    analyst_notes?: string
  }>
): Promise<{ saved: number }> => {
  const { data } = await api.post(`/projects/${projectId}/validation/decide/bulk`, {
    decisions,
  })
  return data
}

// ─── Memory ───────────────────────────────────────────────────────────────────

export const getMemorySummary = async (projectId: string): Promise<ProjectMemorySummary> => {
  const { data } = await api.get(`/projects/${projectId}/memory/summary`)
  return data
}

export const addAnnotation = async (
  projectId: string,
  params: {
    target_type: AnnotationTarget
    target_identifier: string
    annotation_type: AnnotationType
    text: string
  }
): Promise<SemanticAnnotation> => {
  const { data } = await api.post(`/projects/${projectId}/memory/annotations`, params)
  return data
}

export const getAnnotations = async (
  projectId: string,
  targetIdentifier?: string
): Promise<SemanticAnnotation[]> => {
  const url = targetIdentifier
    ? `/projects/${projectId}/memory/annotations?target_identifier=${encodeURIComponent(targetIdentifier)}`
    : `/projects/${projectId}/memory/annotations`
  const { data } = await api.get(url)
  return data
}

// ─── Datasets ─────────────────────────────────────────────────────────────────

export const buildDatasetPlan = async (
  projectId: string,
  params: {
    name: string
    description: string
    base_table: string
    include_tables: string[]
    grain_description?: string
  }
): Promise<DatasetPlan> => {
  const { data } = await api.post(`/projects/${projectId}/datasets`, params)
  return data
}

export const listDatasetPlans = async (
  projectId: string
): Promise<Array<{ id: string; name: string; status: string; created_at: string }>> => {
  const { data } = await api.get(`/projects/${projectId}/datasets`)
  return data
}

export const getDatasetPlan = async (
  projectId: string,
  planId: string
): Promise<DatasetPlan> => {
  const { data } = await api.get(`/projects/${projectId}/datasets/${planId}`)
  return data
}

export const generateSQL = async (
  projectId: string,
  planId: string
): Promise<{ sql: string }> => {
  const { data } = await api.post(`/projects/${projectId}/datasets/${planId}/generate-sql`)
  return data
}
