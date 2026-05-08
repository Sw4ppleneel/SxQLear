import React from 'react'
import { NavLink, useParams } from 'react-router-dom'
import { cn } from '@/lib/utils'
import {
  Database,
  GitBranch,
  CheckSquare,
  Brain,
  Table2,
  Home,
} from 'lucide-react'
import { useProjectStore } from '@/stores/projectStore'

interface NavItem {
  to: string
  label: string
  icon: React.ReactNode
  requiresProject?: boolean
}

export function Sidebar() {
  const { projectId } = useParams<{ projectId?: string }>()
  const { activeProjectId } = useProjectStore()
  const currentProjectId = projectId ?? activeProjectId

  const topItems: NavItem[] = [
    { to: '/', label: 'Projects', icon: <Home className="h-4 w-4" /> },
  ]

  const projectItems: NavItem[] = currentProjectId
    ? [
        {
          to: `/projects/${currentProjectId}/schema`,
          label: 'Schema',
          icon: <Database className="h-4 w-4" />,
        },
        {
          to: `/projects/${currentProjectId}/inference`,
          label: 'Inference',
          icon: <GitBranch className="h-4 w-4" />,
        },
        {
          to: `/projects/${currentProjectId}/validation`,
          label: 'Validation',
          icon: <CheckSquare className="h-4 w-4" />,
        },
        {
          to: `/projects/${currentProjectId}/memory`,
          label: 'Memory',
          icon: <Brain className="h-4 w-4" />,
        },
        {
          to: `/projects/${currentProjectId}/datasets`,
          label: 'Datasets',
          icon: <Table2 className="h-4 w-4" />,
        },
      ]
    : []

  return (
    <nav className="flex h-full w-52 flex-shrink-0 flex-col border-r border-surface-border bg-surface-elevated">
      {/* Logo */}
      <div className="flex h-12 items-center border-b border-surface-border px-4">
        <span className="font-semibold tracking-tight text-text-primary">SxQLear</span>
        <span className="ml-2 rounded bg-accent/20 px-1.5 py-0.5 text-2xs font-medium text-accent">
          alpha
        </span>
      </div>

      {/* Top nav */}
      <div className="px-2 pt-3">
        {topItems.map((item) => (
          <SidebarItem key={item.to} item={item} />
        ))}
      </div>

      {/* Project nav */}
      {currentProjectId && (
        <>
          <div className="mx-4 my-3 border-t border-surface-border" />
          <div className="px-2">
            <p className="mb-1.5 px-2 text-2xs font-medium uppercase tracking-widest text-text-muted">
              Current Project
            </p>
            {projectItems.map((item) => (
              <SidebarItem key={item.to} item={item} />
            ))}
          </div>
        </>
      )}
    </nav>
  )
}

function SidebarItem({ item }: { item: NavItem }) {
  return (
    <NavLink
      to={item.to}
      end={item.to === '/'}
      className={({ isActive }) =>
        cn(
          'mb-0.5 flex items-center gap-2.5 rounded px-2.5 py-1.5 text-sm transition-colors',
          isActive
            ? 'bg-accent/15 text-accent'
            : 'text-text-secondary hover:bg-surface-hover hover:text-text-primary'
        )
      }
    >
      {item.icon}
      {item.label}
    </NavLink>
  )
}
