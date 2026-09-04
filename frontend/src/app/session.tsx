import { createContext, useContext, useMemo, useState, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { Role } from '@/lib/types'
import { api } from '@/lib/api'

interface Session {
  role: Role
  setRole: (role: Role) => void
  name: string
  curatorId: string
}

const SessionContext = createContext<Session | null>(null)

const STORAGE_KEY = 'avito-reviewer:role'

export function SessionProvider({ children }: { children: ReactNode }) {
  const [role, setRoleState] = useState<Role>(
    () => (localStorage.getItem(STORAGE_KEY) as Role | null) ?? 'curator',
  )
  const { data: me } = useQuery({ queryKey: ['me'], queryFn: api.me })

  const value = useMemo<Session>(
    () => ({
      role,
      setRole: (next) => {
        localStorage.setItem(STORAGE_KEY, next)
        setRoleState(next)
      },
      name: role === 'head' ? 'Ирина Ходасевич' : (me?.name ?? '—'),
      curatorId: me?.id ?? '',
    }),
    [role, me],
  )

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
}

export function useSession(): Session {
  const value = useContext(SessionContext)
  if (!value) throw new Error('useSession вне SessionProvider')
  return value
}
