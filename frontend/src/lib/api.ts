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
} from '@/mocks/catalog'
import type {
  Assignment,
  Course,
  Curator,
  Grade,
  Stream,
  StreamStats,
  Student,
} from './types'

const LATENCY = 180

function delay<T>(value: T, ms = LATENCY): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms))
}

const state = { curators: CURATORS.map((curator) => ({ ...curator })) }

export const api = {
  courses: (): Promise<Course[]> => delay(COURSES),

  streams: (courseId: string): Promise<Stream[]> =>
    delay(STREAMS.filter((stream) => stream.courseId === courseId)),

  assignments: (courseId: string): Promise<Assignment[]> =>
    delay(ASSIGNMENTS.filter((assignment) => assignment.courseId === courseId)),

  students: (streamId: string): Promise<Student[]> =>
    delay(STUDENTS.filter((student) => student.streamId === streamId)),

  student: (studentId: string): Promise<Student | undefined> =>
    delay(STUDENTS.find((student) => student.id === studentId)),

  grades: (streamId: string): Promise<Grade[]> => delay(gradesForStream(streamId)),

  gradesForStudent: (studentId: string): Promise<Grade[]> =>
    delay(GRADES.filter((grade) => grade.studentId === studentId)),

  stats: (streamId: string): Promise<StreamStats | null> => delay(statsForStream(streamId), 260),

  curators: (): Promise<Curator[]> => delay(state.curators.map((curator) => ({ ...curator }))),

  /** Назначение куратора на поток — операция руководителя. */
  setCuratorStreams: (curatorId: string, streamIds: string[]): Promise<Curator[]> => {
    const curator = state.curators.find((item) => item.id === curatorId)
    if (curator) {
      curator.streamIds = streamIds
      curator.courseIds = [
        ...new Set(streamIds.map((id) => STREAMS.find((stream) => stream.id === id)!.courseId)),
      ]
    }
    return delay(state.curators.map((item) => ({ ...item })), 120)
  },
}
