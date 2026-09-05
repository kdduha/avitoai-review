import { useState } from 'react'
import { LogIn } from 'lucide-react'
import { ApiError } from '@/lib/backend'
import { useSession } from '@/app/session'
import { Button } from '@/components/ui/Button'
import { Modal } from '@/components/ui/Modal'

const inputClass =
  'h-9 w-full rounded-lg border border-line bg-raised px-3 text-[13.5px] text-ink outline-none placeholder:text-faint focus:border-accent-line'

/** Куратор/руководитель переключаются в один клик (`RoleSwitch`) — сеяным
 *  паролем на один из двух дефолтных аккаунтов. Этот модал — единственный
 *  способ войти под чем-то ещё: вторым ревьюером или вторым admin'ом,
 *  заведённым через `POST /users` (см. `docs/happy-path.md`, сценарий 7). */
export function LoginModal() {
  const { loginAs } = useSession()
  const [open, setOpen] = useState(false)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit() {
    setPending(true)
    setError(null)
    try {
      await loginAs(username.trim(), password)
      setOpen(false)
      setUsername('')
      setPassword('')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось войти')
    } finally {
      setPending(false)
    }
  }

  return (
    <>
      <Button size="sm" variant="ghost" icon={<LogIn size={13} strokeWidth={1.9} />} onClick={() => setOpen(true)}>
        Войти
      </Button>

      <Modal
        open={open}
        title="Войти под другим аккаунтом"
        description="Логин и пароль — из POST /users (см. docs/happy-path.md, сценарий 7) или один из сеяных: student/reviewer/admin."
        onClose={() => setOpen(false)}
        width={380}
        footer={
          <>
            <Button size="sm" onClick={() => setOpen(false)}>
              Отмена
            </Button>
            <Button size="sm" variant="primary" onClick={() => void submit()} disabled={pending || !username || !password}>
              {pending ? 'Вхожу' : 'Войти'}
            </Button>
          </>
        }
      >
        <form
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault()
            void submit()
          }}
        >
          <label className="block">
            <span className="text-[12.5px] font-medium text-ink">Логин</span>
            <input
              autoFocus
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              placeholder="reviewer-2"
              className={`mt-1.5 block ${inputClass}`}
            />
          </label>
          <label className="block">
            <span className="text-[12.5px] font-medium text-ink">Пароль</span>
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className={`mt-1.5 block ${inputClass}`}
            />
          </label>
          {error ? (
            <p className="rounded-lg border border-[#f0d3d3] bg-critical-wash px-3 py-2 text-[12.5px] text-critical-ink">
              {error}
            </p>
          ) : null}
        </form>
      </Modal>
    </>
  )
}
