import { useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowUp, Check, MessageSquare, Sparkles, Wrench } from 'lucide-react'
import { ApiError, backend, type ChatMessage, type ReviewDraft } from '@/lib/backend'
import { Button } from '@/components/ui/Button'

/** Записанная реплика демо-прогона — не то же самое, что `ChatMessage` с
 *  бэкенда: демо не персистентно и не проходит через тулы, ему хватает
 *  автора и текста. */
export interface DemoMessage {
  id: string
  author: 'human' | 'ai'
  text: string
}

interface Props {
  live: boolean
  /** `null` — демо-прогон или разбор без сохранения; чат тогда read-only. */
  submissionId: string | null
  demoThread: DemoMessage[]
  /** Патч применён — родитель сводит его с уже открытым черновиком
   *  (`withPatchedDraft`), а не перечитывает сдачу заново. */
  onPatchApplied?: (draft: ReviewDraft) => void
}

function toolLabel(tool: string | null): string {
  switch (tool) {
    case 'get_file':
      return 'читает файл'
    case 'get_diff':
      return 'смотрит изменения'
    case 'get_criterion':
      return 'смотрит критерий'
    case 'search_submission':
      return 'ищет по работе'
    case 'propose_review_patch':
      return 'предлагает правку'
    default:
      return tool ?? 'инструмент'
  }
}

export function ChatDock({ live, submissionId, demoThread, onPatchApplied }: Props) {
  const [open, setOpen] = useState(false)
  const [text, setText] = useState('')
  const [liveMessages, setLiveMessages] = useState<ChatMessage[]>([])
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [applied, setApplied] = useState<Set<string>>(new Set())
  const [applying, setApplying] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const client = useQueryClient()

  const canChat = live && Boolean(submissionId)

  const history = useQuery({
    queryKey: ['chat', submissionId],
    queryFn: () => backend.chatHistory(submissionId as string),
    enabled: canChat && open,
    retry: false,
  })

  useEffect(() => {
    if (history.data) setLiveMessages(history.data)
  }, [history.data])

  useEffect(() => {
    if (open) bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [liveMessages, open])

  async function send() {
    const message = text.trim()
    if (!message || !submissionId || sending) return

    /* Реплика показывается сразу, но помечена как своя: если отправка не
       удастся, её надо убрать — иначе на экране остаётся сообщение, которого
       модель не видела, а следующий ответ встаёт под ним и выглядит ответом
       на него. */
    const localId = `local-${Date.now()}`
    setText('')
    setSending(true)
    setError(null)
    setLiveMessages((prev) => [
      ...prev,
      {
        id: localId,
        role: 'user',
        content: message,
        tool_name: null,
        proposed_patch: null,
        created_at: new Date().toISOString(),
      },
    ])

    try {
      await backend.sendChat(submissionId, message, (step) => {
        setLiveMessages((prev) => [...prev, step])
      })
      client.invalidateQueries({ queryKey: ['chat', submissionId] })
    } catch (err) {
      setLiveMessages((prev) => prev.filter((item) => item.id !== localId))
      // Текст возвращается в поле: он написан руками, и терять его из-за
      // недоступного бэкенда — худшее, что можно сделать с этой формой.
      setText(message)
      setError(err instanceof ApiError ? err.message : 'Модель не ответила')
    } finally {
      setSending(false)
    }
  }

  async function applyPatch(message: ChatMessage) {
    if (!submissionId || !message.proposed_patch) return
    setApplying(message.id)
    setError(null)
    try {
      const draft = await backend.patchReview(submissionId, {
        patches: [
          {
            criterion_id: message.proposed_patch.criterion_id,
            score: message.proposed_patch.score ?? undefined,
            verdict: message.proposed_patch.verdict ?? undefined,
            student_feedback: message.proposed_patch.student_feedback ?? undefined,
          },
        ],
      })
      setApplied((prev) => new Set(prev).add(message.id))
      onPatchApplied?.(draft)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось применить правку')
    } finally {
      setApplying(null)
    }
  }

  const lastPreview = canChat
    ? liveMessages.at(-1)?.content
    : demoThread.at(-1)?.text

  return (
    <div className="shrink-0 border-t border-line bg-surface">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 px-5 py-2 text-left transition-colors hover:bg-[#f6f7f4]"
      >
        <MessageSquare size={14} strokeWidth={1.7} className="shrink-0 text-faint" />
        <span className="text-[13px] font-medium text-ink">Разговор с моделью</span>
        {!open && lastPreview ? (
          <span className="min-w-0 flex-1 truncate text-[12.5px] text-faint">{lastPreview}</span>
        ) : (
          <span className="flex-1" />
        )}
        <span className="text-[12px] text-faint">{open ? 'свернуть' : 'развернуть'}</span>
      </button>

      {open ? (
        <div className="border-t border-line-soft">
          <div className="max-h-[220px] space-y-3 overflow-y-auto px-5 py-3.5">
            {canChat ? (
              <>
                {history.isLoading ? (
                  <p className="text-[12.5px] text-faint">Загружаю историю…</p>
                ) : null}
                {liveMessages.map((message) => (
                  <div key={message.id} className="flex gap-2.5">
                    <div className="mt-0.5 shrink-0">
                      {message.role === 'user' ? (
                        <div className="size-3.5 rounded-full bg-sunken" />
                      ) : message.role === 'tool' ? (
                        <Wrench size={14} strokeWidth={1.6} className="text-muted" />
                      ) : (
                        <Sparkles size={14} strokeWidth={1.6} className="text-accent" />
                      )}
                    </div>
                    <div className="min-w-0 max-w-[78ch] flex-1">
                      {message.role === 'tool' && message.tool_name ? (
                        <div className="mb-1 text-[11.5px] font-medium uppercase tracking-wide text-faint">
                          {toolLabel(message.tool_name)}
                        </div>
                      ) : null}
                      <p className="whitespace-pre-wrap text-[13px] leading-[1.6] text-ink-soft">
                        {message.content}
                      </p>
                      {message.proposed_patch ? (
                        <div className="mt-2 flex items-center gap-2 rounded-lg border border-accent-line bg-accent-wash px-3 py-2">
                          <span className="text-[12px] text-accent-ink">
                            Предложение: {message.proposed_patch.criterion_id}
                            {message.proposed_patch.score != null ? ` → ${message.proposed_patch.score}` : ''}
                          </span>
                          <Button
                            size="sm"
                            variant="primary"
                            className="ml-auto"
                            disabled={applied.has(message.id) || applying === message.id}
                            onClick={() => applyPatch(message)}
                            icon={applied.has(message.id) ? <Check size={13} strokeWidth={2} /> : undefined}
                          >
                            {applied.has(message.id)
                              ? 'Применено'
                              : applying === message.id
                                ? 'Применяю'
                                : 'Применить'}
                          </Button>
                        </div>
                      ) : null}
                    </div>
                  </div>
                ))}
                {!liveMessages.length && !history.isLoading ? (
                  <p className="max-w-[70ch] text-[13px] leading-[1.6] text-muted">
                    Спросите, почему поставлен такой балл, или попросите проверить конкретный файл —
                    модель читает работу тем же набором инструментов, что описан в архитектуре.
                  </p>
                ) : null}
                <div ref={bottomRef} />
              </>
            ) : (
              <>
                {demoThread.map((message) => (
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
                    Этот разбор не сохранён (нет `submission_id`), поэтому чат недоступен — он работает
                    только над персистентной сдачей.
                  </p>
                ) : null}
              </>
            )}
          </div>

          {error ? (
            <p className="mx-5 mb-2 rounded-lg border border-[#f0d3d3] bg-critical-wash px-3 py-1.5 text-[12px] text-critical-ink">
              {error}
            </p>
          ) : null}

          <div className="flex items-center gap-2 border-t border-line-soft px-5 py-2.5">
            <input
              value={text}
              onChange={(event) => setText(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault()
                  void send()
                }
              }}
              disabled={!canChat || sending}
              placeholder={
                canChat
                  ? 'Обоснуй балл по критерию 2…'
                  : live
                    ? 'Чат доступен только для сохранённых сдач'
                    : 'Демо-ветка: ответы записаны заранее'
              }
              className="h-8 flex-1 rounded-lg border border-line bg-sunken px-3 text-[13px] text-ink outline-none placeholder:text-faint disabled:cursor-not-allowed"
            />
            <Button
              size="sm"
              variant="primary"
              disabled={!canChat || sending || !text.trim()}
              aria-label="Отправить"
              onClick={() => void send()}
            >
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
