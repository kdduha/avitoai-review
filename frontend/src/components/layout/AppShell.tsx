import { Link, Outlet } from 'react-router-dom'
import { Avatar } from '@/components/ui/Avatar'
import { useSession } from '@/app/session'
import { LoginModal } from './LoginModal'
import { RoleSwitch } from './RoleSwitch'
import { Sidebar } from './Sidebar'

export function AppShell() {
  const { name, role, username } = useSession()

  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex h-14 shrink-0 items-center justify-between gap-6 border-b border-line bg-surface px-4">
        <Link to="/" className="flex items-baseline gap-2.5">
          <span className="text-[15px] font-semibold tracking-[-0.01em] text-ink">Ревью</span>
          <span className="text-[13px] text-faint">образовательные программы Авито</span>
        </Link>

        <div className="flex items-center gap-3">
          <RoleSwitch />
          <LoginModal />
          <div className="flex items-center gap-2 pl-1">
            <Avatar name={name} size={28} />
            <div className="leading-tight">
              <div className="text-[13px] font-medium text-ink">{name}</div>
              <div className="text-[11.5px] text-faint">
                {username} · {role === 'head' ? 'руководитель программы' : 'куратор'}
              </div>
            </div>
          </div>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <Sidebar />
        <main className="min-w-0 flex-1">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
