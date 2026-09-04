import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { StreamStats } from '@/lib/types'
import { formatDuration, percent, plural } from '@/lib/format'
import { AXIS, ChartTooltip, GRID, Legend, Panel, SERIES, StatTile } from './chart'

function LoadMeter({ name, minutes, capacity, assigned }: { name: string; minutes: number; capacity: number; assigned: number }) {
  const ratio = Math.min(1, minutes / capacity)
  const tight = ratio > 0.85

  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <span className="truncate text-[13px] text-ink">{name}</span>
        <span className="num shrink-0 text-[12px] text-muted">
          {assigned} {plural(assigned, 'работа', 'работы', 'работ')}, {formatDuration(minutes)}
        </span>
      </div>
      <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-[#e3ecf9]">
        <div
          className="h-full rounded-full transition-[width] duration-500"
          style={{ width: `${ratio * 100}%`, background: tight ? '#d68a00' : SERIES.primary }}
        />
      </div>
      <div className="num mt-1 text-[11px] text-faint">
        {percent(minutes / capacity)} недельной ёмкости
      </div>
    </div>
  )
}

export function CourseDashboard({ stats }: { stats: StreamStats }) {
  const completion = stats.expected ? stats.submitted / stats.expected : 0

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <StatTile
          label="Сдано работ"
          value={`${stats.submitted}`}
          hint={`из ${stats.expected} ожидаемых, ${percent(completion)}`}
        />
        <StatTile
          label="Ждут куратора"
          value={`${stats.awaitingReview}`}
          hint="черновик готов, оценка не утверждена"
          tone={stats.awaitingReview > 12 ? 'warn' : 'neutral'}
        />
        <StatTile
          label="Просрочено"
          value={`${stats.overdue}`}
          hint="сдано после дедлайна"
          tone={stats.overdue > 0 ? 'warn' : 'neutral'}
        />
        <StatTile
          label="Медиана проверки"
          value={`${stats.medianReviewMinutes} мин`}
          hint="от открытия до утверждения"
          tone="good"
        />
        <StatTile
          label="Принято без правок"
          value={percent(stats.autoAcceptRate)}
          hint="черновик утверждён как есть"
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Путь работы" hint="сколько работ дошло до каждого шага">
          <ResponsiveContainer width="100%" height={190}>
            <BarChart data={stats.funnel} layout="vertical" margin={{ left: 0, right: 28, top: 4, bottom: 4 }}>
              <CartesianGrid {...GRID} horizontal={false} vertical />
              <XAxis type="number" {...AXIS} />
              <YAxis type="category" dataKey="stage" width={112} {...AXIS} />
              <Tooltip content={<ChartTooltip />} cursor={{ fill: '#f1f2f0' }} />
              <Bar dataKey="count" name="работ" barSize={18} radius={[0, 4, 4, 0]} isAnimationActive={false}>
                {stats.funnel.map((_, index) => (
                  <Cell key={index} fill={SERIES.ordinal[index]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Panel>

        <Panel title="Распределение баллов" hint="доля от максимума задания — шкалы у заданий разные">
          <ResponsiveContainer width="100%" height={190}>
            <BarChart data={stats.scoreHistogram} margin={{ left: -18, right: 8, top: 8, bottom: 4 }}>
              <CartesianGrid {...GRID} />
              <XAxis dataKey="bucket" {...AXIS} />
              <YAxis {...AXIS} />
              <Tooltip content={<ChartTooltip />} cursor={{ fill: '#f1f2f0' }} />
              <Bar
                dataKey="count"
                name="работ"
                fill={SERIES.primary}
                barSize={22}
                radius={[4, 4, 0, 0]}
                isAnimationActive={false}
              />
            </BarChart>
          </ResponsiveContainer>
        </Panel>

        <Panel
          title="Сдачи и утверждения по неделям"
          legend={<Legend items={[{ name: 'сдано', color: SERIES.primary }, { name: 'утверждено', color: SERIES.second }]} />}
        >
          <ResponsiveContainer width="100%" height={190}>
            <LineChart data={stats.weekly} margin={{ left: -18, right: 12, top: 8, bottom: 4 }}>
              <CartesianGrid {...GRID} />
              <XAxis dataKey="week" {...AXIS} />
              <YAxis {...AXIS} />
              <Tooltip content={<ChartTooltip />} cursor={{ stroke: '#dcdcd6' }} />
              <Line
                type="linear"
                dataKey="submitted"
                name="сдано"
                stroke={SERIES.primary}
                strokeWidth={2}
                dot={{ r: 4, fill: SERIES.primary, stroke: '#fbfbfa', strokeWidth: 2 }}
                activeDot={{ r: 5 }}
              />
              <Line
                type="linear"
                dataKey="approved"
                name="утверждено"
                stroke={SERIES.second}
                strokeWidth={2}
                dot={{ r: 4, fill: SERIES.second, stroke: '#fbfbfa', strokeWidth: 2 }}
                activeDot={{ r: 5 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </Panel>

        <Panel title="Средний балл по критериям" hint="доля от максимума критерия: где поток проседает целиком">
          <ResponsiveContainer width="100%" height={190}>
            <BarChart
              data={stats.criterionAverages}
              layout="vertical"
              margin={{ left: 0, right: 28, top: 4, bottom: 4 }}
            >
              <CartesianGrid {...GRID} horizontal={false} vertical />
              <XAxis type="number" domain={[0, 100]} unit="%" {...AXIS} />
              <YAxis type="category" dataKey="criterion" width={148} {...AXIS} />
              <Tooltip content={<ChartTooltip />} cursor={{ fill: '#f1f2f0' }} />
              <Bar
                dataKey="avg"
                name="средний балл"
                fill={SERIES.primary}
                barSize={16}
                radius={[0, 4, 4, 0]}
                isAnimationActive={false}
              />
            </BarChart>
          </ResponsiveContainer>
        </Panel>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Нагрузка кураторов" hint="минуты разбора против недельной ёмкости">
          <div className="space-y-3.5">
            {stats.reviewLoad.map((row) => (
              <LoadMeter
                key={row.curatorId}
                name={row.name}
                minutes={row.minutes}
                capacity={row.capacity}
                assigned={row.assigned}
              />
            ))}
          </div>
        </Panel>

        <Panel title="Сигналы ГенИИ" hint="решение по каждому сигналу принимает куратор">
          <div className="flex gap-8">
            <div>
              <div className="text-[12.5px] text-muted">Работ с сигналом</div>
              <div className="mt-1 text-[24px] font-semibold leading-none text-ink">{stats.aiFlagged}</div>
            </div>
            <div>
              <div className="text-[12.5px] text-muted">Подтверждено куратором</div>
              <div className="mt-1 text-[24px] font-semibold leading-none text-warn-ink">{stats.aiConfirmed}</div>
            </div>
            <div>
              <div className="text-[12.5px] text-muted">Точность сигнала</div>
              <div className="mt-1 text-[24px] font-semibold leading-none text-ink">
                {stats.aiFlagged ? percent(stats.aiConfirmed / stats.aiFlagged) : '—'}
              </div>
            </div>
          </div>
          <p className="mt-4 max-w-[62ch] text-[12px] leading-[1.55] text-faint">
            Сигнал не влияет на балл и не является доказательством. Подтверждения и отклонения кураторов
            копятся как выборка для калибровки порогов.
          </p>
        </Panel>
      </div>
    </div>
  )
}
