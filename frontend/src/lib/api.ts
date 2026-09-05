/** Данные админки.
 *
 *  У бэкенда пока нет ни курсов, ни потоков, ни ведомости — он без состояния и
 *  работает от ссылки на сдачу. Всё, что связано с проверкой работы, ходит в
 *  настоящий API через `lib/backend.ts`; здесь остались только сущности, для
 *  которых ручек ещё нет. Форма функций — та, что появится в REST.
 */

import {
  ASSIGNMENTS,
  COURSES,
  CURATORS,
  GRADES,
  STREAMS,
  STUDENTS,
  gradesForStream,
  statsForStream,
  totalsForStream,
} from '@/mocks/catalog'
import type {
  Assignment,
  Course,
  Curator,
  Grade,
  Stream,
  StreamStats,
  Student,
  StudentTotals,
} from './types'

const LATENCY = 180

function delay<T>(value: T, ms = LATENCY): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms))
}

const state = { curators: CURATORS.map((curator) => ({ ...curator })) }

export const api = {
  /** Текущий пользователь. Аутентификации ещё нет, поэтому это первый куратор
   *  из каталога; когда появится JWT, поменяется только тело функции. */
  me: (): Promise<Curator> => delay({ ...state.curators[0] }),

  courses: (): Promise<Course[]> => delay(COURSES),

  course: (courseId: string): Promise<Course | undefined> =>
    delay(COURSES.find((course) => course.id === courseId)),

  /** Без `courseId` — все потоки: навигации и карточке куратора нужны сразу все. */
  streams: (courseId?: string): Promise<Stream[]> =>
    delay(courseId ? STREAMS.filter((stream) => stream.courseId === courseId) : STREAMS),

  assignments: (courseId?: string): Promise<Assignment[]> =>
    delay(courseId ? ASSIGNMENTS.filter((item) => item.courseId === courseId) : ASSIGNMENTS),

  students: (streamId: string): Promise<Student[]> =>
    delay(STUDENTS.filter((student) => student.streamId === streamId)),

  student: (studentId: string): Promise<Student | undefined> =>
    delay(STUDENTS.find((student) => student.id === studentId)),

  grades: (streamId: string): Promise<Grade[]> => delay(gradesForStream(streamId)),

  /** Итоговые строки ведомости: сумма за ДЗ, экзамен, итог и оценка. */
  totals: (streamId: string): Promise<StudentTotals[]> => delay(totalsForStream(streamId)),

  gradesForStudent: (studentId: string): Promise<Grade[]> =>
    delay(GRADES.filter((grade) => grade.studentId === studentId)),

  stats: (streamId: string): Promise<StreamStats | null> => delay(statsForStream(streamId), 260),

  curators: (): Promise<Curator[]> => delay(state.curators.map((curator) => ({ ...curator }))),

  /** Назначение куратора на поток — операция руководителя. */
  setCuratorStreams: (curatorId: string, streamIds: string[]): Promise<Curator[]> => {
    const curator = state.curators.find((item) => item.id === curatorId)
    if (curator) {
      /* Несуществующий поток не должен ронять экран: раньше здесь стоял
         non-null assertion, и первая же правка куратора с чужим потоком в
         `streamIds` падала. Такой поток просто отбрасывается. */
      const known = streamIds.filter((id) => STREAMS.some((stream) => stream.id === id))
      curator.streamIds = known
      curator.courseIds = [
        ...new Set(
          known.flatMap((id) => {
            const stream = STREAMS.find((item) => item.id === id)
            return stream ? [stream.courseId] : []
          }),
        ),
      ]
    }
    return delay(state.curators.map((item) => ({ ...item })), 120)
  },
}
