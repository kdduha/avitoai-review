import { useState } from 'react'
import { useSession } from '@/app/session'
import { ApiError } from '@/lib/backend'
import { Button } from '@/components/ui/Button'

const inputClass =
  'h-9 w-full rounded-lg border border-line bg-raised px-3 text-[13.5px] text-ink outline-none placeholder:text-faint focus:border-accent-line'

/** Что показать вместо ответа сервера. Технический `detail` («токен
 *  недействителен», «нужен Bearer-токен») человеку у формы входа ничего не
 *  объясняет, а состав аккаунтов — вообще не его дело: неверная пара логина и
 *  пароля выглядит одинаково независимо от того, какой половины не хватило. */
function readable(error: unknown): string {
  if (error instanceof ApiError && error.status === 401) return 'Неверный логин или пароль'
  if (error instanceof ApiError && error.status === 0) return 'Сервис недоступен. Попробуйте позже'
  return 'Не удалось войти'
}

export function LoginPage() {
  const { signIn } = useSession()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit() {
    if (pending) return
    setPending(true)
    setError(null)
    try {
      await signIn(username.trim(), password)
    } catch (err) {
      setError(readable(err))
      setPending(false)
    }
  }

  return (
    <div className="grid min-h-screen place-items-center px-6">
      <div className="w-full max-w-[340px]">
        <div className="flex items-baseline gap-2.5">
          <span className="text-[15px] font-semibold tracking-[-0.01em] text-ink">Ревью</span>
          <span className="text-[13px] text-faint">образовательные программы Авито</span>
        </div>

        <form
          className="mt-5 rounded-[14px] border border-line bg-surface p-5 shadow-soft"
          onSubmit={(event) => {
            event.preventDefault()
            void submit()
          }}
        >
          <label className="block">
            <span className="text-[12.5px] font-medium text-ink">Логин</span>
            <input
              autoFocus
              autoComplete="username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              className={`mt-1.5 block ${inputClass}`}
            />
          </label>
          <label className="mt-3 block">
            <span className="text-[12.5px] font-medium text-ink">Пароль</span>
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className={`mt-1.5 block ${inputClass}`}
            />
          </label>

          {error ? (
            <p
              role="alert"
              className="mt-3 rounded-lg border border-[#f0d3d3] bg-critical-wash px-3 py-2 text-[12.5px] text-critical-ink"
            >
              {error}
            </p>
          ) : null}

          <Button
            type="submit"
            variant="primary"
            className="mt-4 w-full"
            disabled={pending || !username.trim() || !password}
          >
            {pending ? 'Вхожу' : 'Войти'}
          </Button>
        </form>
      </div>
    </div>
  )
}
