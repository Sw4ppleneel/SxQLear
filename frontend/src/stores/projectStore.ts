import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { Project, SchemaSnapshot, InferredRelationship, ProjectMemorySummary } from '@/types'

interface ProjectState {
  // Active project
  activeProjectId: string | null
  projects: Project[]
  memorySummary: ProjectMemorySummary | null

  // Current schema
  snapshot: SchemaSnapshot | null
  relationships: InferredRelationship[]

  // UI state
  selectedTable: string | null
  selectedRelationshipId: string | null

  // Actions
  setActiveProject: (id: string | null) => void
  setProjects: (projects: Project[]) => void
  addProject: (project: Project) => void
  setSnapshot: (snapshot: SchemaSnapshot | null) => void
  setRelationships: (relationships: InferredRelationship[]) => void
  setMemorySummary: (summary: ProjectMemorySummary | null) => void
  setSelectedTable: (name: string | null) => void
  setSelectedRelationshipId: (id: string | null) => void
  reset: () => void
}

export const useProjectStore = create<ProjectState>()(
  persist(
    (set) => ({
      activeProjectId: null,
      projects: [],
      memorySummary: null,
      snapshot: null,
      relationships: [],
      selectedTable: null,
      selectedRelationshipId: null,

      setActiveProject: (id) => set({ activeProjectId: id, selectedTable: null }),
      setProjects: (projects) => set({ projects }),
      addProject: (project) =>
        set((state) => ({ projects: [project, ...state.projects] })),
      setSnapshot: (snapshot) => set({ snapshot }),
      setRelationships: (relationships) => set({ relationships }),
      setMemorySummary: (summary) => set({ memorySummary: summary }),
      setSelectedTable: (name) => set({ selectedTable: name }),
      setSelectedRelationshipId: (id) => set({ selectedRelationshipId: id }),
      reset: () =>
        set({
          snapshot: null,
          relationships: [],
          memorySummary: null,
          selectedTable: null,
          selectedRelationshipId: null,
        }),
    }),
    {
      name: 'sxqlear-project',
      // Only persist the active project ID — other data is re-fetched from the API
      partialize: (state) => ({ activeProjectId: state.activeProjectId }),
    }
  )
)
