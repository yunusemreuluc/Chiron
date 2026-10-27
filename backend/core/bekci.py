"""Bekçi: ajan işlerinin tehlikeli adımlarını yakalar (Ajan İstasyonu adım 7, 2026-10-26).

Esin: ruflo-protector (ruvnet/ruflo, MIT) — fikir alındı, kod yazıldı; kural listesi Chiron'a göre.

İki katman:
1. **Araç öncesi** (yalnız Claude işleri): `claude_jobs` her `claude -p`'yi `--settings <SETTINGS>`
   ile açar; o dosyadaki PreToolUse hook'u bu betiği çalıştırır (`python bekci.py`). Global
   `~/.claude/settings.json`'a DOKUNULMAZ — kullanıcının kendi oturumları etkilenmez, ayar
   dosyası da ajanın çalıştığı worktree'de değil. (2026-10-26 denendi: `-p` + `--settings`
   hook'u tetikleniyor, `deny` adımı durduruyor, `CHIRON_CLAUDE_JOB` hook'a geliyor.)
2. **Birleştirme öncesi** (bütün motorlar): pano kartı doğrulanırken worktree diff'i
   `scan_diff` ile taranır — Codex/Gemini'nin hook'u yok, onları bu katman görür.

Mod (kullanıcı kararı, plan § adım 7): önce öğren → uyar; engellemeyi Yunus açar.
- `uyar` (varsayılan): her araç çağrısı iş günlüğüne yazılır (öğrenme verisi), kurala
  takılan kartta uyarı olarak görünür; hiçbir şey durdurulmaz.
- `engelle`: `yuksek` seviyeli kurala takılan adım reddedilir, Claude gerekçeyi görür.

Hook hiçbir hatada işi durdurmaz (çıkış 0, kayıt `hata` satırı) — bekçinin kendi hatası
ajanı kilitlememeli. Yalnızca standart kütüphane: her araç çağrısında açılıyor.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[2]
BEKCI_DIR = BASE_DIR / "logs" / "bekci"
MODE_FILE = BEKCI_DIR / "mod.json"
SETTINGS_FILE = BEKCI_DIR / "settings.json"
MODES = ("uyar", "engelle")
HOOK_TIMEOUT = 10  # saniye; Claude Code bu süreden sonra hook'u bırakır
MAX_INPUT_LOG = 600  # günlüğe yazılan araç girdisi (karakter)
MAX_HITS = 50  # kart başına saklanan uyarı

# Ajanın yazma kökü (pano worktree'si). claude_jobs iş ortamına koyar; yoksa kural 4 bakmaz.
ROOT_ENV = "CHIRON_BEKCI_ROOT"
JOB_ENV = "CHIRON_CLAUDE_JOB"

SHELL_TOOLS = ("Bash", "PowerShell")
WRITE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")
READ_TOOLS = ("Read", "Grep", "Glob")

_I = re.IGNORECASE

# Gizli bilgi taşıyan dosyalar (okuma, yazma, kabuktan erişim).
_SECRET_PATH = re.compile(
    r"(^|[\\/\s\"'])(\.env(\.[\w-]+)?|id_(rsa|ed25519|ecdsa)|[\w-]*\.(pem|pfx|p12|key)|"
    r"credentials(\.json)?|\.netrc|\.npmrc|\.pypirc|token\.json|remote_auth\.json)([\s\"']|$)|"
    r"[\\/]\.ssh[\\/]|[\\/]rclone[\\/]rclone\.conf",
    _I,
)
# Ajanın kendi kafesini değiştirmesi: Claude/git hook'ları, global ayar, bekçinin dosyaları.
_GUARD_PATH = re.compile(
    r"[\\/]\.claude[\\/](settings(\.local)?\.json|hooks[\\/])|[\\/]\.git[\\/]hooks[\\/]|"
    r"[\\/]logs[\\/]bekci[\\/]|[\\/]backend[\\/]core[\\/]bekci\.py|[\\/]\.codex[\\/]config\.toml",
    _I,
)

# (id, seviye, ad, desen) — kabuk komutu (Bash/PowerShell) üstünde aranır.
SHELL_RULES: list[tuple[str, str, str, re.Pattern[str]]] = [
    (
        "toplu-silme",
        "yuksek",
        "Özyinelemeli / toplu silme",
        re.compile(
            r"\brm\s+(-\w*[rR]\w*|--recursive)|\bRemove-Item\b[^|;\n]*-Recurse|\b(rmdir|rd)\s+/s|"
            r"\bdel\s+(/\w\s+)*/s|\bshutil\.rmtree\b|\bfind\b[^|;\n]*-delete",
            _I,
        ),
    ),
    ("git-push", "yuksek", "git push (pano notu yasaklıyor)", re.compile(r"\bgit\s+(-\S+\s+(\S+\s+)?)*push\b", _I)),
    (
        "git-yikici",
        "yuksek",
        "Geri alınamayan git komutu",
        re.compile(
            r"\bgit\b[^|;&\n]*\b(reset\s+--hard|clean\s+-\w*f|checkout\s+--\s|restore\s+\.|branch\s+-D|"
            r"stash\s+(drop|clear)|filter-branch|update-ref\s+-d|reflog\s+expire)",
            _I,
        ),
    ),
    (
        "dis-gonderim",
        "yuksek",
        "Dışarı veri gönderme / yükleme",
        re.compile(
            r"\bcurl\b[^|;\n]*\s(-X\s*(POST|PUT|PATCH|DELETE)|-d\b|--data|-F\b|--form|-T\b|--upload-file)|"
            r"\b(Invoke-WebRequest|Invoke-RestMethod|iwr|irm)\b[^|;\n]*-Method\s+(Post|Put|Patch|Delete)|"
            r"\b(scp|sftp|ftp)\s|\brclone(\.exe)?\s+(copy|sync|move|copyto|moveto|delete|purge)\b|"
            r"\bgh\s+(pr|issue|release|gist|repo)\s+(create|edit|delete|merge|comment)|"
            r"\bSend-MailMessage\b|whatsapp-gonder",
            _I,
        ),
    ),
    (
        "indir-calistir",
        "yuksek",
        "İndirileni doğrudan çalıştırma",
        re.compile(
            r"\b(curl|wget)\b[^\n]*\|\s*(ba|z)?sh\b|\b(iwr|irm|Invoke-WebRequest|Invoke-RestMethod)\b[^\n]*\|\s*(iex|Invoke-Expression)|"
            r"\bInvoke-Expression\b.*\bDownloadString\b",
            _I,
        ),
    ),
    (
        "yayinlama",
        "yuksek",
        "Paket yayınlama / global kurulum",
        re.compile(
            r"\bnpm\s+(publish|unpublish)\b|\btwine\s+upload\b|\bpoetry\s+publish\b|\bcargo\s+publish\b|"
            r"\bnpm\s+(i|install|add)\b[^|;\n]*\s(-g|--global)\b|\bwinget\s+install\b|\bchoco\s+install\b",
            _I,
        ),
    ),
    (
        "sistem-ayari",
        "yuksek",
        "Sistem ayarı / zamanlanmış görev / kayıt defteri",
        re.compile(
            r"\breg(\.exe)?\s+(add|delete|import)\b|\b(Set|New|Remove)-ItemProperty\b[^|;\n]*\b(HKLM|HKCU)|"
            r"\bschtasks\b[^|;\n]*/(create|delete|change)|\bRegister-ScheduledTask\b|\bsc(\.exe)?\s+(create|config|delete)\b|"
            r"\bSet-ExecutionPolicy\b|\bnetsh\b|\b(shutdown|Stop-Computer|Restart-Computer)\b|\bformat\s+[a-z]:|\bdiskpart\b|"
            r"\bsetx\b|\[Environment\]::SetEnvironmentVariable",
            _I,
        ),
    ),
    (
        "surec-oldurme",
        "orta",
        "Ada göre süreç öldürme (Chiron'u da vurabilir)",
        re.compile(r"\btaskkill\b[^|;\n]*/im\b|\bStop-Process\b[^|;\n]*-Name\b|\b(pkill|killall)\b", _I),
    ),
    (
        "izin-atlatma",
        "yuksek",
        "İzin / sandbox atlatma",
        re.compile(
            r"--dangerously-skip-permissions|--permission-mode\s+bypassPermissions|danger-full-access|"
            r"--yolo\b|--no-verify\b|--approval-mode\s+yolo",
            _I,
        ),
    ),
    (
        "gizli-ortam",
        "orta",
        "Ortam değişkenlerini / anahtarları dökme",
        re.compile(
            r"(^|[;&|]\s*)(env|printenv|set)\s*($|[;&|>])|\bGet-ChildItem\s+env:|\bgci\s+env:|\bdir\s+env:|"
            r"\$env:\w*(KEY|TOKEN|SECRET|PASSWORD)\w*|\bGetEnvironmentVariable\(\s*['\"]\w*(KEY|TOKEN|SECRET)",
            _I,
        ),
    ),
]

# Bütün kuralların listesi (arayüz ve günlük için). Kabuk dışı kurallar `check` içinde.
RULES: dict[str, tuple[str, str]] = {rid: (level, name) for rid, level, name, _ in SHELL_RULES}
RULES.update(
    {
        "kok-disi-yazma": ("yuksek", "Çalışma kopyası dışına yazma"),
        "gizli-dosya": ("yuksek", "Gizli bilgi dosyasına erişim"),
        "kafes": ("yuksek", "Ajanın kendi ayarını / hook'unu / bekçiyi değiştirmesi"),
    }
)


def _norm(path: str) -> str:
    return os.path.normcase(os.path.normpath(path))


def _inside(full: str, root: str) -> bool:
    return full == root or full.startswith(root.rstrip("\\/") + os.sep)


# Kök dışında olsa da serbest: Claude'un kendi hafızası ve oturum geçici klasörü.
_ALLOWED_ROOTS = (
    Path.home() / ".claude" / "projects",
    Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "Temp" / "claude",
)


def _outside(path: str, root: str, cwd: str) -> bool:
    if not path:
        return False
    full = _norm(path if os.path.isabs(path) else os.path.join(cwd or root, path))
    if any(_inside(full, _norm(str(allowed))) for allowed in _ALLOWED_ROOTS):
        return False
    return not _inside(full, _norm(root))


def check(tool: str, tool_input: dict[str, Any], *, root: str | None = None, cwd: str = "") -> list[tuple[str, str, str]]:
    """Bir araç çağrısının takıldığı kurallar: [(id, seviye, ad)]. Saf fonksiyon (testlenir)."""
    hits: list[str] = []
    if tool in SHELL_TOOLS:
        command = str(tool_input.get("command") or "")
        hits += [rid for rid, _, _, pattern in SHELL_RULES if pattern.search(command)]
        if _SECRET_PATH.search(command):
            hits.append("gizli-dosya")
        if _GUARD_PATH.search(command):
            hits.append("kafes")
    elif tool in WRITE_TOOLS or tool in READ_TOOLS:
        path = str(tool_input.get("file_path") or tool_input.get("notebook_path") or tool_input.get("path") or "")
        probe = " " + path.replace("/", "\\") + " "
        if _SECRET_PATH.search(probe):
            hits.append("gizli-dosya")
        if tool in WRITE_TOOLS:
            if _GUARD_PATH.search(probe):
                hits.append("kafes")
            if root and _outside(path, root, cwd):
                hits.append("kok-disi-yazma")
    return [(rid, *RULES[rid]) for rid in dict.fromkeys(hits)]


# ── Mod ──────────────────────────────────────────────────────────────────
def get_mode() -> str:
    try:
        mode = json.loads(MODE_FILE.read_text(encoding="utf-8")).get("mod")
    except (OSError, ValueError, AttributeError):
        return "uyar"
    return mode if mode in MODES else "uyar"


def set_mode(mode: str) -> str:
    if mode not in MODES:
        raise ValueError(f"Bilinmeyen bekçi modu: {mode}")
    BEKCI_DIR.mkdir(parents=True, exist_ok=True)
    MODE_FILE.write_text(json.dumps({"mod": mode, "at": time.time()}), encoding="utf-8")
    return mode


# ── claude_jobs için ─────────────────────────────────────────────────────
def settings_path() -> Path:
    """`claude -p --settings` dosyası; her açılışta yeniden yazılır (Python yolu değişmiş olabilir)."""
    BEKCI_DIR.mkdir(parents=True, exist_ok=True)
    python = Path(sys.executable).as_posix()
    script = Path(__file__).resolve().as_posix()
    hook = {"type": "command", "command": f'"{python}" "{script}"', "timeout": HOOK_TIMEOUT}
    data = {"hooks": {"PreToolUse": [{"matcher": "*", "hooks": [hook]}]}}
    text = json.dumps(data, indent=2)
    if not SETTINGS_FILE.exists() or SETTINGS_FILE.read_text(encoding="utf-8") != text:
        SETTINGS_FILE.write_text(text, encoding="utf-8")
    return SETTINGS_FILE


def _job_log(job_id: str) -> Path:
    safe = re.sub(r"[^\w-]", "_", job_id)[:64] or "bilinmeyen"
    return BEKCI_DIR / f"{safe}.jsonl"


def job_hits(job_id: str) -> list[dict[str, Any]]:
    """İşin günlüğünden kurala takılan satırlar (kartta gösterilir)."""
    hits: list[dict[str, Any]] = []
    try:
        lines = _job_log(job_id).read_text(encoding="utf-8").splitlines()
    except OSError:
        return hits
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        for rule in row.get("kurallar") or []:
            hits.append(
                {
                    "kural": rule["id"],
                    "seviye": rule["seviye"],
                    "ad": rule["ad"],
                    "arac": row.get("arac", ""),
                    "girdi": row.get("girdi", ""),
                    "engellendi": bool(row.get("engellendi")),
                    "at": row.get("at"),
                    "katman": "arac",
                }
            )
    return hits[-MAX_HITS:]


# ── Birleştirme öncesi tarama ────────────────────────────────────────────
_SECRET_VALUE = re.compile(
    r"(sk-(ant-|proj-)?[A-Za-z0-9_-]{20,}|AIza[0-9A-Za-z_-]{30,}|gh[pousr]_[A-Za-z0-9]{30,}|"
    r"xox[abpr]-[A-Za-z0-9-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|AKIA[0-9A-Z]{16}|"
    r"\b(api[_-]?key|secret|password|token)\b\s*[:=]\s*['\"][^'\"\s]{12,}['\"])",
    _I,
)
_CI_PATH = re.compile(r"^(\.github/workflows/|\.gitlab-ci|azure-pipelines|\.husky/)", _I)


def scan_diff(diff: str) -> list[dict[str, Any]]:
    """`git diff` metninde: eklenen gizli değer, kafes/CI/gizli dosyası değişikliği. Her motor için."""
    hits: list[dict[str, Any]] = []
    current = ""

    def add(rid: str, level: str, name: str, detail: str) -> None:
        hits.append(
            {"kural": rid, "seviye": level, "ad": name, "arac": "diff", "girdi": detail[:200],
             "engellendi": False, "at": time.time(), "katman": "diff"}
        )

    for line in diff.splitlines():
        if line.startswith("+++ "):
            current = line[4:].removeprefix("b/").strip()
            probe = " \\" + current.replace("/", "\\") + " "
            if current == "/dev/null":
                continue
            if _SECRET_PATH.search(probe):
                add("gizli-dosya", "yuksek", RULES["gizli-dosya"][1], current)
            if _GUARD_PATH.search(probe):
                add("kafes", "yuksek", RULES["kafes"][1], current)
            if _CI_PATH.search(current):
                add("ci-degisikligi", "orta", "CI / git hook dosyası değişti", current)
        elif line.startswith("+") and not line.startswith("+++") and _SECRET_VALUE.search(line):
            add("gizli-deger", "yuksek", "Koda gizli anahtar / parola eklendi", f"{current}: {_mask(line[1:])}")
    return hits[:MAX_HITS]


def _mask(text: str) -> str:
    """Günlüğe / karta anahtarın kendisi yazılmasın."""
    return _SECRET_VALUE.sub(lambda m: m.group(0)[:6] + "…", text.strip())[:200]


# ── Hook girişi ──────────────────────────────────────────────────────────
def _short_input(tool_input: dict[str, Any]) -> str:
    value = tool_input.get("command") or tool_input.get("file_path") or tool_input.get("notebook_path") \
        or tool_input.get("path") or tool_input.get("pattern") or tool_input.get("url") or ""
    return _mask(str(value))[:MAX_INPUT_LOG]


def run_hook(raw: str, env: dict[str, str]) -> dict[str, Any] | None:
    """Claude Code'un PreToolUse girdisi → günlük satırı; engelle modunda red cevabı."""
    data = json.loads(raw or "{}")
    tool = str(data.get("tool_name") or "")
    tool_input = data.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        tool_input = {}
    hits = check(tool, tool_input, root=env.get(ROOT_ENV) or None, cwd=str(data.get("cwd") or ""))
    mode = get_mode()
    blocked = [h for h in hits if h[1] == "yuksek"] if mode == "engelle" else []
    row = {
        "at": time.time(),
        "arac": tool,
        "girdi": _short_input(tool_input),
        "kurallar": [{"id": rid, "seviye": level, "ad": name} for rid, level, name in hits],
        "mod": mode,
        "engellendi": bool(blocked),
    }
    BEKCI_DIR.mkdir(parents=True, exist_ok=True)
    with _job_log(env.get(JOB_ENV) or "elle").open("a", encoding="utf-8") as log:
        log.write(json.dumps(row, ensure_ascii=False) + "\n")
    if not blocked:
        return None
    names = ", ".join(name for _, _, name in blocked)
    reason = (
        f"Chiron bekçisi bu adımı durdurdu ({names}). Bu adımı yapma; gerekiyorsa son mesajını "
        "'ONAY_GEREKLI: <ne yapacağın>' satırıyla bitir, Yunus karar versin."
    )
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}


def main() -> int:
    try:
        # Windows'ta varsayılan cp1254; Claude Code girdi ve cevabı UTF-8 bekliyor (gerekçede Türkçe var).
        sys.stdin.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        answer = run_hook(sys.stdin.read(), dict(os.environ))
    except Exception as error:  # bekçinin hatası ajanı durdurmasın
        try:
            BEKCI_DIR.mkdir(parents=True, exist_ok=True)
            with (BEKCI_DIR / "hata.log").open("a", encoding="utf-8") as log:
                log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {type(error).__name__}: {error}\n")
        except OSError:
            pass
        return 0
    if answer:
        sys.stdout.write(json.dumps(answer, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
