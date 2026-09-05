import { Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from '@/components/layout/AppShell'
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
import { useSession } from './session'

export function App() {
  const { role, authReady } = useSession()

  if (!authReady) {
    // Вход в один из сеяных бэкенд-аккаунтов занимает один быстрый запрос —
    // рендерить экраны раньше него значит поймать 401 на первом же useQuery.
    return (
      <div className="grid min-h-screen place-items-center">
        <span className="text-[13px] text-faint">Выполняется вход…</span>
      </div>
    )
  }

  return (
    <Routes>
      {/* Проверка работы — режим фокуса: без сайдбара, на всю ширину. */}
      <Route path="/review/:runId" element={<ReviewPage />} />

      <Route element={<AppShell />}>
        <Route index element={<Navigate to={role === 'student'
              ? '/my-work'
              : role === 'admin'
                ? '/streams'
                : role === 'methodist'
                  ? '/assignments'
                  : '/queue'} replace />} />
        <Route path="/queue" element={<QueuePage />} />
        <Route path="/check" element={<CheckPage />} />
        <Route path="/courses/:courseId" element={<CoursePage />} />
        <Route path="/students/:studentId" element={<StudentPage />} />
        <Route path="/curators" element={<CuratorsPage />} />
        <Route path="/my-work" element={<StudentHomePage />} />
        <Route path="/assignments" element={<AssignmentsPage />} />
        <Route path="/streams" element={<StreamsPage />} />
        <Route path="/rubrics" element={<RubricsPage />} />
        <Route path="/rubrics/new" element={<RubricNewPage />} />
        <Route path="/rubrics/:assignmentId/edit" element={<RubricEditPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
