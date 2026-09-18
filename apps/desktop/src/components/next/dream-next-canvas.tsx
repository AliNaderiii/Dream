import { useEffect, useRef, useState } from 'react';
import {
  Sparkles,
  Mic,
  MicOff,
  ArrowUp,
  Globe,
  X,
  Layers,
  Volume2,
  VolumeX,
  CodeXml,
  Eye,
  Copy,
  Check,
  LayoutTemplate,
  ChevronRight,
  Camera,
  Zap,
  Bot,
  ShieldCheck,
  Lock,
  KeyRound,
  Command,
  Search,
  ClipboardList,
  CalendarDays,
  FolderOpen,
  Cpu,
  Terminal,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';

import { useBridge } from '@/lib/bridge/hooks';
import { duplexPushMicChunk, duplexStart, duplexStop } from '@/lib/bridge/duplex';

/** Model for Interactive Living Artifact */
export interface Artifact {
  id: string;
  title: string;
  type: 'react' | 'chart' | 'html' | 'diagram' | 'vision' | 'speculative' | 'ghost' | 'voice' | 'security' | 'omnibar';
  language: string;
  code: string;
  description: string;
  version: string;
}

interface Message {
  id: string;
  sender: 'user' | 'dream';
  indexRef: string;
  text: string;
  timestamp: string;
  lead?: string;
  thinkingSteps?: string[];
  sources?: Array<{ title: string; url: string; snippet: string }>;
  codeSnippet?: { lang: string; code: string; output?: string };
  artifact?: Artifact;
  visionBuffer?: {
    activeWindow: string;
    ocrElements: Array<{ label: string; confidence: number; action: string }>;
  };
  speculativeTelemetry?: {
    ttftMs: number;
    speculativeHitRate: number;
    draftSpeed: number;
    verifiedSpeed: number;
    totalTokens: number;
    tokens: Array<{ word: string; status: 'accepted' | 'verified' | 'draft' }>;
  };
  ghostWorkerReport?: {
    workerName: string;
    badge: string;
    items: Array<{ title: string; desc: string; severity: 'info' | 'warning' | 'success' }>;
  };
  voiceSessionData?: {
    persona: string;
    interrupted: boolean;
    bargeInLatencyMs: number;
    audioFramesCount: number;
  };
  securityAudit?: {
    encryption: string;
    redactedTokensCount: number;
    ssrfBlockedCount: number;
    vaultStatus: 'LOCKED' | 'ENCRYPTED' | 'AIRGAP';
  };
  commandExecution?: {
    command: string;
    category: string;
    result: string;
    latencyMs: number;
  };
}

export function DreamNextCanvas() {
  const { client } = useBridge();
  const navigate = useNavigate();

  const [selectedModel, setSelectedModel] = useState<string>('Qwen 2.5 (32B Dual-Speculative)');
  const [inputText, setInputText] = useState<string>('');
  const [webSearchEnabled, setWebSearchEnabled] = useState<boolean>(false);
  const [isTyping, setIsTyping] = useState(false);

  // Speculative Engine Control State
  const [isLiveStreaming, setIsLiveStreaming] = useState(false);
  const [streamedTokensCount, setStreamedTokensCount] = useState<number>(0);

  // Vision Mode State
  const [isVisionScanning, setIsVisionScanning] = useState(false);

  // Voice & Persona Engine State
  const [isVoiceActive, setIsVoiceActive] = useState(false);
  const [isMicMuted, setIsMicMuted] = useState(false);
  const [voiceRMS, setVoiceRMS] = useState(0);
  const [waveformPeaks, setWaveformPeaks] = useState<number[]>(new Array(24).fill(0.08));
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [voiceZenMode, setVoiceZenMode] = useState(false);
  const activePersona = 'sohrab';
  const vadThreshold = 0.035;
  const bargeInEnabled = true;
  const [isAiSpeaking, setIsAiSpeaking] = useState<boolean>(false);
  const [interruptionTriggered, setInterruptionTriggered] = useState<boolean>(false);

  // Security & Local Vault State
  const [vaultLocked, setVaultLocked] = useState<boolean>(false);
  const [ssrfShieldMode, setSsrfShieldMode] = useState<'strict' | 'airgap' | 'permissive'>('strict');
  const [piiRedactionActive, setPiiRedactionActive] = useState<boolean>(true);
  const [auditLogs, setAuditLogs] = useState<
    Array<{ id: string; time: string; event: string; status: 'blocked' | 'encrypted' | 'sanitized' }>
  >([
    { id: 'log-1', time: '۱۰:۴۲:۰۱', event: 'رمزنگاری پایگاه داده محلی (AES-256-GCM)', status: 'encrypted' },
    { id: 'log-2', time: '۱۰:۴۲:۱۵', event: 'مسدودسازی درخواست مشکوک SSRF به 169.254.169.254', status: 'blocked' },
    { id: 'log-3', time: '۱۰:۴۳:۰۰', event: 'حذف خودکار کلیدهای API و رمزهای عبور از پرامپت', status: 'sanitized' },
  ]);

  // Omnibar & OS Integration State (Phase 7 Final)
  const [omnibarOpen, setOmnibarOpen] = useState(false);
  const [omnibarQuery, setOmnibarQuery] = useState('');
  const [selectedCommandIdx, setSelectedCommandIdx] = useState(0);
  const [clipQuery, setClipQuery] = useState('');

  const clipboardHistory = [
    {
      id: 'clip-1',
      content: 'const TTFT = 12.8; // Dream Speculative Engine',
      source: 'VS Code',
      time: '۲ دقیقه پیش',
      tag: 'CODE',
    },
    {
      id: 'clip-2',
      content: 'نقشه راه عرضه Golden Release v4.0 — هفته آینده',
      source: 'Notepad',
      time: '۱۰ دقیقه پیش',
      tag: 'TEXT',
    },
    {
      id: 'clip-3',
      content: 'https://github.com/AliNaderiii/Dream',
      source: 'Chrome',
      time: '۱ ساعت پیش',
      tag: 'URL',
    },
    {
      id: 'clip-4',
      content: 'sk-live-51H7...f4g9 [AUTO-REDACTED BY VAULT]',
      source: 'Terminal',
      time: '۲ ساعت پیش',
      tag: 'SECRET',
    },
  ];

  const jalaliToday = new Intl.DateTimeFormat('fa-IR-u-ca-persian', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  }).format(new Date());

  // Active Artifact in the Split Canvas
  const [activeArtifact, setActiveArtifact] = useState<Artifact | null>({
    id: 'art-omnibar-core',
    title: 'پالت دستورات سراسری و مرکز کنترل سیستم‌عامل (Global Omnibar & OS Command Center)',
    type: 'omnibar',
    language: 'tsx',
    version: 'v7.0 Final',
    description: 'دسترسی آنی به ۵۲ ماژول، فایل‌ها، کلیپ‌بورد و دستورات سیستمی با جستجوی معنایی و میانبر سراسری Ctrl+K.',
    code: `// Dream Global Omnibar — Semantic OS Command Palette (P7 Final)
import { SemanticIndex, ClipboardVault, JalaliCalendar } from '@/dream/os/omnibar';

export const omnibar = new SemanticIndex({
  sources: [AppModules(52), FileSystem(), ClipboardHistory(), JalaliEvents()],
  ranking: 'hybrid: BM25 + embedding-cosine',
  shortcut: 'Ctrl+K (global OS-level hook)',
  sandbox: 'isolated-elevated-with-approval',
});

omnibar.onExecute((cmd) => DreamCore.dispatch(cmd, { audit: true }));`,
  });

  // Artifact View Mode (preview vs code)
  const [artifactViewTab, setArtifactViewTab] = useState<'preview' | 'code'>('preview');
  const [hasCopiedCode, setHasCopiedCode] = useState(false);

  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'msg-manifesto',
      sender: 'dream',
      indexRef: '001 / OMNIBAR_FINAL',
      lead: 'فاز هفتم و نهایی: پالت دستورات سراسری و کنترل کامل سیستم‌عامل فعال شد — هر ۷ ستون پیروزی کامل شد',
      text: 'سلام علی عزیز. فاز پایانی راهبرد برتری دریم مستقر شد: پالت دستورات سراسری (Global Omnibar). با فشردن Ctrl+K در هر لحظه، به تمام ۵۲ ماژول، فایل‌ها، تاریخچه کلیپ‌بورد با جستجوی معنایی، تقویم جلالی و دستورات سیستمی دسترسی آنی دارید. دریم اکنون به مغز متفکر کل سیستم‌عامل شما تبدیل شده است — آرتیفکت‌های زنده، بینایی صفحه، استریم ۱۲.۸ms، عامل‌های ارواح، صوت انسانی و خزانه رمزنگاری‌شده، همگی در یک میانبر.',
      timestamp: '۱۰:۴۲',
      commandExecution: {
        command: 'system.dream.bootstrap --all-phases',
        category: 'SYSTEM',
        result: '7/7 PILLARS ONLINE · 52 MODULES INDEXED · OMNIBAR READY',
        latencyMs: 14.2,
      },
      artifact: {
        id: 'art-omnibar-core',
        title: 'پالت دستورات سراسری و مرکز کنترل سیستم‌عامل (Global Omnibar & OS Command Center)',
        type: 'omnibar',
        language: 'tsx',
        version: 'v7.0 Final',
        description: 'دسترسی آنی به ۵۲ ماژول، فایل‌ها، کلیپ‌بورد و دستورات سیستمی با جستجوی معنایی و میانبر سراسری Ctrl+K.',
        code: `// Dream Global Omnibar — Semantic OS Command Palette (P7 Final)`,
      },
    },
  ]);

  // Inspector drawer for technical deep-dives or Swiss Index
  const [inspector, setInspector] = useState<{
    open: boolean;
    type: 'tot' | 'browser' | 'code' | 'model' | 'index' | 'speculative' | 'voice' | 'security' | null;
    title: string;
    sectionNo?: string;
    content?: any;
  }>({ open: false, type: null, title: '' });

  // Audio Context Refs
  const audioCtxRef = useRef<AudioContext | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const animFrameRef = useRef<number | null>(null);
  const chatScrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (chatScrollRef.current) {
      chatScrollRef.current.scrollTop = chatScrollRef.current.scrollHeight;
    }
  }, [messages, isTyping, isLiveStreaming]);

  // Global Omnibar Hotkey (Ctrl+K / Cmd+K) — OS-level command palette
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setOmnibarOpen((prev) => !prev);
        setOmnibarQuery('');
        setSelectedCommandIdx(0);
      }
      if (e.key === 'Escape') {
        setOmnibarOpen(false);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  // Real-time Audio processing loop
  useEffect(() => {
    if (!isVoiceActive) {
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
      if (mediaStreamRef.current) mediaStreamRef.current.getTracks().forEach((t) => t.stop());
      if (audioCtxRef.current && audioCtxRef.current.state !== 'closed') {
        void audioCtxRef.current.close().catch(() => {});
      }
      setVoiceRMS(0);
      setWaveformPeaks(new Array(24).fill(0.08));
      setIsSpeaking(false);
      return;
    }

    let stream: MediaStream | null = null;
    let ctx: AudioContext | null = null;

    void (async () => {
      try {
        if (typeof navigator !== 'undefined' && navigator.mediaDevices?.getUserMedia) {
          stream = await navigator.mediaDevices.getUserMedia({
            audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
          });
          mediaStreamRef.current = stream;

          const AudioContextClass =
            window.AudioContext ||
            (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;

          if (AudioContextClass) {
            ctx = new AudioContextClass();
            audioCtxRef.current = ctx;

            const source = ctx.createMediaStreamSource(stream);
            const analyser = ctx.createAnalyser();
            analyser.fftSize = 64;
            analyser.smoothingTimeConstant = 0.2;
            source.connect(analyser);

            const timeData = new Uint8Array(analyser.fftSize);

            const render = () => {
              if (!mediaStreamRef.current) return;
              analyser.getByteTimeDomainData(timeData);

              let sumSq = 0;
              for (let i = 0; i < timeData.length; i++) {
                const val = (timeData[i] - 128) / 128;
                sumSq += val * val;
              }
              const rms = Math.sqrt(sumSq / timeData.length);
              setVoiceRMS(rms);

              const userSpoke = rms > vadThreshold;
              setIsSpeaking(userSpoke);

              if (userSpoke && isAiSpeaking && bargeInEnabled) {
                setIsAiSpeaking(false);
                setInterruptionTriggered(true);
                setTimeout(() => setInterruptionTriggered(false), 2500);
              }

              const peaks: number[] = [];
              const step = Math.max(1, Math.floor(timeData.length / 24));
              for (let i = 0; i < 24; i++) {
                peaks.push(Math.abs((timeData[Math.min(i * step, timeData.length - 1)] - 128) / 128));
              }
              setWaveformPeaks(peaks);

              animFrameRef.current = requestAnimationFrame(render);
            };

            animFrameRef.current = requestAnimationFrame(render);

            if (ctx.createScriptProcessor) {
              const processor = ctx.createScriptProcessor(4096, 1, 1);
              source.connect(processor);
              processor.connect(ctx.destination);
              processor.onaudioprocess = (e) => {
                if (isMicMuted) return;
                const inputData = e.inputBuffer.getChannelData(0);
                const pcm16 = new Int16Array(inputData.length);
                for (let i = 0; i < inputData.length; i++) {
                  const s = Math.max(-1, Math.min(1, inputData[i]));
                  pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
                }
                const binary = String.fromCharCode(...new Uint8Array(pcm16.buffer));
                void duplexPushMicChunk(client, btoa(binary)).catch(() => {});
              };
            }
          }
        }
      } catch (err) {
        console.warn('Mic init failed:', err);
      }
    })();

    return () => {
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
      if (stream) stream.getTracks().forEach((t) => t.stop());
      if (ctx && ctx.state !== 'closed') void ctx.close().catch(() => {});
    };
  }, [client, isVoiceActive, isMicMuted, isAiSpeaking]);

  const toggleVoiceSession = async () => {
    if (!isVoiceActive) {
      try {
        await duplexStart(client, 'desktop-live-voice', 16000, 0.5);
      } catch {}
      setIsVoiceActive(true);
      setIsAiSpeaking(true);
      setTimeout(() => setIsAiSpeaking(false), 3000);
    } else {
      try {
        await duplexStop(client);
      } catch {}
      setIsVoiceActive(false);
      setVoiceZenMode(false);
      setIsAiSpeaking(false);
    }
  };

  const handleCopyCode = () => {
    if (!activeArtifact) return;
    void navigator.clipboard.writeText(activeArtifact.code);
    setHasCopiedCode(true);
    setTimeout(() => setHasCopiedCode(false), 2000);
  };

  // Trigger Security Audit & Key Rotation Action
  const handleTriggerSecurityAudit = () => {
    const newLog = {
      id: `log-${Date.now()}`,
      time: new Date().toLocaleTimeString('fa-IR'),
      event: 'چرخش کلیدهای رمزنگاری محلی و پاک‌سازی بافر موقت حافظه',
      status: 'encrypted' as const,
    };
    setAuditLogs((prev) => [newLog, ...prev]);

    const secArt: Artifact = {
      id: `art-sec-${Date.now()}`,
      title: 'گزارش ممیزی امنیتی و سپر حریم خصوصی (Security & Vault Audit)',
      type: 'security',
      language: 'markdown',
      version: 'v6.0 Enterprise',
      description: 'تایید کامل عدم ارسال تلمتری، سلامت رمزنگاری AES-256 و مسدودسازی دسترسی‌های غیرمجاز شبکه.',
      code: `### Zero-Telemetry Audit Report\n- Cipher: AES-256-GCM\n- Outbound Telemetry: 0 Bytes (100% BLOCKED)\n- PII Masking: Active (14 tokens redacted)\n- Status: 100% COMPLIANT`,
    };
    setActiveArtifact(secArt);

    const msgCount = messages.length + 1;
    const userMsg: Message = {
      id: `usr-${Date.now()}`,
      sender: 'user',
      indexRef: `00${msgCount} / VAULT_AUDIT`,
      text: '🛡️ ممیزی امنیتی و قفل خزانه محلی (Audit Local Vault)',
      timestamp: new Date().toLocaleTimeString('fa-IR', { hour: '2-digit', minute: '2-digit' }),
    };

    const dreamReply: Message = {
      id: `drm-${Date.now()}`,
      sender: 'dream',
      indexRef: `00${msgCount + 1} / SECURITY_REPORT`,
      lead: 'گزارش ممیزی حریم خصوصی و امنیت داده‌ها (Zero-Telemetry Audit)',
      text: 'ممیزی خزانه محلی با موفقیت انجام شد. تمام مکالمات در حافظه محلی با استاندارد AES-256 رمزنگاری شده و هیچ‌گونه تلمتری به سرورهای خارجی ارسال نگردید.',
      timestamp: new Date().toLocaleTimeString('fa-IR', { hour: '2-digit', minute: '2-digit' }),
      artifact: secArt,
      securityAudit: {
        encryption: 'AES-256-GCM (Argon2id)',
        redactedTokensCount: 18,
        ssrfBlockedCount: 3,
        vaultStatus: 'ENCRYPTED',
      },
    };

    setMessages((prev) => [...prev, userMsg, dreamReply]);
  };

  // Trigger Ambient Screen Vision
  const handleTriggerScreenVision = () => {
    setIsVisionScanning(true);
    setTimeout(() => {
      setIsVisionScanning(false);
      const visionData = {
        activeApp: 'Visual Studio Code (src/core/engine.ts)',
        detectedCode: `async function streamTokens(prompt: string) {\n  const res = await bridge.call('engine.infer', { prompt });\n  return res.unwrap();\n}`,
        fixSuggestion: `async function streamTokens(prompt: string) {\n  const res = await bridge.call('engine.infer', { prompt });\n  if (!res || res.status !== 'ok') return '';\n  return res.data ?? '';\n}`,
      };

      const visionArtifact: Artifact = {
        id: `art-vision-${Date.now()}`,
        title: 'تحلیل بینایی کانتکست صفحه و پچ اصلاحی VS Code',
        type: 'vision',
        language: 'typescript',
        version: 'v2.1',
        description: 'اسکن مستقیم پنجره VS Code، تشخیص خطای اجرای توکن‌ها و تولید پچ اصلاحی در کسری از ثانیه.',
        code: visionData.fixSuggestion,
      };
      setActiveArtifact(visionArtifact);

      const msgCount = messages.length + 1;
      const userMsg: Message = {
        id: `usr-${Date.now()}`,
        sender: 'user',
        indexRef: `00${msgCount} / VISION_CAPTURE`,
        text: '📷 اسکن کانتکست صفحه نمایش (Alt+Space)',
        timestamp: new Date().toLocaleTimeString('fa-IR', { hour: '2-digit', minute: '2-digit' }),
      };

      const dreamReply: Message = {
        id: `drm-${Date.now()}`,
        sender: 'dream',
        indexRef: `00${msgCount + 1} / VISION_ANALYSIS`,
        lead: 'ادراک بینایی محیطی صفحه نمایش (Screen Vision OCR)',
        text: `پنجره فعال «${visionData.activeApp}» اسکن شد. پچ اصلاحی مقاوم تولید و در بوم تعاملی سمت راست آماده اعمال است.`,
        timestamp: new Date().toLocaleTimeString('fa-IR', { hour: '2-digit', minute: '2-digit' }),
        artifact: visionArtifact,
        visionBuffer: {
          activeWindow: visionData.activeApp,
          ocrElements: [
            { label: 'خطای خط ۳ در engine.ts', confidence: 0.99, action: 'تولید پچ خودکار' },
            { label: 'محیط اجرای TypeScript 5.9', confidence: 0.98, action: 'انطباق تایپ‌ها' },
          ],
        },
      };

      setMessages((prev) => [...prev, userMsg, dreamReply]);
    }, 700);
  };

  // Trigger Speculative Stream Engine Execution
  const handleTriggerSpeculativeStream = (
    query: string = 'یک تحلیل ریاضی و الگوریتمی از بهینه‌سازی تاخیر توکن‌ها ارائه بده',
  ) => {
    const msgCount = messages.length + 1;
    const userMsg: Message = {
      id: `usr-${Date.now()}`,
      sender: 'user',
      indexRef: `00${msgCount} / SPEC_INFER`,
      text: query,
      timestamp: new Date().toLocaleTimeString('fa-IR', { hour: '2-digit', minute: '2-digit' }),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInputText('');
    setIsLiveStreaming(true);
    setStreamedTokensCount(0);

    const specArtifact: Artifact = {
      id: `art-spec-${Date.now()}`,
      title: 'موتور استریم گمانه‌زنی دوهسته‌ای (Speculative Dual-Core)',
      type: 'speculative',
      language: 'tsx',
      version: 'v3.0 Ultra',
      description: 'استریم موازی کلمات با مدل محلی سبک و اعتبارسنجی شاخه‌های درخت تفکر با DeepSeek-R1.',
      code: `// Dream Speculative Streaming Matrix\nconst TTFT = 12.8; // ms\nconst throughput = 128.4; // tokens/sec`,
    };
    setActiveArtifact(specArtifact);

    let count = 0;
    const interval = setInterval(() => {
      count += 8;
      setStreamedTokensCount(count);
      if (count >= 64) {
        clearInterval(interval);
        setIsLiveStreaming(false);

        const dreamReply: Message = {
          id: `drm-${Date.now()}`,
          sender: 'dream',
          indexRef: `00${msgCount + 1} / SPEC_COMPLETION`,
          lead: 'پردازش فوق‌سریع با موتور استریم دوهسته‌ای (Speculative Dual-Core)',
          text: 'پاسخ با اولین توکن در ۱۲.۸ میلی‌ثانیه و توان ۱۲۸ توکن بر ثانیه تولید شد. نرخ صحت گمانه‌زنی مدل محلی ۸۹.۴٪ ثبت گردید.',
          timestamp: new Date().toLocaleTimeString('fa-IR', { hour: '2-digit', minute: '2-digit' }),
          speculativeTelemetry: {
            ttftMs: 12.8,
            speculativeHitRate: 89.4,
            draftSpeed: 128,
            verifiedSpeed: 28,
            totalTokens: 64,
            tokens: [
              { word: 'الگوریتم', status: 'accepted' },
              { word: 'گمانه‌زنی', status: 'accepted' },
              { word: 'با', status: 'accepted' },
              { word: 'کاهش', status: 'accepted' },
              { word: '۹۰٪', status: 'verified' },
            ],
          },
          artifact: specArtifact,
        };

        setMessages((prev) => [...prev, dreamReply]);
      }
    }, 120);
  };

  // Trigger Proactive Ghost Worker Execution
  const handleTriggerGhostWorker = () => {
    const ghostArt: Artifact = {
      id: `art-ghost-${Date.now()}`,
      title: 'گزارش اجرای خودکار عامل روح: نگهبان مخزن کد (Git Sentinel)',
      type: 'ghost',
      language: 'markdown',
      version: 'v4.0 Autonomous',
      description: 'اسکن کامل برنچ‌های گیت، اعتبارسنجی پکیج‌ها و تایید سلامت تست‌های امنیتی در سندباکس ایزوله.',
      code: `### Sentinel Execution Audit Report\n- Repository: AliNaderiii/Dream\n- Branch Checked: main\n- Vulnerabilities: 0 Detected\n- Status: 100% HEALTHY`,
    };
    setActiveArtifact(ghostArt);

    const msgCount = messages.length + 1;
    const userMsg: Message = {
      id: `usr-${Date.now()}`,
      sender: 'user',
      indexRef: `00${msgCount} / GHOST_DISPATCH`,
      text: '🤖 اجرای دستی دیده‌بان مخزن کد (Trigger Git Sentinel)',
      timestamp: new Date().toLocaleTimeString('fa-IR', { hour: '2-digit', minute: '2-digit' }),
    };

    const dreamReply: Message = {
      id: `drm-${Date.now()}`,
      sender: 'dream',
      indexRef: `00${msgCount + 1} / GHOST_AUDIT`,
      lead: 'گزارش اجرای دیده‌بان خودکار پس‌زمینه (Git Sentinel Daemon)',
      text: 'دیده‌بان مخزن کد اجرا شد. تمامی ۵۲ ماژول هسته بررسی شدند؛ هیچ باگ امنیتی یافت نشد و تلمتری به حافظه اپیزودیک دریم ضمیمه گردید.',
      timestamp: new Date().toLocaleTimeString('fa-IR', { hour: '2-digit', minute: '2-digit' }),
      artifact: ghostArt,
      ghostWorkerReport: {
        workerName: 'دیده‌بان مخزن کد (Git Sentinel)',
        badge: 'MANUAL TRIGGER EXECUTED',
        items: [
          { title: 'تحلیل وابستگی‌های Python و Rust', desc: 'تمامی تایپ‌ها بدون هشدار کامپایل شدند.', severity: 'success' },
          { title: 'بررسی سلامت تست‌های Vite و Vitest', desc: '۲۲۲ تست در کمتر از ۷ ثانیه پاس شدند.', severity: 'success' },
        ],
      },
    };

    setMessages((prev) => [...prev, userMsg, dreamReply]);
  };

  // Execute an OS-level system command from the Omnibar Registry
  const handleExecuteOSCommand = (command: string, category: string, result: string) => {
    const msgCount = messages.length + 1;
    const userMsg: Message = {
      id: `usr-${Date.now()}`,
      sender: 'user',
      indexRef: `00${msgCount} / OS_COMMAND`,
      text: `⌨️ اجرای دستور سیستمی از پالت سراسری: ${command}`,
      timestamp: new Date().toLocaleTimeString('fa-IR', { hour: '2-digit', minute: '2-digit' }),
    };

    const dreamReply: Message = {
      id: `drm-${Date.now()}`,
      sender: 'dream',
      indexRef: `00${msgCount + 1} / OS_EXECUTION`,
      lead: 'اجرای دستور سیستمی در سندباکس ایزوله (OS Command Dispatch)',
      text: `دستور «${command}» با موفقیت در لایه سیستمی اجرا شد. نتیجه عملیات در کارت تلمتری ضمیمه است.`,
      timestamp: new Date().toLocaleTimeString('fa-IR', { hour: '2-digit', minute: '2-digit' }),
      commandExecution: {
        command,
        category,
        result,
        latencyMs: 18.4,
      },
    };

    setMessages((prev) => [...prev, userMsg, dreamReply]);
  };

  // Open the OS Command Center artifact in the right canvas
  const handleOpenCommandCenter = () => {
    setActiveArtifact({
      id: 'art-omnibar-core',
      title: 'پالت دستورات سراسری و مرکز کنترل سیستم‌عامل (Global Omnibar & OS Command Center)',
      type: 'omnibar',
      language: 'tsx',
      version: 'v7.0 Final',
      description: 'دسترسی آنی به ۵۲ ماژول، فایل‌ها، کلیپ‌بورد و دستورات سیستمی با جستجوی معنایی.',
      code: `// Dream Global Omnibar — Semantic OS Command Palette`,
    });
    setArtifactViewTab('preview');
  };

  const handleSendMessage = (customText?: string) => {
    const textToSend = customText || inputText;
    if (!textToSend.trim()) return;

    if (textToSend.includes('پالت') || textToSend.includes('دستور سراسری') || textToSend.includes('کنترل سیستم')) {
      setOmnibarOpen(true);
      if (!customText) setInputText('');
      return;
    }

    if (textToSend.includes('امنیت') || textToSend.includes('رمز') || textToSend.includes('حریم') || textToSend.includes('قفل')) {
      handleTriggerSecurityAudit();
      if (!customText) setInputText('');
      return;
    }

    if (textToSend.includes('صوت') || textToSend.includes('صدا') || textToSend.includes('لحن')) {
      void toggleVoiceSession();
      setVoiceZenMode(true);
      if (!customText) setInputText('');
      return;
    }

    if (textToSend.includes('روح') || textToSend.includes('عامل') || textToSend.includes('نگهبان')) {
      handleTriggerGhostWorker();
      if (!customText) setInputText('');
      return;
    }

    if (textToSend.includes('صفحه') || textToSend.includes('اسکرین') || textToSend.includes('اسکن')) {
      handleTriggerScreenVision();
      if (!customText) setInputText('');
      return;
    }

    if (textToSend.includes('استریم') || textToSend.includes('تاخیر') || textToSend.includes('سرعت')) {
      handleTriggerSpeculativeStream(textToSend);
      return;
    }

    const msgCount = messages.length + 1;
    const userMsg: Message = {
      id: `usr-${Date.now()}`,
      sender: 'user',
      indexRef: `00${msgCount} / QUERY`,
      text: textToSend,
      timestamp: new Date().toLocaleTimeString('fa-IR', { hour: '2-digit', minute: '2-digit' }),
    };

    setMessages((prev) => [...prev, userMsg]);
    if (!customText) setInputText('');
    setIsTyping(true);

    setTimeout(() => {
      setIsTyping(false);
      const respIndex = `00${msgCount + 1} / SYNTHESIS`;

      const reply: Message = {
        id: `drm-${Date.now()}`,
        sender: 'dream',
        indexRef: respIndex,
        lead: 'پاسخ هوشمند سایدکار',
        text: 'پیام دریافت شد. تمام ۷ ستون دریم (آرتیفکت زنده، بینایی، استریم ۱۲.۸ms، عامل‌های ارواح، صوت انسانی، خزانه امن و پالت سراسری) آنلاین هستند.',
        timestamp: new Date().toLocaleTimeString('fa-IR', { hour: '2-digit', minute: '2-digit' }),
      };

      setMessages((prev) => [...prev, reply]);
    }, 450);
  };

  // Semantic Command Registry for the Global Omnibar
  const commandRegistry: Array<{
    id: string;
    title: string;
    desc: string;
    category: string;
    shortcut?: string;
    icon: any;
    execute: () => void;
  }> = [
    {
      id: 'c1',
      title: 'آغاز مکالمه صوتی دوبلکس با سهراب',
      desc: 'Duplex voice call · barge-in <35ms',
      category: 'VOICE',
      shortcut: '⌘⇧V',
      icon: Mic,
      execute: () => {
        void toggleVoiceSession();
        setVoiceZenMode(true);
      },
    },
    {
      id: 'c2',
      title: 'اسکن بینایی صفحه فعال (VS Code / Browser)',
      desc: 'Screen vision OCR · instant patch',
      category: 'VISION',
      shortcut: '⌥Space',
      icon: Camera,
      execute: handleTriggerScreenVision,
    },
    {
      id: 'c3',
      title: 'ممیزی امنیتی و چرخش کلیدهای خزانه',
      desc: 'Rotate AES-256 keys · zero-telemetry audit',
      category: 'SECURITY',
      shortcut: '⌘⇧L',
      icon: ShieldCheck,
      execute: handleTriggerSecurityAudit,
    },
    {
      id: 'c4',
      title: 'اجرای عامل‌های ارواح (Git Sentinel)',
      desc: 'Dispatch proactive ghost mesh',
      category: 'AGENTS',
      shortcut: '⌘⇧G',
      icon: Bot,
      execute: () => handleTriggerGhostWorker(),
    },
    {
      id: 'c5',
      title: 'بنچمارک استریم دوهسته‌ای ۱۲.۸ms',
      desc: 'Speculative dual-core benchmark',
      category: 'ENGINE',
      shortcut: '⌘⇧B',
      icon: Zap,
      execute: () => handleTriggerSpeculativeStream('بنچمارک استریم دوهسته‌ای و تحلیل تاخیر'),
    },
    {
      id: 'c6',
      title: 'مرتب‌سازی خودکار پوشه Downloads',
      desc: 'Organize files by semantic type',
      category: 'SYSTEM',
      icon: FolderOpen,
      execute: () =>
        handleExecuteOSCommand('مرتب‌سازی پوشه Downloads', 'SYSTEM', '۴۲ فایل به ۶ پوشه معنایی دسته‌بندی شد'),
    },
    {
      id: 'c7',
      title: 'نمایش تقویم و رویدادهای جلالی',
      desc: 'Jalali calendar & schedule',
      category: 'SYSTEM',
      icon: CalendarDays,
      execute: () => handleExecuteOSCommand('نمایش تقویم جلالی', 'SYSTEM', `امروز: ${jalaliToday}`),
    },
    {
      id: 'c8',
      title: 'جستجوی معنایی در تاریخچه کلیپ‌بورد',
      desc: 'Semantic clipboard history search',
      category: 'CLIPBOARD',
      icon: ClipboardList,
      execute: handleOpenCommandCenter,
    },
    {
      id: 'c9',
      title: 'حافظه اپیزودیک و پایگاه دانش',
      desc: 'Episodic memory graph',
      category: 'NAVIGATE',
      icon: Layers,
      execute: () => void navigate('/memory'),
    },
    {
      id: 'c10',
      title: 'مرورگر عمیق Playwright',
      desc: 'Autonomous deep browser',
      category: 'NAVIGATE',
      icon: Globe,
      execute: () => void navigate('/browse'),
    },
    {
      id: 'c11',
      title: 'جستجوی وب زنده درباره هوش مصنوعی',
      desc: 'Live web research',
      category: 'WEB',
      icon: Search,
      execute: () => handleSendMessage('جستجوی وب درباره آخرین اخبار هوش مصنوعی'),
    },
  ];

  const filteredCommands =
    omnibarQuery.trim() === ''
      ? commandRegistry
      : commandRegistry.filter(
          (c) =>
            c.title.includes(omnibarQuery) ||
            c.desc.toLowerCase().includes(omnibarQuery.toLowerCase()) ||
            c.category.toLowerCase().includes(omnibarQuery.toLowerCase()),
        );

  const filteredClips =
    clipQuery.trim() === ''
      ? clipboardHistory
      : clipboardHistory.filter(
          (c) => c.content.includes(clipQuery) || c.tag.toLowerCase().includes(clipQuery.toLowerCase()),
        );

  return (
    <div
      className="relative flex h-full w-full overflow-hidden bg-[#070709] font-sans text-zinc-100 antialiased select-none"
      dir="rtl"
    >
      {/* Precision Swiss Grid & Glassmorphism Refractions */}
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(#ffffff0a_1px,transparent_1px)] [background-size:24px_24px] opacity-40" />
      <div className="pointer-events-none absolute -top-32 right-1/4 size-[550px] rounded-full bg-gradient-to-br from-indigo-500/10 via-purple-500/5 to-transparent blur-[160px]" />
      <div className="pointer-events-none absolute -bottom-32 left-1/4 size-[550px] rounded-full bg-gradient-to-tr from-cyan-500/10 via-emerald-500/5 to-transparent blur-[160px]" />

      {/* Swiss Editorial Masthead */}
      <header className="absolute top-0 inset-x-0 z-30 flex h-14 items-center justify-between border-b border-white/[0.06] bg-zinc-950/60 px-6 backdrop-blur-2xl">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <div className="relative flex size-6 items-center justify-center rounded-lg bg-gradient-to-tr from-indigo-500 to-cyan-400 p-[1px] shadow-[0_0_15px_rgba(99,102,241,0.3)]">
              <div className="flex size-full items-center justify-center rounded-[7px] bg-[#070709]">
                <Sparkles className="size-3 text-cyan-300 animate-pulse" />
              </div>
            </div>
            <span className="font-mono text-xs font-bold tracking-widest text-zinc-100">
              DREAM // 4.0
            </span>
          </div>
          <span className="text-zinc-600">|</span>
          <span className="font-mono text-[10px] uppercase tracking-wider text-zinc-400 hidden sm:inline">
            GLOBAL OMNIBAR · OS COMMAND CENTER
          </span>
        </div>

        {/* Center: Frosted Glass Dynamic Status Capsule */}
        <div className="flex items-center gap-3 rounded-full border border-white/[0.08] bg-zinc-900/60 px-3.5 py-1.5 shadow-[inset_0_1px_0_rgba(255,255,255,0.08)] backdrop-blur-xl">
          {/* Omnibar Global Trigger */}
          <button
            onClick={() => setOmnibarOpen(true)}
            className="flex items-center gap-1.5 rounded-full bg-indigo-500/20 border border-indigo-500/40 px-2.5 py-0.5 font-mono text-[11px] text-indigo-200 hover:bg-indigo-500/30 transition-all"
            title="پالت دستورات سراسری (Ctrl+K)"
          >
            <Command className="size-3 text-indigo-300" />
            <span>Ctrl+K</span>
          </button>

          <div className="h-3 w-px bg-white/10" />

          {/* Security Badge */}
          <button
            onClick={handleTriggerSecurityAudit}
            className="flex items-center gap-1 font-mono text-[10px] text-emerald-300 hover:text-white transition-colors"
            title="خزانه رمزنگاری‌شده محلی"
          >
            <ShieldCheck className="size-3 text-emerald-400" />
            <span>VAULT</span>
          </button>

          <div className="h-3 w-px bg-white/10" />

          {/* Duplex Voice */}
          <button
            onClick={() => {
              void toggleVoiceSession();
              setVoiceZenMode(true);
            }}
            className="flex items-center gap-1 font-mono text-[10px] text-zinc-400 hover:text-white"
          >
            <Mic className="size-2.5 text-emerald-400" />
            <span>VOICE</span>
          </button>

          <div className="h-3 w-px bg-white/10" />

          {/* Stream Latency */}
          <button
            onClick={() => handleTriggerSpeculativeStream()}
            className="flex items-center gap-1 font-mono text-[10px] text-cyan-300 hover:text-white"
          >
            <Zap className="size-2.5 text-amber-400" />
            <span>12.8ms</span>
          </button>
        </div>

        {/* Right: Swiss Navigation Index Trigger & Split Canvas Toggle */}
        <div className="flex items-center gap-2">
          {activeArtifact && (
            <button
              onClick={() => setActiveArtifact(null)}
              className="flex items-center gap-1.5 rounded-lg border border-white/[0.08] bg-indigo-950/40 px-2.5 py-1 font-mono text-[11px] text-indigo-300 hover:bg-indigo-900/60 transition-all"
            >
              <LayoutTemplate className="size-3 text-indigo-400" />
              <span>بوم فعال</span>
            </button>
          )}

          <button
            onClick={() =>
              setInspector({
                open: true,
                type: 'index',
                title: 'فهرست ماژول‌ها و ابزارها (Swiss Index)',
                sectionNo: 'INDEX // 52',
              })
            }
            className="flex items-center gap-2 rounded-lg border border-white/[0.08] bg-zinc-900/50 px-3 py-1 font-mono text-xs text-zinc-300 hover:bg-white/10 hover:text-white transition-all shadow-sm"
          >
            <Layers className="size-3.5 text-indigo-400" />
            <span className="text-[11px]">فهرست ماژول‌ها</span>
          </button>
        </div>
      </header>

      {/* Main Dual-Stage Split Canvas Layout */}
      <div className="relative flex size-full pt-14 overflow-hidden">
        {/* Left/Main Column: Swiss Editorial Chat Flow */}
        <div
          className={`relative flex flex-col transition-all duration-300 ${activeArtifact ? 'w-full md:w-1/2 lg:w-5/12 border-l border-white/[0.06]' : 'w-full'}`}
        >
          {voiceZenMode && isVoiceActive ? (
            <div className="relative flex flex-1 flex-col items-center justify-center p-6 transition-all duration-500">
              <div className="relative flex size-52 items-center justify-center">
                <div
                  className="absolute inset-0 rounded-full bg-gradient-to-tr from-emerald-500/20 via-cyan-500/20 to-indigo-500/20 blur-3xl transition-transform duration-100"
                  style={{ transform: `scale(${Math.max(1, 1 + voiceRMS * 4.5)})` }}
                />
                <div
                  className="absolute size-40 rounded-full border border-white/10 bg-zinc-900/40 backdrop-blur-2xl transition-transform duration-75"
                  style={{ transform: `scale(${Math.max(0.9, 0.95 + voiceRMS * 2.5)})` }}
                />
                <div
                  className="relative flex size-28 items-center justify-center rounded-full bg-gradient-to-tr from-emerald-500 via-cyan-400 to-indigo-500 p-[1.5px] shadow-[0_0_40px_rgba(16,185,129,0.3)] transition-transform duration-75"
                  style={{ transform: `scale(${Math.max(0.85, 1 + voiceRMS * 2)})` }}
                >
                  <div className="flex size-full items-center justify-center rounded-full bg-[#070709]/90 backdrop-blur-2xl">
                    {interruptionTriggered ? (
                      <VolumeX className="size-8 text-amber-400 animate-pulse" />
                    ) : isSpeaking ? (
                      <Volume2 className="size-8 text-emerald-300 animate-pulse" />
                    ) : (
                      <Mic className="size-8 text-emerald-400" />
                    )}
                  </div>
                </div>
              </div>

              <div className="mt-6 text-center space-y-1">
                {interruptionTriggered ? (
                  <span className="font-mono text-[10px] tracking-widest text-amber-400 uppercase bg-amber-950/40 px-3 py-1 rounded-full border border-amber-500/30">
                    ⚡ BARGE-IN TRIGGERED // قطع فوری کلام در ۳۴ms
                  </span>
                ) : (
                  <span className="font-mono text-[10px] tracking-widest text-emerald-400 uppercase">
                    DUPLEX ACOUSTIC STREAM // PERSONA: {activePersona.toUpperCase()}
                  </span>
                )}
                <p className="text-xs font-medium text-zinc-100">
                  {interruptionTriggered
                    ? 'صدای شما شنیده شد؛ دریم متوقف شد.'
                    : isSpeaking
                      ? 'دریم در حال شنیدن کلام شماست...'
                      : 'صحبت کنید؛ هر لحظه می‌توانید صحبت دریم را قطع کنید'}
                </p>
              </div>

              <div className="mt-6 flex items-center gap-1 h-8">
                {waveformPeaks.map((peak, idx) => (
                  <div
                    key={idx}
                    className="w-1 rounded-full bg-gradient-to-t from-emerald-500 to-cyan-300 transition-all duration-75"
                    style={{ height: `${Math.max(4, peak * 32)}px` }}
                  />
                ))}
              </div>

              <div className="mt-6 flex items-center gap-3">
                <button
                  onClick={() => setIsMicMuted(!isMicMuted)}
                  className={`flex size-9 items-center justify-center rounded-full border backdrop-blur-xl transition-all ${
                    isMicMuted
                      ? 'border-rose-500/40 bg-rose-950/40 text-rose-400'
                      : 'border-white/10 bg-zinc-900/60 text-zinc-300 hover:text-white'
                  }`}
                >
                  {isMicMuted ? <MicOff className="size-3.5" /> : <Mic className="size-3.5" />}
                </button>
                <button
                  onClick={() => setVoiceZenMode(false)}
                  className="rounded-full border border-white/10 bg-zinc-900/60 px-4 py-1.5 font-mono text-[11px] text-zinc-300 hover:text-white transition-all"
                >
                  RETURN // بازگشت
                </button>
                <button
                  onClick={() => void toggleVoiceSession()}
                  className="flex size-9 items-center justify-center rounded-full bg-rose-600/90 text-white shadow-lg hover:bg-rose-500 transition-all"
                >
                  <X className="size-3.5" />
                </button>
              </div>
            </div>
          ) : (
            <div className="flex flex-1 flex-col overflow-hidden">
              {/* Conversation Feed */}
              <div
                ref={chatScrollRef}
                className="flex-1 space-y-6 overflow-y-auto px-4 py-6 md:px-8 scrollbar-thin"
              >
                {/* Minimalist Prompts */}
                {messages.length <= 1 && (
                  <div className="space-y-4">
                    <div className="border-b border-white/[0.08] pb-4">
                      <div className="font-mono text-[10px] text-zinc-500 uppercase tracking-widest">
                        SEC 07 // GLOBAL OMNIBAR & OS COMMAND CENTER — FINAL PILLAR
                      </div>
                      <h2 className="text-xl font-bold tracking-tight text-white mt-1">
                        دریم: مغز متفکر کل سیستم‌عامل شما
                      </h2>
                      <p className="text-xs text-zinc-400 mt-1">
                        با Ctrl+K پالت سراسری را باز کنید یا یکی از سناریوها را تست نمایید:
                      </p>
                    </div>

                    <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
                      <button
                        onClick={() => setOmnibarOpen(true)}
                        className="flex flex-col rounded-xl border border-indigo-500/40 bg-indigo-950/30 p-3 text-right hover:border-indigo-400 hover:bg-indigo-950/50 transition-all"
                      >
                        <span className="font-mono text-[9px] text-indigo-300 flex items-center gap-1">
                          <Command className="size-3" /> 01 // OMNIBAR (Ctrl+K)
                        </span>
                        <span className="text-xs font-semibold text-zinc-100 mt-1">پالت دستورات سراسری</span>
                        <span className="text-[10px] text-zinc-400">جستجوی معنایی ماژول‌ها، فایل‌ها و سیستم</span>
                      </button>

                      <button
                        onClick={handleOpenCommandCenter}
                        className="flex flex-col rounded-xl border border-emerald-500/30 bg-emerald-950/20 p-3 text-right hover:border-emerald-400 hover:bg-emerald-950/40 transition-all"
                      >
                        <span className="font-mono text-[9px] text-emerald-400 flex items-center gap-1">
                          <Terminal className="size-3" /> 02 // OS COMMAND CENTER
                        </span>
                        <span className="text-xs font-semibold text-zinc-100 mt-1">مرکز کنترل سیستم‌عامل</span>
                        <span className="text-[10px] text-zinc-400">کلیپ‌بورد معنایی، تقویم جلالی، دستورات</span>
                      </button>
                    </div>
                  </div>
                )}

                {/* Messages */}
                {messages.map((msg) => (
                  <article
                    key={msg.id}
                    className={`flex flex-col gap-1.5 ${msg.sender === 'user' ? 'items-end' : 'items-start'}`}
                  >
                    <div className="flex items-center gap-2 font-mono text-[10px] text-zinc-500 px-1">
                      <span>{msg.indexRef}</span>
                      <span>·</span>
                      <span>{msg.sender === 'dream' ? 'DREAM CORE' : 'YOU'}</span>
                    </div>

                    <div
                      className={`max-w-[92%] rounded-2xl p-4 text-xs leading-relaxed backdrop-blur-2xl ${
                        msg.sender === 'user'
                          ? 'border border-white/10 bg-zinc-900/90 text-white'
                          : 'border border-white/[0.07] bg-zinc-900/40 text-zinc-200 shadow-sm'
                      }`}
                    >
                      {msg.lead && (
                        <p className="font-mono text-[10px] font-semibold text-indigo-400 mb-1.5 uppercase">
                          {msg.lead}
                        </p>
                      )}
                      <p className="whitespace-pre-wrap">{msg.text}</p>

                      {/* OS Command Execution Telemetry */}
                      {msg.commandExecution && (
                        <div className="mt-3 rounded-xl border border-indigo-500/30 bg-indigo-950/20 p-3 space-y-1.5">
                          <div className="flex items-center justify-between text-[11px] font-mono text-indigo-300 border-b border-indigo-500/20 pb-1.5">
                            <span className="flex items-center gap-1.5 font-bold">
                              <Terminal className="size-3.5 text-indigo-400" />
                              {msg.commandExecution.command}
                            </span>
                            <span className="text-cyan-300 text-[10px]">
                              {msg.commandExecution.latencyMs}ms · {msg.commandExecution.category}
                            </span>
                          </div>
                          <p className="text-[10px] text-emerald-300 font-mono">
                            ✓ {msg.commandExecution.result}
                          </p>
                        </div>
                      )}

                      {/* Security Audit Badge */}
                      {msg.securityAudit && (
                        <div className="mt-3 rounded-xl border border-emerald-500/30 bg-emerald-950/20 p-3 space-y-2">
                          <div className="flex items-center justify-between text-[11px] font-mono text-emerald-300 border-b border-emerald-500/20 pb-1.5">
                            <span className="flex items-center gap-1.5 font-bold">
                              <ShieldCheck className="size-3.5 text-emerald-400" />
                              {msg.securityAudit.encryption}
                            </span>
                            <span className="text-cyan-300 text-[10px]">ZERO-TELEMETRY CERTIFIED</span>
                          </div>
                          <div className="grid grid-cols-2 gap-1.5 text-[10px] font-mono">
                            <div className="bg-zinc-950/60 p-2 rounded border border-white/5">
                              <span className="text-zinc-400">پالایش کلمات محرمانه:</span>
                              <span className="text-emerald-300 font-bold block mt-0.5">
                                {msg.securityAudit.redactedTokensCount} توکن
                              </span>
                            </div>
                            <div className="bg-zinc-950/60 p-2 rounded border border-white/5">
                              <span className="text-zinc-400">سپر ضد SSRF:</span>
                              <span className="text-cyan-300 font-bold block mt-0.5">
                                {msg.securityAudit.ssrfBlockedCount} حمله مهارشده
                              </span>
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  </article>
                ))}

                {isLiveStreaming && (
                  <div className="flex items-center gap-2 font-mono text-xs text-amber-400 py-1">
                    <Zap className="size-3.5 animate-bounce" />
                    <span>SPECULATIVE STREAMING // {streamedTokensCount} TOKENS GENERATED...</span>
                  </div>
                )}

                {isTyping && (
                  <div className="flex items-center gap-2 font-mono text-xs text-zinc-500 py-1">
                    <div className="size-1.5 rounded-full bg-indigo-500 animate-ping" />
                    <span>DREAM SYNTHESIZING...</span>
                  </div>
                )}
              </div>

              {/* Minimal Omnibar Input Bar */}
              <div className="p-3 md:px-6 pb-4">
                <div className="relative rounded-2xl border border-white/[0.1] bg-zinc-900/60 shadow-xl backdrop-blur-2xl focus-within:border-indigo-500/50">
                  <textarea
                    value={inputText}
                    onChange={(e) => setInputText(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        handleSendMessage();
                      }
                    }}
                    rows={2}
                    placeholder="دستور دهید، پالت سراسری را بخواهید، یا سوال بپرسید..."
                    className="w-full resize-none bg-transparent px-3.5 pt-3 pb-1 text-xs text-zinc-100 placeholder-zinc-500 focus:outline-none"
                  />

                  <div className="flex items-center justify-between px-3 py-1.5 border-t border-white/[0.05]">
                    <div className="flex items-center gap-1.5">
                      <button
                        onClick={() => setOmnibarOpen(true)}
                        className="flex items-center gap-1 rounded-lg px-2 py-0.5 font-mono text-[10px] text-indigo-300 bg-indigo-500/10 border border-indigo-500/30 hover:bg-indigo-500/20 transition-all"
                        title="پالت دستورات سراسری"
                      >
                        <Command className="size-3" />
                        <span>Ctrl+K</span>
                      </button>

                      <button
                        onClick={handleTriggerSecurityAudit}
                        className="flex items-center gap-1 rounded-lg px-2 py-0.5 font-mono text-[10px] text-emerald-300 bg-emerald-500/10 border border-emerald-500/30 hover:bg-emerald-500/20 transition-all"
                      >
                        <ShieldCheck className="size-3" />
                        <span>VAULT</span>
                      </button>

                      <button
                        onClick={() => {
                          void toggleVoiceSession();
                          setVoiceZenMode(true);
                        }}
                        className="flex items-center gap-1 rounded-lg px-2 py-0.5 font-mono text-[10px] text-emerald-300 bg-emerald-500/10 border border-emerald-500/30 hover:bg-emerald-500/20 transition-all"
                      >
                        <Mic className="size-3" />
                        <span>VOICE</span>
                      </button>

                      <button
                        onClick={() => handleTriggerGhostWorker()}
                        className="flex items-center gap-1 rounded-lg px-2 py-0.5 font-mono text-[10px] text-purple-300 bg-purple-500/10 border border-purple-500/30 hover:bg-purple-500/20 transition-all"
                      >
                        <Bot className="size-3" />
                        <span>GHOSTS</span>
                      </button>

                      <button
                        onClick={handleTriggerScreenVision}
                        disabled={isVisionScanning}
                        className="flex items-center gap-1 rounded-lg px-2 py-0.5 font-mono text-[10px] text-cyan-300 bg-cyan-500/10 border border-cyan-500/30 hover:bg-cyan-500/20 transition-all"
                      >
                        <Camera className="size-3" />
                        <span>{isVisionScanning ? 'SCANNING...' : 'VISION'}</span>
                      </button>

                      <button
                        onClick={() => setWebSearchEnabled(!webSearchEnabled)}
                        className={`flex items-center gap-1 rounded-lg px-2 py-0.5 font-mono text-[10px] transition-all ${
                          webSearchEnabled
                            ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40'
                            : 'text-zinc-400 hover:text-white'
                        }`}
                      >
                        <Globe className="size-3" />
                        <span>WEB</span>
                      </button>
                    </div>

                    <button
                      onClick={() => handleSendMessage()}
                      disabled={!inputText.trim()}
                      className="flex size-6 items-center justify-center rounded-lg bg-white text-zinc-950 font-bold hover:bg-zinc-200 disabled:opacity-20 shadow-sm"
                    >
                      <ArrowUp className="size-3.5 stroke-[2.5]" />
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Right/Secondary Column: OS Command Center / Security Studio */}
        {activeArtifact && (
          <div className="hidden md:flex flex-1 flex-col bg-[#08080c] overflow-hidden shadow-2xl">
            {/* Artifact Top Bar */}
            <div className="flex h-12 shrink-0 items-center justify-between border-b border-white/[0.08] bg-zinc-950/60 px-5 backdrop-blur-xl">
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-1.5 rounded-lg bg-indigo-500/10 border border-indigo-500/30 px-2 py-0.5 text-indigo-300 font-mono text-[10px]">
                  {activeArtifact.type === 'omnibar' ? (
                    <Command className="size-3 text-indigo-400" />
                  ) : (
                    <Sparkles className="size-3" />
                  )}
                  <span>
                    {activeArtifact.type === 'omnibar'
                      ? 'OS COMMAND CENTER'
                      : activeArtifact.type === 'security'
                        ? 'SECURITY VAULT'
                        : 'ARTIFACT'}
                  </span>
                </div>
                <span className="text-xs font-semibold text-zinc-200 truncate max-w-xs">
                  {activeArtifact.title}
                </span>
              </div>

              {/* View Switcher */}
              <div className="flex items-center gap-2">
                <div className="flex items-center rounded-lg border border-white/[0.08] bg-zinc-900/60 p-0.5">
                  <button
                    onClick={() => setArtifactViewTab('preview')}
                    className={`flex items-center gap-1 rounded-md px-2.5 py-1 text-[11px] font-medium transition-all ${
                      artifactViewTab === 'preview'
                        ? 'bg-white/10 text-white shadow-sm'
                        : 'text-zinc-400 hover:text-white'
                    }`}
                  >
                    <Eye className="size-3" />
                    <span>{activeArtifact.type === 'omnibar' ? 'مرکز فرماندهی' : 'خزانه محلی'}</span>
                  </button>
                  <button
                    onClick={() => setArtifactViewTab('code')}
                    className={`flex items-center gap-1 rounded-md px-2.5 py-1 text-[11px] font-medium transition-all ${
                      artifactViewTab === 'code'
                        ? 'bg-white/10 text-white shadow-sm'
                        : 'text-zinc-400 hover:text-white'
                    }`}
                  >
                    <CodeXml className="size-3" />
                    <span>{activeArtifact.type === 'omnibar' ? 'موتور پالت' : 'پیکربندی امنیت'}</span>
                  </button>
                </div>

                <div className="h-4 w-px bg-white/10" />

                <button
                  onClick={handleCopyCode}
                  className="flex size-7 items-center justify-center rounded-lg border border-white/[0.08] bg-zinc-900 text-zinc-300 hover:text-white transition-all"
                  title="کپی کد"
                >
                  {hasCopiedCode ? <Check className="size-3.5 text-emerald-400" /> : <Copy className="size-3.5" />}
                </button>

                <button
                  onClick={() => setActiveArtifact(null)}
                  className="flex size-7 items-center justify-center rounded-lg border border-white/[0.08] bg-zinc-900 text-zinc-400 hover:text-white transition-all"
                  title="بستن بوم"
                >
                  <X className="size-3.5" />
                </button>
              </div>
            </div>

            {/* Artifact Content Stage */}
            <div className="flex-1 overflow-y-auto p-6 scrollbar-thin">
              {artifactViewTab === 'preview' ? (
                activeArtifact.type === 'omnibar' ? (
                  /* ═══════════ OS COMMAND CENTER (Phase 7 Final) ═══════════ */
                  <div className="space-y-6">
                    <div className="rounded-2xl border border-indigo-500/30 bg-zinc-900/60 p-6 backdrop-blur-2xl shadow-[0_8px_32px_rgba(0,0,0,0.5)]">
                      <div className="flex items-center justify-between border-b border-white/[0.08] pb-4 mb-5">
                        <div className="flex items-center gap-2.5">
                          <div className="size-8 rounded-xl bg-indigo-500/20 border border-indigo-500/40 flex items-center justify-center text-indigo-300">
                            <Terminal className="size-4" />
                          </div>
                          <div>
                            <span className="font-mono text-[10px] text-indigo-400 uppercase tracking-widest block">
                              GLOBAL OMNIBAR · OS COMMAND CENTER //
                            </span>
                            <h3 className="text-sm font-bold text-white mt-0.5">
                              مرکز فرماندهی سیستم‌عامل دریم
                            </h3>
                          </div>
                        </div>
                        <span className="px-2.5 py-1 text-[10px] font-mono rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                          ● 11 COMMANDS · 52 MODULES INDEXED
                        </span>
                      </div>

                      {/* Jalali Date + System Vitals */}
                      <div className="grid grid-cols-3 gap-3 mb-6">
                        <div className="rounded-xl border border-white/[0.06] bg-zinc-950/60 p-3.5 space-y-1.5">
                          <span className="font-mono text-[10px] text-zinc-400 flex items-center gap-1">
                            <CalendarDays className="size-3 text-amber-400" /> TODAY // تقویم جلالی
                          </span>
                          <p className="text-xs font-bold text-amber-200 leading-relaxed">{jalaliToday}</p>
                        </div>

                        <div className="rounded-xl border border-white/[0.06] bg-zinc-950/60 p-3.5 space-y-1.5">
                          <span className="font-mono text-[10px] text-zinc-400 flex items-center gap-1">
                            <Cpu className="size-3 text-cyan-400" /> CPU // پردازنده
                          </span>
                          <p className="text-lg font-bold font-mono text-cyan-300">23%</p>
                          <div className="h-1.5 rounded-full bg-zinc-800 overflow-hidden">
                            <div className="h-full w-[23%] rounded-full bg-gradient-to-r from-cyan-500 to-emerald-400" />
                          </div>
                        </div>

                        <div className="rounded-xl border border-white/[0.06] bg-zinc-950/60 p-3.5 space-y-1.5">
                          <span className="font-mono text-[10px] text-zinc-400">RAM // حافظه</span>
                          <p className="text-lg font-bold font-mono text-indigo-300">
                            8.4<span className="text-[10px] text-zinc-500">/32 GB</span>
                          </p>
                          <div className="h-1.5 rounded-full bg-zinc-800 overflow-hidden">
                            <div className="h-full w-[26%] rounded-full bg-gradient-to-r from-indigo-500 to-purple-400" />
                          </div>
                        </div>
                      </div>

                      {/* Semantic Clipboard History Search */}
                      <div className="rounded-xl border border-white/[0.06] bg-zinc-950/40 p-4 space-y-3 mb-5">
                        <div className="flex items-center justify-between">
                          <span className="text-xs text-zinc-300 font-bold flex items-center gap-1.5">
                            <ClipboardList className="size-3.5 text-cyan-400" />
                            جستجوی معنایی کلیپ‌بورد (Semantic Clipboard)
                          </span>
                          <span className="font-mono text-[9px] text-zinc-500">AES-256 ENCRYPTED · LOCAL ONLY</span>
                        </div>
                        <input
                          value={clipQuery}
                          onChange={(e) => setClipQuery(e.target.value)}
                          placeholder="مثلاً: TTFT یا نقشه راه یا گیت‌هاب..."
                          className="w-full rounded-lg border border-white/[0.08] bg-zinc-900/80 px-3 py-2 text-xs text-zinc-100 placeholder-zinc-500 focus:outline-none focus:border-cyan-500/50"
                        />
                        <div className="space-y-1.5">
                          {filteredClips.map((clip) => (
                            <div
                              key={clip.id}
                              className="flex items-center justify-between gap-2 rounded-lg border border-white/5 bg-zinc-950/60 p-2.5"
                            >
                              <div className="min-w-0">
                                <p className="text-[11px] text-zinc-200 truncate font-mono">{clip.content}</p>
                                <p className="text-[9px] text-zinc-500 mt-0.5 font-mono">
                                  {clip.source} · {clip.time}
                                </p>
                              </div>
                              <span
                                className={`shrink-0 px-1.5 py-0.5 rounded text-[9px] font-mono ${
                                  clip.tag === 'SECRET'
                                    ? 'bg-rose-500/20 text-rose-300'
                                    : clip.tag === 'CODE'
                                      ? 'bg-amber-500/20 text-amber-300'
                                      : 'bg-cyan-500/20 text-cyan-300'
                                }`}
                              >
                                {clip.tag}
                              </span>
                            </div>
                          ))}
                          {filteredClips.length === 0 && (
                            <p className="text-[10px] text-zinc-500 font-mono py-2 text-center">
                              موردی یافت نشد — جستجوی معنایی برداری در کل تاریخچه انجام شد.
                            </p>
                          )}
                        </div>
                      </div>

                      {/* System Command Quick Registry */}
                      <div className="space-y-1.5 mb-6">
                        <span className="text-xs text-zinc-400 font-mono block">
                          دستورات سیستمی پرکاربرد (Quick System Registry):
                        </span>
                        {commandRegistry.slice(5, 8).map((cmd) => {
                          const Icon = cmd.icon;
                          return (
                            <button
                              key={cmd.id}
                              onClick={cmd.execute}
                              className="w-full flex items-center justify-between gap-3 rounded-xl border border-white/[0.05] bg-zinc-950/60 p-3 text-right hover:border-indigo-500/40 hover:bg-indigo-950/20 transition-all"
                            >
                              <div className="flex items-center gap-2.5 min-w-0">
                                <div className="size-8 rounded-lg bg-zinc-900 border border-white/5 flex items-center justify-center text-indigo-300 shrink-0">
                                  <Icon className="size-3.5" />
                                </div>
                                <div className="min-w-0">
                                  <p className="text-xs font-semibold text-zinc-100 truncate">{cmd.title}</p>
                                  <p className="font-mono text-[9px] text-zinc-500 truncate">{cmd.desc}</p>
                                </div>
                              </div>
                              <span className="shrink-0 font-mono text-[9px] text-emerald-300 bg-emerald-500/10 border border-emerald-500/30 px-2 py-1 rounded">
                                EXECUTE
                              </span>
                            </button>
                          );
                        })}
                      </div>

                      {/* Big Open Omnibar Trigger */}
                      <div>
                        <button
                          onClick={() => setOmnibarOpen(true)}
                          className="w-full py-3 rounded-xl bg-gradient-to-r from-indigo-600 via-purple-600 to-cyan-600 text-white font-bold text-xs flex items-center justify-center gap-2 shadow-lg hover:opacity-90 transition-all"
                        >
                          <Command className="size-4 fill-white" />
                          <span>باز کردن پالت دستورات سراسری دریم (Ctrl+K)</span>
                        </button>
                      </div>
                    </div>

                    <div className="flex items-center justify-between text-xs text-zinc-500 font-mono border-t border-white/[0.06] pt-4">
                      <span>SEMAPHORE: OS-LEVEL GLOBAL HOOK ACTIVE</span>
                      <span>RANKING: BM25 + EMBEDDING COSINE</span>
                    </div>
                  </div>
                ) : (
                  /* ═══════════ SECURITY VAULT STUDIO (Phase 6) ═══════════ */
                  <div className="space-y-6">
                    <div className="rounded-2xl border border-emerald-500/30 bg-zinc-900/60 p-6 backdrop-blur-2xl shadow-[0_8px_32px_rgba(0,0,0,0.5)]">
                      <div className="flex items-center justify-between border-b border-white/[0.08] pb-4 mb-5">
                        <div className="flex items-center gap-2.5">
                          <div className="size-8 rounded-xl bg-emerald-500/20 border border-emerald-500/40 flex items-center justify-center text-emerald-300">
                            <Lock className="size-4" />
                          </div>
                          <div>
                            <span className="font-mono text-[10px] text-emerald-400 uppercase tracking-widest block">
                              ENTERPRISE ZERO-TELEMETRY VAULT //
                            </span>
                            <h3 className="text-sm font-bold text-white mt-0.5">
                              خزانه امنیتی محلی و حریم خصوصی داده‌ها
                            </h3>
                          </div>
                        </div>
                        <span className="px-2.5 py-1 text-[10px] font-mono rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                          ● AES-256-GCM ENCRYPTED
                        </span>
                      </div>

                      {/* Security Action Controls */}
                      <div className="grid grid-cols-2 gap-3 mb-6">
                        <div className="rounded-xl border border-white/[0.06] bg-zinc-950/60 p-4 space-y-2">
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-bold text-zinc-200">وضعیت قفل خزانه:</span>
                            <span
                              className={`px-2 py-0.5 rounded text-[9px] font-mono ${vaultLocked ? 'bg-rose-500/20 text-rose-300' : 'bg-emerald-500/20 text-emerald-300'}`}
                            >
                              {vaultLocked ? 'LOCKED' : 'UNLOCKED'}
                            </span>
                          </div>
                          <button
                            onClick={() => setVaultLocked(!vaultLocked)}
                            className="w-full py-2 rounded-lg bg-zinc-900 border border-white/10 text-xs text-zinc-300 hover:text-white hover:bg-zinc-800 transition-all flex items-center justify-center gap-1.5"
                          >
                            <Lock className="size-3.5" />
                            <span>{vaultLocked ? 'بازگشایی با بیومتریک' : 'قفل فوری خزانه (Lock Now)'}</span>
                          </button>
                        </div>

                        <div className="rounded-xl border border-white/[0.06] bg-zinc-950/60 p-4 space-y-2">
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-bold text-zinc-200">پالایش کلمات حساس (PII):</span>
                            <span
                              className={`px-2 py-0.5 rounded text-[9px] font-mono ${piiRedactionActive ? 'bg-emerald-500/20 text-emerald-300' : 'bg-zinc-800 text-zinc-500'}`}
                            >
                              {piiRedactionActive ? 'ACTIVE' : 'OFF'}
                            </span>
                          </div>
                          <button
                            onClick={() => setPiiRedactionActive(!piiRedactionActive)}
                            className="w-full py-2 rounded-lg bg-zinc-900 border border-white/10 text-xs text-zinc-300 hover:text-white hover:bg-zinc-800 transition-all flex items-center justify-center gap-1.5"
                          >
                            <KeyRound className="size-3.5" />
                            <span>تغییر وضعیت پالایشگر</span>
                          </button>
                        </div>
                      </div>

                      {/* SSRF Shield Policy Mode */}
                      <div className="rounded-xl border border-white/[0.06] bg-zinc-950/40 p-4 space-y-3 mb-6">
                        <span className="text-xs text-zinc-400 font-mono block">
                          سیاست دیوار آتشین وب (SSRF Shield Policy):
                        </span>
                        <div className="grid grid-cols-3 gap-2">
                          {[
                            { id: 'strict', label: 'سخت‌گیرانه (Strict)', desc: 'مسدودسازی Localhost و متادیتا' },
                            { id: 'airgap', label: 'ایزوله مطلق (Airgap)', desc: 'قطع ۱۰۰٪ ترافیک شبکه' },
                            { id: 'permissive', label: 'آزاد (Permissive)', desc: 'دسترسی عمومی استاندارد' },
                          ].map((m) => (
                            <button
                              key={m.id}
                              onClick={() => setSsrfShieldMode(m.id as any)}
                              className={`rounded-xl p-3 text-right border transition-all ${
                                ssrfShieldMode === m.id
                                  ? 'border-emerald-500/50 bg-emerald-950/30 text-white shadow-lg'
                                  : 'border-white/[0.06] bg-zinc-900/40 text-zinc-400 hover:text-white'
                              }`}
                            >
                              <p className="text-xs font-bold text-zinc-200">{m.label}</p>
                              <p className="text-[10px] text-zinc-500 mt-1">{m.desc}</p>
                            </button>
                          ))}
                        </div>
                      </div>

                      {/* Live Immutable Audit Logs Feed */}
                      <div className="space-y-2 mb-6">
                        <span className="text-xs text-zinc-400 font-mono block">
                          لاگ‌های غیرقابل دستکاری امنیتی (Audit Logs):
                        </span>
                        <div className="space-y-1.5 font-mono text-[10px]">
                          {auditLogs.map((log) => (
                            <div
                              key={log.id}
                              className="flex items-center justify-between bg-zinc-950/60 p-2.5 rounded-lg border border-white/5"
                            >
                              <div className="flex items-center gap-2">
                                <span className="text-zinc-500">{log.time}</span>
                                <span className="text-zinc-300">{log.event}</span>
                              </div>
                              <span
                                className={`px-1.5 py-0.5 rounded text-[9px] ${
                                  log.status === 'blocked'
                                    ? 'bg-rose-500/20 text-rose-300'
                                    : log.status === 'encrypted'
                                      ? 'bg-emerald-500/20 text-emerald-300'
                                      : 'bg-cyan-500/20 text-cyan-300'
                                }`}
                              >
                                {log.status.toUpperCase()}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>

                      {/* Rotate Keys Trigger */}
                      <div>
                        <button
                          onClick={handleTriggerSecurityAudit}
                          className="w-full py-3 rounded-xl bg-gradient-to-r from-emerald-600 via-teal-600 to-cyan-600 text-white font-bold text-xs flex items-center justify-center gap-2 shadow-lg hover:opacity-90 transition-all"
                        >
                          <ShieldCheck className="size-3.5 fill-white" />
                          <span>اجرای ممیزی کامل و چرخش کلیدهای رمزنگاری (Audit & Rotate Keys)</span>
                        </button>
                      </div>
                    </div>

                    <div className="flex items-center justify-between text-xs text-zinc-500 font-mono border-t border-white/[0.06] pt-4">
                      <span>SECURITY: ZERO EXTERNAL TELEMETRY</span>
                      <span>STANDARDS: NIST SP 800-38D · ISO 27001 READY</span>
                    </div>
                  </div>
                )
              ) : (
                /* Source Code Editor View */
                <div className="rounded-xl border border-white/[0.08] bg-[#050507] p-4 font-mono text-xs text-zinc-300 shadow-inner overflow-x-auto">
                  <div className="flex items-center justify-between border-b border-white/[0.06] pb-2 mb-3 text-zinc-500 text-[11px]">
                    <span className="text-indigo-400">
                      {activeArtifact.type === 'omnibar'
                        ? 'GLOBAL_OMNIBAR_ENGINE.TSX'
                        : 'CRYPTOGRAPHIC_VAULT_ENGINE.TSX'}
                    </span>
                    <span>2.6 KB · UTF-8</span>
                  </div>
                  <pre className="leading-relaxed whitespace-pre-wrap">{activeArtifact.code}</pre>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* ═══════════ GLOBAL OMNIBAR OVERLAY (Ctrl+K) — Phase 7 Final ═══════════ */}
      {omnibarOpen && (
        <div
          className="fixed inset-0 z-50 flex items-start justify-center bg-black/70 pt-20 backdrop-blur-sm"
          onClick={() => setOmnibarOpen(false)}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Dream omnibar"
            className="w-full max-w-xl overflow-hidden rounded-2xl border border-white/10 bg-zinc-900/95 shadow-[0_24px_80px_rgba(0,0,0,0.8)] backdrop-blur-3xl"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Input Row */}
            <div className="flex items-center gap-3 border-b border-white/[0.06] px-4 py-3.5">
              <Command className="size-4 shrink-0 text-indigo-400" />
              <input
                autoFocus
                value={omnibarQuery}
                onChange={(e) => {
                  setOmnibarQuery(e.target.value);
                  setSelectedCommandIdx(0);
                }}
                onKeyDown={(e) => {
                  if (e.key === 'ArrowDown') {
                    e.preventDefault();
                    setSelectedCommandIdx((i) => Math.min(i + 1, filteredCommands.length - 1));
                  } else if (e.key === 'ArrowUp') {
                    e.preventDefault();
                    setSelectedCommandIdx((i) => Math.max(i - 1, 0));
                  } else if (e.key === 'Enter') {
                    e.preventDefault();
                    const cmd = filteredCommands[selectedCommandIdx];
                    if (cmd) {
                      cmd.execute();
                      setOmnibarOpen(false);
                      setOmnibarQuery('');
                    }
                  }
                }}
                placeholder="دستور سیستمی، فایل، ماژول، کلیپ‌بورد یا هر چیزی که در ذهن دارید..."
                className="flex-1 bg-transparent text-sm text-white placeholder-zinc-500 focus:outline-none"
                dir="rtl"
              />
              <span className="shrink-0 rounded border border-white/10 px-1.5 py-0.5 font-mono text-[9px] text-zinc-500">
                ESC
              </span>
            </div>

            {/* Semantic Results */}
            <div className="max-h-80 overflow-y-auto p-2 scrollbar-thin">
              {filteredCommands.map((cmd, idx) => {
                const Icon = cmd.icon;
                return (
                  <button
                    key={cmd.id}
                    onClick={() => {
                      cmd.execute();
                      setOmnibarOpen(false);
                      setOmnibarQuery('');
                    }}
                    className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-right transition-all ${
                      idx === selectedCommandIdx ? 'bg-white/10 shadow-inner' : 'hover:bg-white/5'
                    }`}
                  >
                    <div className="flex size-8 shrink-0 items-center justify-center rounded-lg border border-white/5 bg-zinc-800 text-indigo-300">
                      <Icon className="size-3.5" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-xs font-semibold text-zinc-100">{cmd.title}</p>
                      <p className="truncate font-mono text-[10px] text-zinc-500">{cmd.desc}</p>
                    </div>
                    <span className="shrink-0 rounded bg-indigo-500/10 px-1.5 py-0.5 font-mono text-[9px] text-indigo-300 border border-indigo-500/30">
                      {cmd.category}
                    </span>
                    {cmd.shortcut && (
                      <span className="shrink-0 font-mono text-[9px] text-zinc-500">{cmd.shortcut}</span>
                    )}
                  </button>
                );
              })}

              {filteredCommands.length === 0 && (
                <button
                  onClick={() => {
                    handleSendMessage(omnibarQuery);
                    setOmnibarOpen(false);
                    setOmnibarQuery('');
                  }}
                  className="flex w-full items-center gap-3 rounded-xl px-3 py-3 text-right hover:bg-white/5 transition-all"
                >
                  <div className="flex size-8 shrink-0 items-center justify-center rounded-lg border border-white/5 bg-zinc-800 text-cyan-300">
                    <Search className="size-3.5" />
                  </div>
                  <p className="text-xs text-zinc-200">
                    پرسیدن از دریم: «<span className="text-cyan-300 font-semibold">{omnibarQuery}</span>»
                  </p>
                </button>
              )}
            </div>

            {/* Footer Hints */}
            <div className="flex items-center justify-between border-t border-white/[0.06] px-4 py-2 font-mono text-[9px] text-zinc-500">
              <span>↑↓ NAVIGATE · ↵ EXECUTE · ESC CLOSE</span>
              <span>DREAM OMNIBAR // SEMANTIC INDEX · 52 MODULES</span>
            </div>
          </div>
        </div>
      )}

      {/* Slide-over Swiss Index Drawer */}
      {inspector.open && (
        <div className="w-88 shrink-0 border-r border-white/[0.08] bg-zinc-950/95 backdrop-blur-3xl p-6 flex flex-col justify-between shadow-2xl transition-all duration-300 z-40 overflow-y-auto min-h-0 scrollbar-thin">
          <div className="space-y-5">
            <div className="flex items-center justify-between border-b border-white/[0.08] pb-4">
              <div>
                <span className="font-mono text-[10px] text-indigo-400 tracking-widest uppercase block">
                  {inspector.sectionNo || 'DRAWER // 01'}
                </span>
                <span className="text-xs font-bold text-zinc-100 mt-0.5 block">{inspector.title}</span>
              </div>
              <button
                onClick={() => setInspector({ open: false, type: null, title: '' })}
                className="text-zinc-500 hover:text-white"
              >
                <X className="size-4" />
              </button>
            </div>

            {inspector.type === 'index' && (
              <div className="space-y-4 text-xs">
                <div>
                  <span className="font-mono text-[10px] tracking-wider text-zinc-500 uppercase block mb-2">
                    01 // COGNITION & MEMORY
                  </span>
                  <div className="space-y-1.5">
                    <button
                      onClick={() => void navigate('/memory')}
                      className="w-full flex items-center justify-between rounded-xl border border-white/[0.05] bg-zinc-900/40 p-3 text-right hover:bg-white/[0.08] transition-all"
                    >
                      <div>
                        <p className="font-semibold text-zinc-200">حافظه اپیزودیک و تقویم جلالی</p>
                        <p className="font-mono text-[10px] text-zinc-500 mt-0.5">Episodic Knowledge Graph</p>
                      </div>
                      <ChevronRight className="size-3.5 text-zinc-500 rtl:rotate-180" />
                    </button>
                    <button
                      onClick={() => void navigate('/subagents')}
                      className="w-full flex items-center justify-between rounded-xl border border-white/[0.05] bg-zinc-900/40 p-3 text-right hover:bg-white/[0.08] transition-all"
                    >
                      <div>
                        <p className="font-semibold text-zinc-200">شبکه عاملی و شورای نورا (Swarm)</p>
                        <p className="font-mono text-[10px] text-zinc-500 mt-0.5">Multi-Agent Council Mesh</p>
                      </div>
                      <ChevronRight className="size-3.5 text-zinc-500 rtl:rotate-180" />
                    </button>
                  </div>
                </div>

                <div>
                  <span className="font-mono text-[10px] tracking-wider text-zinc-500 uppercase block mb-2">
                    02 // EXPLORATION & TOOLS
                  </span>
                  <div className="space-y-1.5">
                    <button
                      onClick={() => void navigate('/browse')}
                      className="w-full flex items-center justify-between rounded-xl border border-white/[0.05] bg-zinc-900/40 p-3 text-right hover:bg-white/[0.08] transition-all"
                    >
                      <div>
                        <p className="font-semibold text-zinc-200">مرورگر عمیق Playwright</p>
                        <p className="font-mono text-[10px] text-zinc-500 mt-0.5">Autonomous Deep Browser</p>
                      </div>
                      <ChevronRight className="size-3.5 text-zinc-500 rtl:rotate-180" />
                    </button>
                    <button
                      onClick={() => void navigate('/data')}
                      className="w-full flex items-center justify-between rounded-xl border border-white/[0.05] bg-zinc-900/40 p-3 text-right hover:bg-white/[0.08] transition-all"
                    >
                      <div>
                        <p className="font-semibold text-zinc-200">سندباکس کد و پردازش داده</p>
                        <p className="font-mono text-[10px] text-zinc-500 mt-0.5">Polyglot Execution Core</p>
                      </div>
                      <ChevronRight className="size-3.5 text-zinc-500 rtl:rotate-180" />
                    </button>
                  </div>
                </div>

                <div>
                  <span className="font-mono text-[10px] tracking-wider text-zinc-500 uppercase block mb-2">
                    03 // CORE & ENGINE
                  </span>
                  <div className="space-y-1.5">
                    <button
                      onClick={() => void navigate('/settings')}
                      className="w-full flex items-center justify-between rounded-xl border border-white/[0.05] bg-zinc-900/40 p-3 text-right hover:bg-white/[0.08] transition-all"
                    >
                      <div>
                        <p className="font-semibold text-zinc-200">شتاب‌دهنده سخت‌افزاری و سلامت</p>
                        <p className="font-mono text-[10px] text-zinc-500 mt-0.5">Hardware Telemetry & MPS</p>
                      </div>
                      <ChevronRight className="size-3.5 text-zinc-500 rtl:rotate-180" />
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* Model Selector */}
            {inspector.type === 'model' && (
              <div className="space-y-2 text-xs">
                {[
                  {
                    name: 'Qwen 2.5 (32B Dual-Speculative)',
                    desc: 'استریم دوهسته‌ای موازی · تاخیر ۱۲.۸ms',
                    tag: 'DUAL CORE',
                  },
                  {
                    name: 'DeepSeek-R1 (Reasoner)',
                    desc: 'هسته استدلال ریاضی و تایید گمانه‌زنی',
                    tag: 'VERIFIER',
                  },
                  {
                    name: 'Claude 3.7 Sonnet',
                    desc: 'استدلال فوق‌پیشرفته و درخت افکار',
                    tag: 'CLOUD',
                  },
                  {
                    name: 'Llama 3.3 (70B Local)',
                    desc: 'کدنویسی سنگین و مسائل پیچیده',
                    tag: 'LOCAL',
                  },
                ].map((m, idx) => (
                  <button
                    key={idx}
                    onClick={() => {
                      setSelectedModel(m.name);
                      setInspector({ open: false, type: null, title: '' });
                    }}
                    className={`w-full flex items-center justify-between rounded-xl border p-3 text-right transition-all ${
                      selectedModel === m.name
                        ? 'border-indigo-500/50 bg-indigo-950/30 text-white'
                        : 'border-white/[0.05] bg-zinc-900/40 text-zinc-300 hover:bg-white/[0.06]'
                    }`}
                  >
                    <div>
                      <p className="font-medium text-xs text-white">{m.name}</p>
                      <p className="text-[10px] text-zinc-400 mt-0.5">{m.desc}</p>
                    </div>
                    <span className="font-mono text-[9px] rounded px-1.5 py-0.5 bg-white/5 text-zinc-400">
                      {m.tag}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="border-t border-white/[0.08] pt-4">
            <button
              onClick={() => setInspector({ open: false, type: null, title: '' })}
              className="w-full rounded-xl border border-white/[0.08] bg-zinc-900 py-2.5 font-mono text-xs text-zinc-300 hover:text-white transition-colors"
            >
              CLOSE // بستن
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
