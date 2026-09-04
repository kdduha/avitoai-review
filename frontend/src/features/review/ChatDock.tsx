import { useState } from 'react'
import { ArrowUp, MessageSquare, Sparkles } from 'lucide-react'
import { Button } from '@/components/ui/Button'

export interface ChatMessage {
  id: string
  author: 'human' | 'ai'
  text: string
}

/** Разговор с моделью. Ручки на бэкенде ещё нет, поэтому на живом прогоне
 *  панель честно говорит об этом, а не подсовывает выдуманный ответ.
 *  Записанная ветка приходит вместе с прогоном: разбор по системному дизайну
 *  не должен обсуждать чужой сервис на Go. */
export function ChatDock({ live, thread }: { live: boolean; thread: ChatMessage[] }) {
  const [open, setOpen] = useState(false)
  const [text, setText] = useState('')
  const messages = live ? [] : thread

  return (
    <div className="shrink-0 border-t border-line bg-surface">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 px-5 py-2 text-left transition-colors hover:bg-[#f6f7f4]"
      >
        <MessageSquare size={14} strokeWidth={1.7} className="shrink-0 text-faint" />
        <span className="text-[13px] font-medium text-ink">Разговор с моделью</span>
        {!open && messages.length ? (
          <span className="min-w-0 flex-1 truncate text-[12.5px] text-faint">
            {messages[messages.length - 1].text}
          </span>
        ) : (
          <span className="flex-1" />
        )}
        <span className="text-[12px] text-faint">{open ? 'свернуть' : 'развернуть'}</span>
      </button>

      {open ? (
        <div className="border-t border-line-soft">
          <div className="max-h-[190px] space-y-3 overflow-y-auto px-5 py-3.5">
            {messages.map((message) => (
              <div key={message.id} className="flex gap-2.5">
                <div className="mt-0.5 shrink-0">
                  {message.author === 'ai' ? (
                    <Sparkles size={14} strokeWidth={1.6} className="text-accent" />
                  ) : (
                    <div className="size-3.5 rounded-full bg-sunken" />
                  )}
                </div>
                <p className="max-w-[78ch] text-[13px] leading-[1.6] text-ink-soft">{message.text}</p>
              </div>
            ))}

            {live ? (
              <p className="max-w-[70ch] text-[13px] leading-[1.6] text-muted">
                Итеративный разбор с моделью ещё не подключён: у бэкенда нет ручки чата, а показывать
                придуманный ответ рядом с настоящим черновиком нельзя. Пока правьте баллы вручную —
                каждая правка помечается в карточке критерия.
              </p>
            ) : null}
          </div>

          <div className="flex items-center gap-2 border-t border-line-soft px-5 py-2.5">
            <input
              value={text}
              onChange={(event) => setText(event.target.value)}
              disabled
              placeholder={live ? 'Чат появится вместе с ручкой на бэкенде' : 'Демо-ветка: ответы записаны заранее'}
              className="h-8 flex-1 rounded-lg border border-line bg-sunken px-3 text-[13px] text-ink outline-none placeholder:text-faint disabled:cursor-not-allowed"
            />
            <Button size="sm" variant="primary" disabled aria-label="Отправить">
              <ArrowUp size={14} strokeWidth={2.2} />
            </Button>
          </div>

          <p className="border-t border-line-soft px-5 py-2 text-[11.5px] text-faint">
            Модель предлагает правку черновика, но сама ничего не меняет. Каждое применённое
            предложение пишется в журнал с авторством ai / human / ai-assisted.
          </p>
        </div>
      ) : null}
    </div>
  )
}
