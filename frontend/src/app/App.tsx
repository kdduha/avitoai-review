import { Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from '@/components/layout/AppShell'
import { QueuePage } from '@/features/inbox/QueuePage'
import { CheckPage } from '@/features/review/CheckPage'
import { ReviewPage } from '@/features/review/ReviewPage'
import { CoursePage } from '@/features/courses/CoursePage'
import { CuratorsPage } from '@/features/courses/CuratorsPage'
import { RubricsPage } from '@/features/rubrics/RubricsPage'
import { StudentPage } from '@/features/students/StudentPage'
import { useSession } from './session'

export function App() {
  const { role } = useSession()

  return (
    <Routes>
      {/* Проверка работы — режим фокуса: без сайдбара, на всю ширину. */}
      <Route path="/review/:runId" element={<ReviewPage />} />

      <Route element={<AppShell />}>
        <Route index element={<Navigate to={role === 'head' ? '/courses/go' : '/queue'} replace />} />
        <Route path="/queue" element={<QueuePage />} />
        <Route path="/check" element={<CheckPage />} />
        <Route path="/courses/:courseId" element={<CoursePage />} />
        <Route path="/students/:studentId" element={<StudentPage />} />
        <Route path="/curators" element={<CuratorsPage />} />
        <Route path="/rubrics" element={<RubricsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
