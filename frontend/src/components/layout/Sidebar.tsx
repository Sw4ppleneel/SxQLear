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
    <nav className="flex h-full w-14 flex-shrink-0 flex-col border-r border-surface-border bg-surface-elevated sm:w-52">
      {/* Logo */}
      <div className="flex h-12 items-center justify-center border-b border-surface-border px-2 sm:justify-start sm:px-4">
        <span className="font-semibold tracking-tight text-text-primary sm:hidden">S</span>
        <span className="hidden font-semibold tracking-tight text-text-primary sm:inline">SxQLear</span>
        <span className="ml-2 hidden rounded bg-accent/20 px-1.5 py-0.5 text-2xs font-medium text-accent sm:inline">
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
            <p className="mb-1.5 hidden px-2 text-2xs font-medium uppercase tracking-widest text-text-muted sm:block">
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
      title={item.label}
      aria-label={item.label}
      className={({ isActive }) =>
        cn(
          'mb-0.5 flex min-h-11 items-center justify-center gap-2.5 rounded px-2.5 py-1.5 text-sm transition-colors sm:justify-start',
          isActive
            ? 'bg-accent/15 text-accent'
            : 'text-text-secondary hover:bg-surface-hover hover:text-text-primary'
        )
      }
    >
      {item.icon}
      <span className="hidden sm:inline">{item.label}</span>
    </NavLink>
  )
}
