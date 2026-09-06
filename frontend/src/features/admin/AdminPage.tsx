import { useState } from 'react'
import { Navigate } from 'react-router-dom'
import { useSession } from '@/app/session'
import { Tabs } from '@/components/ui/Tabs'
import { CatalogPanel } from './CatalogPanel'
import { UsersPanel } from './UsersPanel'

const TABS = [
  { id: 'accounts', label: 'Аккаунты' },
  { id: 'catalog', label: 'Курсы' },
]

/** Управление сущностями: кто заведён и что кому выдано.
 *  Всё остальное — проверка работ — живёт на своих экранах. */
export function AdminPage() {
  const { role } = useSession()
  const [tab, setTab] = useState('accounts')

  if (role !== 'admin') return <Navigate to="/" replace />

  return (
    <div className="mx-auto max-w-[900px] px-6 py-7">
      <h1 className="text-[20px] font-semibold tracking-[-0.01em] text-ink">Управление</h1>
      <Tabs items={TABS} value={tab} onChange={setTab} className="mt-4" />
      <div className="mt-5">{tab === 'accounts' ? <UsersPanel /> : <CatalogPanel />}</div>
    </div>
  )
}
