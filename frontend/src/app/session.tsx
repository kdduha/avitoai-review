import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import type { Role } from '@/lib/types'
import { backend, hasAuthToken, onUnauthorized, setAuthToken, type TokenResponse } from '@/lib/backend'

/** `restoring` — в хранилище есть токен, и мы спрашиваем сервер, чей он.
 *  Экраны в это время не рендерятся: иначе первый же `useQuery` уйдёт раньше,
 *  чем станет известно, кто вошёл. */
type Status = 'restoring' | 'anonymous' | 'signed-in'

interface Account {
  username: string
  name: string
  role: Role
}

interface Session {
  status: Status
  role: Role
  name: string
  username: string
  signIn: (username: string, password: string) => Promise<void>
  /** Вход одной кнопкой под сеяного ревьюера. Пароля здесь нет: его выдаёт
   *  сервер по `POST /auth/demo`, и только пока включён `AUTH_DEMO_LOGIN`. */
  signInDemo: () => Promise<void>
  signOut: () => void
}

const SessionContext = createContext<Session | null>(null)

export function SessionProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [account, setAccount] = useState<Account | null>(null)
  const [status, setStatus] = useState<Status>(() => (hasAuthToken() ? 'restoring' : 'anonymous'))

  /** Роль восстанавливается из ответа `/me`, а не из хранилища рядом с токеном:
   *  сервер — источник правды о правах, и подписанный им токен всё равно
   *  проверяется на каждом запросе. Не ответил 200 — сессии нет. */
  useEffect(() => {
    onUnauthorized(() => {
      setAccount(null)
      setStatus('anonymous')
      queryClient.clear()
    })

    if (!hasAuthToken()) return
    let cancelled = false
    backend
      .me()
      .then((me) => {
        if (cancelled) return
        setAccount({ username: me.username, name: me.display_name, role: me.role })
        setStatus('signed-in')
      })
      .catch(() => {
        if (cancelled) return
        setAuthToken(null)
        setAccount(null)
        setStatus('anonymous')
      })
    return () => {
      cancelled = true
    }
  }, [queryClient])

  function enter(username: string, token: TokenResponse): void {
    setAuthToken(token.access_token)
    queryClient.clear()
    setAccount({ username, name: token.display_name, role: token.role })
    setStatus('signed-in')
  }

  const value = useMemo<Session>(
    () => ({
      status,
      // Аноним не видит ни одного экрана приложения (`App`), поэтому роль здесь
      // — просто самая бесправная: показать по ней нечего.
      role: account?.role ?? 'student',
      name: account?.name ?? '—',
      username: account?.username ?? '',
      signIn: async (username, password) => {
        enter(username, await backend.login({ username, password }))
      },
      signInDemo: async () => {
        const token = await backend.demoLogin()
        enter('reviewer', token)
      },
      signOut: () => {
        setAuthToken(null)
        setAccount(null)
        setStatus('anonymous')
        queryClient.clear()
      },
    }),
    [status, account, queryClient],
  )

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
}

export function useSession(): Session {
  const value = useContext(SessionContext)
  if (!value) throw new Error('useSession вне SessionProvider')
  return value
}
