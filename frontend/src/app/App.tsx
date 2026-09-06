import type { ReactElement } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from '@/components/layout/AppShell'
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

/** Не свой маршрут — не пустой экран и не 403 на первом запросе, а свой
 *  стартовый: адрес, набранный руками или оставшийся в закладке, ведёт туда,
 *  где человеку есть что делать. Что *разрешено*, решает сервер; здесь решается
 *  только, что показывать. */
function Gate({ allow, children }: { allow: boolean; children: ReactElement }) {
  const { role } = useSession()
  return allow ? children : <Navigate to={HOME[role]} replace />
}

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

  return (
    <Routes>
      <Route path="/login" element={<Navigate to={home} replace />} />

      {/* Проверка работы — режим фокуса: без сайдбара, на всю ширину. */}
      <Route
        path="/review/:runId"
        element={
          <Gate allow={atLeast(role, 'reviewer')}>
            <ReviewPage />
          </Gate>
        }
      />

      <Route element={<AppShell />}>
        <Route index element={<Navigate to={home} replace />} />
        <Route
          path="/my-work"
          element={
            <Gate allow={role === 'student'}>
              <StudentHomePage />
            </Gate>
          }
        />
        <Route
          path="/queue"
          element={
            <Gate allow={atLeast(role, 'reviewer')}>
              <QueuePage />
            </Gate>
          }
        />
        <Route
          path="/check"
          element={
            <Gate allow={atLeast(role, 'reviewer')}>
              <CheckPage />
            </Gate>
          }
        />
        <Route
          path="/courses/:courseId"
          element={
            <Gate allow={atLeast(role, 'reviewer')}>
              <CoursePage />
            </Gate>
          }
        />
        <Route
          path="/students/:studentId"
          element={
            <Gate allow={atLeast(role, 'reviewer')}>
              <StudentPage />
            </Gate>
          }
        />
        <Route
          path="/curators"
          element={
            <Gate allow={role === 'admin'}>
              <CuratorsPage />
            </Gate>
          }
        />
        <Route
          path="/assignments"
          element={
            <Gate allow={atLeast(role, 'reviewer')}>
              <AssignmentsPage />
            </Gate>
          }
        />
        <Route
          path="/streams"
          element={
            <Gate allow={atLeast(role, 'reviewer')}>
              <StreamsPage />
            </Gate>
          }
        />
        <Route
          path="/rubrics"
          element={
            <Gate allow={atLeast(role, 'reviewer')}>
              <RubricsPage />
            </Gate>
          }
        />
        <Route
          path="/rubrics/new"
          element={
            <Gate allow={atLeast(role, 'methodist')}>
              <RubricNewPage />
            </Gate>
          }
        />
        <Route
          path="/rubrics/:assignmentId/edit"
          element={
            <Gate allow={atLeast(role, 'methodist')}>
              <RubricEditPage />
            </Gate>
          }
        />
      </Route>

      <Route path="*" element={<Navigate to={home} replace />} />
    </Routes>
  )
}
