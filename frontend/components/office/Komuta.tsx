'use client';

import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react';
import dynamic from 'next/dynamic';
import { AnimatePresence, motion } from 'framer-motion';
import { LuArrowUp, LuSquare, LuTrash2, LuMonitor, LuPlus } from 'react-icons/lu';
import {
  answerChat,
  createChat,
  deleteChat,
  fetchChat,
  fetchChats,
  fetchTerminalSessions,
  sendMessage,
  stopChat,
  takeOver,
  type Chat,
  type ChatAgent,
  type ChatMessage,
  type ChatSummary,
  type TerminalSession,
} from '@/services/sohbetApi';
import {
  answerCard,
  fetchPano,
  mergeCard,
  setBekciMode,
  switchLoop,
  type PanoCard,
  type PanoSnapshot,
} from '@/services/panoApi';
import type { ApiResult } from '@/services/apiClient';
import { useOfficeStore, type WorkerStatus } from '@/stores/officeStore';
import type { CrewId } from './station/StationScene';
import { ago, basename } from './format';

// Komuta ekranı (2026-10-27). Kullanıcı isteği: "sana terminalde nasıl iş veriyorsam Chiron'da
// da öyle olsun" + "istasyon gözümün önünde olsun". Tek ekran: solda ekip ve sohbetler, ortada
// canlı sohbet (her mesaj aynı Claude oturumunu sürdürür), sağda mini istasyon, senden
// bekleyenler, sıra, bekçi ve 7/24. Sohbet mantığı backend/core/sohbet.py'de.

const StationScene = dynamic(() => import('./station/StationScene').then((m) => m.StationScene), { ssr: false });

interface Member {
  id: CrewId;
  name: string;
  model: string;
  color: string;
  desks: string[];
  chat: ChatAgent | null;
  lock?: string;
}

const CREW: Member[] = [
  { id: 'jarvis', name: 'Jarvis', model: 'Claude · lider', color: '#7aa2ff', desks: ['claude'], chat: 'claude' },
  { id: 'gemini', name: 'Gemini', model: 'gemini-3.8-flash · yalnız okur', color: '#b794f6', desks: ['gemini'], chat: 'gemini' },
  {
    id: 'alt',
    name: 'Alt ajan',
    model: 'Claude · Jarvis’in ekibi',
    color: '#f0a6e8',
    desks: ['subagents'],
    chat: null,
    lock: 'Alt ajana doğrudan yazılmaz — işini Jarvis böler ve verir.',
  },
  {
    id: 'terra',
    name: 'Terra',
    model: 'Codex gpt-5.6-terra',
    color: '#4fd1c5',
    desks: ['sol', 'astra'],
    chat: null,
    lock: 'Terra’yla sohbet yok — mekanik kod işini İşler sekmesinden kart olarak ver.',
  },
];

const CHAT_POLL_LIVE = 1500;
const CHAT_POLL_IDLE = 6000;
const LIST_POLL = 4000;
const PANO_POLL = 6000;
const STEPS_SHOWN = 6;

const MEMBER_STATUS: Record<WorkerStatus, string> = {
  calisiyor: 'çalışıyor',
  onay_bekliyor: 'onay bekliyor',
  bosta: 'boşta',
  bitti: 'boşta',
  hata: 'hata',
  ayrildi: 'boşta',
};

const MSG_STATUS: Record<string, string> = {
  sirada: 'Sırada',
  calisiyor: 'Çalışıyor',
  onay: 'Onayını bekliyor',
  hata: 'Hata',
  durdu: 'Durduruldu',
};

function useNow(): number {
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now() / 1000), 5000);
    return () => clearInterval(id);
  }, []);
  return now;
}

export function Komuta() {
  const snapshot = useOfficeStore((s) => s.snapshot);
  const setTab = useOfficeStore((s) => s.setTab);
  const now = useNow();

  const [memberId, setMemberId] = useState<CrewId>('jarvis');
  const [chats, setChats] = useState<ChatSummary[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [chat, setChat] = useState<Chat | null>(null);
  const [pano, setPano] = useState<PanoSnapshot | null>(null);
  const [notice, setNotice] = useState('');
  const [sending, setSending] = useState(false);
  const picked = useRef(false); // kullanıcı bir sohbet seçti mi (yoksa ilk yüklemede en sonuncusu açılır)

  const member = CREW.find((m) => m.id === memberId) ?? CREW[0];

  const loadChats = useCallback(
    () =>
      fetchChats().then((data) => {
        if (!data) return;
        setChats(data.chats);
        if (!picked.current) {
          picked.current = true;
          const first = data.chats.find((c) => c.agent === 'claude') ?? data.chats[0];
          if (first) setActiveId(first.id);
        }
      }),
    [],
  );

  useEffect(() => {
    void loadChats();
    const id = setInterval(() => void loadChats(), LIST_POLL);
    return () => clearInterval(id);
  }, [loadChats]);

  const live = !!chat?.busy;
  useEffect(() => {
    if (!activeId) return;
    let cancelled = false;
    const load = () =>
      void fetchChat(activeId).then((data) => {
        if (!cancelled && data) setChat(data.chat);
      });
    load();
    const id = setInterval(load, live ? CHAT_POLL_LIVE : CHAT_POLL_IDLE);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [activeId, live]);

  const loadPano = useCallback(() => fetchPano().then((data) => data && setPano(data)), []);
  useEffect(() => {
    void loadPano();
    const id = setInterval(() => void loadPano(), PANO_POLL);
    return () => clearInterval(id);
  }, [loadPano]);

  /** Bir uç çağrısı: başarısızsa mesajı göster, başarılıysa sohbeti güncelle. */
  const act = useCallback(
    async (call: () => Promise<ApiResult<{ chat: Chat }>>) => {
      const result = await call();
      if (!result.success || !result.data) {
        setNotice(result.message || 'Olmadı.');
        return null;
      }
      setNotice('');
      setChat(result.data.chat);
      setActiveId(result.data.chat.id);
      void loadChats();
      return result.data.chat;
    },
    [loadChats],
  );

  /** Terminalden devralınan sohbet: Jarvis'in sohbeti olarak aç. */
  const adopt = (c: Chat) => {
    picked.current = true;
    setMemberId('jarvis');
    setChat(c);
    setActiveId(c.id);
    setNotice('');
    void loadChats();
  };

  const pickMember = (id: CrewId) => {
    const m = CREW.find((x) => x.id === id) ?? CREW[0];
    setMemberId(id);
    picked.current = true;
    setNotice('');
    if (!m.chat) {
      setActiveId(null);
      setChat(null);
      return;
    }
    const latest = chats.find((c) => c.agent === m.chat);
    setActiveId(latest?.id ?? null);
    if (!latest) setChat(null);
  };

  const openChat = (c: ChatSummary) => {
    picked.current = true;
    setMemberId(c.agent === 'gemini' ? 'gemini' : 'jarvis');
    setActiveId(c.id);
    setNotice('');
  };

  const newChat = () => {
    const agent = member.chat ?? 'claude';
    if (!member.chat) setMemberId('jarvis');
    void act(() => createChat(agent));
  };

  const send = async (text: string) => {
    const agent = member.chat;
    if (!agent || sending) return false;
    setSending(true);
    try {
      let id = activeId && chat?.agent === agent ? activeId : null;
      if (!id) {
        const created = await act(() => createChat(agent));
        if (!created) return false;
        id = created.id;
      }
      const target = id;
      return !!(await act(() => sendMessage(target, text)));
    } finally {
      setSending(false);
    }
  };

  const workerStatus = (m: Member): WorkerStatus => {
    const desks = snapshot?.desks.filter((d) => m.desks.includes(d.id)) ?? [];
    if (desks.some((d) => d.status === 'onay_bekliyor')) return 'onay_bekliyor';
    if (desks.some((d) => d.status === 'calisiyor')) return 'calisiyor';
    return 'bosta';
  };

  const memberState = (m: Member) => {
    const busyChat = chats.find((c) => c.busy && m.chat && c.agent === m.chat);
    if (m.id === 'terra' && pano?.agents?.codex && !pano.agents.codex.available) {
      const until = pano.agents.codex.until;
      return { status: 'uyuyor', tone: 'sleep', line: until ? `Kota ${new Date(until * 1000).toLocaleDateString('tr-TR')} açılır` : 'Kota doldu' };
    }
    if (busyChat) return { status: 'çalışıyor', tone: 'work', line: busyChat.last_step || busyChat.title };
    const ws = workerStatus(m);
    const desk = snapshot?.workers
      .filter((w) => m.desks.includes(w.desk) && (w.status === 'calisiyor' || w.status === 'onay_bekliyor'))
      .sort((a, b) => b.last_ts - a.last_ts)[0];
    const tone = ws === 'calisiyor' ? 'work' : ws === 'onay_bekliyor' ? 'wait' : 'idle';
    return { status: MEMBER_STATUS[ws], tone, line: desk?.current || desk?.title || m.model };
  };

  return (
    <div className="komuta">
      <aside className="komuta-col komuta-left" aria-label="Ekip ve sohbetler">
        <span className="label-micro">Ekip</span>
        <div className="komuta-crew">
          {CREW.map((m) => {
            const s = memberState(m);
            return (
              <button
                key={m.id}
                type="button"
                className={`komuta-member ${memberId === m.id ? 'is-on' : ''} is-${s.tone}`}
                style={{ ['--member' as string]: m.color }}
                aria-pressed={memberId === m.id}
                onClick={() => pickMember(m.id)}
              >
                <span className="komuta-member__avatar" aria-hidden>
                  {m.name[0]}
                </span>
                <span className="komuta-member__body">
                  <span className="komuta-member__head">
                    <strong>{m.name}</strong>
                    <span className="komuta-pill">{s.status}</span>
                  </span>
                  <span className="komuta-member__line">{s.line}</span>
                </span>
              </button>
            );
          })}
        </div>

        <div className="komuta-sep" />
        <div className="komuta-row">
          <span className="label-micro">Sohbetler</span>
          <button type="button" className="pano-btn" onClick={newChat}>
            <LuPlus size={12} /> Yeni
          </button>
        </div>
        <ChatList chats={chats} activeId={activeId} now={now} onOpen={openChat} onDeleted={() => void loadChats()} />
        <TerminalList now={now} onTaken={adopt} />
      </aside>

      <main className="komuta-col komuta-chat" aria-label="Sohbet">
        <ChatPane
          member={member}
          chat={activeId ? chat : null}
          now={now}
          notice={notice}
          sending={sending}
          onSend={send}
          onStop={() => activeId && void act(() => stopChat(activeId))}
          onAnswer={(ok) => activeId && void act(() => answerChat(activeId, ok))}
        />
      </main>

      <aside className="komuta-col komuta-right" aria-label="İstasyon ve senden bekleyenler">
        <div className="komuta-row">
          <span className="label-micro">İstasyon</span>
          <span className="komuta-hint">karaktere tıkla, sohbeti açılsın</span>
        </div>
        <div className="komuta-station">
          <StationScene paused={false} mini onPick={pickMember} />
        </div>
        <Pending
          pano={pano}
          chats={chats}
          approvals={snapshot?.approvals ?? []}
          onOpenChat={openChat}
          onChanged={() => void loadPano()}
          onAll={() => setTab('isler')}
        />
      </aside>
    </div>
  );
}

// ── Sol: sohbet listesi ve terminal oturumları ─────────────────────────

function ChatList({
  chats,
  activeId,
  now,
  onOpen,
  onDeleted,
}: {
  chats: ChatSummary[];
  activeId: string | null;
  now: number;
  onOpen: (c: ChatSummary) => void;
  onDeleted: () => void;
}) {
  if (!chats.length) return <p className="komuta-empty-line">Henüz sohbet yok. Ortadan yazmaya başla.</p>;
  return (
    <ul className="komuta-chats">
      {chats.map((c) => (
        <li key={c.id}>
          <button type="button" className={`komuta-chatrow ${activeId === c.id ? 'is-on' : ''}`} onClick={() => onOpen(c)}>
            <span className="komuta-chatrow__title">
              <span className={`komuta-dot is-${c.agent}`} aria-hidden />
              {c.title}
            </span>
            <span className="komuta-chatrow__meta">
              {c.busy ? (
                <span className="is-work">çalışıyor</span>
              ) : c.status === 'onay' ? (
                <span className="is-wait">onay bekliyor</span>
              ) : (
                ago(c.updated, now)
              )}
              {c.source === 'terminal' && <span className="komuta-tag">terminal</span>}
            </span>
          </button>
          {!c.busy && (
            <button
              type="button"
              className="komuta-chatrow__del"
              aria-label={`${c.title} sohbetini sil`}
              onClick={() => void deleteChat(c.id).then(onDeleted)}
            >
              <LuTrash2 size={12} />
            </button>
          )}
        </li>
      ))}
    </ul>
  );
}

function TerminalList({ now, onTaken }: { now: number; onTaken: (c: Chat) => void }) {
  const [open, setOpen] = useState(false);
  const [sessions, setSessions] = useState<TerminalSession[] | null>(null);
  const [confirm, setConfirm] = useState<string | null>(null);
  const [error, setError] = useState('');

  const toggle = () => {
    const next = !open;
    setOpen(next);
    setError('');
    if (next) void fetchTerminalSessions().then((d) => setSessions(d?.sessions ?? []));
  };

  const take = async (s: TerminalSession) => {
    if (s.open && confirm !== s.session_id) {
      setConfirm(s.session_id);
      return;
    }
    const result = await takeOver(s.session_id, s.open);
    setConfirm(null);
    if (!result.success || !result.data) {
      setError(result.message);
      return;
    }
    setOpen(false);
    onTaken(result.data.chat);
  };

  return (
    <div className="komuta-terminal">
      <button type="button" className="komuta-terminal__toggle" onClick={toggle} aria-expanded={open}>
        <LuMonitor size={13} /> PC’deki oturumlar
      </button>
      {open && (
        <div className="komuta-terminal__list">
          {sessions === null && <p className="komuta-empty-line">Okunuyor…</p>}
          {sessions?.length === 0 && <p className="komuta-empty-line">Son iki haftada oturum yok.</p>}
          {sessions?.map((s) => (
            <div key={s.session_id} className="komuta-session">
              <div className="komuta-session__title">{s.title}</div>
              <div className="komuta-session__meta">
                {basename(s.cwd)} · {ago(s.updated, now)}
                {s.open && <span className="is-wait"> · PC’de açık</span>}
              </div>
              {s.taken ? (
                <span className="komuta-session__done">Sohbetlerde</span>
              ) : (
                <button type="button" className="pano-btn" onClick={() => void take(s)}>
                  {confirm === s.session_id ? 'Yine de devral' : 'Devral'}
                </button>
              )}
              {confirm === s.session_id && (
                <p className="komuta-session__warn">
                  PC’de açık görünüyor. Terminalde kapatmadan devralırsan ikisi aynı kayda yazar.
                </p>
              )}
            </div>
          ))}
          {error && <p className="komuta-session__warn">{error}</p>}
        </div>
      )}
    </div>
  );
}

// ── Orta: sohbet ───────────────────────────────────────────────────────

function ChatPane({
  member,
  chat,
  now,
  notice,
  sending,
  onSend,
  onStop,
  onAnswer,
}: {
  member: Member;
  chat: Chat | null;
  now: number;
  notice: string;
  sending: boolean;
  onSend: (text: string) => Promise<boolean>;
  onStop: () => void;
  onAnswer: (approved: boolean) => void;
}) {
  const [draft, setDraft] = useState('');
  const endRef = useRef<HTMLDivElement>(null);
  const messages = useMemo(() => chat?.messages ?? [], [chat]);
  const last = messages[messages.length - 1];
  const tail = `${messages.length}:${last?.status ?? ''}:${last?.steps?.length ?? 0}`;

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end', behavior: 'smooth' });
  }, [tail]);

  const busy = !!chat?.busy;
  const canTalk = !!member.chat && (!chat || chat.agent === member.chat);
  const submit = async () => {
    const text = draft.trim();
    if (!text || busy || sending) return;
    if (await onSend(text)) setDraft('');
  };
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      void submit();
    }
  };

  return (
    <>
      <header className="komuta-chat__head">
        <span className="komuta-member__avatar is-lg" style={{ ['--member' as string]: member.color }} aria-hidden>
          {member.name[0]}
        </span>
        <div className="komuta-chat__title">
          <strong>{chat ? chat.title : member.name}</strong>
          <span>
            {chat
              ? `${member.name} · ${chat.cwd ? basename(chat.cwd) : 'ev klasörü'}${chat.source === 'terminal' ? ' · terminalden devralındı' : ''}`
              : member.model}
          </span>
        </div>
        {busy && (
          <button type="button" className="pano-btn is-danger" onClick={onStop}>
            <LuSquare size={11} /> Durdur
          </button>
        )}
      </header>

      <div className="komuta-chat__scroll">
        {!chat && (
          <div className="komuta-chat__empty">
            {member.lock ?? (
              <>
                <strong>{member.name} ile yeni sohbet</strong>
                <span>
                  Terminalde nasıl yazıyorsan öyle yaz. Her mesaj aynı oturumu sürdürür — önceki konuşmayı bilir.
                  Geri alınamayan bir adımda durur ve onayını ister.
                </span>
              </>
            )}
          </div>
        )}
        <AnimatePresence initial={false}>
          {messages.map((m, i) => (
            <Message key={`${m.at}-${i}`} m={m} isLast={i === messages.length - 1} onAnswer={onAnswer} now={now} />
          ))}
        </AnimatePresence>
        <div ref={endRef} />
      </div>

      <footer className="komuta-chat__foot">
        {notice && <p className="komuta-notice">{notice}</p>}
        {canTalk ? (
          <div className="komuta-compose">
            <label htmlFor="komuta-input" className="sr-only">
              Mesaj
            </label>
            <textarea
              id="komuta-input"
              rows={1}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={onKey}
              placeholder={busy ? `${member.name} çalışıyor — bitince yazabilirsin` : `${member.name}’e yaz…  (Enter gönderir, Shift+Enter alt satır)`}
              disabled={busy}
              maxLength={4000}
            />
            <button
              type="button"
              className="komuta-send"
              onClick={() => void submit()}
              disabled={busy || sending || !draft.trim()}
              aria-label="Gönder"
            >
              <LuArrowUp size={16} strokeWidth={2.2} />
            </button>
          </div>
        ) : (
          <p className="komuta-locked">{member.lock}</p>
        )}
        {canTalk && <p className="komuta-foot-note">Aynı oturum sürer · bekçi ve kota freni açık</p>}
      </footer>
    </>
  );
}

/** Ajan cevabındaki hafif Markdown: ```kod bloğu```, `satır içi kod`, **kalın**. HTML üretmez
 *  (innerHTML yok) — metin React düğümü olarak kalır. */
function Rich({ text }: { text: string }) {
  return (
    <>
      {text.split(/(```[\s\S]*?```)/g).map((part, i) => {
        if (part.startsWith('```') && part.endsWith('```') && part.length >= 6) {
          const body = part.slice(3, -3).replace(/^[\w+-]*\n/, '');
          return (
            <pre key={i} className="komuta-code">
              {body}
            </pre>
          );
        }
        return part.split(/(`[^`\n]+`|\*\*[^*\n]+\*\*)/g).map((bit, j) => {
          if (bit.startsWith('`') && bit.endsWith('`') && bit.length > 2)
            return <code key={`${i}-${j}`}>{bit.slice(1, -1)}</code>;
          if (bit.startsWith('**') && bit.endsWith('**') && bit.length > 4)
            return <strong key={`${i}-${j}`}>{bit.slice(2, -2)}</strong>;
          return bit;
        });
      })}
    </>
  );
}

function Message({
  m,
  isLast,
  onAnswer,
  now,
}: {
  m: ChatMessage;
  isLast: boolean;
  onAnswer: (approved: boolean) => void;
  now: number;
}) {
  const [allSteps, setAllSteps] = useState(false);
  const steps = m.steps ?? [];
  const shown = allSteps ? steps : steps.slice(-STEPS_SHOWN);
  const liveMsg = m.status === 'sirada' || m.status === 'calisiyor';
  const motionProps = {
    initial: { opacity: 0, y: 8 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.28, ease: [0.22, 1, 0.36, 1] as const },
  };

  if (m.role === 'ben') {
    return (
      <motion.div className="komuta-msg is-me" {...motionProps}>
        {m.text}
      </motion.div>
    );
  }
  if (m.role === 'sistem') {
    return (
      <motion.div className="komuta-msg is-system" {...motionProps}>
        {m.text}
      </motion.div>
    );
  }
  return (
    <motion.div className="komuta-agent" {...motionProps}>
      {steps.length > 0 && (
        <div className="komuta-steps">
          {steps.length > STEPS_SHOWN && (
            <button type="button" className="komuta-steps__more" onClick={() => setAllSteps((v) => !v)}>
              {allSteps ? 'Son adımları göster' : `${steps.length - STEPS_SHOWN} adım daha`}
            </button>
          )}
          {shown.map((s, i) => {
            const [tool, ...rest] = s.split(': ');
            return (
              <div key={i} className="komuta-step">
                <span className={`komuta-step__tool is-${tool.toLowerCase()}`}>{tool}</span>
                <span className="komuta-step__target">{rest.join(': ')}</span>
              </div>
            );
          })}
        </div>
      )}
      {liveMsg ? (
        <div className="komuta-typing">
          <span className="komuta-typing__dot" aria-hidden />
          {m.status === 'sirada' ? 'Sırada — önceki iş bitince başlar' : m.last_step || 'Düşünüyor…'}
        </div>
      ) : (
        <div className={`komuta-msg is-agent ${m.status === 'hata' ? 'is-error' : ''}`}>
          <Rich text={m.text} />
          {(m.status === 'hata' || m.status === 'durdu') && <span className="komuta-msg__state">{MSG_STATUS[m.status]}</span>}
        </div>
      )}
      {m.status === 'onay' && (
        <div className="komuta-approval">
          <span className="label-micro">Onayını bekliyor</span>
          <p>{m.approval}</p>
          {isLast && (
            <div className="komuta-approval__actions">
              <button type="button" className="pano-btn is-primary" onClick={() => onAnswer(true)}>
                Onayla
              </button>
              <button type="button" className="pano-btn" onClick={() => onAnswer(false)}>
                Reddet
              </button>
            </div>
          )}
        </div>
      )}
      {!liveMsg && m.bekci && m.bekci.length > 0 && (
        <p className="komuta-guardnote">Bekçi yakaladı: {m.bekci.join(', ')}</p>
      )}
      {!liveMsg && m.at > 0 && <span className="komuta-msg__time">{ago(m.at, now)}</span>}
    </motion.div>
  );
}

// ── Sağ: senden bekleyenler, sıra, bekçi, 7/24 ─────────────────────────

function Pending({
  pano,
  chats,
  approvals,
  onOpenChat,
  onChanged,
  onAll,
}: {
  pano: PanoSnapshot | null;
  chats: ChatSummary[];
  approvals: { id: string; tool: string; what: string }[];
  onOpenChat: (c: ChatSummary) => void;
  onChanged: () => void;
  onAll: () => void;
}) {
  const [error, setError] = useState('');
  const [confirmGuard, setConfirmGuard] = useState(false);
  const cards = pano?.cards ?? [];
  const waitingCards = cards.filter((c) => c.status === 'onay' || c.status === 'birlestir');
  const waitingChats = chats.filter((c) => c.status === 'onay');
  const queue = cards.filter((c) => c.status === 'bekliyor').slice(0, 3);
  const total = waitingCards.length + waitingChats.length + approvals.length;

  const run = async (call: () => Promise<ApiResult<unknown>>) => {
    const result = await call();
    setError(result.success ? '' : result.message);
    onChanged();
  };

  const guard = pano?.bekci;
  const loop = pano?.dongu;
  const blocking = guard?.mod === 'engelle';
  const flipGuard = () => {
    if (blocking && !confirmGuard) return setConfirmGuard(true);
    setConfirmGuard(false);
    void run(() => setBekciMode(blocking ? 'uyar' : 'engelle'));
  };

  return (
    <>
      <div className="komuta-sep" />
      <div className="komuta-row">
        <span className="label-micro">Senden bekleyenler</span>
        <span className={`komuta-count ${total ? 'is-wait' : ''}`}>{total}</span>
      </div>
      {total === 0 && <p className="komuta-empty-line">Bekleyen yok. Ajanlar kendi işinde.</p>}
      <div className="komuta-pending">
        {waitingChats.map((c) => (
          <div key={c.id} className="komuta-wait is-wait">
            <span className="komuta-wait__tag">Sohbet</span>
            <p className="komuta-wait__title">{c.title}</p>
            <p className="komuta-wait__detail">{c.approval}</p>
            <button type="button" className="pano-btn is-primary" onClick={() => onOpenChat(c)}>
              Sohbeti aç
            </button>
          </div>
        ))}
        {waitingCards.map((c) => (
          <CardWait key={c.id} card={c} run={run} />
        ))}
        {approvals.map((a) => (
          <div key={a.id} className="komuta-wait is-wait">
            <span className="komuta-wait__tag">PC’deki Claude Code</span>
            <p className="komuta-wait__detail">
              <strong>{a.tool}</strong> {a.what}
            </p>
            <p className="komuta-empty-line">Onay o pencerede veriliyor.</p>
          </div>
        ))}
      </div>
      {error && <p className="komuta-notice">{error}</p>}

      <div className="komuta-row">
        <span className="label-micro">Sırada</span>
        <button type="button" className="pano-btn" onClick={onAll}>
          Tüm işler
        </button>
      </div>
      {queue.length === 0 ? (
        <p className="komuta-empty-line">Sıra boş.</p>
      ) : (
        <ul className="komuta-queue">
          {queue.map((c) => (
            <li key={c.id}>
              <span>{c.title}</span>
              <span className="komuta-queue__who">{c.agent === 'gemini' ? 'Gemini' : c.agent === 'codex' ? 'Terra' : 'Jarvis'}</span>
            </li>
          ))}
        </ul>
      )}

      <div className="komuta-sep" />
      {guard && (
        <div className="komuta-switch">
          <div>
            <strong>Bekçi</strong>
            <span>{confirmGuard ? 'Yalnız uyarıya dönülsün mü?' : blocking ? 'Tehlikeli adımı durdurur' : 'Kaydeder, durdurmaz'}</span>
          </div>
          <button type="button" className={`komuta-toggle ${blocking ? 'is-ok' : 'is-wait'}`} onClick={flipGuard}>
            {confirmGuard ? 'Evet, uyar' : blocking ? 'Engelliyor' : 'Uyarıyor'}
          </button>
        </div>
      )}
      {loop && (
        <div className="komuta-switch">
          <div>
            <strong>7/24 döngü</strong>
            <span>
              {loop.acik ? (loop.neden && loop.durum !== 'bekliyor' ? loop.neden : 'Sıradakileri kendisi başlatır') : 'Kartları sen başlatırsın'}
            </span>
          </div>
          <button
            type="button"
            className={`komuta-toggle ${loop.acik ? 'is-ok' : ''}`}
            onClick={() => void run(() => switchLoop(!loop.acik))}
          >
            {loop.acik ? 'Açık' : 'Kapalı'}
          </button>
        </div>
      )}
    </>
  );
}

function CardWait({ card, run }: { card: PanoCard; run: (call: () => Promise<ApiResult<unknown>>) => Promise<void> }) {
  const merge = card.status === 'birlestir';
  return (
    <div className={`komuta-wait ${merge ? 'is-ok' : 'is-wait'}`}>
      <span className="komuta-wait__tag">{merge ? 'Birleştir' : 'Onay'}</span>
      <p className="komuta-wait__title">{card.title}</p>
      <p className="komuta-wait__detail">
        {merge ? `${card.diff || 'değişiklik hazır'}${card.test?.ok ? ' · test ✓' : ''}` : card.approval}
      </p>
      <div className="komuta-approval__actions">
        <button
          type="button"
          className="pano-btn is-primary"
          onClick={() => void run(() => (merge ? mergeCard(card.id, true) : answerCard(card.id, true)))}
        >
          {merge ? 'Ana dala al' : 'Onayla'}
        </button>
        <button
          type="button"
          className="pano-btn"
          onClick={() => void run(() => (merge ? mergeCard(card.id, false) : answerCard(card.id, false)))}
        >
          Reddet
        </button>
      </div>
    </div>
  );
}
