'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { LuCheck, LuGitMerge, LuMessageSquare, LuShieldAlert, LuX } from 'react-icons/lu';
import {
  answerCard,
  fetchCardChanges,
  fetchPano,
  mergeCard,
  type CardChanges,
  type PanoCard,
} from '@/services/panoApi';
import { fetchChats, type ChatSummary } from '@/services/sohbetApi';
import { useNavigationStore } from '@/stores/navigationStore';
import { useOfficeStore } from '@/stores/officeStore';

// Ana ekrandaki onay merkezi (2026-11-04, kullanıcı isteği): Komuta'daki "Senden bekleyenler"
// ana ekranda da görünsün, tıklayınca pencere açılsın, birleştirme oradan yapılsın.
// Pencere kartın gerçek değişikliğini gösterir (dosya listesi + diff, /api/pano/{id}/changes) —
// "Ana dala al"a basmadan neyin geleceği görülür. Sohbet onayı Komuta'da verilir (oturum orada).

const POLL_MS = 6000;

type Item = { kind: 'card'; card: PanoCard } | { kind: 'chat'; chat: ChatSummary };

function usePending() {
  const [cards, setCards] = useState<PanoCard[]>([]);
  const [chats, setChats] = useState<ChatSummary[]>([]);
  const refresh = useCallback(
    () =>
      Promise.all([fetchPano(), fetchChats()]).then(([pano, list]) => {
        if (pano) setCards(pano.cards.filter((c) => c.status === 'birlestir' || c.status === 'onay'));
        if (list) setChats(list.chats.filter((c) => c.status === 'onay'));
      }),
    [],
  );
  useEffect(() => {
    void refresh();
    const id = setInterval(() => {
      if (document.visibilityState === 'visible') void refresh();
    }, POLL_MS);
    return () => clearInterval(id);
  }, [refresh]);
  const items: Item[] = [
    ...cards.map((card) => ({ kind: 'card' as const, card })),
    ...chats.map((chat) => ({ kind: 'chat' as const, chat })),
  ];
  return { items, refresh };
}

function openChat(chatId: string) {
  const office = useOfficeStore.getState();
  office.setPendingChat(chatId);
  office.setFocusSession(null);
  office.setTab('komuta');
  if (useNavigationStore.getState().activeModule !== 'agents') useNavigationStore.getState().toggleModule('agents');
}

// ── Ana ekrandaki kutu ────────────────────────────────────────────────

export function OnayKutusu() {
  const { items, refresh } = usePending();
  const [openId, setOpenId] = useState<string | null>(null);
  const open = items.find((i) => i.kind === 'card' && i.card.id === openId);

  return (
    <>
      <AnimatePresence>
        {items.length > 0 && (
          <motion.section
            key="onay-kutusu"
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
            className="onay-box surface-card"
            aria-label="Senden bekleyenler"
          >
            <header className="onay-box__head">
              <span className="onay-box__pulse" aria-hidden />
              <span className="label-micro">Senden bekleyenler</span>
              <span className="onay-box__count">{items.length}</span>
            </header>
            <ul className="onay-box__list">
              {items.slice(0, 4).map((item) =>
                item.kind === 'card' ? (
                  <li key={item.card.id}>
                    <button type="button" className="onay-row" onClick={() => setOpenId(item.card.id)}>
                      <span className={`onay-row__tag ${item.card.status === 'birlestir' ? 'is-ok' : 'is-wait'}`}>
                        {item.card.status === 'birlestir' ? <LuGitMerge size={11} /> : <LuShieldAlert size={11} />}
                        {item.card.status === 'birlestir' ? 'Birleştir' : 'Onay'}
                      </span>
                      <span className="onay-row__title">{item.card.title}</span>
                      <span className="onay-row__meta">
                        {item.card.status === 'birlestir'
                          ? `${shortDiff(item.card.diff)}${item.card.test?.ok ? ' · test ✓' : ''}`
                          : item.card.approval || 'Onay bekliyor'}
                      </span>
                    </button>
                  </li>
                ) : (
                  <li key={item.chat.id}>
                    <button type="button" className="onay-row" onClick={() => openChat(item.chat.id)}>
                      <span className="onay-row__tag is-wait">
                        <LuMessageSquare size={11} />
                        Sohbet
                      </span>
                      <span className="onay-row__title">{item.chat.title}</span>
                      <span className="onay-row__meta">{item.chat.approval || 'Komuta’da onay bekliyor'}</span>
                    </button>
                  </li>
                ),
              )}
            </ul>
            {items.length > 4 && <p className="onay-box__more">+{items.length - 4} daha · Komuta’da</p>}
          </motion.section>
        )}
      </AnimatePresence>
      <AnimatePresence>
        {open && open.kind === 'card' && (
          <OnayPenceresi
            key={open.card.id}
            card={open.card}
            onClose={() => setOpenId(null)}
            onDone={() => {
              setOpenId(null);
              void refresh();
            }}
          />
        )}
      </AnimatePresence>
    </>
  );
}

function shortDiff(diff?: string): string {
  if (!diff) return 'değişiklik hazır';
  const m = diff.match(/(\d+) files? changed(?:, (\d+) insertions?\(\+\))?(?:, (\d+) deletions?\(-\))?/);
  if (!m) return diff;
  return `${m[1]} dosya${m[2] ? ` · +${m[2]}` : ''}${m[3] ? ` −${m[3]}` : ''}`;
}

// ── Pencere ───────────────────────────────────────────────────────────

interface FilePatch {
  path: string;
  lines: string[];
}

function splitPatch(patch: string): FilePatch[] {
  const out: FilePatch[] = [];
  for (const chunk of patch.split(/^(?=diff --git )/m)) {
    if (!chunk.startsWith('diff --git ')) continue;
    const lines = chunk.replace(/\n$/, '').split('\n');
    const plus = lines.find((l) => l.startsWith('+++ '));
    const minus = lines.find((l) => l.startsWith('--- '));
    const raw = plus && plus !== '+++ /dev/null' ? plus.slice(4) : minus ? minus.slice(4) : lines[0].split(' b/')[1] ?? '';
    out.push({ path: raw.replace(/^[ab]\//, ''), lines: lines.filter((l) => !/^(diff --git|index |--- |\+\+\+ )/.test(l)) });
  }
  return out;
}

function lineClass(line: string): string {
  if (line.startsWith('@@')) return 'is-hunk';
  if (line.startsWith('+')) return 'is-add';
  if (line.startsWith('-')) return 'is-del';
  if (/^(new file|deleted file|rename |similarity |Binary )/.test(line)) return 'is-note';
  return '';
}

function OnayPenceresi({ card, onClose, onDone }: { card: PanoCard; onClose: () => void; onDone: () => void }) {
  const merge = card.status === 'birlestir';
  const [changes, setChanges] = useState<CardChanges | null>(null);
  const [loadError, setLoadError] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [confirmReject, setConfirmReject] = useState(false);
  const [showTest, setShowTest] = useState(false);
  const diffRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!merge) return;
    let alive = true;
    void fetchCardChanges(card.id).then((res) => {
      if (!alive) return;
      if (res.success && res.data) setChanges(res.data);
      else setLoadError(res.message || 'Değişiklikler okunamadı.');
    });
    return () => {
      alive = false;
    };
  }, [card.id, merge]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !busy) onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [busy, onClose]);

  const files = useMemo(() => (changes ? splitPatch(changes.patch) : []), [changes]);

  const act = async (approved: boolean) => {
    if (!approved && !confirmReject) return setConfirmReject(true);
    setBusy(true);
    setError('');
    const res = merge ? await mergeCard(card.id, approved) : await answerCard(card.id, approved);
    setBusy(false);
    if (!res.success) return setError(res.message || 'İşlem yapılamadı.');
    // Çakışmada backend kartı `hata`ya alır ama başarı döner — sessizce kapatma, söyle.
    if (approved && merge && res.data?.card.status === 'hata') return setError(res.data.card.error);
    onDone();
  };

  const jump = (i: number) => {
    diffRef.current?.querySelector(`[data-file="${i}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const totals = changes?.files.reduce(
    (acc, f) => ({ add: acc.add + (f.added ?? 0), del: acc.del + (f.removed ?? 0) }),
    { add: 0, del: 0 },
  );
  const guardHits = card.bekci ?? [];

  return createPortal(
    <motion.div
      className="onay-modal"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.2 }}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !busy) onClose();
      }}
    >
      <motion.div
        role="dialog"
        aria-modal="true"
        aria-labelledby="onay-modal-title"
        className="onay-modal__panel"
        initial={{ opacity: 0, y: 14, scale: 0.985 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 8, scale: 0.99 }}
        transition={{ duration: 0.32, ease: [0.22, 1, 0.36, 1] }}
      >
        <header className="onay-modal__head">
          <div className="onay-modal__headline">
            <span className={`onay-row__tag ${merge ? 'is-ok' : 'is-wait'}`}>
              {merge ? <LuGitMerge size={11} /> : <LuShieldAlert size={11} />}
              {merge ? 'Birleştir' : 'Onay'}
            </span>
            <span className="onay-modal__id">{card.id}</span>
          </div>
          <button type="button" className="onay-modal__close" onClick={onClose} disabled={busy} aria-label="Kapat">
            <LuX size={15} />
          </button>
        </header>
        <h2 id="onay-modal-title" className="onay-modal__title">
          {card.title}
        </h2>
        {merge && card.branch && (
          <p className="onay-modal__branch">
            <code>{card.branch}</code> → <code>{card.base_branch || 'ana dal'}</code>
            {card.repo && <span> · {card.repo.split(/[\\/]/).pop()}</span>}
          </p>
        )}

        <div className="onay-modal__body">
          {(card.summary || card.detail) && (
            <section className="onay-sec">
              <span className="label-micro">Ne yapıldı</span>
              <p className="onay-sec__text">{card.summary || card.detail}</p>
            </section>
          )}

          {!merge && (
            <section className="onay-sec">
              <span className="label-micro">İstenen onay</span>
              <p className="onay-sec__text onay-sec__text--wait">{card.approval || 'Ajan devam etmek için onay bekliyor.'}</p>
            </section>
          )}

          {merge && (
            <section className="onay-sec onay-stats">
              <div className={`onay-stat ${card.test ? (card.test.ok ? 'is-ok' : 'is-err') : ''}`}>
                <span className="label-micro">Test</span>
                <strong>{card.test ? (card.test.ok ? 'Geçti' : `Kaldı (${card.test.code ?? '—'})`) : 'Koşulmadı'}</strong>
                {card.test?.tail && (
                  <button type="button" className="onay-link" onClick={() => setShowTest((v) => !v)}>
                    {showTest ? 'Çıktıyı gizle' : 'Çıktıyı göster'}
                  </button>
                )}
              </div>
              <div className="onay-stat">
                <span className="label-micro">Dosya</span>
                <strong>{changes ? changes.files.length : '…'}</strong>
              </div>
              <div className="onay-stat">
                <span className="label-micro">Satır</span>
                <strong>
                  {totals ? (
                    <>
                      <span className="is-add">+{totals.add}</span> <span className="is-del">−{totals.del}</span>
                    </>
                  ) : (
                    '…'
                  )}
                </strong>
              </div>
              <div className={`onay-stat ${guardHits.length ? 'is-wait' : 'is-ok'}`}>
                <span className="label-micro">Bekçi</span>
                <strong>{guardHits.length ? `${guardHits.length} uyarı` : 'Temiz'}</strong>
              </div>
            </section>
          )}

          {showTest && card.test && (
            <pre className="onay-pre">
              <span className="onay-pre__cmd">$ {card.test.cmd}</span>
              {'\n'}
              {card.test.tail}
            </pre>
          )}

          {guardHits.length > 0 && (
            <section className="onay-sec">
              <span className="label-micro">Bekçinin gördükleri</span>
              <ul className="onay-guard">
                {guardHits.map((h, i) => (
                  <li key={i} className={h.seviye === 'yuksek' ? 'is-err' : 'is-wait'}>
                    <strong>{h.ad}</strong>
                    <span>{h.girdi}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {merge && (
            <section className="onay-sec onay-changes">
              {loadError && <p className="onay-error">{loadError}</p>}
              {!changes && !loadError && <p className="onay-muted">Değişiklikler okunuyor…</p>}
              {changes && (
                <div className="onay-changes__grid">
                  <ul className="onay-files" aria-label="Değişen dosyalar">
                    {changes.files.map((f, i) => (
                      <li key={f.path}>
                        <button type="button" onClick={() => jump(i)} title={f.path}>
                          <span className="onay-files__path">{f.path}</span>
                          <span className="onay-files__num">
                            {f.added === null ? (
                              'ikili'
                            ) : (
                              <>
                                <span className="is-add">+{f.added}</span> <span className="is-del">−{f.removed}</span>
                              </>
                            )}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                  <div className="onay-diff" ref={diffRef}>
                    {files.map((f, i) => (
                      <div key={`${f.path}-${i}`} className="onay-diff__file" data-file={i}>
                        <div className="onay-diff__name">{f.path}</div>
                        <pre>
                          {f.lines.map((l, j) => (
                            <span key={j} className={`onay-diff__line ${lineClass(l)}`}>
                              {l || ' '}
                              {'\n'}
                            </span>
                          ))}
                        </pre>
                      </div>
                    ))}
                    {changes.truncated && <p className="onay-muted">Diff çok uzun, kesildi.</p>}
                  </div>
                </div>
              )}
            </section>
          )}
        </div>

        <footer className="onay-modal__foot">
          {error && <p className="onay-error">{error}</p>}
          <div className="onay-modal__actions">
            <button type="button" className="pano-btn" onClick={() => void act(false)} disabled={busy}>
              {confirmReject ? (merge ? 'Evet, reddet (kopya silinir)' : 'Evet, reddet') : 'Reddet'}
            </button>
            <button type="button" className="pano-btn is-primary onay-modal__go" onClick={() => void act(true)} disabled={busy}>
              {merge ? <LuGitMerge size={13} /> : <LuCheck size={13} />}
              {busy ? 'Yapılıyor…' : merge ? 'Ana dala al' : 'Onayla'}
            </button>
          </div>
        </footer>
      </motion.div>
    </motion.div>,
    document.body,
  );
}
