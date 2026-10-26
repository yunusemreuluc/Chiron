'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { LuPlus } from 'react-icons/lu';
import {
  answerCard,
  cardAction,
  createCard,
  deleteCard,
  fetchPano,
  fetchRepos,
  mergeCard,
  planCard,
  setCardAgent,
  type CardAgent,
  type ClaudeQuota,
  type PanoAgents,
  type PanoRepo,
  type CardStatus,
  type PanoCard,
} from '@/services/panoApi';
import { ago, duration } from './format';

// Görev panosu — YAZILABİLİR (Ajan İstasyonu adım 1, 2026-10-25). Kart açılır,
// "Başlat" ile Claude'a gider; durum backend'de iş kuyruğundan türetilir
// (backend/core/pano.py). Eski gözlem panosu "Etkinlik" sekmesinde (TaskBoard).
// Yenileme: sekme açıkken 2 sn'de bir — kart sayısı küçük, WebSocket şart değil.

const POLL_MS = 2000;

const COLUMNS: { id: string; label: string; accepts: CardStatus[] }[] = [
  { id: 'bekliyor', label: 'Bekliyor', accepts: ['bekliyor'] },
  { id: 'calisiyor', label: 'Çalışıyor', accepts: ['planlaniyor', 'calisiyor', 'dogrulaniyor', 'bolundu'] },
  { id: 'onay', label: 'Onayını bekliyor', accepts: ['onay', 'birlestir'] },
  { id: 'durdu', label: 'Durdu / hata', accepts: ['duraklatildi', 'hata'] },
  { id: 'kapandi', label: 'Bitti', accepts: ['bitti', 'iptal'] },
];

const STATUS_TEXT: Record<CardStatus, string> = {
  bekliyor: 'Bekliyor',
  calisiyor: 'Çalışıyor',
  duraklatildi: 'Durduruldu',
  onay: 'Onay bekliyor',
  bitti: 'Bitti',
  iptal: 'Sonlandırıldı',
  hata: 'Hata',
  dogrulaniyor: 'Test ediliyor',
  birlestir: 'Birleştirme onayı',
  planlaniyor: 'Jarvis planlıyor',
  bolundu: 'Bölündü',
};

// Ekip adları ofisteki karakterlerle aynı (Notes/Plan-Ajan-Istasyonu.md).
const AGENT_TEXT: Record<CardAgent, string> = { claude: 'Claude', codex: 'Terra', gemini: 'Gemini' };
const AGENT_HINT: Record<CardAgent, string> = {
  claude: 'her iş: tasarım, çok dosyalı, zor',
  codex: 'Codex · tanımı net mekanik kod',
  gemini: 'yalnız okur, dosyaya dokunmaz',
};

// Claude'un özeti Markdown gelebiliyor; kartta düz metin gösterilir, `**` görünmesin.
function plain(text: string): string {
  return text
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/`([^`\n]+)`/g, '$1')
    .replace(/^#{1,6}\s+/gm, '');
}

function useNow(): number {
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => clearInterval(id);
  }, []);
  return now;
}

export function CardBoard() {
  const [cards, setCards] = useState<PanoCard[] | null>(null);
  const [agents, setAgents] = useState<PanoAgents>({});
  const [offline, setOffline] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const now = useNow();

  const apply = useCallback((data: { cards: PanoCard[]; agents?: PanoAgents } | null) => {
    if (data) {
      setCards(data.cards);
      setAgents(data.agents ?? {});
      setOffline(false);
    } else {
      setOffline(true);
    }
  }, []);

  const refresh = useCallback(() => fetchPano().then(apply), [apply]);

  useEffect(() => {
    let cancelled = false;
    const load = () =>
      void fetchPano().then((data) => {
        if (!cancelled) apply(data);
      });
    load();
    const id = setInterval(load, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [apply]);

  useEffect(() => {
    if (!notice) return;
    const id = setTimeout(() => setNotice(null), 4000);
    return () => clearTimeout(id);
  }, [notice]);

  // Her düğme aynı yoldan: istek → hata varsa söyle → panoyu tazele.
  const run = useCallback(
    async (work: () => Promise<{ success: boolean; message: string }>) => {
      const result = await work();
      if (!result.success) setNotice(result.message || 'İşlem yapılamadı.');
      await refresh();
      return result.success;
    },
    [refresh],
  );

  if (cards === null) {
    return (
      <div className="office-empty">
        <p>{offline ? 'Aıron backend’ine ulaşılamıyor.' : 'Pano yükleniyor…'}</p>
      </div>
    );
  }

  const byId = new Map(cards.map((c) => [c.id, c]));
  // Terra'nın kotası doluysa ne zamana kadar — seçimde ve kartta gösterilir.
  const codexUntil = agents.codex && !agents.codex.available ? (agents.codex.until ?? 0) : null;

  return (
    <div className="pano">
      <AnimatePresence>
        {notice && (
          <motion.div
            key="notice"
            className="pano-notice"
            role="status"
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
          >
            {notice}
          </motion.div>
        )}
      </AnimatePresence>
      {agents.claude && <QuotaStrip quota={agents.claude} codexUntil={codexUntil} />}
      <div className="office-board">
        {COLUMNS.map((col) => {
          const items = cards.filter((c) => col.accepts.includes(c.status));
          return (
            <section key={col.id} className={`office-board__col pano-col--${col.id}`}>
              <header>
                <span className="label-micro">{col.label}</span>
                <span className="office-board__count">{items.length}</span>
              </header>
              <div className="office-board__list">
                {col.id === 'bekliyor' && <Composer run={run} codexUntil={codexUntil} />}
                <AnimatePresence initial={false}>
                  {items.map((card) => (
                    <CardItem key={card.id} card={card} now={now} run={run} byId={byId} codexUntil={codexUntil} />
                  ))}
                </AnimatePresence>
                {!items.length && col.id !== 'bekliyor' && <p className="pano-col__empty">Boş</p>}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}

type Run = (work: () => Promise<{ success: boolean; message: string }>) => Promise<boolean>;

// Kota şeridi (adım 6): Claude'un gerçek doluluğu, %90'da yeni iş durur; Terra'nın kotası.
const QUOTA_TEXT: Record<ClaudeQuota['level'], string> = {
  ok: 'Kota rahat',
  info: 'Kotanın yarısı kullanıldı',
  warn: 'Kota azalıyor',
  stop: 'Yeni Claude işi durdu',
};

function QuotaStrip({ quota, codexUntil }: { quota: ClaudeQuota; codexUntil: number | null }) {
  const bar = (label: string, w?: { used: number; resets_at: number | null }) =>
    w && (
      <span className="pano-quota__win" title={w.resets_at ? `Sıfırlanma: ${new Date(w.resets_at * 1000).toLocaleString('tr-TR')}` : undefined}>
        <span>{label}</span>
        <span className="office-quota__track">
          <span className="office-quota__fill" style={{ width: `${Math.min(100, w.used * 100)}%` }} />
        </span>
        <span>%{Math.round(w.used * 100)}</span>
      </span>
    );
  return (
    <div className={`pano-quota is-${quota.level}`} role="status">
      <span className="label-micro">Claude</span>
      {bar('5 sa', quota.five_hour)}
      {bar('hafta', quota.seven_day)}
      <span className="pano-quota__note">{quota.level === 'stop' && quota.reason ? quota.reason : QUOTA_TEXT[quota.level]}</span>
      {codexUntil !== null && <span className="pano-quota__note is-muted">Terra uyuyor · kota {untilText(codexUntil)}</span>}
    </div>
  );
}

function untilText(ts: number): string {
  return ts ? new Date(ts * 1000).toLocaleDateString('tr-TR', { day: 'numeric', month: 'short' }) : 'bir süre';
}

function AgentOptions({ codexUntil }: { codexUntil: number | null }) {
  return (
    <>
      {(Object.keys(AGENT_TEXT) as CardAgent[]).map((a) => (
        <option key={a} value={a} disabled={a === 'codex' && codexUntil !== null}>
          {AGENT_TEXT[a]} · {a === 'codex' && codexUntil !== null ? `kota dolu, ${untilText(codexUntil)}` : AGENT_HINT[a]}
        </option>
      ))}
    </>
  );
}

function Composer({ run, codexUntil }: { run: Run; codexUntil: number | null }) {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState('');
  const [detail, setDetail] = useState('');
  const [repos, setRepos] = useState<PanoRepo[]>([]);
  const [repo, setRepo] = useState('');
  const [testCmd, setTestCmd] = useState('');
  const [agent, setAgent] = useState<CardAgent>('claude');
  const [busy, setBusy] = useState(false);
  const titleRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    titleRef.current?.focus();
    let cancelled = false;
    void fetchRepos().then((data) => {
      if (!cancelled && data) setRepos(data.repos);
    });
    return () => {
      cancelled = true;
    };
  }, [open]);

  const pickRepo = (path: string) => {
    setRepo(path);
    // Önerilen test komutu her seçimde yazılır; kullanıcı sonra değiştirebilir.
    setTestCmd(repos.find((r) => r.path === path)?.test_cmd ?? '');
  };

  const submit = async (andStart: boolean) => {
    if (!title.trim() || busy) return;
    setBusy(true);
    let createdId: string | null = null;
    const ok = await run(async () => {
      const result = await createCard(title, detail, repo, repo ? testCmd : '', agent);
      createdId = result.data?.card.id ?? null;
      return result;
    });
    if (ok && andStart && createdId) {
      const id: string = createdId;
      await run(() => cardAction(id, 'start'));
    }
    if (ok) {
      setTitle('');
      setDetail('');
      setRepo('');
      setTestCmd('');
      setAgent('claude');
      setOpen(false);
    }
    setBusy(false);
  };

  if (!open) {
    return (
      <button type="button" className="pano-new" onClick={() => setOpen(true)}>
        <LuPlus size={14} strokeWidth={2} />
        Yeni kart
      </button>
    );
  }

  return (
    <form
      className="pano-composer"
      onSubmit={(e) => {
        e.preventDefault();
        void submit(false);
      }}
      onKeyDown={(e) => {
        if (e.key === 'Escape') {
          e.stopPropagation();
          setOpen(false);
        }
      }}
    >
      <input
        id="pano-title"
        ref={titleRef}
        value={title}
        maxLength={200}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="Ne yapılsın?"
        aria-label="Kart başlığı"
      />
      <textarea
        id="pano-detail"
        value={detail}
        maxLength={3500}
        rows={4}
        onChange={(e) => setDetail(e.target.value)}
        placeholder="Ayrıntı: hangi proje, hangi dosyalar, bitince ne olmalı (isteğe bağlı)"
        aria-label="Kart ayrıntısı"
      />
      <label className="pano-field" htmlFor="pano-agent">
        <span className="label-micro">Kim yapsın · büyük işi Jarvis&apos;e böldürebilirsin</span>
        <select id="pano-agent" value={agent} onChange={(e) => setAgent(e.target.value as CardAgent)}>
          <AgentOptions codexUntil={codexUntil} />
        </select>
      </label>
      <label className="pano-field" htmlFor="pano-repo">
        <span className="label-micro">Proje</span>
        <select id="pano-repo" value={repo} onChange={(e) => pickRepo(e.target.value)}>
          <option value="">Proje yok · ana klasörde çalışsın</option>
          {repos.map((r) => (
            <option key={r.path} value={r.path}>
              {r.name}
            </option>
          ))}
        </select>
      </label>
      {repo && (
        <>
          <label className="pano-field" htmlFor="pano-test">
            <span className="label-micro">Test komutu · Aıron koşar</span>
            <input
              id="pano-test"
              value={testCmd}
              maxLength={500}
              onChange={(e) => setTestCmd(e.target.value)}
              placeholder="Boş bırakırsan test koşulmaz"
              spellCheck={false}
            />
          </label>
          <p className="pano-hint">
            İş bu projenin ayrı bir kopyasında yapılır. Test geçerse ana dala birleştirmeyi sen onaylarsın.
          </p>
        </>
      )}
      <div className="pano-actions">
        <button type="button" className="pano-btn is-primary" disabled={!title.trim() || busy} onClick={() => void submit(true)}>
          Aç ve başlat
        </button>
        <button type="submit" className="pano-btn" disabled={!title.trim() || busy}>
          Sadece aç
        </button>
        <button type="button" className="pano-btn is-quiet" onClick={() => setOpen(false)}>
          Vazgeç
        </button>
      </div>
    </form>
  );
}

function CardItem({
  card,
  now,
  run,
  byId,
  codexUntil,
}: {
  card: PanoCard;
  now: number;
  run: Run;
  byId: Map<string, PanoCard>;
  codexUntil: number | null;
}) {
  const [confirm, setConfirm] = useState<'stop' | 'delete' | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [busy, setBusy] = useState(false);

  const act = async (work: () => Promise<{ success: boolean; message: string }>) => {
    setBusy(true);
    await run(work);
    setConfirm(null);
    setBusy(false);
  };

  const s = card.status;
  const planning = s === 'planlaniyor';
  const live = s === 'calisiyor' || planning;
  const testing = s === 'dogrulaniyor';
  const agent = card.agent ?? 'claude';
  const blockedBy = (card.after ?? []).filter((id) => byId.get(id)?.status !== 'bitti');
  const kids = (card.children ?? []).map((id) => byId.get(id)).filter((k): k is PanoCard => Boolean(k));
  const meta = live
    ? card.queue_position
      ? `Sırada · ${card.queue_position}.`
      : `${duration(now - card.updated)} · ${card.steps} adım`
    : testing
      ? `${duration(now - card.updated)} · commit + test`
      : ago(card.updated, now);
  // Bölünmüş/planlanan kartta özet Jarvis'in ham JSON'u — gösterilmez, plan listesi var.
  const body = s === 'bolundu' || planning ? '' : plain(s === 'hata' ? card.error : card.summary);
  const repoName = card.repo ? card.repo.split(/[\\/]/).pop() : null;

  return (
    <motion.article
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.97 }}
      transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
      className={`office-task pano-card is-${s}`}
    >
      <span className="pano-card__head">
        <span className="office-task__id">{card.id}</span>
        <span className={`pano-chip is-${s}`}>
          {(live || testing) && <span className="pano-pulse" aria-hidden />}
          {card.stopping ? 'Durduruluyor…' : STATUS_TEXT[s]}
        </span>
      </span>
      <span className="office-task__title">{card.title}</span>
      <span className="office-task__meta">{meta}</span>

      <span className="office-task__chips pano-crew">
        <span className={`pano-agent is-${agent}`}>{planning || s === 'bolundu' ? 'Jarvis' : AGENT_TEXT[agent]}</span>
        {card.parent && <span title="Bu kart bir planın parçası">↳ {card.parent}</span>}
        {blockedBy.length > 0 && <span className="is-wait">{blockedBy.join(', ')} bitince</span>}
      </span>

      {s === 'bolundu' && (
        <div className="pano-plan">
          {card.plan_summary && <p>{plain(card.plan_summary)}</p>}
          <span className="label-micro">
            {kids.filter((k) => k.status === 'bitti').length}/{kids.length} bitti
          </span>
          <ul>
            {kids.map((k) => (
              <li key={k.id} className={`is-${k.status}`}>
                <span className="pano-plan__dot" aria-hidden />
                <span className="office-task__id">{k.id}</span>
                <span className="truncate">{k.title}</span>
                <span className={`pano-agent is-${k.agent ?? 'claude'}`}>{AGENT_TEXT[k.agent ?? 'claude']}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {repoName && (
        <span className="office-task__chips pano-repo">
          <span title={card.repo ?? ''}>{repoName}</span>
          {card.branch && !card.merged && <span title="Kartın dalı">{card.branch}</span>}
          {card.merged && <span className="is-green" title="Birleşme commit'i">birleşti · {card.merged}</span>}
          {card.test && (
            <span className={card.test.ok ? 'is-green' : 'is-red'} title={card.test.cmd}>
              test {card.test.ok ? '✓' : '✕'}
            </span>
          )}
        </span>
      )}

      {live && card.last_step && <span className="pano-card__step">{card.last_step}</span>}

      {s === 'birlestir' && (
        <div className={`pano-merge ${card.test ? 'is-tested' : ''}`}>
          <span className="label-micro">{card.test ? 'Test geçti · birleştirilsin mi?' : 'Test koşulmadı · birleştirilsin mi?'}</span>
          <p>
            {card.diff || 'Değişiklik özeti yok'} → <strong>{card.base_branch}</strong>
          </p>
        </div>
      )}

      {s === 'onay' && card.approval && (
        <div className="pano-approval">
          <span className="label-micro">Onayın isteniyor</span>
          <p>{card.approval}</p>
        </div>
      )}

      {body && s !== 'onay' && (
        <button
          type="button"
          className={`pano-card__body ${expanded ? 'is-open' : ''} ${s === 'hata' ? 'is-red' : ''}`}
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
        >
          {body}
        </button>
      )}

      {confirm ? (
        <div className="pano-actions">
          <span className="pano-confirm">
            {confirm === 'stop'
              ? 'İş sonlandırılsın mı?'
              : card.worktree
                ? 'Kart ve çalışma kopyası silinsin mi? Dal kalır.'
                : 'Kart silinsin mi?'}
          </span>
          <button
            type="button"
            className="pano-btn is-danger"
            disabled={busy}
            onClick={() => void act(() => (confirm === 'stop' ? cardAction(card.id, 'stop') : deleteCard(card.id)))}
          >
            Evet
          </button>
          <button type="button" className="pano-btn is-quiet" onClick={() => setConfirm(null)}>
            Hayır
          </button>
        </div>
      ) : (
        <div className="pano-actions">
          {s === 'bekliyor' && (
            <button
              type="button"
              className="pano-btn is-primary"
              disabled={busy || blockedBy.length > 0}
              title={blockedBy.length ? `Önce ${blockedBy.join(', ')} bitmeli` : undefined}
              onClick={() => void act(() => cardAction(card.id, 'start'))}
            >
              Başlat
            </button>
          )}
          {(s === 'bekliyor' || s === 'duraklatildi' || s === 'hata') && !card.planning && (
            <select
              className="pano-agent-pick"
              aria-label="Ajanı değiştir"
              value={agent}
              disabled={busy}
              onChange={(e) => void act(() => setCardAgent(card.id, e.target.value as CardAgent))}
            >
              <AgentOptions codexUntil={codexUntil} />
            </select>
          )}
          {s === 'bekliyor' && !card.parent && (
            <button type="button" className="pano-btn is-jarvis" disabled={busy} onClick={() => void act(() => planCard(card.id))}>
              Jarvis&apos;e böldür
            </button>
          )}
          {s === 'duraklatildi' && (
            <button type="button" className="pano-btn is-primary" disabled={busy} onClick={() => void act(() => cardAction(card.id, 'start'))}>
              Devam et
            </button>
          )}
          {s === 'hata' && (
            <button type="button" className="pano-btn is-primary" disabled={busy} onClick={() => void act(() => cardAction(card.id, 'start'))}>
              Yeniden dene
            </button>
          )}
          {s === 'onay' && (
            <>
              <button type="button" className="pano-btn is-ok" disabled={busy} onClick={() => void act(() => answerCard(card.id, true))}>
                Onayla
              </button>
              <button type="button" className="pano-btn" disabled={busy} onClick={() => void act(() => answerCard(card.id, false))}>
                Reddet
              </button>
            </>
          )}
          {s === 'birlestir' && (
            <>
              <button type="button" className="pano-btn is-ok" disabled={busy} onClick={() => void act(() => mergeCard(card.id, true))}>
                Birleştir
              </button>
              <button type="button" className="pano-btn" disabled={busy} onClick={() => void act(() => mergeCard(card.id, false))}>
                Reddet
              </button>
            </>
          )}
          {live && !planning && (
            <button
              type="button"
              className="pano-btn"
              disabled={busy || card.stopping}
              onClick={() => void act(() => cardAction(card.id, 'pause'))}
            >
              Durdur
            </button>
          )}
          {(live || s === 'onay' || s === 'duraklatildi' || s === 'hata') && (
            <button type="button" className="pano-btn is-quiet" disabled={busy || card.stopping} onClick={() => setConfirm('stop')}>
              Sonlandır
            </button>
          )}
          {!live && !testing && s !== 'bolundu' && (
            <button type="button" className="pano-btn is-quiet" disabled={busy} onClick={() => setConfirm('delete')}>
              Sil
            </button>
          )}
        </div>
      )}
    </motion.article>
  );
}
