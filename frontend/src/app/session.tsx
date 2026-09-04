import { createContext, useContext, useMemo, useState, type ReactNode } from 'react'
import type { Role } from '@/lib/types'
import { CURATORS } from '@/mocks/catalog'

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

  const value = useMemo<Session>(
    () => ({
      role,
      setRole: (next) => {
        localStorage.setItem(STORAGE_KEY, next)
        setRoleState(next)
      },
      name: role === 'head' ? 'Ирина Ходасевич' : CURATORS[0].name,
      curatorId: CURATORS[0].id,
    }),
    [role],
  )

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
}

export function useSession(): Session {
  const value = useContext(SessionContext)
  if (!value) throw new Error('useSession вне SessionProvider')
  return value
}
