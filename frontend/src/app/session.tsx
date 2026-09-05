import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { Role } from '@/lib/types'
import { api } from '@/lib/api'
import { ApiError, backend, setAuthToken } from '@/lib/backend'

interface Session {
  role: Role
  setRole: (role: Role) => void
  name: string
  /** Настоящий бэкенд-логин, а не синтетическая роль — заведён через `/users`
   *  или один из трёх сеяных. Показывается в шапке, входит в CredentialsModal. */
  username: string
  curatorId: string
  /** Бэкенд требует Bearer-токен на всём, кроме /health, /init и /auth/login —
   *  пока он не получен, дальнейшие запросы (рубрики, разбор, очередь) 401-ят. */
  authReady: boolean
  /** Вход произвольным логином/паролем — например, аккаунтом, заведённым через
   *  `/users` (не одним из двух захардкоженных). `student` отклоняется: у этой
   *  роли пока нет экрана в интерфейсе (см. `db/models.py::Role`). */
  loginAs: (username: string, password: string) => Promise<void>
}

const SessionContext = createContext<Session | null>(null)

const ROLE_KEY = 'avito-reviewer:role'

/** Синтетическая роль интерфейса → один из трёх сеяных бэкенд-аккаунтов
 *  (см. `docs/backend.md`): куратор проверяет работы сам — `reviewer`,
 *  руководитель видит и решает за весь поток — `admin` (бэкенд не заводит
 *  отдельной роли координатора, пока некому дать под неё отдельный аккаунт).
 *  Любой другой аккаунт, заведённый через `/users`, попадает в ту же пару
 *  корзин по своей настоящей роли — `reviewer` → куратор, `admin` → руководитель. */
const BACKEND_USERNAME: Record<Role, string> = { curator: 'reviewer', head: 'admin' }
const BACKEND_PASSWORD = (import.meta.env.VITE_BACKEND_PASSWORD as string | undefined) ?? 'avito2026'

export function SessionProvider({ children }: { children: ReactNode }) {
  const [role, setRoleState] = useState<Role>(
    () => (localStorage.getItem(ROLE_KEY) as Role | null) ?? 'curator',
  )
  const [username, setUsername] = useState(BACKEND_USERNAME[role])
  const [name, setName] = useState('—')
  const [authReady, setAuthReady] = useState(false)
  const { data: me } = useQuery({ queryKey: ['me'], queryFn: api.me })

  /** Вход не персистится за паролем — только `role` переживает перезагрузку
   *  (см. `ROLE_KEY`). Токен и так живёт лишь в памяти вкладки (`backend.ts`);
   *  хранить где-то пароль произвольного логина, заведённого через `/users`,
   *  ради восстановления после reload было бы хуже, чем просто перелогиниться
   *  сеяным аккаунтом и предложить войти вручную снова через CredentialsModal. */
  async function loginAs(nextUsername: string, password: string): Promise<void> {
    const token = await backend.login({ username: nextUsername, password })
    if (token.role === 'student') {
      throw new ApiError(403, 'у роли student пока нет экрана в этом интерфейсе')
    }
    setAuthToken(token.access_token)
    setUsername(nextUsername)
    setName(token.display_name)
    const nextRole: Role = token.role === 'admin' ? 'head' : 'curator'
    setRoleState(nextRole)
    localStorage.setItem(ROLE_KEY, nextRole)
    setAuthReady(true)
  }

  // Токен живёт в памяти (`backend.ts`), не в состоянии React: компоненты не
  // читают его напрямую, им достаточно знать, что вход завершён — успехом или
  // не(т). Бэкенд недоступен — тоже "завершён": офлайн-состояния экранов уже
  // умеют показывать это сами (см. CheckPage), реального 401 без сети не будет.
  useEffect(() => {
    loginAs(BACKEND_USERNAME[role], BACKEND_PASSWORD).catch(() => setAuthReady(true))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const value = useMemo<Session>(
    () => ({
      role,
      setRole: (next) => {
        loginAs(BACKEND_USERNAME[next], BACKEND_PASSWORD).catch(() => {})
      },
      name: name === '—' ? (me?.name ?? '—') : name,
      username,
      curatorId: me?.id ?? '',
      authReady,
      loginAs,
    }),
    [role, name, username, me, authReady],
  )

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
}

export function useSession(): Session {
  const value = useContext(SessionContext)
  if (!value) throw new Error('useSession вне SessionProvider')
  return value
}
