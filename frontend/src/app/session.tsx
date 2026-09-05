import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { Role } from '@/lib/types'
import { api } from '@/lib/api'
import { backend, setAuthToken } from '@/lib/backend'

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
 *  (см. `docs/backend.md`): ревьюер проверяет работы сам — `reviewer`,
 *  руководитель видит и решает за весь поток — `admin` (бэкенд не заводит
 *  отдельной роли координатора, пока некому дать под неё отдельный аккаунт).
 *  Любой другой аккаунт, заведённый через `/users`, попадает в ту же пару
 *  корзин по своей настоящей роли — `reviewer` → ревьюер, `admin` → руководитель. */
/** Роль из прошлой сессии, но только если она ещё существует.

 *  Словарь ролей менялся (`curator` / `head` → имена бэкенда), и сохранённое
 *  в localStorage значение переживает обновление интерфейса. Без проверки
 *  `BACKEND_USERNAME[role]` давал `undefined`, вход молча не проходил, и все
 *  запросы уходили без токена: экран выглядел как «бэкенд не отвечает», хотя
 *  бэкенд отвечал. Неизвестная роль — это не ошибка пользователя, поэтому
 *  просто откатываемся к ревьюеру. */
function storedRole(): Role {
  const saved = localStorage.getItem(ROLE_KEY)
  return saved !== null && saved in BACKEND_USERNAME ? (saved as Role) : 'reviewer'
}

const BACKEND_USERNAME: Record<Role, string> = {
  student: 'student',
  reviewer: 'reviewer',
  methodist: 'methodist',
  admin: 'admin',
}
const BACKEND_PASSWORD = (import.meta.env.VITE_BACKEND_PASSWORD as string | undefined) ?? 'avito2026'

export function SessionProvider({ children }: { children: ReactNode }) {
  const [role, setRoleState] = useState<Role>(storedRole)
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
    setAuthToken(token.access_token)
    setUsername(nextUsername)
    setName(token.display_name)
    // Роль берётся из токена как есть: сервер — источник правды о правах,
    // и любой перевод здесь был бы вторым мнением о том, что человеку можно.
    const nextRole = token.role as Role
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
