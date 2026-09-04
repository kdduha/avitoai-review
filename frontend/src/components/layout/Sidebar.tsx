import { NavLink, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ClipboardCheck, GraduationCap, Play, Users } from 'lucide-react'
import { api } from '@/lib/api'
import { cn } from '@/lib/cn'
import { useSession } from '@/app/session'

function Section({ children }: { children: string }) {
  return <div className="px-3 pb-1.5 pt-5 text-[11.5px] font-medium text-faint">{children}</div>
}

const linkClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    'flex items-center gap-2 rounded-lg px-3 py-1.5 text-[13.5px] transition-colors',
    isActive ? 'bg-sunken font-medium text-ink' : 'text-ink-soft hover:bg-[#f4f5f2]',
  )

export function Sidebar() {
  const { role } = useSession()
  const location = useLocation()
  const { data: courses = [] } = useQuery({ queryKey: ['courses'], queryFn: api.courses })
  const { data: streams = [] } = useQuery({
    queryKey: ['all-streams'],
    queryFn: async () => (await Promise.all((await api.courses()).map((c) => api.streams(c.id)))).flat(),
  })

  return (
    <nav className="flex w-[228px] shrink-0 flex-col border-r border-line bg-surface px-2.5 pb-4">
      <Section>Работа</Section>
      <NavLink to="/check" className={linkClass}>
        <Play size={15} strokeWidth={1.7} className="text-faint" />
        Проверить работу
      </NavLink>
      {role === 'curator' ? (
        <NavLink to="/queue" className={linkClass}>
          <ClipboardCheck size={15} strokeWidth={1.7} className="text-faint" />
          Мои проверки
        </NavLink>
      ) : null}

      <Section>Курсы</Section>
      <div className="space-y-0.5">
        {courses.map((course) => {
          const courseStreams = streams.filter((s) => s.courseId === course.id)
          const open = location.pathname.startsWith(`/courses/${course.id}`)
          return (
            <div key={course.id}>
              <NavLink to={`/courses/${course.id}`} className={linkClass} end={false}>
                <GraduationCap size={15} strokeWidth={1.7} className="text-faint" />
                <span className="truncate">{course.short}</span>
              </NavLink>
              {open ? (
                <div className="ml-[26px] border-l border-line pl-2.5">
                  {courseStreams.map((stream) => (
                    <NavLink
                      key={stream.id}
                      to={`/courses/${course.id}?stream=${stream.id}`}
                      className={cn(
                        'block rounded-md px-2 py-1 text-[12.5px] transition-colors',
                        location.search.includes(stream.id)
                          ? 'font-medium text-accent-ink'
                          : 'text-muted hover:text-ink',
                      )}
                    >
                      {stream.title}
                    </NavLink>
                  ))}
                </div>
              ) : null}
            </div>
          )
        })}
      </div>

      {role === 'head' ? (
        <>
          <Section>Программа</Section>
          <NavLink to="/curators" className={linkClass}>
            <Users size={15} strokeWidth={1.7} className="text-faint" />
            Кураторы
          </NavLink>
        </>
      ) : null}
    </nav>
  )
}
