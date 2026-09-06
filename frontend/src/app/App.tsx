import type { ReactElement } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from '@/components/layout/AppShell'
import { AdminPage } from '@/features/admin/AdminPage'
import { LoginPage } from '@/features/auth/LoginPage'
import { QueuePage } from '@/features/inbox/QueuePage'
import { CheckPage } from '@/features/review/CheckPage'
import { ReviewPage } from '@/features/review/ReviewPage'
import { CoursePage } from '@/features/courses/CoursePage'
import { CuratorsPage } from '@/features/courses/CuratorsPage'
import { RubricEditPage } from '@/features/rubrics/RubricEditPage'
import { RubricNewPage } from '@/features/rubrics/RubricNewPage'
import { AssignmentsPage } from '@/features/teaching/AssignmentsPage'
import { StreamsPage } from '@/features/teaching/StreamsPage'
import { StudentHomePage } from '@/features/student/StudentHomePage'
import { RubricsPage } from '@/features/rubrics/RubricsPage'
import { StudentPage } from '@/features/students/StudentPage'
import { atLeast, type Role } from '@/lib/types'
import { useSession } from './session'

/** Куда попадает человек, войдя, и куда его возвращает чужой маршрут. */
const HOME: Record<Role, string> = {
  student: '/my-work',
  reviewer: '/queue',
  methodist: '/assignments',
  admin: '/streams',
}

type Allow = (role: Role) => boolean

const student: Allow = (role) => role === 'student'
const reviewer: Allow = (role) => atLeast(role, 'reviewer')
const methodist: Allow = (role) => atLeast(role, 'methodist')
const admin: Allow = (role) => role === 'admin'

/** Что *разрешено*, решает сервер; здесь решается только, что показывать.
 *  Не свой маршрут ведёт на свой стартовый экран, а не на пустую страницу:
 *  адрес из закладки должен приводить туда, где человеку есть что делать. */
const SHELL: [path: string, element: ReactElement, allow: Allow][] = [
  ['/my-work', <StudentHomePage />, student],
  ['/queue', <QueuePage />, reviewer],
  ['/check', <CheckPage />, reviewer],
  ['/courses/:courseId', <CoursePage />, reviewer],
  ['/students/:studentId', <StudentPage />, reviewer],
  ['/assignments', <AssignmentsPage />, reviewer],
  ['/streams', <StreamsPage />, reviewer],
  ['/rubrics', <RubricsPage />, reviewer],
  ['/rubrics/new', <RubricNewPage />, methodist],
  ['/rubrics/:assignmentId/edit', <RubricEditPage />, methodist],
  ['/admin', <AdminPage />, admin],
  ['/curators', <CuratorsPage />, admin],
]

export function App() {
  const { status, role } = useSession()

  if (status === 'restoring') {
    return (
      <div className="grid min-h-screen place-items-center">
        <span className="text-[13px] text-faint">Загрузка…</span>
      </div>
    )
  }

  if (status === 'anonymous') {
    return (
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    )
  }

  const home = HOME[role]
  const gate = (element: ReactElement, allow: Allow) =>
    allow(role) ? element : <Navigate to={home} replace />

  return (
    <Routes>
      <Route path="/login" element={<Navigate to={home} replace />} />

      {/* Проверка работы — режим фокуса: без сайдбара, на всю ширину. */}
      <Route path="/review/:runId" element={gate(<ReviewPage />, reviewer)} />

      <Route element={<AppShell />}>
        <Route index element={<Navigate to={home} replace />} />
        {SHELL.map(([path, element, allow]) => (
          <Route key={path} path={path} element={gate(element, allow)} />
        ))}
      </Route>

      <Route path="*" element={<Navigate to={home} replace />} />
    </Routes>
  )
}
