import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { backend, type UserOut } from '@/lib/backend'
import type { Role } from '@/lib/types'
import { Button } from '@/components/ui/Button'
import { Field, SelectField, TextField, inputClass } from '@/components/ui/Field'
import { ConfirmDelete, Empty, ErrorLine, errorText } from './parts'

const ROLE_LABEL: Record<Role, string> = {
  student: 'студент',
  reviewer: 'ревьюер',
  methodist: 'методист',
  admin: 'руководитель',
}
const ROLE_OPTIONS = (Object.keys(ROLE_LABEL) as Role[]).map((value) => ({
  value,
  label: ROLE_LABEL[value],
}))

function NewAccount({ onDone }: { onDone: () => void }) {
  const client = useQueryClient()
  const [username, setUsername] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [role, setRole] = useState<Role>('student')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)

  const create = useMutation({
    mutationFn: () =>
      backend.createUser({ username, password, role, display_name: displayName }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ['users'] })
      onDone()
    },
    onError: (err) => setError(errorText(err, 'Не удалось создать')),
  })

  return (
    <section aria-label="Новый аккаунт" className="mt-4 rounded-card border border-line bg-surface px-5 py-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Логин">
          <TextField value={username} onChange={setUsername} placeholder="ivanov" />
        </Field>
        <Field label="Имя">
          <TextField value={displayName} onChange={setDisplayName} placeholder="Иван Иванов" />
        </Field>
        <Field label="Роль">
          <SelectField value={role} onChange={setRole} options={ROLE_OPTIONS} />
        </Field>
        <Field label="Пароль" hint="от 4 знаков">
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className={inputClass}
          />
        </Field>
      </div>
      <ErrorLine>{error}</ErrorLine>
      <div className="mt-3 flex gap-2">
        <Button
          variant="primary"
          size="sm"
          disabled={create.isPending || username.length < 2 || password.length < 4}
          onClick={() => create.mutate()}
        >
          {create.isPending ? 'Создаю' : 'Создать'}
        </Button>
        <Button variant="ghost" size="sm" onClick={onDone}>
          Отмена
        </Button>
      </div>
    </section>
  )
}

function AccountRow({ account }: { account: UserOut }) {
  const client = useQueryClient()
  const [name, setName] = useState(account.display_name)
  const [password, setPassword] = useState('')
  const [changing, setChanging] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)

  const refresh = () => client.invalidateQueries({ queryKey: ['users'] })
  const patch = useMutation({
    mutationFn: (body: Parameters<typeof backend.patchUser>[1]) =>
      backend.patchUser(account.id, body),
    onSuccess: () => {
      setError(null)
      refresh()
    },
    onError: (err) => setError(errorText(err, 'Не удалось сохранить')),
  })
  const remove = useMutation({
    mutationFn: () => backend.deleteUser(account.id),
    onSuccess: refresh,
    onError: (err) => setError(errorText(err, 'Не удалось удалить')),
  })

  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-card border border-line bg-surface px-4 py-3">
      <input
        value={name}
        onChange={(event) => setName(event.target.value)}
        onBlur={() => {
          if (name !== account.display_name) patch.mutate({ display_name: name })
        }}
        aria-label={`Имя ${account.username}`}
        className="h-8 w-[22ch] rounded-lg border border-transparent bg-transparent px-2 text-[13.5px] text-ink outline-none hover:border-line focus:border-accent-line"
      />
      <span className="w-[16ch] font-mono text-[12.5px] text-faint">{account.username}</span>
      <select
        value={account.role}
        aria-label={`Роль ${account.username}`}
        onChange={(event) => patch.mutate({ role: event.target.value as Role })}
        className="h-8 appearance-none rounded-lg border border-line bg-raised px-2 text-[12.5px] text-ink outline-none"
      >
        {ROLE_OPTIONS.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>

      <span className="ml-auto flex flex-wrap items-center gap-2">
        {changing ? (
          <>
            <input
              type="password"
              value={password}
              autoFocus
              placeholder="новый пароль"
              aria-label={`Новый пароль ${account.username}`}
              onChange={(event) => setPassword(event.target.value)}
              className="h-8 w-[20ch] rounded-lg border border-line bg-raised px-2 text-[12.5px] text-ink outline-none placeholder:text-faint focus:border-accent-line"
            />
            <Button
              size="sm"
              variant="primary"
              disabled={password.length < 4}
              onClick={() => {
                patch.mutate(
                  { password },
                  {
                    onSuccess: () => {
                      setChanging(false)
                      setPassword('')
                      setNote('Пароль изменён')
                    },
                  },
                )
              }}
            >
              Сохранить
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setChanging(false)}>
              Отмена
            </Button>
          </>
        ) : (
          <Button size="sm" variant="ghost" onClick={() => setChanging(true)}>
            Пароль
          </Button>
        )}
        <ConfirmDelete what={account.username} onConfirm={() => remove.mutate()} pending={remove.isPending} />
      </span>

      {note && !error ? <p className="w-full text-[12px] text-muted">{note}</p> : null}
      <ErrorLine>{error}</ErrorLine>
    </li>
  )
}

export function UsersPanel() {
  const [creating, setCreating] = useState(false)
  const users = useQuery({ queryKey: ['users'], queryFn: backend.users })

  return (
    <div>
      <div className="flex items-center justify-end gap-3">
        {!creating ? (
          <Button size="sm" variant="primary" icon={<Plus size={14} strokeWidth={2} />} onClick={() => setCreating(true)}>
            Новый аккаунт
          </Button>
        ) : null}
      </div>

      {creating ? <NewAccount onDone={() => setCreating(false)} /> : null}

      {users.isError ? <Empty>Список не загрузился — бэкенд не отвечает.</Empty> : null}

      {users.data?.length ? (
        <ul className="mt-4 space-y-2">
          {users.data.map((account) => (
            <AccountRow key={account.id} account={account} />
          ))}
        </ul>
      ) : !users.isError && !users.isLoading ? (
        <Empty>Аккаунтов нет — заведите первый.</Empty>
      ) : null}
    </div>
  )
}
