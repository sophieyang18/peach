import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode, RefObject } from 'react'
import './App.css'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'
const PEACH_PORTRAIT = '/peach-assets/peach-portrait.png'
const PEACH_ICON = '/peach-assets/peach-icon.png'
const NAV_ICONS: Record<PrimaryModule, string> = {
  peach: '/peach-assets/nav-peach.jpg',
  profile: '/peach-assets/nav-profile.jpg',
  knowledge: '/peach-assets/nav-knowledge.jpg',
}

type PrimaryModule = 'peach' | 'profile' | 'knowledge'
type PeachPanel = 'new-chat' | 'interview-setup' | 'question-bank-setup' | 'live-interview'
type InterviewMode = 'voice' | 'video'
type TtsRateMode = 'slow' | 'medium' | 'fast'
type VoiceCaptureMode = 'auto' | 'dictation'
type ProfileSectionId = 'reviews' | 'full' | 'internship' | 'project' | 'education' | 'skills' | 'competition'
type AgentToolName =
  | 'start_interview'
  | 'finish_latest_interview'
  | 'update_profile_fields'
  | 'update_resume'
  | 'append_profile_note'
  | 'add_knowledge_item'
  | 'update_knowledge_item'
  | 'delete_knowledge_item'
  | 'unsupported'
type AgentActionStatus = 'pending' | 'executing' | 'approved' | 'dismissed'
type ToolActionDetail = {
  title: string
  summary: string
  items: string[]
  content?: string
}
type AgentToolProposal = {
  id: string
  tool: AgentToolName
  title: string
  summary: string
  payload: Record<string, unknown>
  approval_required: boolean
  status?: AgentActionStatus
  result?: ToolActionDetail
}
type MemoryWrite = { id: string; kind: string; content: string }
type ChatMessage = { role: 'peach' | 'user' | 'system'; content: string; actions?: AgentToolProposal[] }
type Conversation = { id: string; title: string; updatedAt: string; messages: ChatMessage[] }
type BusyKey = 'account' | 'refresh' | 'recommend' | 'chat' | 'interviewStart' | 'profile' | 'knowledge' | 'upload'
type Account = { username: string; display_name?: string }

type Profile = {
  id: string
  username?: string
  name: string
  target_role: string
  target_company: string
  target_city: string
  stage: string
  resume_text: string
  communication_style: string
  strengths: string[]
  weak_points: string[]
  plan: Array<{ day: number; title: string; focus: string }>
}

type Dashboard = {
  profile: Profile
  checkin: {
    message: string
    task: { title: string; question: string; duration: string; focus: string }
  }
  recent_practices: Array<{
    id: string
    question: string
    answer: string
    score: number
    tags: string[]
    feedback: {
      summary?: string
      highlights?: string[]
      improvements?: string[]
      archive?: string
      next_task?: string
    }
  }>
  recent_interviews: Array<{
    id: string
    interview_type: string
    interviewer_style: string
    company: string
    role: string
    status: string
    transcript: Array<{ role: string; content: string }>
    report: InterviewReport
    created_at?: string
  }>
  growth: {
    avg_score: number
    practice_count: number
    interview_count: number
    completed_interview_count: number
    strengths: string[]
    weak_points: string[]
    progress_points: Array<{ label: string; score: number }>
  }
}

type InterviewReport = {
  position?: string
  overall_score?: number
  level?: string
  percentile?: number
  dimensions?: Array<{ name: string; score: number }>
  summary?: string
  key_improvements?: string[]
  next_plan?: string[]
  question_review?: Array<{
    question?: string
    assessment_focus?: string
    candidate_transcript?: string
    sample_answer?: string
  }>
}

type InterviewSettings = {
  resume: string
  jd: string
  gender: string
  style: string
  mode: InterviewMode
  questionBank: string
}

type InterviewProgress = {
  answer_count: number
  question_count: number
  min_answers_for_llm_finish: number
  target_answers: number
  max_answers: number
  completion: number
  can_llm_finish: boolean
  checklist?: Array<{ key: string; label: string; description: string; done: boolean }>
}

type ResumeFolder = {
  id: string
  title: string
  summary: string
  sectionId?: ProfileSectionId
  children?: Array<{ id: ProfileSectionId; title: string; summary: string }>
}

type KnowledgeItem = {
  id: string
  title: string
  summary: string
  content?: string
  url?: string
  source: string
  saved?: boolean
}

type ParsedUpload = {
  filename: string
  extension: string
  title: string
  summary: string
  content: string
  warning?: string
}

type KnowledgeDraft = {
  title: string
  summary: string
  content: string
  url: string
}

type KnowledgeTab = 'personal' | 'saved' | 'discover'
type KnowledgeFolder = {
  id: string
  name: string
  scope: Exclude<KnowledgeTab, 'discover'>
  item_ids: string[]
  sort_order?: number
  created_at?: string
  updated_at?: string
  collapsed?: boolean
}
type SortMode = 'updated' | 'name'
type SpeechRecognitionEventLike = {
  results: ArrayLike<{ isFinal?: boolean; 0?: { transcript?: string } }>
}
type BrowserSpeechRecognition = {
  lang: string
  interimResults: boolean
  continuous: boolean
  onresult: ((event: SpeechRecognitionEventLike) => void) | null
  onerror: (() => void) | null
  onend: (() => void) | null
  start: () => void
  stop: () => void
}
type SpeechRecognitionWindow = Window & {
  SpeechRecognition?: new () => BrowserSpeechRecognition
  webkitSpeechRecognition?: new () => BrowserSpeechRecognition
}

const profileSectionMeta: Record<ProfileSectionId, { title: string; summary: string; helper: string }> = {
  reviews: {
    title: '面试复盘',
    summary: '记录真实面试后的情绪、题目、回答卡点和下一步行动。',
    helper: '适合补充面试题、卡住的问题、面试官反馈、自己的体感和下一次要改的动作。',
  },
  full: {
    title: '完整简历',
    summary: '用于投递和面试的主版本简历。',
    helper: '可以粘贴完整简历，也可以先写岗位目标、经历摘要和你最想突出的亮点。',
  },
  internship: {
    title: '实习经历',
    summary: '沉淀公司、岗位、职责、产出和可量化结果。',
    helper: '建议按公司、岗位、任务、行动、结果来写，桃子会帮你补结构和追问点。',
  },
  project: {
    title: '项目经历',
    summary: '沉淀背景、目标、行动、结果和可追问细节。',
    helper: '建议写清楚项目背景、你负责的部分、关键决策、指标结果和复盘。',
  },
  education: {
    title: '教育背景',
    summary: '整理学校、专业、课程和与岗位相关的学习经历。',
    helper: '适合补充专业、课程、论文、社团、交换、证书和与岗位相关的学习证据。',
  },
  skills: {
    title: '个人技能',
    summary: '整理工具、方法论、数据分析和协作能力。',
    helper: '适合列出工具、方法论、数据能力、行业理解、表达协作能力和熟练程度。',
  },
  competition: {
    title: '竞赛经历',
    summary: '记录比赛角色、方案亮点、排名和复盘收获。',
    helper: '建议写清比赛背景、你的角色、方案亮点、结果排名和能迁移到岗位的能力。',
  },
}

const initialProfileSections: Record<ProfileSectionId, string> = {
  reviews: '',
  full: '',
  internship: '',
  project: '',
  education: '',
  skills: '',
  competition: '',
}

const defaultProfile: Profile = {
  id: 'local',
  name: '同学',
  target_role: '产品经理',
  target_company: '',
  target_city: '',
  stage: '投递期',
  resume_text: '',
  communication_style: '温暖直接',
  strengths: ['目标岗位聚焦', '愿意持续练习'],
  weak_points: ['回答结构需要稳定', '简历亮点需要量化'],
  plan: [
    { day: 1, title: '自我介绍', focus: '把经历、目标和岗位连接起来' },
    { day: 2, title: '项目深挖', focus: '准备能被追问的证据' },
    { day: 3, title: '模拟面试', focus: '练习真实压力下的表达节奏' },
  ],
}

const fixedBubbles = ['帮我模拟面试', '帮我写简历', '帮我改简历']
const composerActions = ['模拟面试', '题库练习', '简历优化', '简历撰写']
const defaultInterviewProgress: InterviewProgress = {
  answer_count: 0,
  question_count: 0,
  min_answers_for_llm_finish: 8,
  target_answers: 10,
  max_answers: 12,
  completion: 0,
  can_llm_finish: false,
  checklist: [
    { key: 'self_intro', label: '自我介绍', description: '开场介绍已经建立候选人背景和目标', done: false },
    { key: 'experience_deep_dive', label: '经历深挖', description: '至少追问过一段实习或项目', done: false },
    { key: 'role_understanding', label: '岗位理解', description: '覆盖岗位、公司或业务理解', done: false },
    { key: 'evidence_quality', label: '证据质量', description: '回答中有贡献、指标或事实边界', done: false },
    { key: 'pressure_followup', label: '压力追问', description: '完成过质疑或挑战追问', done: false },
    { key: 'closing_readiness', label: '收尾准备', description: '足够生成复盘和下一步计划', done: false },
  ],
}

const initialConversations: Conversation[] = [
  {
    id: 'chat-default',
    title: '新建对话',
    updatedAt: '刚刚',
    messages: [],
  },
]

function App() {
  const [account, setAccount] = useState<Account | null>(null)
  const [accountInput, setAccountInput] = useState(() => window.localStorage.getItem('peach:last-username') ?? '')
  const [accountMessage, setAccountMessage] = useState('输入用户名登录，或直接创建一个 demo 账号。')
  const [module, setModule] = useState<PrimaryModule>('peach')
  const [peachPanel, setPeachPanel] = useState<PeachPanel>('new-chat')
  const [dashboard, setDashboard] = useState<Dashboard | null>(null)
  const [busy, setBusy] = useState<Partial<Record<BusyKey, string>>>({})
  const [notice, setNotice] = useState('准备好了就开始。')
  const [error, setError] = useState('')
  const [input, setInput] = useState('')
  const [profileInput, setProfileInput] = useState('')
  const [activeProfileSection, setActiveProfileSection] = useState<ProfileSectionId>('full')
  const [profileSections, setProfileSections] = useState<Record<ProfileSectionId, string>>({ ...initialProfileSections })
  const [profileActionResult, setProfileActionResult] = useState('')
  const [profileMessages, setProfileMessages] = useState<ChatMessage[]>([])
  const [resumeFiles, setResumeFiles] = useState<ParsedUpload[]>([])
  const [knowledgeQuestion, setKnowledgeQuestion] = useState('')
  const [knowledgeMessages, setKnowledgeMessages] = useState<ChatMessage[]>([])
  const [personalKnowledge, setPersonalKnowledge] = useState<KnowledgeItem[]>([])
  const [discoverKnowledge, setDiscoverKnowledge] = useState<KnowledgeItem[]>(discoverKnowledgeFeed())
  const [activeKnowledgeId, setActiveKnowledgeId] = useState('')
  const [knowledgeQuery, setKnowledgeQuery] = useState('')
  const [knowledgeDraft, setKnowledgeDraft] = useState<KnowledgeDraft>({
    title: '',
    summary: '',
    content: '',
    url: '',
  })
  const [knowledgeActionResult, setKnowledgeActionResult] = useState('')
  const [knowledgeActionMode, setKnowledgeActionMode] = useState('')
  const [isCreatingKnowledge, setIsCreatingKnowledge] = useState(false)
  const [conversations, setConversations] = useState<Conversation[]>(initialConversations)
  const [activeConversationId, setActiveConversationId] = useState(initialConversations[0].id)
  const [recommendations, setRecommendations] = useState<string[]>([])
  const [settings, setSettings] = useState<InterviewSettings>({
    resume: '完整简历',
    jd: '',
    gender: '女性',
    style: '温和型',
    mode: 'voice',
    questionBank: '产品经理通用题库',
  })
  const [liveKind, setLiveKind] = useState<'interview' | 'question-bank'>('interview')
  const [activeInterviewId, setActiveInterviewId] = useState('')
  const [interviewProgress, setInterviewProgress] = useState<InterviewProgress>(defaultInterviewProgress)
  const [finishSuggestionShown, setFinishSuggestionShown] = useState(false)
  const [seconds, setSeconds] = useState(0)
  const [paused, setPaused] = useState(false)
  const [subtitleCollapsed, setSubtitleCollapsed] = useState(false)
  const [timerCollapsed, setTimerCollapsed] = useState(false)
  const [mediaStream, setMediaStream] = useState<MediaStream | null>(null)
  const [mediaReady, setMediaReady] = useState(false)
  const [ttsMuted, setTtsMuted] = useState(false)
  const [ttsSpeaking, setTtsSpeaking] = useState(false)
  const [lastTtsText, setLastTtsText] = useState('')
  const [ttsRateMode, setTtsRateMode] = useState<TtsRateMode>('medium')
  const [immersiveInterview, setImmersiveInterview] = useState(false)
  const [subNavCollapsed, setSubNavCollapsed] = useState(false)
  const [knowledgeTab, setKnowledgeTab] = useState<KnowledgeTab>('personal')
  const [knowledgeFolderSort, setKnowledgeFolderSort] = useState<SortMode>('updated')
  const [knowledgeFileSort, setKnowledgeFileSort] = useState<SortMode>('updated')
  const [knowledgeFolders, setKnowledgeFolders] = useState<Record<Exclude<KnowledgeTab, 'discover'>, KnowledgeFolder[]>>({
    personal: [{ id: 'personal-default', name: '默认文件夹', scope: 'personal', item_ids: [] }],
    saved: [{ id: 'saved-default', name: '默认收藏', scope: 'saved', item_ids: [] }],
  })
  const [activeKnowledgeFolderId, setActiveKnowledgeFolderId] = useState('personal-default')
  const [savedKnowledge, setSavedKnowledge] = useState<string[]>(['pm-method'])

  const chatScrollRef = useRef<HTMLElement | null>(null)
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const ttsUtteranceRef = useRef<SpeechSynthesisUtterance | null>(null)
  const lastInterviewAnswerRef = useRef<{ text: string; at: number }>({ text: '', at: 0 })
  const recommendationsHydratedRef = useRef(false)
  const profileHydratedRef = useRef(false)
  const knowledgeHydratedRef = useRef(false)

  const profile = dashboard?.profile ?? defaultProfile
  const activeConversation = conversations.find((item) => item.id === activeConversationId) ?? conversations[0]
  const busyText = Object.values(busy)[0]
  const fallbackRecommendations = useMemo(() => buildRecommendations(profile, dashboard), [profile, dashboard])
  const visibleRecommendations = useMemo(
    () => safeRecommendations(recommendations, fallbackRecommendations),
    [fallbackRecommendations, recommendations],
  )
  const resumeFolders = useMemo(() => buildResumeFolders(profile, dashboard, profileSections), [profile, dashboard, profileSections])
  const knowledgeItems = useMemo(
    () => uniqueKnowledgeItems([...personalKnowledge, ...buildKnowledgeItems(profile), ...discoverKnowledge]),
    [discoverKnowledge, personalKnowledge, profile],
  )

  const api = useCallback(async <T,>(path: string, options?: RequestInit): Promise<T> => {
    setError('')
    return fetchJsonWithRetry<T>(`${API_BASE}${path}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...(account?.username ? { 'X-Peach-User': account.username } : {}),
        ...(options?.headers ?? {}),
      },
    })
  }, [account?.username])

  const uploadApi = useCallback(async <T,>(path: string, file: File, fields: Record<string, string> = {}): Promise<T> => {
    setError('')
    const body = new FormData()
    body.append('file', file)
    Object.entries(fields).forEach(([key, value]) => body.append(key, value))
    const response = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      body,
      headers: account?.username ? { 'X-Peach-User': account.username } : undefined,
    })
    if (!response.ok) throw new Error(await responseErrorMessage(response))
    return response.json()
  }, [account?.username])

  const begin = useCallback((key: BusyKey, message: string) => {
    setBusy((current) => ({ ...current, [key]: message }))
    setNotice(message)
  }, [])

  const end = useCallback((key: BusyKey) => {
    setBusy((current) => {
      const next = { ...current }
      delete next[key]
      return next
    })
  }, [])

  const stopTts = useCallback(() => {
    if ('speechSynthesis' in window) window.speechSynthesis.cancel()
    ttsUtteranceRef.current = null
    setTtsSpeaking(false)
  }, [])

  const speakInterviewText = useCallback((raw: string, force = false) => {
    const text = cleanAssistantText(raw)
      .replace(/\s+/g, ' ')
      .trim()
    if (!text) return
    setLastTtsText(text)
    if (ttsMuted && !force) return
    if (!('speechSynthesis' in window) || !('SpeechSynthesisUtterance' in window)) {
      setNotice('当前浏览器不支持语音朗读。')
      return
    }

    window.speechSynthesis.cancel()
    const utterance = new SpeechSynthesisUtterance(text)
    utterance.lang = 'zh-CN'
    utterance.rate = ttsRateValue(ttsRateMode)
    utterance.pitch = 1
    utterance.volume = 1
    const voices = window.speechSynthesis.getVoices()
    const zhVoice = voices.find((voice) => voice.lang.toLowerCase().startsWith('zh')) ?? voices[0]
    if (zhVoice) utterance.voice = zhVoice
    utterance.onstart = () => setTtsSpeaking(true)
    utterance.onend = () => {
      if (ttsUtteranceRef.current === utterance) ttsUtteranceRef.current = null
      setTtsSpeaking(false)
    }
    utterance.onerror = () => {
      if (ttsUtteranceRef.current === utterance) ttsUtteranceRef.current = null
      setTtsSpeaking(false)
    }
    ttsUtteranceRef.current = utterance
    setTtsSpeaking(true)
    window.speechSynthesis.speak(utterance)
  }, [ttsMuted, ttsRateMode])

  const toggleTtsMuted = useCallback(() => {
    setTtsMuted((current) => {
      const next = !current
      if (next) {
        if ('speechSynthesis' in window) window.speechSynthesis.cancel()
        ttsUtteranceRef.current = null
        setTtsSpeaking(false)
      }
      return next
    })
  }, [])

  const replayTts = useCallback(() => {
    if (lastTtsText) speakInterviewText(lastTtsText, true)
  }, [lastTtsText, speakInterviewText])

  const resetClientWorkspace = useCallback(() => {
    const freshConversations = initialConversations.map((conversation) => ({ ...conversation, messages: [...conversation.messages] }))
    setModule('peach')
    setPeachPanel('new-chat')
    setDashboard(null)
    setNotice('准备好了就开始。')
    setError('')
    setInput('')
    setProfileInput('')
    setActiveProfileSection('full')
    setProfileSections({ ...initialProfileSections })
    setProfileActionResult('')
    setProfileMessages([])
    setResumeFiles([])
    setKnowledgeQuestion('')
    setKnowledgeMessages([])
    setPersonalKnowledge([])
    setDiscoverKnowledge(discoverKnowledgeFeed())
    setActiveKnowledgeId('')
    setKnowledgeQuery('')
    setKnowledgeDraft({ title: '', summary: '', content: '', url: '' })
    setKnowledgeActionResult('')
    setKnowledgeActionMode('')
    setIsCreatingKnowledge(false)
    setConversations(freshConversations)
    setActiveConversationId(freshConversations[0].id)
    setRecommendations([])
    setSettings({
      resume: '完整简历',
      jd: '',
      gender: '女性',
      style: '温和型',
      mode: 'voice',
      questionBank: '产品经理通用题库',
    })
    setLiveKind('interview')
    setActiveInterviewId('')
    setInterviewProgress(defaultInterviewProgress)
    setFinishSuggestionShown(false)
    setSeconds(0)
    setPaused(false)
    setSubtitleCollapsed(false)
    setTimerCollapsed(false)
    mediaStream?.getTracks().forEach((track) => track.stop())
    setMediaStream(null)
    setMediaReady(false)
    if ('speechSynthesis' in window) window.speechSynthesis.cancel()
    ttsUtteranceRef.current = null
    setTtsSpeaking(false)
    setLastTtsText('')
    setTtsRateMode('medium')
    setImmersiveInterview(false)
    setSubNavCollapsed(false)
    setKnowledgeTab('personal')
    setKnowledgeFolderSort('updated')
    setKnowledgeFileSort('updated')
    setKnowledgeFolders({
      personal: [{ id: 'personal-default', name: '默认文件夹', scope: 'personal', item_ids: [] }],
      saved: [{ id: 'saved-default', name: '默认收藏', scope: 'saved', item_ids: [] }],
    })
    setActiveKnowledgeFolderId('personal-default')
    setSavedKnowledge(['pm-method'])
    recommendationsHydratedRef.current = false
    profileHydratedRef.current = false
    knowledgeHydratedRef.current = false
  }, [mediaStream])

  const accountRequest = useCallback(async (path: string, username?: string) => {
    return fetchJsonWithRetry<{ account: Account; profile?: Profile }>(`${API_BASE}${path}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(username ? { 'X-Peach-User': username } : {}),
      },
      body: username ? JSON.stringify({ username }) : undefined,
    })
  }, [])

  const enterAccount = useCallback((nextAccount: Account) => {
    const username = nextAccount.username.trim()
    window.localStorage.setItem('peach:last-username', username)
    resetClientWorkspace()
    setAccount({ ...nextAccount, username })
    setAccountInput(username)
    setAccountMessage(`已进入 ${username}。`)
  }, [resetClientWorkspace])

  async function loginAccount() {
    const username = accountInput.trim()
    if (!username) {
      setAccountMessage('先输入一个用户名。')
      return
    }
    begin('account', '正在登录账号')
    setError('')
    try {
      const data = await accountRequest('/api/accounts/login', username)
      enterAccount(data.account)
    } catch (err) {
      setAccountMessage(err instanceof Error ? err.message : '登录失败，可以试试创建账号。')
    } finally {
      end('account')
    }
  }

  async function createAccount() {
    const username = accountInput.trim()
    if (!username) {
      setAccountMessage('先输入一个用户名。')
      return
    }
    begin('account', '正在创建账号')
    setError('')
    try {
      const data = await accountRequest('/api/accounts', username)
      enterAccount(data.account)
    } catch (err) {
      setAccountMessage(err instanceof Error ? err.message : '创建失败，请换一个用户名。')
    } finally {
      end('account')
    }
  }

  function switchAccount() {
    resetClientWorkspace()
    setAccount(null)
    setAccountMessage('已回到账号入口。')
  }

  async function resetAccount() {
    if (!account) return
    const confirmed = window.confirm(`确定重置账号「${account.username}」吗？这个账号下的档案、面试、练习和知识库会恢复为空白 demo 状态。`)
    if (!confirmed) return
    begin('account', '正在重置账号')
    try {
      const data = await api<{ account: Account; profile: Profile }>('/api/accounts/reset', { method: 'POST' })
      resetClientWorkspace()
      setAccount(data.account)
      setAccountInput(data.account.username)
      setNotice('账号已重置。')
    } catch (err) {
      setError('账号重置失败，请稍后再试。')
      console.error(err)
    } finally {
      end('account')
    }
  }

  const refreshDashboard = useCallback(async () => {
    try {
      begin('refresh', '正在同步个人档案')
      const data = await api<Dashboard>('/api/dashboard')
      setDashboard(data)
      setNotice('个人档案已同步。')
    } catch (err) {
      setError('后端暂时没有连上。确认 FastAPI 在 8000 端口运行后再刷新。')
      console.error(err)
    } finally {
      end('refresh')
    }
  }, [api, begin, end])

  const refreshKnowledgeFolders = useCallback(async () => {
    const data = await api<{ folders: KnowledgeFolder[] }>('/api/knowledge/folders')
    const grouped = groupKnowledgeFolders(data.folders)
    setKnowledgeFolders(grouped)
    setSavedKnowledge(Array.from(new Set(grouped.saved.flatMap((folder) => folder.item_ids || []))))
    setActiveKnowledgeFolderId((current) => {
      if (data.folders.some((folder) => folder.id === current)) return current
      return grouped.personal[0]?.id ?? 'personal-default'
    })
  }, [api])

  useEffect(() => {
    if (!account) return
    void refreshDashboard()
  }, [account, refreshDashboard])

  useEffect(() => {
    if (!dashboard || profileHydratedRef.current) return
    profileHydratedRef.current = true
    setProfileSections(buildInitialProfileSections(dashboard.profile, dashboard))
  }, [dashboard])

  useEffect(() => {
    if (!dashboard || knowledgeHydratedRef.current) return
    knowledgeHydratedRef.current = true

    async function hydrateKnowledge() {
      try {
        const [knowledgeData, discoverData] = await Promise.all([
          api<{ items: KnowledgeItem[] }>('/api/knowledge'),
          api<{ items: KnowledgeItem[] }>('/api/knowledge/discover'),
        ])
        setPersonalKnowledge(knowledgeData.items)
        setDiscoverKnowledge(discoverData.items)
        await refreshKnowledgeFolders()
      } catch (err) {
        console.error(err)
      }
    }

    void hydrateKnowledge()
  }, [api, dashboard, refreshKnowledgeFolders])

  useEffect(() => {
    if (!dashboard || recommendationsHydratedRef.current) return
    recommendationsHydratedRef.current = true
    const currentDashboard = dashboard

    async function hydrateRecommendations() {
      begin('recommend', '正在生成个性化推荐')
      try {
        const history = conversations
          .flatMap((conversation) => conversation.messages)
          .filter((message) => message.role !== 'system')
          .slice(-8)
          .map((message) => `${message.role}: ${message.content}`)
          .join('\n')
        const data = await api<{ reply: string }>('/api/chat', {
          method: 'POST',
          body: JSON.stringify({
            message: `请基于我的个人档案、历史对话和面试记录，生成 4 条我会感兴趣且能提升求职能力的短建议。每条 18 字以内，只输出清单本身。\n历史对话：${history || '暂无'}\n面试记录：${JSON.stringify(currentDashboard.recent_interviews.slice(0, 3))}`,
          }),
        })
        const parsed = parseRecommendationReply(data.reply)
        if (parsed.length) setRecommendations(parsed)
      } catch (err) {
        console.error(err)
      } finally {
        end('recommend')
      }
    }

    void hydrateRecommendations()
  }, [api, begin, conversations, dashboard, end])

  useEffect(() => {
    const node = chatScrollRef.current
    if (!node) return
    requestAnimationFrame(() => {
      node.scrollTo({ top: node.scrollHeight, behavior: 'smooth' })
    })
  }, [activeConversation.messages, peachPanel])

  useEffect(() => {
    if (videoRef.current && mediaStream) {
      videoRef.current.srcObject = mediaStream
    }
  }, [mediaStream])

  useEffect(() => {
    if (peachPanel !== 'live-interview' || paused) return undefined
    const timer = window.setInterval(() => setSeconds((value) => value + 1), 1000)
    return () => window.clearInterval(timer)
  }, [paused, peachPanel])

  useEffect(() => () => {
    mediaStream?.getTracks().forEach((track) => track.stop())
  }, [mediaStream])

  useEffect(() => () => {
    if ('speechSynthesis' in window) window.speechSynthesis.cancel()
  }, [])

  function updateConversation(id: string, updater: (conversation: Conversation) => Conversation) {
    setConversations((current) => current.map((item) => (item.id === id ? updater(item) : item)))
  }

  function appendMessage(message: ChatMessage) {
    updateConversation(activeConversationId, (conversation) => {
      const shouldRetitle = message.role === 'user' && conversation.messages.filter((item) => item.role === 'user').length === 0
      return {
        ...conversation,
        title: shouldRetitle ? message.content.slice(0, 18) || conversation.title : conversation.title,
        updatedAt: '刚刚',
        messages: [...conversation.messages, message],
      }
    })
  }

  function removeSystemMessage(content: string) {
    updateConversation(activeConversationId, (conversation) => ({
      ...conversation,
      messages: conversation.messages.filter((message) => message.content !== content),
    }))
  }

  function markActionStatus(actionId: string, status: AgentActionStatus, result?: ToolActionDetail) {
    const updateMessages = (messages: ChatMessage[]) => messages.map((message) => ({
      ...message,
      actions: message.actions?.map((action) => (action.id === actionId ? { ...action, status, ...(result ? { result } : {}) } : action)),
    }))
    updateConversation(activeConversationId, (conversation) => ({
      ...conversation,
      messages: updateMessages(conversation.messages),
    }))
    setProfileMessages(updateMessages)
    setKnowledgeMessages(updateMessages)
  }

  function warnInterviewNavigationLocked() {
    setNotice('请先结束当前面试，再切换功能。')
  }

  function openModule(nextModule: PrimaryModule) {
    if (peachPanel === 'live-interview') {
      warnInterviewNavigationLocked()
      return
    }
    setModule(nextModule)
    if (nextModule === 'peach') setPeachPanel('new-chat')
    if (nextModule === 'knowledge') {
      setKnowledgeTab('personal')
      setActiveKnowledgeFolderId('personal-default')
      setActiveKnowledgeId('')
      setKnowledgeActionResult('')
      setIsCreatingKnowledge(false)
    }
    setSubNavCollapsed(false)
    setNotice(moduleNotice(nextModule))
  }

  function createConversation() {
    if (peachPanel === 'live-interview') {
      warnInterviewNavigationLocked()
      return
    }
    const active = conversations.find((conversation) => conversation.id === activeConversationId)
    if (active && active.messages.length === 0) {
      setPeachPanel('new-chat')
      setNotice('当前已经是空白对话。')
      return
    }
    const id = `chat-${Date.now()}`
    setConversations((current) => [
      { id, title: '新建对话', updatedAt: '刚刚', messages: [] },
      ...current,
    ])
    setActiveConversationId(id)
    setPeachPanel('new-chat')
    setNotice('已新建对话。')
  }

  function openConversation(id: string) {
    if (peachPanel === 'live-interview') {
      warnInterviewNavigationLocked()
      return
    }
    setActiveConversationId(id)
    setPeachPanel('new-chat')
    setNotice('已切回历史对话。')
  }

  function renameConversation(id: string) {
    if (peachPanel === 'live-interview') {
      warnInterviewNavigationLocked()
      return
    }
    const conversation = conversations.find((item) => item.id === id)
    if (!conversation) return
    const nextTitle = window.prompt('重命名对话', conversation.title)?.trim()
    if (!nextTitle) return
    setConversations((current) => current.map((item) => (
      item.id === id ? { ...item, title: nextTitle.slice(0, 28), updatedAt: '刚刚' } : item
    )))
    setNotice('对话已重命名。')
  }

  function deleteConversation(id: string) {
    if (peachPanel === 'live-interview') {
      warnInterviewNavigationLocked()
      return
    }
    const conversation = conversations.find((item) => item.id === id)
    if (!conversation) return
    const confirmed = window.confirm(`确定删除「${conversation.title}」吗？这会移除当前浏览器里的这条对话记录。`)
    if (!confirmed) return

    const rest = conversations.filter((item) => item.id !== id)
    const fallback: Conversation = { id: `chat-${Date.now()}`, title: '新建对话', updatedAt: '刚刚', messages: [] }
    const nextConversations = rest.length ? rest : [fallback]
    setConversations(nextConversations)
    if (activeConversationId === id) {
      setActiveConversationId(nextConversations[0].id)
      setPeachPanel('new-chat')
    }
    setNotice('对话已删除。')
  }

  async function sendPrompt(prompt: string, extraContext: Record<string, unknown> = {}, visibleContent = prompt) {
    if (!prompt.trim()) return
    const snapshot = prompt.trim()
    const visibleSnapshot = visibleContent.trim()
    setInput('')
    appendMessage({ role: 'user', content: visibleSnapshot || snapshot })
    appendMessage({ role: 'system', content: '桃子正在回复。' })
    begin('chat', '桃子正在回复')
    try {
      const data = await api<{ reply: string; actions?: AgentToolProposal[]; memory_writes?: MemoryWrite[] }>('/api/agent/actions', {
        method: 'POST',
        body: JSON.stringify({
          message: snapshot,
          context: {
            current_panel: peachPanel,
            active_interview_id: activeInterviewId,
            interview_active: peachPanel === 'live-interview' && Boolean(activeInterviewId),
            interview_progress: interviewProgress,
            active_profile_section: activeProfileSection,
            profile_sections: profileSections,
            recent_messages: activeConversation.messages.slice(-8),
            knowledge_items: knowledgeItems.slice(0, 8),
            ...extraContext,
          },
        }),
      })
      removeSystemMessage('桃子正在回复。')
      appendMessage({ role: 'peach', content: cleanAssistantText(data.reply), actions: normalizeAgentActions(data.actions) })
      setNotice(data.memory_writes?.length ? '桃子已记住。' : '回复已生成。')
    } catch (err) {
      removeSystemMessage('桃子正在回复。')
      setInput(snapshot)
      const detail = err instanceof Error ? err.message : ''
      setError(detail ? `桃子刚刚卡了一下：${detail}。内容已经放回输入框。` : '桃子刚刚掉线了一下，内容已经放回输入框。')
      console.error(err)
    } finally {
      end('chat')
    }
  }

  async function approveAgentAction(action: AgentToolProposal) {
    if (action.tool === 'unsupported') {
      markActionStatus(action.id, 'dismissed')
      setError('这个动作当前版本还不支持。')
      return
    }

    markActionStatus(action.id, 'executing')
    if (action.tool === 'start_interview') {
      setSettings((current) => ({
        ...current,
        style: String(action.payload.interviewer_style ?? current.style),
        jd: String(action.payload.jd ?? current.jd),
        questionBank: String(action.payload.question_bank ?? current.questionBank),
      }))
      setActiveInterviewId('')
      setInterviewProgress(defaultInterviewProgress)
      setFinishSuggestionShown(false)
      setLiveKind(String(action.payload.interview_type ?? '').includes('题库') ? 'question-bank' : 'interview')
      setSeconds(0)
      setPaused(false)
      setImmersiveInterview(true)
      setPeachPanel('live-interview')
      appendMessage({ role: 'system', content: '正在生成第一题。' })
    }
    begin('chat', `正在执行${action.title}`)
    try {
      const data = await api<{
        message?: string
        profile?: Profile
        interview?: { id: string; interview_type: string; interviewer_style: string; company: string; role: string; status: string; report?: InterviewReport }
        opening?: { opening?: string; question?: string }
        progress?: InterviewProgress
        report?: InterviewReport
        knowledge?: KnowledgeItem
        deleted_knowledge_id?: string
      }>('/api/agent/actions/execute', {
        method: 'POST',
        body: JSON.stringify({ tool: action.tool, payload: action.payload }),
      })

      const resultDetail = buildToolActionDetail(action, data, profile, knowledgeItems)
      markActionStatus(action.id, 'approved', resultDetail)
      removeSystemMessage('正在生成第一题。')
      applyToolResult(action, data)
      appendMessage({ role: 'system', content: data.message || '动作已完成。' })
      void refreshDashboard()
    } catch (err) {
      removeSystemMessage('正在生成第一题。')
      markActionStatus(action.id, 'pending')
      if (action.tool === 'start_interview') setPeachPanel('interview-setup')
      setError('动作执行失败，先没有改动任何内容。')
      console.error(err)
    } finally {
      end('chat')
    }
  }

  function dismissAgentAction(action: AgentToolProposal) {
    markActionStatus(action.id, 'dismissed')
    setNotice(`已取消${action.title}。`)
  }

  function applyToolResult(
    action: AgentToolProposal,
    data: {
      profile?: Profile
      interview?: { id?: string; interview_type: string; interviewer_style: string; company: string; role: string; status: string; report?: InterviewReport }
      opening?: { opening?: string; question?: string }
      progress?: InterviewProgress
      report?: InterviewReport
      knowledge?: KnowledgeItem
      deleted_knowledge_id?: string
    },
  ) {
    if (data.profile) {
      setDashboard((current) => (current ? { ...current, profile: data.profile as Profile } : current))
      setProfileSections((current) => syncProfileSectionsFromAction(current, action, data.profile as Profile))
    }
    if (data.knowledge) {
      setPersonalKnowledge((current) => [data.knowledge as KnowledgeItem, ...current.filter((item) => item.id !== data.knowledge?.id)])
      setKnowledgeTab('personal')
      setActiveKnowledgeId(data.knowledge.id)
      setKnowledgeDraft(toKnowledgeDraft(data.knowledge))
      setIsCreatingKnowledge(false)
    }
    if (data.deleted_knowledge_id) {
      setPersonalKnowledge((current) => current.filter((item) => item.id !== data.deleted_knowledge_id))
      setKnowledgeTab('personal')
    }
    if (action.tool === 'start_interview' && data.interview) {
      setSettings((current) => ({
        ...current,
        style: data.interview?.interviewer_style || current.style,
        resume: '完整简历',
        jd: String(action.payload.jd ?? current.jd),
        questionBank: String(action.payload.question_bank ?? current.questionBank),
      }))
      setActiveInterviewId(data.interview.id || '')
      setInterviewProgress(data.progress ?? defaultInterviewProgress)
      setFinishSuggestionShown(false)
      setLiveKind(String(data.interview.interview_type).includes('题库') ? 'question-bank' : 'interview')
      setSeconds(0)
      setPaused(false)
      setImmersiveInterview(true)
      setPeachPanel('live-interview')
      if (data.opening?.opening || data.opening?.question) {
        const openingText = cleanAssistantText([data.opening.opening, data.opening.question].filter(Boolean).join('\n\n'))
        appendMessage({ role: 'peach', content: openingText })
        speakInterviewText(openingText)
      }
    }
    if (action.tool === 'finish_latest_interview') {
      setActiveInterviewId('')
      setInterviewProgress(defaultInterviewProgress)
      setFinishSuggestionShown(false)
      setPeachPanel('new-chat')
      if (data.report?.summary) {
        const summaryText = `这场面试我已经收尾了。${data.report.summary}`
        appendMessage({ role: 'peach', content: summaryText })
        speakInterviewText(summaryText)
      }
    }
  }

  function runComposerAction(action: string) {
    if (action === '模拟面试') {
      setPeachPanel('interview-setup')
      return
    }
    if (action === '题库练习') {
      setPeachPanel('question-bank-setup')
      return
    }
    const promptMap: Record<string, string> = {
      简历优化: '帮我优化简历，重点提升项目经历和岗位匹配度。',
      简历撰写: '帮我从零写一版适合目标岗位的简历。',
    }
    void sendPrompt(promptMap[action] ?? action)
  }

  async function startLiveInterview(kind: 'interview' | 'question-bank') {
    setError('')
    begin('interviewStart', settings.mode === 'video' ? '正在申请麦克风和摄像头权限' : '正在申请麦克风权限')
    try {
      const stream = await navigator.mediaDevices?.getUserMedia({
        audio: true,
        video: settings.mode === 'video',
      })
      if (stream) {
        mediaStream?.getTracks().forEach((track) => track.stop())
        setMediaStream(stream)
      }
      setMediaReady(true)
      setSeconds(0)
      setPaused(false)
      setImmersiveInterview(true)
      setInterviewProgress(defaultInterviewProgress)
      setFinishSuggestionShown(false)
      setLiveKind(kind)

      begin('interviewStart', '正在生成面试开场')
      const data = await api<{
        interview: { id: string; interview_type: string; interviewer_style: string; company: string; role: string; status: string }
        opening: { opening: string; question: string; rubric?: string[] }
        progress?: InterviewProgress
      }>('/api/interviews', {
        method: 'POST',
        body: JSON.stringify({
          interview_type: kind === 'question-bank' ? '题库练习' : '模拟面试',
          interviewer_style: `${settings.gender} / ${settings.style}`,
          company: profile.target_company,
          role: profile.target_role,
          jd: settings.jd,
          question_bank: kind === 'question-bank' ? settings.questionBank : '',
        }),
      })

      setActiveInterviewId(data.interview.id)
      setInterviewProgress(data.progress ?? defaultInterviewProgress)
      setPeachPanel('live-interview')
      const openingText = cleanAssistantText(`${data.opening.opening}\n\n${data.opening.question}`)
      appendMessage({ role: 'peach', content: openingText })
      speakInterviewText(openingText)

      setNotice('实时面试已开始。')
    } catch (err) {
      setMediaReady(false)
      setError(settings.mode === 'video' ? '摄像头或麦克风权限未开启，无法进入视频面试。' : '麦克风权限未开启，无法进入语音面试。')
      console.error(err)
    } finally {
      end('interviewStart')
    }
  }

  async function sendInterviewAnswer() {
    await sendInterviewAnswerText(input.trim())
  }

  async function sendInterviewAnswerText(answer: string) {
    if (!answer || paused || busy.chat) return
    const normalizedAnswer = normalizeVoiceAnswer(answer)
    if (!normalizedAnswer) return
    const now = Date.now()
    if (lastInterviewAnswerRef.current.text === normalizedAnswer && now - lastInterviewAnswerRef.current.at < 2400) {
      return
    }
    lastInterviewAnswerRef.current = { text: normalizedAnswer, at: now }
    if (!activeInterviewId) {
      setError('当前没有连接到进行中的面试，请回到设置页重新开始。')
      return
    }
    if (isInterviewFinishIntent(normalizedAnswer)) {
      setInput('')
      appendMessage({ role: 'user', content: normalizedAnswer })
      await finishActiveInterview()
      return
    }
    const interviewId = activeInterviewId
    setInput('')
    appendMessage({ role: 'user', content: normalizedAnswer })
    appendMessage({ role: 'system', content: '面试官正在追问。' })
    begin('chat', '面试官正在追问')
    try {
      const data = await api<{
        interview: { id: string; status: string; report?: InterviewReport }
        next: { micro_feedback?: string; next_question?: string; hint?: string; should_finish?: boolean }
        report?: InterviewReport
        progress?: InterviewProgress
      }>(`/api/interviews/${interviewId}/answer`, {
        method: 'POST',
        body: JSON.stringify({ answer: normalizedAnswer }),
      })
      removeSystemMessage('面试官正在追问。')
      const reply = [
        data.next.micro_feedback,
        data.next.next_question,
        data.next.hint ? `提示：${data.next.hint}` : '',
      ].filter(Boolean).join('\n\n')
      const replyText = cleanAssistantText(reply || '收到，我们继续下一题。')
      appendMessage({ role: 'peach', content: replyText })
      speakInterviewText(replyText)
      const nextProgress = data.progress ?? interviewProgress
      setInterviewProgress(nextProgress)
      if (data.interview.status === 'completed') {
        setActiveInterviewId('')
        setInterviewProgress(defaultInterviewProgress)
        setFinishSuggestionShown(false)
        setImmersiveInterview(false)
        setPeachPanel('new-chat')
        const reportText = formatInterviewReportMessage(data.report || data.interview.report)
        appendMessage({ role: 'peach', content: reportText })
        speakInterviewText(reportText)
      } else if (data.next.should_finish && nextProgress.can_llm_finish && !finishSuggestionShown) {
        appendMessage({
          role: 'peach',
          content: '这场已经达到可复盘的最低轮数。你可以继续练，也可以现在结束生成报告。',
          actions: [{
            id: `finish-${interviewId}-${Date.now()}`,
            tool: 'finish_latest_interview',
            title: '结束并生成报告',
            summary: `已回答 ${nextProgress.answer_count}/${nextProgress.target_answers} 轮，完成度 ${nextProgress.completion}%。确认后生成面试复盘报告。`,
            payload: { interview_id: interviewId, reason: '达到最低面试完成度' },
            approval_required: true,
            status: 'pending',
          }],
        })
        setFinishSuggestionShown(true)
      }
      setNotice(data.interview.status === 'completed' ? '面试已完成。' : '追问已生成。')
    } catch (err) {
      removeSystemMessage('面试官正在追问。')
      setInput(answer)
      setError('面试追问生成失败，回答已经放回输入框。')
      console.error(err)
    } finally {
      end('chat')
    }
  }

  async function finishActiveInterview() {
    if (busy.chat) return
    if (!activeInterviewId) {
      setPeachPanel('new-chat')
      setInterviewProgress(defaultInterviewProgress)
      setFinishSuggestionShown(false)
      setImmersiveInterview(false)
      setNotice('已退出面试。')
      return
    }
    begin('chat', '正在结束面试并生成报告')
    appendMessage({ role: 'system', content: '正在生成面试报告。' })
    try {
      const data = await api<{
        interview: { id: string; status: string; report?: InterviewReport }
        report?: InterviewReport
      }>(`/api/interviews/${activeInterviewId}/finish`, { method: 'POST' })
      removeSystemMessage('正在生成面试报告。')
      setActiveInterviewId('')
      setPaused(false)
      setInterviewProgress(defaultInterviewProgress)
      setFinishSuggestionShown(false)
      setImmersiveInterview(false)
      setPeachPanel('new-chat')
      const reportText = formatInterviewReportMessage(data.report || data.interview.report)
      appendMessage({ role: 'peach', content: reportText })
      speakInterviewText(reportText)
      setNotice('面试已结束，报告已生成。')
      void refreshDashboard()
    } catch (err) {
      removeSystemMessage('正在生成面试报告。')
      setError('面试报告生成失败，可以稍后再试一次。')
      console.error(err)
    } finally {
      end('chat')
    }
  }

  function selectProfileSection(id: ProfileSectionId) {
    setActiveProfileSection(id)
    setProfileActionResult('')
    setNotice(`正在编辑${profileSectionMeta[id].title}。`)
  }

  function updateProfileSection(id: ProfileSectionId, content: string) {
    setProfileSections((current) => ({ ...current, [id]: content }))
  }

  function appendProfileMessage(message: ChatMessage) {
    setProfileMessages((current) => [...current, message])
  }

  function removeProfileSystemMessage(content: string) {
    setProfileMessages((current) => current.filter((message) => message.content !== content))
  }

  async function sendProfileChat() {
    const message = profileInput.trim()
    if (!message || busy.profile) return
    const section = profileSectionMeta[activeProfileSection]
    setProfileInput('')
    appendProfileMessage({ role: 'user', content: message })
    appendProfileMessage({ role: 'system', content: '桃子正在处理档案请求。' })
    begin('profile', '桃子正在处理档案请求')
    try {
      const data = await api<{ reply: string; actions?: AgentToolProposal[] }>('/api/agent/actions', {
        method: 'POST',
        body: JSON.stringify({
          message: [
            `用户正在个人档案的「${section.title}」分区内对话。`,
            '如果用户是在补充经历、要求整理简历、优化档案、沉淀材料，请优先提出 append_profile_note 或 update_resume 动作，让用户确认后再改资料。',
            `用户输入：${message}`,
          ].join('\n'),
          context: {
            current_panel: 'profile',
            active_profile_section: activeProfileSection,
            profile_sections: profileSections,
            current_section_content: profileSections[activeProfileSection],
            profile,
          },
        }),
      })
      removeProfileSystemMessage('桃子正在处理档案请求。')
      appendProfileMessage({ role: 'peach', content: cleanAssistantText(data.reply), actions: normalizeAgentActions(data.actions) })
      setNotice('档案对话已生成。')
    } catch (err) {
      removeProfileSystemMessage('桃子正在处理档案请求。')
      setProfileInput(message)
      setError('档案对话失败，内容已经放回输入框。')
      console.error(err)
    } finally {
      end('profile')
    }
  }

  async function saveProfileSections(nextSections = profileSections) {
    begin('profile', '正在保存个人档案')
    try {
      const data = await api<{ profile: Profile; greeting?: string }>('/api/profile', {
        method: 'POST',
        body: JSON.stringify({
          name: profile.name,
          target_role: profile.target_role,
          target_company: profile.target_company,
          target_city: profile.target_city,
          stage: profile.stage,
          communication_style: profile.communication_style,
          resume_text: composeProfileResumeText(nextSections),
        }),
      })
      setDashboard((current) => (current ? { ...current, profile: data.profile } : current))
      setNotice('个人档案已保存。')
    } catch (err) {
      setError('个人档案保存失败，稍后再试一次。')
      console.error(err)
    } finally {
      end('profile')
    }
  }

  async function runProfileAction(action: string) {
    const section = profileSectionMeta[activeProfileSection]
    const content = profileSections[activeProfileSection].trim()
    const actionPrompt: Record<string, string> = {
      简历生成: `请基于用户当前个人档案，为「${section.title}」生成一版可直接放进简历或档案的内容。要求真实、具体、结构清晰，不要编造不存在的数据。`,
      经历生成: `请基于「${section.title}」里的素材，生成一版适合${profile.target_role}求职的经历描述。要求包含背景、任务、行动、结果和可追问细节，不要编造不存在的数据。`,
      简历优化: `请优化「${section.title}」这段档案内容，让它更适合${profile.target_role}求职。请指出可以补证据的位置，并给出改写版本。`,
      面试深挖: `请围绕「${section.title}」生成 6 个面试深挖问题，并说明每题考察点。问题要贴近${profile.target_role}。`,
      面试复盘: `请基于当前上传或记录的面试材料，生成一份面试复盘总结，分为情绪承接、问题回顾、可执行改进和下一次练习计划。`,
    }
    begin('profile', `桃子正在处理${action}`)
    setProfileActionResult('')
    try {
      const data = await api<{ reply: string }>('/api/chat', {
        method: 'POST',
        body: JSON.stringify({
          message: `${actionPrompt[action] ?? action}\n\n当前文件夹内容：${content || '暂无'}\n\n完整档案摘要：${composeProfileResumeText(profileSections) || '暂无'}`,
        }),
      })
      setProfileActionResult(cleanAssistantText(data.reply))
      setNotice(`${action}已生成。`)
    } catch (err) {
      setError(`${action}失败，桃子刚刚没有拿到结果。`)
      console.error(err)
    } finally {
      end('profile')
    }
  }

  function acceptProfileActionResult() {
    if (!profileActionResult.trim()) return
    const nextSections = {
      ...profileSections,
      [activeProfileSection]: [profileSections[activeProfileSection], profileActionResult.trim()].filter(Boolean).join('\n\n'),
    }
    setProfileSections(nextSections)
    setProfileActionResult('')
    setNotice('已采纳到当前文件夹，记得保存档案。')
  }

  async function saveKnowledge(id: string) {
    if (savedKnowledge.includes(id)) return
    const folder = knowledgeFolders.saved[0]
    if (!folder) {
      setSavedKnowledge((current) => [...current, id])
      return
    }
    begin('knowledge', '正在收藏知识库')
    try {
      const itemIds = Array.from(new Set([id, ...(folder.item_ids || [])]))
      const data = await api<{ folder: KnowledgeFolder }>(`/api/knowledge/folders/${folder.id}`, {
        method: 'PUT',
        body: JSON.stringify({ ...folder, item_ids: itemIds }),
      })
      setKnowledgeFolders((current) => ({
        ...current,
        saved: current.saved.map((item) => (item.id === data.folder.id ? data.folder : item)),
      }))
      setSavedKnowledge(itemIds)
      setNotice('已收藏到收藏知识库。')
    } catch (err) {
      setError('收藏失败，稍后再试一次。')
      console.error(err)
    } finally {
      end('knowledge')
    }
  }

  function selectKnowledgeItem(item: KnowledgeItem) {
    setActiveKnowledgeId(item.id)
    setKnowledgeDraft(toKnowledgeDraft(item))
    setKnowledgeActionResult('')
    setKnowledgeActionMode('')
    setIsCreatingKnowledge(false)
    setNotice(`正在查看${item.title}。`)
  }

  function createKnowledgeDraft() {
    setActiveKnowledgeId('')
    setKnowledgeDraft({ title: '', summary: '', content: '', url: '' })
    setKnowledgeActionResult('')
    setKnowledgeActionMode('')
    setIsCreatingKnowledge(true)
    setKnowledgeTab('personal')
    setActiveKnowledgeFolderId(knowledgeFolders.personal[0]?.id ?? 'personal-default')
    setNotice('可以新增一条个人知识。')
  }

  function closeKnowledgeDetail() {
    setActiveKnowledgeId('')
    setKnowledgeDraft({ title: '', summary: '', content: '', url: '' })
    setKnowledgeActionResult('')
    setKnowledgeActionMode('')
    setIsCreatingKnowledge(false)
    setNotice('已回到知识库问答。')
  }

  async function saveKnowledgeDraft() {
    if (!knowledgeDraft.title.trim() || !knowledgeDraft.content.trim()) return
    const active = knowledgeItems.find((item) => item.id === activeKnowledgeId)
    begin('knowledge', active?.source === 'personal' ? '正在保存知识库' : '正在添加个人知识')
    try {
      const payload = {
        title: knowledgeDraft.title.trim(),
        summary: knowledgeDraft.summary.trim() || summarizeClientText(knowledgeDraft.content),
        content: knowledgeDraft.content.trim(),
        source: 'personal',
        url: knowledgeDraft.url.trim(),
      }
      if (active?.source === 'personal') {
        const data = await api<{ item: KnowledgeItem }>(`/api/knowledge/${active.id}`, {
          method: 'PUT',
        body: JSON.stringify(payload),
      })
        setPersonalKnowledge((current) => current.map((item) => (item.id === data.item.id ? data.item : item)))
        setKnowledgeDraft(toKnowledgeDraft(data.item))
        setKnowledgeActionResult('')
        setKnowledgeActionMode('')
        setNotice('知识库已保存。')
      } else {
        const folder = [...knowledgeFolders.personal, ...knowledgeFolders.saved].find((item) => item.id === activeKnowledgeFolderId)
        const folderId = folder?.scope === 'personal' ? activeKnowledgeFolderId : knowledgeFolders.personal[0]?.id
        const data = await api<{ item: KnowledgeItem }>('/api/knowledge', {
          method: 'POST',
          body: JSON.stringify({ ...payload, folder_id: folderId ?? '' }),
        })
        setPersonalKnowledge((current) => [data.item, ...current])
        setActiveKnowledgeId(data.item.id)
        setKnowledgeDraft(toKnowledgeDraft(data.item))
        setKnowledgeActionResult('')
        setKnowledgeActionMode('')
        setIsCreatingKnowledge(false)
        await refreshKnowledgeFolders()
        setNotice('已添加到个人知识库。')
      }
    } catch (err) {
      setError('知识库保存失败，稍后再试一次。')
      console.error(err)
    } finally {
      end('knowledge')
    }
  }

  async function deleteKnowledgeItem(id: string) {
    const item = personalKnowledge.find((value) => value.id === id)
    if (!item) return
    begin('knowledge', '正在删除知识库资料')
    try {
      await api<{ deleted: boolean; id: string }>(`/api/knowledge/${id}`, { method: 'DELETE' })
      setPersonalKnowledge((current) => current.filter((value) => value.id !== id))
      const next = personalKnowledge.find((value) => value.id !== id)
      setActiveKnowledgeId(next?.id ?? '')
      setKnowledgeDraft(next ? toKnowledgeDraft(next) : { title: '', summary: '', content: '', url: '' })
      setKnowledgeActionResult('')
      setKnowledgeActionMode('')
      setIsCreatingKnowledge(false)
      await refreshKnowledgeFolders()
      setNotice('知识库资料已删除。')
    } catch (err) {
      setError('知识库删除失败，稍后再试一次。')
      console.error(err)
    } finally {
      end('knowledge')
    }
  }

  async function createKnowledgeFolder(scope: Exclude<KnowledgeTab, 'discover'>) {
    const name = window.prompt('文件夹名称', scope === 'personal' ? '求职资料' : '收藏资料')
    if (!name?.trim()) return
    begin('knowledge', '正在新建文件夹')
    try {
      const data = await api<{ folder: KnowledgeFolder }>('/api/knowledge/folders', {
        method: 'POST',
        body: JSON.stringify({ name: name.trim(), scope, item_ids: [], sort_order: knowledgeFolders[scope].length }),
      })
      setKnowledgeFolders((current) => ({ ...current, [scope]: [...current[scope], data.folder] }))
      setActiveKnowledgeFolderId(data.folder.id)
      setKnowledgeTab(scope)
      setNotice('文件夹已新建。')
    } catch (err) {
      setError('文件夹新建失败，稍后再试一次。')
      console.error(err)
    } finally {
      end('knowledge')
    }
  }

  async function renameKnowledgeFolder(scope: Exclude<KnowledgeTab, 'discover'>, folderId: string) {
    const folder = knowledgeFolders[scope].find((item) => item.id === folderId)
    const name = window.prompt('重命名文件夹', folder?.name ?? '')
    if (!name?.trim()) return
    if (!folder) return
    begin('knowledge', '正在重命名文件夹')
    try {
      const data = await api<{ folder: KnowledgeFolder }>(`/api/knowledge/folders/${folderId}`, {
        method: 'PUT',
        body: JSON.stringify({ ...folder, name: name.trim() }),
      })
      setKnowledgeFolders((current) => ({
        ...current,
        [scope]: current[scope].map((item) => (item.id === folderId ? data.folder : item)),
      }))
      setNotice('文件夹已重命名。')
    } catch (err) {
      setError('文件夹重命名失败，稍后再试一次。')
      console.error(err)
    } finally {
      end('knowledge')
    }
  }

  async function deleteKnowledgeFolder(scope: Exclude<KnowledgeTab, 'discover'>, folderId: string) {
    if (knowledgeFolders[scope].length <= 1) return
    begin('knowledge', '正在删除文件夹')
    try {
      await api<{ deleted: boolean; id: string }>(`/api/knowledge/folders/${folderId}`, { method: 'DELETE' })
      setKnowledgeFolders((current) => {
      const nextFolders = current[scope].filter((item) => item.id !== folderId)
      if (activeKnowledgeFolderId === folderId) setActiveKnowledgeFolderId(nextFolders[0]?.id ?? `${scope}-default`)
      return { ...current, [scope]: nextFolders }
      })
      setNotice('文件夹已删除。')
    } catch (err) {
      setError('文件夹删除失败，稍后再试一次。')
      console.error(err)
    } finally {
      end('knowledge')
    }
  }

  function selectKnowledgeFolder(scope: Exclude<KnowledgeTab, 'discover'>, folderId: string) {
    setKnowledgeTab(scope)
    setActiveKnowledgeFolderId(folderId)
    setActiveKnowledgeId('')
    setKnowledgeDraft({ title: '', summary: '', content: '', url: '' })
    setKnowledgeActionResult('')
    setKnowledgeActionMode('')
    setIsCreatingKnowledge(false)
  }

  function folderKnowledgeItems(folder: KnowledgeFolder, scope: Exclude<KnowledgeTab, 'discover'>) {
    const folderIds = folder.item_ids ?? []
    const keyword = knowledgeQuery.trim().toLowerCase()
    return sortKnowledgeItems(
      knowledgeItems
        .filter((item) => {
          if (!folderIds.includes(item.id)) return false
          if (scope === 'personal') return item.source === 'personal'
          return savedKnowledge.includes(item.id)
        })
        .filter((item) => {
          if (!keyword) return true
          return [item.title, item.summary, item.content, item.url].some((part) => part?.toLowerCase().includes(keyword))
        }),
      knowledgeFileSort,
    )
  }

  async function renameKnowledgeItem(item: KnowledgeItem) {
    const title = window.prompt('重命名文件', item.title)
    if (!title?.trim()) return
    if (item.source !== 'personal') {
      setPersonalKnowledge((current) => current.map((value) => (value.id === item.id ? { ...value, title: title.trim() } : value)))
      setKnowledgeDraft((current) => (item.id === activeKnowledgeId ? { ...current, title: title.trim() } : current))
      return
    }
    begin('knowledge', '正在重命名资料')
    try {
      const data = await api<{ item: KnowledgeItem }>(`/api/knowledge/${item.id}`, {
        method: 'PUT',
        body: JSON.stringify({ ...toKnowledgeDraft(item), title: title.trim(), source: 'personal' }),
      })
      setPersonalKnowledge((current) => current.map((value) => (value.id === data.item.id ? data.item : value)))
      if (item.id === activeKnowledgeId) setKnowledgeDraft(toKnowledgeDraft(data.item))
      setNotice('资料已重命名。')
    } catch (err) {
      setError('重命名失败，稍后再试一次。')
      console.error(err)
    } finally {
      end('knowledge')
    }
  }

  async function parseKnowledgeLink() {
    const url = window.prompt('粘贴要加入知识库的链接')
    if (!url?.trim()) return
    begin('knowledge', '正在解析链接')
    try {
      const data = await api<{ item: KnowledgeItem; file?: ParsedUpload }>('/api/knowledge/link', {
        method: 'POST',
        body: JSON.stringify({ url: url.trim(), folder_id: activeKnowledgeFolderId }),
      })
      setPersonalKnowledge((current) => [data.item, ...current])
      setActiveKnowledgeId(data.item.id)
      setKnowledgeDraft(toKnowledgeDraft(data.item))
      setKnowledgeActionResult('')
      setKnowledgeActionMode('')
      setIsCreatingKnowledge(false)
      setKnowledgeTab('personal')
      await refreshKnowledgeFolders()
      setNotice(data.file?.warning || '链接已解析并加入个人知识库。')
    } catch (err) {
      setError('链接解析失败，稍后再试一次。')
      console.error(err)
    } finally {
      end('knowledge')
    }
  }

  async function uploadKnowledgeFile(file: File) {
    begin('upload', '正在解析并添加知识库')
    try {
      const data = await uploadApi<{ item: KnowledgeItem; file: ParsedUpload }>('/api/knowledge/upload', file, { folder_id: activeKnowledgeFolderId })
      setPersonalKnowledge((current) => [data.item, ...current])
      setActiveKnowledgeId(data.item.id)
      setKnowledgeDraft(toKnowledgeDraft(data.item))
      setKnowledgeActionResult('')
      setKnowledgeActionMode('')
      setIsCreatingKnowledge(false)
      setKnowledgeTab('personal')
      await refreshKnowledgeFolders()
      setNotice(data.file.warning || '文件已解析并加入知识库。')
    } catch (err) {
      setError(fileUploadErrorMessage(err))
      console.error(err)
    } finally {
      end('upload')
    }
  }

  async function uploadChatFile(file: File) {
    const instruction = input.trim()
    const parsingMessage = `正在解析附件：${file.name}`
    appendMessage({ role: 'system', content: parsingMessage })
    begin('upload', '正在解析聊天附件')
    try {
      const data = await uploadApi<{ file: ParsedUpload }>('/api/files/parse', file)
      removeSystemMessage(parsingMessage)
      const userIntent = instruction || '我上传了这个文件，请你判断它更适合加入知识库、更新简历、补充档案，还是用于模拟面试准备。'
      const prompt = [
        userIntent,
        '',
        `文件名：${data.file.filename}`,
        `文件标题：${data.file.title}`,
        `文件摘要：${data.file.summary}`,
        '',
        `文件正文：${data.file.content.slice(0, 14000)}`,
      ].join('\n')
      const visible = [
        `上传文件：${data.file.filename}`,
        userIntent,
        `摘要：${data.file.summary}`,
      ].join('\n')
      setInput('')
      setNotice(data.file.warning || '附件已解析，桃子正在判断下一步。')
      await sendPrompt(
        prompt,
        {
          uploaded_file: {
            filename: data.file.filename,
            extension: data.file.extension,
            title: data.file.title,
            summary: data.file.summary,
            content: data.file.content,
            warning: data.file.warning || '',
            user_intent: userIntent,
          },
        },
        visible,
      )
    } catch (err) {
      removeSystemMessage(parsingMessage)
      setError(fileUploadErrorMessage(err))
      console.error(err)
    } finally {
      end('upload')
    }
  }

  async function uploadProfileFile(file: File) {
    begin('upload', '正在解析并补充档案')
    try {
      const data = await uploadApi<{ file: ParsedUpload }>('/api/files/parse', file)
      const content = `【${data.file.title}】\n${data.file.content}`
      updateProfileSection(
        activeProfileSection,
        [profileSections[activeProfileSection], content].filter(Boolean).join('\n\n'),
      )
      if (activeProfileSection === 'full') {
        setResumeFiles((current) => [data.file, ...current.filter((item) => item.filename !== data.file.filename)])
      }
      setNotice(data.file.warning || `已补充到${profileSectionMeta[activeProfileSection].title}。`)
    } catch (err) {
      setError(fileUploadErrorMessage(err))
      console.error(err)
    } finally {
      end('upload')
    }
  }

  async function uploadInterviewFile(file: File, target: 'resume' | 'questionBank') {
    begin('upload', '正在解析面试材料')
    try {
      const data = await uploadApi<{ file: ParsedUpload }>('/api/files/parse', file)
      if (target === 'resume') {
        setSettings((current) => ({ ...current, resume: data.file.title }))
        updateProfileSection('full', [profileSections.full, `【${data.file.title}】\n${data.file.content}`].filter(Boolean).join('\n\n'))
      } else {
        setSettings((current) => ({ ...current, questionBank: data.file.title }))
      }
      setNotice(data.file.warning || '面试材料已解析。')
    } catch (err) {
      setError(fileUploadErrorMessage(err))
      console.error(err)
    } finally {
      end('upload')
    }
  }

  function sendKnowledgeToPeach(item: KnowledgeItem) {
    openModule('peach')
    void sendPrompt(`请基于这份知识资料帮我提炼面试准备重点。\n标题：${item.title}\n内容：${item.content || item.summary}`)
  }

  function addKnowledgeToProfile(item: KnowledgeItem) {
    const content = `【知识库：${item.title}】\n${item.content || item.summary}`
    updateProfileSection(activeProfileSection, [profileSections[activeProfileSection], content].filter(Boolean).join('\n\n'))
    setModule('profile')
    setNotice(`已沉淀到${profileSectionMeta[activeProfileSection].title}。`)
  }

  async function runKnowledgeItemAction(action: string) {
    const active = knowledgeItems.find((item) => item.id === activeKnowledgeId)
    const title = knowledgeDraft.title.trim() || active?.title || '当前资料'
    const summary = knowledgeDraft.summary.trim() || active?.summary || ''
    const content = knowledgeDraft.content.trim() || active?.content || active?.summary || ''
    if (!content.trim()) {
      setError('当前资料还没有正文，先补充内容再让桃子调整。')
      return
    }
    const actionPrompt: Record<string, string> = {
      智能摘要: '请为这份求职知识资料生成一段 120 字以内的摘要。只输出摘要本身。',
      优化正文: '请优化这份求职知识资料的正文，让结构更清楚、更适合后续求职问答引用。不要编造新事实，只输出优化后的正文。',
      提炼面试题: '请基于这份资料提炼 8 个高质量面试题，并给出每题考察点。不要使用 markdown 加粗。',
      生成行动项: '请基于这份资料整理一份求职行动项，要求具体、可执行、按优先级排列。',
    }
    begin('knowledge', `桃子正在${action}`)
    setKnowledgeActionResult('')
    setKnowledgeActionMode(action)
    try {
      const data = await api<{ reply: string }>('/api/chat', {
        method: 'POST',
        body: JSON.stringify({
          message: [
            actionPrompt[action] ?? action,
            `标题：${title}`,
            `摘要：${summary || '暂无'}`,
            `正文：${content.slice(0, 14000)}`,
          ].join('\n\n'),
        }),
      })
      setKnowledgeActionResult(cleanAssistantText(data.reply))
      setNotice(`${action}已生成。`)
    } catch (err) {
      setError(`${action}失败，桃子刚刚没有拿到结果。`)
      console.error(err)
    } finally {
      end('knowledge')
    }
  }

  function acceptKnowledgeActionResult() {
    if (!knowledgeActionResult.trim()) return
    if (knowledgeActionMode === '智能摘要') {
      setKnowledgeDraft((current) => ({ ...current, summary: knowledgeActionResult.trim() }))
    } else {
      setKnowledgeDraft((current) => ({
        ...current,
        content: [current.content, knowledgeActionResult.trim()].filter(Boolean).join('\n\n'),
      }))
    }
    setKnowledgeActionResult('')
    setKnowledgeActionMode('')
    setNotice('已采纳到当前资料，记得保存修改。')
  }

  async function askKnowledgeQuestion() {
    const question = knowledgeQuestion.trim()
    if (!question || busy.chat) return
    const folder = [...knowledgeFolders.personal, ...knowledgeFolders.saved].find((item) => item.id === activeKnowledgeFolderId)
    const folderIds = folder?.item_ids ?? []
    const sourceItems = knowledgeItems
      .filter((item) => {
        if (knowledgeTab === 'personal') return item.source === 'personal'
        if (knowledgeTab === 'saved') return savedKnowledge.includes(item.id)
        return item.source === 'discover'
      })
      .filter((item) => (knowledgeTab === 'discover' || !folder ? true : folderIds.includes(item.id)))
      .slice(0, 8)
    setKnowledgeQuestion('')
    setKnowledgeMessages((current) => [...current, { role: 'user', content: question }, { role: 'system', content: '桃子正在基于知识库回答。' }])
    begin('chat', '桃子正在基于知识库回答')
    try {
      const data = await api<{ reply: string }>('/api/chat', {
        method: 'POST',
        body: JSON.stringify({
          message: [
            `请基于以下求职知识库资料回答用户问题。回答要具体，无法从资料判断时要说明需要补充什么。`,
            `资料：${JSON.stringify(sourceItems.map((item) => ({ title: item.title, summary: item.summary, content: item.content?.slice(0, 2500) })), null, 2)}`,
            `用户问题：${question}`,
          ].join('\n\n'),
        }),
      })
      setKnowledgeMessages((current) => [
        ...current.filter((message) => message.content !== '桃子正在基于知识库回答。'),
        { role: 'peach', content: cleanAssistantText(data.reply) },
      ])
      setNotice('知识库回答已生成。')
    } catch (err) {
      setKnowledgeMessages((current) => current.filter((message) => message.content !== '桃子正在基于知识库回答。'))
      setKnowledgeQuestion(question)
      setError('知识库问答失败，问题已经放回输入框。')
      console.error(err)
    } finally {
      end('chat')
    }
  }

  const hasSubNav = module === 'peach' || module === 'knowledge'
  const isInterviewNavigationLocked = peachPanel === 'live-interview'
  const appClass = `app-shell module-${module} ${hasSubNav ? 'has-sub-nav' : 'no-sub-nav'} ${subNavCollapsed ? 'subnav-collapsed' : ''}`
  const activeKnowledgeFolder = knowledgeTab === 'discover'
    ? undefined
    : [...knowledgeFolders.personal, ...knowledgeFolders.saved].find((item) => item.id === activeKnowledgeFolderId)
  const activeKnowledgeFolderItems = activeKnowledgeFolder
    ? folderKnowledgeItems(activeKnowledgeFolder, activeKnowledgeFolder.scope)
    : []

  if (!account) {
    return (
      <AccountGate
        username={accountInput}
        message={accountMessage}
        busy={Boolean(busy.account)}
        onUsername={setAccountInput}
        onLogin={() => void loginAccount()}
        onCreate={() => void createAccount()}
      />
    )
  }

  return (
    <main className={appClass}>
      <aside className="main-nav" aria-label="主导航栏">
        <nav className="main-nav-list">
          <button
            className={[
              'main-nav-item',
              module === 'peach' ? 'active' : '',
              isInterviewNavigationLocked ? 'locked' : '',
            ].filter(Boolean).join(' ')}
            type="button"
            aria-disabled={isInterviewNavigationLocked}
            title={isInterviewNavigationLocked ? '请先结束当前面试' : undefined}
            onClick={() => openModule('peach')}
          >
            <span className="nav-icon"><img src={NAV_ICONS.peach} alt="" /></span>
            <strong>问问桃子</strong>
            {isInterviewNavigationLocked ? <span className="nav-lock" aria-hidden="true">锁定</span> : null}
          </button>
          <button
            className={[
              'main-nav-item',
              module === 'profile' ? 'active' : '',
              isInterviewNavigationLocked ? 'locked' : '',
            ].filter(Boolean).join(' ')}
            type="button"
            aria-disabled={isInterviewNavigationLocked}
            title={isInterviewNavigationLocked ? '请先结束当前面试' : undefined}
            onClick={() => openModule('profile')}
          >
            <span className="nav-icon"><img src={NAV_ICONS.profile} alt="" /></span>
            <strong>个人档案</strong>
            {isInterviewNavigationLocked ? <span className="nav-lock" aria-hidden="true">锁定</span> : null}
          </button>
          <button
            className={[
              'main-nav-item',
              module === 'knowledge' ? 'active' : '',
              isInterviewNavigationLocked ? 'locked' : '',
            ].filter(Boolean).join(' ')}
            type="button"
            aria-disabled={isInterviewNavigationLocked}
            title={isInterviewNavigationLocked ? '请先结束当前面试' : undefined}
            onClick={() => openModule('knowledge')}
          >
            <span className="nav-icon"><img src={NAV_ICONS.knowledge} alt="" /></span>
            <strong>求职知识库</strong>
            {isInterviewNavigationLocked ? <span className="nav-lock" aria-hidden="true">锁定</span> : null}
          </button>
        </nav>
        <div className="account-switcher" aria-label="账号管理">
          <div className="account-avatar">{account.username.slice(0, 1).toUpperCase()}</div>
          <strong title={account.username}>{account.username}</strong>
          <button type="button" onClick={switchAccount}>切换</button>
          <button type="button" onClick={() => void resetAccount()}>重置</button>
        </div>
      </aside>

      {module === 'peach' ? (
        <PeachSubNav
          activePanel={peachPanel}
          conversations={conversations}
          activeConversationId={activeConversationId}
          collapsed={subNavCollapsed}
          locked={isInterviewNavigationLocked}
          onNew={createConversation}
          onOpenHistory={openConversation}
          onRenameHistory={renameConversation}
          onDeleteHistory={deleteConversation}
          onToggle={() => setSubNavCollapsed((value) => !value)}
        />
      ) : null}

      {module === 'knowledge' ? (
        <KnowledgeSubNav
          collapsed={subNavCollapsed}
          tab={knowledgeTab}
          query={knowledgeQuery}
          folders={knowledgeFolders}
          activeFolderId={activeKnowledgeFolderId}
          folderSort={knowledgeFolderSort}
          onToggle={() => setSubNavCollapsed((value) => !value)}
          onTab={(tab) => {
            setKnowledgeTab(tab)
            setActiveKnowledgeId('')
            setKnowledgeDraft({ title: '', summary: '', content: '', url: '' })
            setKnowledgeActionResult('')
            setKnowledgeActionMode('')
            setIsCreatingKnowledge(false)
            if (tab === 'personal') setActiveKnowledgeFolderId(knowledgeFolders.personal[0]?.id ?? 'personal-default')
            if (tab === 'saved') setActiveKnowledgeFolderId(knowledgeFolders.saved[0]?.id ?? 'saved-default')
          }}
          onQuery={setKnowledgeQuery}
          onFolderSort={setKnowledgeFolderSort}
          onCreateFolder={createKnowledgeFolder}
          onSelectFolder={selectKnowledgeFolder}
          getFolderItems={folderKnowledgeItems}
        />
      ) : null}

      <section className="workspace" aria-label="工作区">
        {module === 'peach' && peachPanel !== 'new-chat' ? (
          <header className="workspace-topbar">
            <div>
              <p>{workspaceKicker(module, peachPanel)}</p>
              <h1>{workspaceTitle(module, peachPanel)}</h1>
            </div>
            <div className={busyText ? 'status-pill busy' : 'status-pill'}>{busyText || notice}</div>
          </header>
        ) : null}

        {error ? <div className="inline-error">{error}</div> : null}
        {!dashboard && !error ? <LoadingScreen /> : null}

        {module === 'peach' ? (
          <PeachWorkspace
            key={activeConversation.id}
            panel={peachPanel}
            profile={profile}
            conversation={activeConversation}
            recommendations={visibleRecommendations}
            input={input}
            settings={settings}
            liveKind={liveKind}
            activeInterviewId={activeInterviewId}
            interviewProgress={interviewProgress}
            seconds={seconds}
            paused={paused}
            mediaReady={mediaReady}
            mediaStream={mediaStream}
            ttsMuted={ttsMuted}
            ttsSpeaking={ttsSpeaking}
            lastTtsText={lastTtsText}
            ttsRateMode={ttsRateMode}
            immersiveInterview={immersiveInterview}
            subtitleCollapsed={subtitleCollapsed}
            timerCollapsed={timerCollapsed}
            videoRef={videoRef}
            chatScrollRef={chatScrollRef}
            busy={busy}
            onInput={setInput}
            onSend={() => (peachPanel === 'live-interview' ? void sendInterviewAnswer() : void sendPrompt(input))}
            onVoiceSubmit={(text) => void sendInterviewAnswerText(text)}
            onQuickSend={(value) => void sendPrompt(value)}
            onAction={runComposerAction}
            onSettingsChange={setSettings}
            onStartInterview={() => void startLiveInterview('interview')}
            onStartQuestionBank={() => void startLiveInterview('question-bank')}
            onUploadInterviewFile={(file, target) => void uploadInterviewFile(file, target)}
            onUploadChatFile={(file) => void uploadChatFile(file)}
            onPauseToggle={() => setPaused((value) => !value)}
            onFinishInterview={() => void finishActiveInterview()}
            onImmersiveToggle={() => setImmersiveInterview((value) => !value)}
            onTtsMuteToggle={toggleTtsMuted}
            onTtsStop={stopTts}
            onTtsReplay={replayTts}
            onTtsRateMode={setTtsRateMode}
            onSubtitleToggle={() => setSubtitleCollapsed((value) => !value)}
            onTimerToggle={() => setTimerCollapsed((value) => !value)}
            onBackToSetup={() => {
              stopTts()
              setImmersiveInterview(false)
              setPeachPanel(liveKind === 'question-bank' ? 'question-bank-setup' : 'interview-setup')
            }}
            onApproveAction={(action) => void approveAgentAction(action)}
            onDismissAction={dismissAgentAction}
          />
        ) : null}

        {module === 'profile' ? (
          <ProfileWorkspace
            profile={profile}
            folders={resumeFolders}
            interviews={dashboard?.recent_interviews ?? []}
            activeSection={activeProfileSection}
            sectionContent={profileSections[activeProfileSection]}
            sections={profileSections}
            actionResult={profileActionResult}
            messages={profileMessages}
            resumeFiles={resumeFiles}
            isSaving={Boolean(busy.profile)}
            value={profileInput}
            onSelectSection={selectProfileSection}
            onSectionContent={(content) => updateProfileSection(activeProfileSection, content)}
            onValue={setProfileInput}
            onSubmit={() => void sendProfileChat()}
            onSave={() => void saveProfileSections()}
            onAction={(action) => void runProfileAction(action)}
            onAcceptResult={acceptProfileActionResult}
            onUploadFile={(file) => void uploadProfileFile(file)}
            onApproveAction={(action) => void approveAgentAction(action)}
            onDismissAction={dismissAgentAction}
          />
        ) : null}

        {module === 'knowledge' ? (
          <KnowledgeWorkspace
            tab={knowledgeTab}
            question={knowledgeQuestion}
            messages={knowledgeMessages}
            items={knowledgeItems}
            savedIds={savedKnowledge}
            activeFolder={activeKnowledgeFolder}
            folderItems={activeKnowledgeFolderItems}
            activeId={activeKnowledgeId}
            draft={knowledgeDraft}
            actionResult={knowledgeActionResult}
            actionMode={knowledgeActionMode}
            isCreating={isCreatingKnowledge}
            busy={Boolean(busy.knowledge || busy.upload || busy.chat)}
            fileSort={knowledgeFileSort}
            onFileSort={setKnowledgeFileSort}
            onApproveAction={(action) => void approveAgentAction(action)}
            onDismissAction={dismissAgentAction}
            onQuestion={setKnowledgeQuestion}
            onAskQuestion={() => void askKnowledgeQuestion()}
            onSave={saveKnowledge}
            onDraft={setKnowledgeDraft}
            onSaveDraft={() => void saveKnowledgeDraft()}
            onDelete={(id) => void deleteKnowledgeItem(id)}
            onUpload={(file) => void uploadKnowledgeFile(file)}
            onAsk={sendKnowledgeToPeach}
            onUseInProfile={addKnowledgeToProfile}
            onSelectItem={selectKnowledgeItem}
            onNewItem={createKnowledgeDraft}
            onRenameFolder={(scope, id) => void renameKnowledgeFolder(scope, id)}
            onDeleteFolder={(scope, id) => void deleteKnowledgeFolder(scope, id)}
            onRenameItem={(item) => void renameKnowledgeItem(item)}
            onDeleteItem={(id) => void deleteKnowledgeItem(id)}
            onParseLink={() => void parseKnowledgeLink()}
            onBackToAsk={closeKnowledgeDetail}
            onRunItemAction={(action) => void runKnowledgeItemAction(action)}
            onAcceptActionResult={acceptKnowledgeActionResult}
          />
        ) : null}
      </section>
    </main>
  )
}

function AccountGate({
  username,
  message,
  busy,
  onUsername,
  onLogin,
  onCreate,
}: {
  username: string
  message: string
  busy: boolean
  onUsername: (value: string) => void
  onLogin: () => void
  onCreate: () => void
}) {
  return (
    <main className="account-gate">
      <section className="account-hero" aria-label="账号管理">
        <div className="account-portrait-wrap">
          <img src={PEACH_PORTRAIT} alt="桃子" />
        </div>
        <div className="account-copy">
          <p>桃子账号</p>
          <h1>先告诉桃子你是谁</h1>
          <span>Demo 版本只需要用户名。每个用户名都有独立的档案、知识库、面试和练习记录。</span>
        </div>
      </section>

      <section className="account-card">
        <div className="account-card-head">
          <img src={PEACH_ICON} alt="" />
          <div>
            <strong>进入你的求职空间</strong>
            <span>{message}</span>
          </div>
        </div>
        <label className="account-field">
          <span>用户名</span>
          <input
            autoFocus
            value={username}
            maxLength={40}
            placeholder="比如 Apple01 / Banana052 / Peach88"
            onChange={(event) => onUsername(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') onLogin()
            }}
          />
        </label>
        <div className="account-actions">
          <button className="primary" type="button" disabled={busy} onClick={onLogin}>
            {busy ? '处理中' : '登录'}
          </button>
          <button type="button" disabled={busy} onClick={onCreate}>
            创建账号
          </button>
        </div>
      </section>
    </main>
  )
}

function PeachSubNav({
  activePanel,
  conversations,
  activeConversationId,
  collapsed,
  locked,
  onNew,
  onOpenHistory,
  onRenameHistory,
  onDeleteHistory,
  onToggle,
}: {
  activePanel: PeachPanel
  conversations: Conversation[]
  activeConversationId: string
  collapsed: boolean
  locked?: boolean
  onNew: () => void
  onOpenHistory: (id: string) => void
  onRenameHistory: (id: string) => void
  onDeleteHistory: (id: string) => void
  onToggle: () => void
}) {
  return (
    <aside className={collapsed ? 'sub-nav collapsed' : 'sub-nav'} aria-label="桃子副导航栏">
      <button className="sub-nav-toggle" type="button" onClick={onToggle} aria-label={collapsed ? '展开副导航' : '收起副导航'}>
        <span>{collapsed ? '›' : '‹'}</span>
      </button>
      {collapsed ? null : (
        <>
      <div className="sub-nav-actions">
        <button
          className={[
            'sub-action',
            activePanel === 'new-chat' ? 'active' : '',
            locked ? 'locked' : '',
          ].filter(Boolean).join(' ')}
          type="button"
          aria-disabled={locked}
          title={locked ? '请先结束当前面试' : undefined}
          onClick={onNew}
        >
          新建对话
          {locked ? <span className="inline-lock" aria-hidden="true">锁定</span> : null}
        </button>
      </div>
      <div className="history-section">
        <div className="section-label">历史对话</div>
        <div className="history-list">
          {conversations.map((conversation) => (
            <article
              className={[
                'history-item',
                conversation.id === activeConversationId ? 'active' : '',
                locked ? 'locked' : '',
              ].filter(Boolean).join(' ')}
              key={conversation.id}
            >
              <button
                className="history-open-button"
                type="button"
                aria-disabled={locked}
                title={locked ? '请先结束当前面试' : undefined}
                onClick={() => onOpenHistory(conversation.id)}
              >
                <strong>{conversation.title}</strong>
                <span>{conversation.updatedAt}</span>
              </button>
              <div className="history-item-actions">
                {locked ? <span className="history-lock" aria-hidden="true">锁定</span> : (
                  <>
                    <button type="button" onClick={() => onRenameHistory(conversation.id)} aria-label={`重命名${conversation.title}`}>改名</button>
                    <button type="button" onClick={() => onDeleteHistory(conversation.id)} aria-label={`删除${conversation.title}`}>删除</button>
                  </>
                )}
              </div>
            </article>
          ))}
        </div>
      </div>
        </>
      )}
    </aside>
  )
}

function KnowledgeSubNav({
  collapsed,
  tab,
  query,
  folders,
  activeFolderId,
  folderSort,
  onToggle,
  onTab,
  onQuery,
  onFolderSort,
  onCreateFolder,
  onSelectFolder,
  getFolderItems,
}: {
  collapsed: boolean
  tab: KnowledgeTab
  query: string
  folders: Record<Exclude<KnowledgeTab, 'discover'>, KnowledgeFolder[]>
  activeFolderId: string
  folderSort: SortMode
  onToggle: () => void
  onTab: (tab: KnowledgeTab) => void
  onQuery: (value: string) => void
  onFolderSort: (mode: SortMode) => void
  onCreateFolder: (scope: Exclude<KnowledgeTab, 'discover'>) => void
  onSelectFolder: (scope: Exclude<KnowledgeTab, 'discover'>, id: string) => void
  getFolderItems: (folder: KnowledgeFolder, scope: Exclude<KnowledgeTab, 'discover'>) => KnowledgeItem[]
}) {
  const personalFolders = sortFolders(folders.personal, folderSort)

  const renderGroup = (scope: Exclude<KnowledgeTab, 'discover'>, title: string, scopedFolders: KnowledgeFolder[]) => (
    <section className="kb-nav-group" key={scope}>
      <div className="kb-nav-group-head">
        <button type="button" onClick={() => onTab(scope)} aria-label={`切换到${title}`}>
          <span>⌄</span>
          <strong>{title}</strong>
        </button>
        <button type="button" onClick={() => onCreateFolder(scope)} aria-label={`新建${title}`}>+</button>
      </div>
      <div className="kb-nav-folder-list">
        {scopedFolders.map((folder) => {
          const count = getFolderItems(folder, scope).length
          return (
            <button
              className={tab === scope && folder.id === activeFolderId ? 'kb-nav-folder active' : 'kb-nav-folder'}
              type="button"
              key={folder.id}
              onClick={() => onSelectFolder(scope, folder.id)}
            >
              <span className="kb-folder-mark" aria-hidden="true" />
              <span>{folder.name}</span>
              <small>{count}</small>
            </button>
          )
        })}
      </div>
    </section>
  )

  return (
    <aside className={collapsed ? 'sub-nav knowledge-sub-nav collapsed' : 'sub-nav knowledge-sub-nav'} aria-label="知识库副导航栏">
      <div className="kb-nav-top">
        <button className="kb-icon-button" type="button" onClick={onToggle} aria-label={collapsed ? '展开副导航' : '收起副导航'}>
          <span>{collapsed ? '›' : '‹'}</span>
        </button>
        {collapsed ? null : <button className="kb-icon-button" type="button" aria-label="搜索知识库">⌕</button>}
      </div>
      {collapsed ? null : (
        <div className="kb-nav-content">
          <div className="kb-nav-search">
            <input value={query} onChange={(event) => onQuery(event.target.value)} placeholder="搜索知识库" />
            <select value={folderSort} onChange={(event) => onFolderSort(event.target.value as SortMode)} aria-label="知识库排序">
              <option value="updated">最近更新</option>
              <option value="name">名称排序</option>
            </select>
          </div>

          {renderGroup('personal', '个人知识库', personalFolders)}
        </div>
      )}
    </aside>
  )
}

function PeachWorkspace(props: {
  panel: PeachPanel
  profile: Profile
  conversation: Conversation
  recommendations: string[]
  input: string
  settings: InterviewSettings
  liveKind: 'interview' | 'question-bank'
  activeInterviewId: string
  interviewProgress: InterviewProgress
  seconds: number
  paused: boolean
  mediaReady: boolean
  mediaStream: MediaStream | null
  ttsMuted: boolean
  ttsSpeaking: boolean
  lastTtsText: string
  ttsRateMode: TtsRateMode
  immersiveInterview: boolean
  subtitleCollapsed: boolean
  timerCollapsed: boolean
  videoRef: RefObject<HTMLVideoElement | null>
  chatScrollRef: RefObject<HTMLElement | null>
  busy: Partial<Record<BusyKey, string>>
  onInput: (value: string) => void
  onSend: () => void
  onVoiceSubmit: (value: string) => void
  onQuickSend: (value: string) => void
  onAction: (value: string) => void
  onSettingsChange: (value: InterviewSettings) => void
  onStartInterview: () => void
  onStartQuestionBank: () => void
  onUploadInterviewFile: (file: File, target: 'resume' | 'questionBank') => void
  onUploadChatFile: (file: File) => void
  onPauseToggle: () => void
  onFinishInterview: () => void
  onImmersiveToggle: () => void
  onTtsMuteToggle: () => void
  onTtsStop: () => void
  onTtsReplay: () => void
  onTtsRateMode: (mode: TtsRateMode) => void
  onSubtitleToggle: () => void
  onTimerToggle: () => void
  onBackToSetup: () => void
  onApproveAction: (action: AgentToolProposal) => void
  onDismissAction: (action: AgentToolProposal) => void
}) {
  if (props.panel === 'interview-setup') {
    return <InterviewSetup kind="interview" {...props} />
  }

  if (props.panel === 'question-bank-setup') {
    return <InterviewSetup kind="question-bank" {...props} />
  }

  if (props.panel === 'live-interview') {
    return <LiveInterview {...props} />
  }

  const isBlankConversation = props.conversation.messages.length === 0
  const bubbleItems = uniqueStrings([...fixedBubbles, ...props.recommendations]).slice(0, 8)

  return (
    <div className={isBlankConversation ? 'chat-home' : 'chat-home chatting'}>
      {isBlankConversation ? <section className="greeting-panel">
        <div className="peach-hero-portrait">
          <img src={PEACH_PORTRAIT} alt="桃子形象" />
        </div>
        <div className="greeting-copy">
          <h2>{personalGreeting(props.profile)}</h2>
          <p>我是专属于你的求职搭子</p>
        </div>
        <div className="bubble-group">
          <div className="bubble-grid fixed-bubbles">
            {bubbleItems.map((item) => (
              <button key={item} type="button" onClick={() => props.onQuickSend(item)}>{item}</button>
            ))}
          </div>
        </div>
      </section> : null}

      <section className="chat-thread" ref={props.chatScrollRef}>
        {props.conversation.messages.map((message, index) => (
          <Message
            actions={message.actions}
            key={`${message.role}-${index}`}
            role={message.role}
            onApproveAction={props.onApproveAction}
            onDismissAction={props.onDismissAction}
          >
            {message.content}
          </Message>
        ))}
      </section>

      <ChatComposer
        value={props.input}
        placeholder="和桃子聊聊你的求职问题"
        actions={composerActions}
        disabled={Boolean(props.busy.chat)}
        button={props.busy.chat ? '回复中' : '语音输入'}
        buttonKind="voice"
        onChange={props.onInput}
        onSubmit={props.onSend}
        onAction={props.onAction}
        onUpload={props.onUploadChatFile}
        uploadDisabled={Boolean(props.busy.upload || props.busy.chat)}
      />
    </div>
  )
}

function InterviewSetup({
  kind,
  settings,
  profile,
  busy,
  onSettingsChange,
  onStartInterview,
  onStartQuestionBank,
  onUploadInterviewFile,
}: {
  kind: 'interview' | 'question-bank'
  settings: InterviewSettings
  profile: Profile
  busy: Partial<Record<BusyKey, string>>
  onSettingsChange: (value: InterviewSettings) => void
  onStartInterview: () => void
  onStartQuestionBank: () => void
  onUploadInterviewFile: (file: File, target: 'resume' | 'questionBank') => void
}) {
  const isBank = kind === 'question-bank'
  const title = isBank ? '面试题库练习' : '模拟面试'

  return (
    <section className="setup-panel">
      <div className="setup-header">
        <div>
          <h2>{title}</h2>
          <p>{isBank ? '选择题库、简历和面试形式，桃子会按题目连续追问。' : '配置简历、岗位和面试官风格，进入实时对话模式。'}</p>
        </div>
        <div className="setup-peach-card" aria-label="桃子陪练官">
          <img src={PEACH_PORTRAIT} alt="桃子" />
          <div>
            <strong>桃子在场</strong>
            <span>{settings.style}陪练官</span>
          </div>
        </div>
      </div>

      <div className="setup-grid">
        {isBank ? (
          <Field label="面试题库">
            <select value={settings.questionBank} onChange={(event) => onSettingsChange({ ...settings, questionBank: event.target.value })}>
              <option>产品经理通用题库</option>
              <option>简历深挖题库</option>
              <option>AIGC 产品题库</option>
            </select>
            <label className="upload-card">
              <input type="file" accept=".pdf,.doc,.docx,.md,.markdown,.html,.htm" onChange={(event) => event.target.files?.[0] && onUploadInterviewFile(event.target.files[0], 'questionBank')} />
              <span>上传题库文件</span>
            </label>
          </Field>
        ) : null}
        <Field label="面试简历">
          <select value={settings.resume} onChange={(event) => onSettingsChange({ ...settings, resume: event.target.value })}>
            <option>完整简历</option>
            <option>产品经理版本</option>
            <option>实习经历版本</option>
          </select>
          <label className="upload-card">
            <input type="file" accept=".pdf,.doc,.docx,.md,.markdown,.html,.htm" onChange={(event) => event.target.files?.[0] && onUploadInterviewFile(event.target.files[0], 'resume')} />
            <span>上传新简历</span>
          </label>
        </Field>
        <Field label="岗位 JD">
          <textarea
            rows={5}
            value={settings.jd}
            onChange={(event) => onSettingsChange({ ...settings, jd: event.target.value })}
            placeholder="选填，粘贴岗位描述后追问会更贴近真实面试"
          />
        </Field>
        <Field label="面试官">
          <Segmented value={settings.gender} options={['女性', '男性', '不指定']} onChange={(gender) => onSettingsChange({ ...settings, gender })} />
        </Field>
        <Field label="面试官风格">
          <Segmented value={settings.style} options={['温和型', '专业型', '压力型']} onChange={(style) => onSettingsChange({ ...settings, style })} />
        </Field>
        <Field label="面试形式">
          <Segmented value={settings.mode} options={['voice', 'video']} labels={{ voice: '语音面试', video: '视频面试' }} onChange={(mode) => onSettingsChange({ ...settings, mode: mode as InterviewMode })} />
        </Field>
      </div>

      <div className="setup-footer">
        <button type="button" onClick={isBank ? onStartQuestionBank : onStartInterview} disabled={Boolean(busy.interviewStart)}>
          {busy.interviewStart ? '准备中' : '开始面试'}
        </button>
      </div>

      <div className="setup-summary">
        <div>
          <span>目标岗位</span>
          <strong>{profile.target_role}</strong>
        </div>
        <div>
          <span>目标公司</span>
          <strong>{profile.target_company || '未填写'}</strong>
        </div>
        <div>
          <span>当前阶段</span>
          <strong>{profile.stage}</strong>
        </div>
      </div>
    </section>
  )
}

function LiveInterview({
  settings,
  liveKind,
  activeInterviewId,
  interviewProgress,
  conversation,
  input,
  seconds,
  paused,
  mediaReady,
  mediaStream,
  ttsMuted,
  ttsSpeaking,
  lastTtsText,
  ttsRateMode,
  immersiveInterview,
  subtitleCollapsed,
  timerCollapsed,
  videoRef,
  chatScrollRef,
  busy,
  onInput,
  onSend,
  onVoiceSubmit,
  onUploadChatFile,
  onPauseToggle,
  onFinishInterview,
  onImmersiveToggle,
  onTtsMuteToggle,
  onTtsStop,
  onTtsReplay,
  onTtsRateMode,
  onSubtitleToggle,
  onTimerToggle,
  onBackToSetup,
  onApproveAction,
  onDismissAction,
}: Parameters<typeof PeachWorkspace>[0]) {
  const liveTitle = liveKind === 'question-bank' ? '题库练习进行中' : '模拟面试进行中'
  const contextItems = [
    { label: '岗位', value: settings.resume },
    { label: '风格', value: settings.style },
    { label: '形式', value: settings.mode === 'video' ? '视频' : '语音' },
  ]
  const transcriptPreview = conversation.messages
    .filter((message) => message.role !== 'system')
    .slice(-4)

  return (
    <section className="live-stage">
      <div className="live-main">
        <div className="interview-status-strip">
          <div>
            <span>{activeInterviewId ? '面试已连接' : '等待连接'}</span>
            <strong>{liveTitle}</strong>
          </div>
          <div className="interview-status-meta">
            <span>{formatTime(seconds)}</span>
            <span>{paused ? '暂停中' : '进行中'}</span>
            <span>{interviewProgress.answer_count}/{interviewProgress.target_answers} 轮</span>
          </div>
        </div>

        <div className="avatar-stage" aria-label="桃子的半身形象">
          <div className={paused ? 'peach-avatar paused' : 'peach-avatar'}>
            <div className="avatar-aura" />
            <img className="peach-live-portrait" src={PEACH_PORTRAIT} alt="桃子面试官形象" />
            <div className="avatar-body">
              <strong>{liveTitle}</strong>
              <span>{settings.mode === 'video' ? '视频面试' : '语音面试'} / {settings.style}</span>
            </div>
          </div>
          <div className="interview-context-grid">
            {contextItems.map((item) => (
              <div key={item.label}>
                <span>{item.label}</span>
                <strong>{item.value}</strong>
              </div>
            ))}
          </div>
          <div className="live-controls">
            <button type="button" onClick={onPauseToggle}>{paused ? '继续面试' : '暂停面试'}</button>
            <button type="button" className={immersiveInterview ? 'secondary active' : 'secondary'} onClick={onImmersiveToggle}>
              {immersiveInterview ? '文字面试' : '沉浸式面试'}
            </button>
            <button type="button" className="danger" onClick={onFinishInterview}>结束面试</button>
            <button type="button" className="secondary" onClick={onBackToSetup}>返回设置</button>
          </div>
        </div>

        <section className="live-chat" ref={chatScrollRef}>
          {conversation.messages.map((message, index) => (
            <Message
              actions={message.actions}
              key={`${message.role}-${index}`}
              role={message.role}
              onApproveAction={onApproveAction}
              onDismissAction={onDismissAction}
            >
              {message.content}
            </Message>
          ))}
        </section>

        <ChatComposer
          value={input}
          placeholder={immersiveInterview ? (paused ? '面试暂停中' : ttsSpeaking ? '桃子正在说话' : '沉浸式已开启，说完后桃子会自动追问') : (paused ? '面试暂停中，点击继续后再回答' : '输入你的回答，或点击麦克风实时转写')}
          actions={immersiveInterview ? ['结束面试'] : [paused ? '继续面试' : '暂停面试', '结束面试']}
          disabled={paused || Boolean(busy.chat) || (immersiveInterview && ttsSpeaking)}
          button={busy.chat ? '发送中' : '语音输入'}
          buttonKind="voice"
          voiceMode="stream"
          voiceOnly={immersiveInterview}
          autoListen={immersiveInterview && !ttsSpeaking && !paused && !busy.chat}
          listeningText={immersiveInterview ? '麦克风已开，说完自动提交' : undefined}
          onChange={onInput}
          onSubmit={onSend}
          onVoiceSubmit={onVoiceSubmit}
          onAction={(action) => {
            if (action === '结束面试') onFinishInterview()
            else onPauseToggle()
          }}
          onUpload={onUploadChatFile}
          uploadDisabled={paused || Boolean(busy.upload || busy.chat)}
        />
      </div>

      <aside className="live-side">
        <section className="side-widget interview-focus-card">
          <div className="widget-head">
            <span>当前面试</span>
            <strong>{activeInterviewId ? '已同步' : '本地模式'}</strong>
          </div>
          <p>{settings.jd.trim() ? summarizeClientText(settings.jd, 120) : '未填写 JD。桃子会先按目标岗位和简历追问。'}</p>
          <p className="interview-progress-note">
            已回答 {interviewProgress.answer_count} 轮，完成度 {interviewProgress.completion}%。
            桃子至少完成 {interviewProgress.min_answers_for_llm_finish} 轮，并覆盖主要考察项后才会建议结束。
          </p>
          <div className="interview-checklist">
            {(interviewProgress.checklist ?? []).map((item) => (
              <span className={item.done ? 'done' : ''} key={item.key}>{item.done ? '✓' : '○'} {item.label}</span>
            ))}
          </div>
        </section>

        <section className="side-widget voice-widget">
          <div className="widget-head">
            <span>面试官语音</span>
            <strong>{ttsSpeaking ? '朗读中' : ttsMuted ? '已静音' : '待命'}</strong>
          </div>
          <div className="voice-widget-actions">
            <button type="button" className={ttsMuted ? 'active' : ''} onClick={onTtsMuteToggle}>
              {ttsMuted ? '开声' : '静音'}
            </button>
            <button type="button" onClick={onTtsStop} disabled={!ttsSpeaking}>打断</button>
            <button type="button" onClick={onTtsReplay} disabled={!lastTtsText}>重播</button>
          </div>
          <label className="tts-rate-control">
            <span>语速</span>
            <input
              type="range"
              min={0}
              max={2}
              step={1}
              value={ttsRateIndex(ttsRateMode)}
              onChange={(event) => onTtsRateMode(ttsRateFromIndex(Number(event.target.value)))}
              aria-label="面试官语速"
            />
            <strong>{ttsRateLabel(ttsRateMode)}</strong>
          </label>
        </section>

        {settings.mode === 'video' ? (
          <section className="side-widget video-widget">
            <div className="widget-head">
              <span>我的视频</span>
              <strong>{mediaStream ? '已连接' : '未连接'}</strong>
            </div>
            {mediaStream ? <video ref={videoRef} autoPlay muted playsInline /> : <div className="video-placeholder">等待摄像头权限</div>}
          </section>
        ) : null}

        <section className={subtitleCollapsed ? 'side-widget collapsed' : 'side-widget'}>
          <div className="widget-head">
            <span>实时字幕</span>
            <button type="button" onClick={onSubtitleToggle}>{subtitleCollapsed ? '展开' : '收起'}</button>
          </div>
          {!subtitleCollapsed ? (
            <div className="subtitle-lines">
              {transcriptPreview.length ? transcriptPreview.map((message, index) => (
                <p className={message.role === 'user' ? 'candidate-line' : ''} key={`${message.role}-${index}`}>
                  <strong>{message.role === 'user' ? '我' : '桃子'}</strong>
                  {cleanAssistantText(message.content)}
                </p>
              )) : (
                <p>{mediaReady ? '等待第一轮回答。' : '等待媒体权限开启。'}</p>
              )}
            </div>
          ) : null}
        </section>

        <section className={timerCollapsed ? 'side-widget collapsed' : 'side-widget'}>
          <div className="widget-head">
            <span>计时器</span>
            <button type="button" onClick={onTimerToggle}>{timerCollapsed ? '展开' : '收起'}</button>
          </div>
          {!timerCollapsed ? (
            <div className="timer-readout">
              <strong>{formatTime(seconds)}</strong>
              <span>{paused ? '暂停中' : '进行中'}</span>
            </div>
          ) : null}
        </section>
      </aside>
    </section>
  )
}

function ProfileWorkspace({
  profile,
  folders,
  interviews,
  activeSection,
  sectionContent,
  sections,
  actionResult,
  messages,
  resumeFiles,
  isSaving,
  value,
  onSelectSection,
  onSectionContent,
  onValue,
  onSubmit,
  onSave,
  onAction,
  onAcceptResult,
  onUploadFile,
  onApproveAction,
  onDismissAction,
}: {
  profile: Profile
  folders: ResumeFolder[]
  interviews: Dashboard['recent_interviews']
  activeSection: ProfileSectionId
  sectionContent: string
  sections: Record<ProfileSectionId, string>
  actionResult: string
  messages: ChatMessage[]
  resumeFiles: ParsedUpload[]
  isSaving: boolean
  value: string
  onSelectSection: (id: ProfileSectionId) => void
  onSectionContent: (value: string) => void
  onValue: (value: string) => void
  onSubmit: () => void
  onSave: () => void
  onAction: (action: string) => void
  onAcceptResult: () => void
  onUploadFile: (file: File) => void
  onApproveAction: (action: AgentToolProposal) => void
  onDismissAction: (action: AgentToolProposal) => void
}) {
  const current = profileSectionMeta[activeSection]
  const sectionItems = flattenResumeFolders(folders)
  const [reportsCollapsed, setReportsCollapsed] = useState(false)
  const [resumeListCollapsed, setResumeListCollapsed] = useState(false)
  const [resumeSortMode, setResumeSortMode] = useState<'time' | 'role'>('time')
  const [selectedReportId, setSelectedReportId] = useState('')
  const selectedReport = interviews.find((item) => item.id === selectedReportId) ?? interviews[0]

  return (
    <section className="profile-workspace">
      <div className="profile-layout">
        <aside className="profile-overview-panel" aria-label="个人档案分区">
          <div className="profile-overview-head">
            <strong>个人档案</strong>
          </div>

          <div className="profile-section-list">
            {sectionItems.map((item) => {
              const filled = Boolean(sections[item.id]?.trim())
              return (
                <button
                  className={item.id === activeSection ? 'profile-section-button active' : 'profile-section-button'}
                  key={item.id}
                  type="button"
                  onClick={() => onSelectSection(item.id)}
                >
                  <span>
                    <strong>{item.title}</strong>
                    <small>{filled ? '已记录' : '待补充'}</small>
                  </span>
                  <p>{item.summary}</p>
                </button>
              )
            })}
          </div>
        </aside>

        <section className={`profile-detail-panel${activeSection === 'full' ? ' with-resume-files' : ''}${activeSection === 'reviews' ? ' with-review-board' : ''}`}>
          <div className="profile-detail-head">
            <div>
              <span>正在编辑</span>
              <h2>{current.title}</h2>
            </div>
            <button type="button" onClick={onSave} disabled={isSaving}>
              {isSaving ? '保存中' : '保存档案'}
            </button>
          </div>

          {activeSection === 'reviews' ? (
            <section className="profile-review-board">
              <article className="profile-review-card">
                <div className="profile-card-head">
                  <strong>历史面试总结</strong>
                  <span>{interviews.length} 份报告</span>
                </div>
                <p>{buildInterviewHistorySummary(interviews, profile)}</p>
              </article>

              <article className="profile-review-card report-list-card">
                <div className="profile-card-head">
                  <strong>历史面试报告</strong>
                  <button type="button" onClick={() => setReportsCollapsed((value) => !value)}>{reportsCollapsed ? '展开' : '收起'}</button>
                </div>
                {!reportsCollapsed ? (
                  <div className="profile-report-list">
                    {interviews.length ? interviews.map((interview) => (
                      <button
                        className={selectedReport?.id === interview.id ? 'active' : ''}
                        type="button"
                        key={interview.id}
                        onClick={() => setSelectedReportId(interview.id)}
                      >
                        <strong>{formatInterviewReportTitle(interview, profile)}</strong>
                        <span>{interview.report?.summary || '点击查看报告详情'}</span>
                      </button>
                    )) : <p>还没有生成过面试复盘报告。</p>}
                  </div>
                ) : null}
              </article>

              {selectedReport ? (
                <InterviewReportPanel interview={selectedReport} profile={profile} onDownload={() => downloadInterviewReport(selectedReport, profile)} />
              ) : null}

              <article className="profile-review-upload">
                <strong>上传其他面试的语音/文字，桃子帮你面试复盘</strong>
                <div>
                  <label>
                    <input type="file" accept=".pdf,.doc,.docx,.md,.markdown,.html,.htm" onChange={(event) => event.target.files?.[0] && onUploadFile(event.target.files[0])} />
                    上传材料
                  </label>
                  <button type="button" onClick={() => onAction('面试复盘')}>生成复盘</button>
                </div>
              </article>
            </section>
          ) : null}

          {activeSection === 'full' ? (
            <div className="resume-file-strip">
              <label className="resume-upload-card">
                <input type="file" accept=".pdf,.doc,.docx,.md,.markdown,.html,.htm" onChange={(event) => event.target.files?.[0] && onUploadFile(event.target.files[0])} />
                <span>+</span>
                <strong>上传简历附件</strong>
              </label>
              <div className="resume-file-list">
                <div className="resume-list-toolbar">
                  <button type="button" onClick={() => setResumeListCollapsed((value) => !value)}>{resumeListCollapsed ? '展开简历列表' : '收起简历列表'}</button>
                  <select value={resumeSortMode} onChange={(event) => setResumeSortMode(event.target.value as 'time' | 'role')} aria-label="简历排序">
                    <option value="time">按上传时间</option>
                    <option value="role">按对应岗位</option>
                  </select>
                </div>
                <div className="resume-file-items">
                  {!resumeListCollapsed && resumeFiles.length ? sortResumeFiles(resumeFiles, resumeSortMode).map((file) => (
                    <button type="button" key={file.filename} onClick={() => onSectionContent([sectionContent, `【${file.title}】\n${file.content}`].filter(Boolean).join('\n\n'))}>
                      <strong>{file.filename}</strong>
                      <span>{file.summary || '已解析'}</span>
                    </button>
                  )) : null}
                  {!resumeListCollapsed && !resumeFiles.length ? <p>还没有上传简历文件。</p> : null}
                </div>
              </div>
            </div>
          ) : null}

          {activeSection === 'reviews' ? null : (
            <>
              {activeSection === 'full' ? <ResumeInsightCard profile={profile} sectionContent={sectionContent} resumeFiles={resumeFiles} /> : null}
              {(activeSection === 'internship' || activeSection === 'project') ? <ExperienceNameList title={current.title} content={sectionContent} /> : null}
              <textarea
                className="profile-editor"
                value={sectionContent}
                onChange={(event) => onSectionContent(event.target.value)}
                placeholder={`在这里整理${current.title}。桃子会基于这些内容帮你生成简历、优化表达和准备追问题。`}
                rows={10}
              />
            </>
          )}

          {actionResult ? (
            <section className="profile-action-result">
              <div className="profile-action-head">
                <strong>桃子的建议</strong>
                <button type="button" onClick={onAcceptResult}>采纳到当前文件</button>
              </div>
              <p>{actionResult}</p>
            </section>
          ) : (
            activeSection === 'reviews' || activeSection === 'full' ? null : (
              <section className="profile-empty-hint" aria-label="当前分区状态">
                <strong>{sectionContent.trim() ? '这部分内容已记录，后续可继续优化。' : '当前文件暂无内容。'}</strong>
              </section>
            )
          )}

          {messages.length ? (
            <section className="profile-chat-thread" aria-label="个人档案对话">
              {messages.map((message, index) => (
                <Message
                  key={`${message.role}-${index}`}
                  role={message.role}
                  actions={message.actions}
                  onApproveAction={onApproveAction}
                  onDismissAction={onDismissAction}
                >
                  {message.content}
                </Message>
              ))}
            </section>
          ) : null}
        </section>
      </div>
      <ChatComposer
        value={value}
        placeholder="补充个人档案"
        actions={['简历生成', '经历生成', '简历优化', '面试深挖']}
        disabled={isSaving}
        button={isSaving ? '保存中' : '语音输入'}
        buttonKind="voice"
        onChange={onValue}
        onSubmit={onSubmit}
        onAction={onAction}
        onUpload={onUploadFile}
        uploadDisabled={isSaving}
      />
    </section>
  )
}

function InterviewReportPanel({
  interview,
  profile,
  onDownload,
}: {
  interview: Dashboard['recent_interviews'][number]
  profile: Profile
  onDownload: () => void
}) {
  const report = normalizeInterviewReport(interview.report, interview, profile)
  return (
    <article className="interview-report-panel">
      <div className="profile-card-head">
        <strong>{report.position}</strong>
        <button type="button" onClick={onDownload}>下载 PDF</button>
      </div>
      <div className="report-score-row">
        <div>
          <span>得分</span>
          <strong>{report.overall_score}</strong>
        </div>
        <div>
          <span>等级</span>
          <strong>{report.level}</strong>
        </div>
        <div>
          <span>超过同类求职者</span>
          <strong>{report.percentile}%</strong>
        </div>
      </div>
      <p>{report.summary}</p>
      <section className="report-dimension-card" aria-label="多维评价">
        <strong>多维评价</strong>
        {report.dimensions.map((item) => (
          <div className="report-dimension-row" key={item.name}>
            <span>{item.name}</span>
            <div><i style={{ width: `${Math.max(8, Math.min(100, item.score))}%` }} /></div>
            <strong>{item.score}</strong>
          </div>
        ))}
      </section>
      <div className="report-suggestions">
        <strong>评价建议</strong>
        <ul>{report.key_improvements.map((item) => <li key={item}>{item}</li>)}</ul>
      </div>
      <div className="report-question-review">
        <strong>问题回顾</strong>
        {report.question_review.map((item, index) => (
          <section key={`${item.question}-${index}`}>
            <h4>{item.question || '待优化问题'}</h4>
            <p><b>考察点：</b>{item.assessment_focus || '岗位匹配、表达结构和证据质量。'}</p>
            <p><b>回答转文字：</b>{item.candidate_transcript || '暂无转文字。'}</p>
            <p><b>示例回答：</b>{item.sample_answer || '建议按结论、经历证据、岗位匹配三段式回答。'}</p>
          </section>
        ))}
      </div>
    </article>
  )
}

function ResumeInsightCard({
  profile,
  sectionContent,
  resumeFiles,
}: {
  profile: Profile
  sectionContent: string
  resumeFiles: ParsedUpload[]
}) {
  const hasContent = Boolean(sectionContent.trim() || resumeFiles.length)
  return (
    <section className="resume-insight-card">
      <div>
        <strong>已有简历总结</strong>
        <p>{hasContent ? summarizeClientText(sectionContent || resumeFiles[0]?.summary || '', 120) : '暂时还没有完整简历，可以先上传或粘贴一版。'}</p>
      </div>
      <div>
        <strong>与目标岗位匹配度</strong>
        <p>{hasContent ? `当前与「${profile.target_role}」已有基础匹配，建议继续补充量化结果、项目角色和业务指标。` : `目标岗位是「${profile.target_role}」，先补经历后才能判断匹配度。`}</p>
      </div>
      <div>
        <strong>改进建议</strong>
        <p>{hasContent ? '优先把“负责”改成“主导/推动 + 动作 + 结果”，每段经历至少补 1 个可追问证据。' : '先上传主简历，再让桃子做简历优化和面试深挖。'}</p>
      </div>
    </section>
  )
}

function ExperienceNameList({ title, content }: { title: string; content: string }) {
  const names = extractExperienceNames(content)
  return (
    <section className="experience-name-list">
      <div className="profile-card-head">
        <strong>{title}列表</strong>
        <span>按上传/录入时间排序</span>
      </div>
      {names.length ? names.map((name) => <span key={name}>{name}</span>) : <p>还没有可识别的经历名称。</p>}
    </section>
  )
}

function KnowledgeWorkspace({
  tab,
  question,
  messages,
  items,
  savedIds,
  activeFolder,
  folderItems,
  activeId,
  draft,
  actionResult,
  actionMode,
  isCreating,
  busy,
  fileSort,
  onFileSort,
  onQuestion,
  onAskQuestion,
  onSave,
  onDraft,
  onSaveDraft,
  onDelete,
  onUpload,
  onAsk,
  onUseInProfile,
  onSelectItem,
  onNewItem,
  onRenameFolder,
  onDeleteFolder,
  onRenameItem,
  onDeleteItem,
  onParseLink,
  onApproveAction,
  onDismissAction,
  onBackToAsk,
  onRunItemAction,
  onAcceptActionResult,
}: {
  tab: KnowledgeTab
  question: string
  messages: ChatMessage[]
  items: KnowledgeItem[]
  savedIds: string[]
  activeFolder?: KnowledgeFolder
  folderItems: KnowledgeItem[]
  activeId: string
  draft: KnowledgeDraft
  actionResult: string
  actionMode: string
  isCreating: boolean
  busy: boolean
  fileSort: SortMode
  onFileSort: (mode: SortMode) => void
  onQuestion: (value: string) => void
  onAskQuestion: () => void
  onSave: (id: string) => void
  onDraft: (draft: KnowledgeDraft) => void
  onSaveDraft: () => void
  onDelete: (id: string) => void
  onUpload: (file: File) => void
  onAsk: (item: KnowledgeItem) => void
  onUseInProfile: (item: KnowledgeItem) => void
  onSelectItem: (item: KnowledgeItem) => void
  onNewItem: () => void
  onRenameFolder: (scope: Exclude<KnowledgeTab, 'discover'>, id: string) => void
  onDeleteFolder: (scope: Exclude<KnowledgeTab, 'discover'>, id: string) => void
  onRenameItem: (item: KnowledgeItem) => void
  onDeleteItem: (id: string) => void
  onParseLink: () => void
  onApproveAction: (action: AgentToolProposal) => void
  onDismissAction: (action: AgentToolProposal) => void
  onBackToAsk: () => void
  onRunItemAction: (action: string) => void
  onAcceptActionResult: () => void
}) {
  const activeItem = items.find((item) => item.id === activeId)
  const canEdit = isCreating || activeItem?.source === 'personal'
  const discoverItems = items.filter((item) => item.source === 'discover')

  return (
    <section className="knowledge-workspace">
      {tab === 'discover' ? (
        <section className="knowledge-discover">
          <div className="discover-head">
            <div>
              <h2>知识库</h2>
              <p>精选</p>
            </div>
            <input aria-label="搜索知识库" placeholder="搜索知识库" />
          </div>
          <div className="featured-grid">
            {discoverItems.slice(0, 4).map((item, index) => (
              <KnowledgeFeedCard
                featured
                item={item}
                index={index}
                key={item.id}
                saved={savedIds.includes(item.id)}
                onSave={onSave}
                onAsk={onAsk}
              />
            ))}
          </div>
          <div className="recommend-tabs">
            {['推荐', '科技', '教育', '职场', '财经', '产业', 'AI'].map((item) => <button key={item} type="button">{item}</button>)}
          </div>
          <div className="recommend-grid">
            {discoverItems.map((item, index) => (
              <KnowledgeFeedCard
                item={item}
                index={index}
                key={item.id}
                saved={savedIds.includes(item.id)}
                onSave={onSave}
                onAsk={() => onAsk(item)}
              />
            ))}
          </div>
        </section>
      ) : (
        <section className="knowledge-library">
          <KnowledgeCollectionPanel
            folder={activeFolder}
            items={folderItems}
            activeId={activeId}
            fileSort={fileSort}
            busy={busy}
            onFileSort={onFileSort}
            onSelectItem={onSelectItem}
            onNewItem={onNewItem}
            onRenameFolder={onRenameFolder}
            onDeleteFolder={onDeleteFolder}
            onRenameItem={onRenameItem}
            onDeleteItem={onDeleteItem}
            onParseLink={onParseLink}
            onUpload={onUpload}
          />
          <div className="knowledge-reader-shell">
            {activeItem || isCreating ? (
              <KnowledgeDetailView
                activeItem={activeItem}
                canEdit={canEdit}
                isCreating={isCreating}
                draft={draft}
                actionResult={actionResult}
                actionMode={actionMode}
                busy={busy}
                saved={Boolean(activeItem && savedIds.includes(activeItem.id))}
                onBack={onBackToAsk}
                onDraft={onDraft}
                onSaveDraft={onSaveDraft}
                onDelete={onDelete}
                onSave={onSave}
                onAsk={onAsk}
                onUseInProfile={onUseInProfile}
                onRunItemAction={onRunItemAction}
                onAcceptActionResult={onAcceptActionResult}
              />
            ) : (
              <KnowledgeAskView
                tab={tab}
                question={question}
                messages={messages}
                busy={busy}
                onQuestion={onQuestion}
                onAskQuestion={onAskQuestion}
                onUpload={onUpload}
                onApproveAction={onApproveAction}
                onDismissAction={onDismissAction}
              />
            )}
          </div>
        </section>
      )}
    </section>
  )
}

function KnowledgeCollectionPanel({
  folder,
  items,
  activeId,
  fileSort,
  busy,
  onFileSort,
  onSelectItem,
  onNewItem,
  onRenameFolder,
  onDeleteFolder,
  onRenameItem,
  onDeleteItem,
  onParseLink,
  onUpload,
}: {
  folder?: KnowledgeFolder
  items: KnowledgeItem[]
  activeId: string
  fileSort: SortMode
  busy: boolean
  onFileSort: (mode: SortMode) => void
  onSelectItem: (item: KnowledgeItem) => void
  onNewItem: () => void
  onRenameFolder: (scope: Exclude<KnowledgeTab, 'discover'>, id: string) => void
  onDeleteFolder: (scope: Exclude<KnowledgeTab, 'discover'>, id: string) => void
  onRenameItem: (item: KnowledgeItem) => void
  onDeleteItem: (id: string) => void
  onParseLink: () => void
  onUpload: (file: File) => void
}) {
  const title = folder?.name || '个人知识库'
  const scopeLabel = folder?.scope === 'saved' ? '共享资料' : '个人资料'

  return (
    <section className="knowledge-collection-panel">
      <header className="kb-collection-head">
        <div className="kb-collection-cover" aria-hidden="true">
          <span />
        </div>
        <div>
          <h2>{title}</h2>
          <p>{scopeLabel}</p>
          <small>{items.length ? `${items.length} 份内容` : '快来填写描述吧'}</small>
        </div>
      </header>

      <div className="kb-collection-meta">
        <span>{folder?.scope === 'saved' ? '已收藏' : '已设为私密'}</span>
        {folder ? (
          <div>
            <button type="button" onClick={() => onRenameFolder(folder.scope, folder.id)}>重命名</button>
            <button type="button" onClick={() => onDeleteFolder(folder.scope, folder.id)}>删除</button>
          </div>
        ) : null}
      </div>

      <div className="kb-content-head">
        <strong>内容({items.length})</strong>
        <div>
          <button type="button" onClick={onNewItem} disabled={busy}>新建</button>
          <button type="button" onClick={onParseLink} disabled={busy}>链接</button>
          <label>
            <input type="file" accept=".pdf,.doc,.docx,.md,.markdown,.html,.htm" onChange={(event) => event.target.files?.[0] && onUpload(event.target.files[0])} disabled={busy} />
            <span>上传</span>
          </label>
          <select value={fileSort} onChange={(event) => onFileSort(event.target.value as SortMode)} aria-label="内容排序">
            <option value="updated">最近</option>
            <option value="name">名称</option>
          </select>
        </div>
      </div>

      <div className="kb-content-list">
        {items.length ? items.map((item) => (
          <article className={item.id === activeId ? 'kb-content-item active' : 'kb-content-item'} key={item.id}>
            <button type="button" onClick={() => onSelectItem(item)}>
              <span className="kb-file-mark" aria-hidden="true" />
              <span>
                <strong>{item.title}</strong>
                <small>{item.summary || '暂无摘要'}</small>
              </span>
            </button>
            <div>
              <button type="button" onClick={() => onRenameItem(item)}>改名</button>
              {item.source === 'personal' ? <button type="button" onClick={() => onDeleteItem(item.id)}>删除</button> : null}
            </div>
          </article>
        )) : (
          <div className="kb-content-empty">
            <strong>没有更多内容了</strong>
            <p>上传文件、解析链接，或新建一份资料。</p>
          </div>
        )}
      </div>
    </section>
  )
}

function KnowledgeAskView({
  tab,
  question,
  messages,
  busy,
  onQuestion,
  onAskQuestion,
  onUpload,
  onApproveAction,
  onDismissAction,
}: {
  tab: KnowledgeTab
  question: string
  messages: ChatMessage[]
  busy: boolean
  onQuestion: (value: string) => void
  onAskQuestion: () => void
  onUpload: (file: File) => void
  onApproveAction: (action: AgentToolProposal) => void
  onDismissAction: (action: AgentToolProposal) => void
}) {
  return (
    <section className="knowledge-ask-view">
      <div className="knowledge-ask-center">
        <h2>基于知识库问答</h2>
        {!messages.length ? (
          <p>{tab === 'personal' ? '可以围绕个人资料梳理经历、准备面试题和整理投递策略。' : '可以围绕收藏资料解释概念、拆解方法并迁移到你的求职场景。'}</p>
        ) : null}
      </div>
      <div className="knowledge-chat-thread">
        {messages.map((message, index) => (
          <Message
            key={`${message.role}-${index}`}
            role={message.role}
            actions={message.actions}
            onApproveAction={onApproveAction}
            onDismissAction={onDismissAction}
          >
            {message.content}
          </Message>
        ))}
      </div>

      <ChatComposer
        value={question}
        placeholder={tab === 'personal' ? '基于个人知识库向桃子提问' : '基于收藏知识库向桃子提问'}
        actions={[]}
        disabled={Boolean(busy)}
        button={busy ? '回答中' : '语音输入'}
        buttonKind="voice"
        onChange={onQuestion}
        onSubmit={onAskQuestion}
        onAction={() => undefined}
        onUpload={onUpload}
        uploadDisabled={Boolean(busy)}
      />
    </section>
  )
}

function KnowledgeDetailView({
  activeItem,
  canEdit,
  isCreating,
  draft,
  actionResult,
  actionMode,
  busy,
  saved,
  onBack,
  onDraft,
  onSaveDraft,
  onDelete,
  onSave,
  onAsk,
  onUseInProfile,
  onRunItemAction,
  onAcceptActionResult,
}: {
  activeItem?: KnowledgeItem
  canEdit: boolean
  isCreating: boolean
  draft: KnowledgeDraft
  actionResult: string
  actionMode: string
  busy: boolean
  saved: boolean
  onBack: () => void
  onDraft: (draft: KnowledgeDraft) => void
  onSaveDraft: () => void
  onDelete: (id: string) => void
  onSave: (id: string) => void
  onAsk: (item: KnowledgeItem) => void
  onUseInProfile: (item: KnowledgeItem) => void
  onRunItemAction: (action: string) => void
  onAcceptActionResult: () => void
}) {
  const displayTitle = draft.title.trim() || activeItem?.title || '新建资料'
  const displaySummary = draft.summary.trim() || activeItem?.summary || '暂无摘要'
  const displayContent = draft.content.trim() || activeItem?.content || activeItem?.summary || ''

  return (
    <section className="knowledge-detail-view">
      <header className="knowledge-detail-hero">
        <button className="text-button" type="button" onClick={onBack}>返回问答</button>
        <div>
          <span>{isCreating ? '新建资料' : canEdit ? '个人资料' : '收藏资料'}</span>
          <h2>{displayTitle}</h2>
          <p>{displaySummary}</p>
        </div>
        <div className="knowledge-detail-actions">
          {activeItem?.source === 'discover' ? (
            <button type="button" onClick={() => onSave(activeItem.id)} disabled={saved}>{saved ? '已收藏' : '收藏'}</button>
          ) : null}
          {activeItem ? <button type="button" onClick={() => onAsk(activeItem)}>问桃子</button> : null}
          {activeItem ? <button type="button" onClick={() => onUseInProfile(activeItem)}>沉淀到档案</button> : null}
        </div>
      </header>

      <div className="knowledge-detail-body">
        <section className="knowledge-edit-pane">
          {canEdit ? (
            <div className="knowledge-editor spacious">
              <label>
                <span>标题</span>
                <input value={draft.title} onChange={(event) => onDraft({ ...draft, title: event.target.value })} />
              </label>
              <label>
                <span>摘要</span>
                <textarea rows={3} value={draft.summary} onChange={(event) => onDraft({ ...draft, summary: event.target.value })} />
              </label>
              <label>
                <span>正文</span>
                <textarea rows={12} value={draft.content} onChange={(event) => onDraft({ ...draft, content: event.target.value })} />
              </label>
            </div>
          ) : (
            <article className="knowledge-readonly">
              <p>{displayContent || '这条收藏资料暂时没有正文。'}</p>
            </article>
          )}
        </section>

        <aside className="knowledge-ai-pane">
          <div className="knowledge-ai-head">
            <strong>桃子调整</strong>
            <p>先生成建议，确认后再写入当前资料。</p>
          </div>
          <div className="knowledge-ai-actions">
            {['智能摘要', '优化正文', '提炼面试题', '生成行动项'].map((action) => (
              <button key={action} type="button" onClick={() => onRunItemAction(action)} disabled={busy || !displayContent.trim()}>
                {busy && actionMode === action ? '处理中' : action}
              </button>
            ))}
          </div>
          {actionResult ? (
            <section className="knowledge-ai-result">
              <div>
                <span>{actionMode || '桃子建议'}</span>
                <button type="button" onClick={onAcceptActionResult}>采纳</button>
              </div>
              <p>{actionResult}</p>
            </section>
          ) : (
            <section className="knowledge-ai-empty">
              <strong>{canEdit ? '可以让桃子先整理，再决定是否采纳。' : '收藏资料不能直接改原文，但可以提炼成档案或面试题。'}</strong>
            </section>
          )}
        </aside>
      </div>

      <footer className="knowledge-detail-footer">
        <div>
          <span>{draft.url || activeItem?.url ? '来源已记录' : '无来源链接'}</span>
        </div>
        <div className="knowledge-editor-actions">
          {activeItem?.source === 'personal' ? <button type="button" className="secondary-danger" onClick={() => onDelete(activeItem.id)}>删除</button> : null}
          {canEdit ? (
            <button type="button" onClick={onSaveDraft} disabled={busy || !draft.title.trim() || !draft.content.trim()}>
              {busy ? '保存中' : isCreating ? '新建资料' : '保存修改'}
            </button>
          ) : (
            <button type="button" onClick={onSaveDraft} disabled={busy || !draft.title.trim() || !draft.content.trim()}>
              {busy ? '保存中' : '保存为个人资料'}
            </button>
          )}
        </div>
      </footer>
    </section>
  )
}

function KnowledgeFeedCard({
  item,
  featured,
  index,
  saved,
  onSave,
  onAsk,
}: {
  item: KnowledgeItem
  featured?: boolean
  index: number
  saved: boolean
  onSave: (id: string) => void
  onAsk: (item: KnowledgeItem) => void
}) {
  return (
    <article className={featured ? 'knowledge-feed-card featured' : 'knowledge-feed-card'}>
      <div className={`feed-cover feed-cover-${index % 6}`} aria-hidden="true" />
      <div>
        <h3>{item.title}</h3>
        <p>{item.summary}</p>
        <span>{knowledgeMetaLine(item, index)}</span>
      </div>
      <div className="feed-actions">
        <button type="button" onClick={() => onAsk(item)}>提问</button>
        <button type="button" onClick={() => onSave(item.id)} disabled={saved}>{saved ? '已收藏' : '收藏'}</button>
      </div>
    </article>
  )
}

function ChatComposer({
  value,
  placeholder,
  actions,
  disabled,
  button,
  buttonKind = 'send',
  voiceMode = 'single',
  voiceOnly = false,
  autoListen = false,
  listeningText,
  uploadDisabled,
  onChange,
  onSubmit,
  onVoiceSubmit,
  onAction,
  onUpload,
}: {
  value: string
  placeholder: string
  actions: string[]
  disabled: boolean
  button: string
  buttonKind?: 'send' | 'voice'
  voiceMode?: 'single' | 'stream'
  voiceOnly?: boolean
  autoListen?: boolean
  listeningText?: string
  uploadDisabled?: boolean
  onChange: (value: string) => void
  onSubmit: () => void
  onVoiceSubmit?: (value: string) => void
  onAction: (action: string) => void
  onUpload?: (file: File) => void
}) {
  const recognitionRef = useRef<BrowserSpeechRecognition | null>(null)
  const valueRef = useRef(value)
  const disabledRef = useRef(disabled)
  const autoListenRef = useRef(autoListen)
  const voiceModeRef = useRef(voiceMode)
  const finalTextRef = useRef('')
  const baseValueRef = useRef('')
  const autoSubmitTimerRef = useRef<number | null>(null)
  const manualStopRef = useRef(false)
  const startingRef = useRef(false)
  const submittingRef = useRef(false)
  const [captureMode, setCaptureMode] = useState<VoiceCaptureMode>('auto')
  const [listening, setListening] = useState(false)

  useEffect(() => { valueRef.current = value }, [value])
  useEffect(() => { disabledRef.current = disabled }, [disabled])
  useEffect(() => { autoListenRef.current = autoListen }, [autoListen])
  useEffect(() => { voiceModeRef.current = voiceMode }, [voiceMode])

  const clearAutoSubmitTimer = useCallback(() => {
    if (autoSubmitTimerRef.current) {
      window.clearTimeout(autoSubmitTimerRef.current)
      autoSubmitTimerRef.current = null
    }
  }, [])

  const stopRecognition = useCallback((manual = false) => {
    if (manual) manualStopRef.current = true
    clearAutoSubmitTimer()
    const recognition = recognitionRef.current
    recognitionRef.current = null
    startingRef.current = false
    if (recognition) {
      try {
        recognition.onresult = null
        recognition.onerror = null
        recognition.onend = null
        recognition.stop()
      } catch {
        // Browser speech recognition may throw if already stopped.
      }
    }
    setListening(false)
  }, [clearAutoSubmitTimer])

  const submitVoiceText = useCallback((text: string) => {
    const content = normalizeVoiceAnswer(text)
    if (!content || submittingRef.current) return
    submittingRef.current = true
    stopRecognition(true)
    onChange('')
    window.setTimeout(() => {
      onVoiceSubmit?.(content)
      window.setTimeout(() => {
        submittingRef.current = false
      }, 900)
    }, 0)
  }, [onChange, onVoiceSubmit, stopRecognition])

  useEffect(() => () => {
    stopRecognition(true)
  }, [stopRecognition])

  const startVoiceInput = useCallback((mode: VoiceCaptureMode = 'auto') => {
    if (disabledRef.current || startingRef.current || recognitionRef.current) return

    const recognitionConstructor = (window as SpeechRecognitionWindow).SpeechRecognition ?? (window as SpeechRecognitionWindow).webkitSpeechRecognition
    if (!recognitionConstructor) {
      window.alert('当前浏览器暂不支持语音输入，可以直接打字。')
      return
    }

    startingRef.current = true
    manualStopRef.current = false
    finalTextRef.current = ''
    baseValueRef.current = valueRef.current.trim()
    setCaptureMode(mode)
    const recognition = new recognitionConstructor()
    recognition.lang = 'zh-CN'
    recognition.interimResults = true
    recognition.continuous = voiceModeRef.current === 'stream'
    recognition.onresult = (event) => {
      if (manualStopRef.current) return
      const chunks = Array.from(event.results)
      const transcript = normalizeVoiceAnswer(chunks.map((result) => result[0]?.transcript || '').join(''))
      const finalText = chunks
        .filter((result) => result.isFinal)
        .map((result) => result[0]?.transcript || '')
        .join('')
      const cleanFinal = normalizeVoiceAnswer(finalText)
      if (cleanFinal) finalTextRef.current = cleanFinal

      if (transcript) {
        const merged = [baseValueRef.current, transcript].filter(Boolean).join(' ')
        onChange(merged)
      }

      if (voiceModeRef.current === 'stream' && mode === 'auto' && cleanFinal && onVoiceSubmit) {
        clearAutoSubmitTimer()
        autoSubmitTimerRef.current = window.setTimeout(() => {
          submitVoiceText(finalTextRef.current)
        }, 1200)
      }
    }
    recognition.onerror = () => {
      clearAutoSubmitTimer()
      recognitionRef.current = null
      startingRef.current = false
      setListening(false)
    }
    recognition.onend = () => {
      const hasFinalText = Boolean(finalTextRef.current)
      clearAutoSubmitTimer()
      recognitionRef.current = null
      startingRef.current = false
      setListening(false)
      if (
        voiceModeRef.current === 'stream'
        && mode === 'auto'
        && hasFinalText
        && !manualStopRef.current
        && !disabledRef.current
        && !submittingRef.current
      ) {
        window.setTimeout(() => submitVoiceText(finalTextRef.current), 0)
        return
      }
      if (
        voiceModeRef.current === 'stream'
        && (mode === 'auto' || mode === 'dictation')
        && (autoListenRef.current || mode === 'dictation')
        && !manualStopRef.current
        && !disabledRef.current
        && !submittingRef.current
      ) {
        window.setTimeout(() => startVoiceInput(mode), 260)
      }
    }
    recognitionRef.current = recognition
    setListening(true)
    try {
      recognition.start()
      startingRef.current = false
    } catch {
      recognitionRef.current = null
      startingRef.current = false
      setListening(false)
    }
  }, [clearAutoSubmitTimer, onChange, onVoiceSubmit, submitVoiceText])

  const stopVoiceInput = useCallback(() => {
    stopRecognition(true)
  }, [stopRecognition])

  useEffect(() => {
    if (!autoListen || disabled) {
      if (listening) stopVoiceInput()
      return
    }
    if (!listening && !value.trim() && !submittingRef.current && captureMode === 'auto') startVoiceInput('auto')
  }, [autoListen, captureMode, disabled, listening, startVoiceInput, stopVoiceInput, value])

  function toggleVoiceInput() {
    if (disabled && !listening) return
    if (listening) {
      if (captureMode === 'dictation') {
        const content = finalTextRef.current || value
        submitVoiceText(content)
      } else {
        stopVoiceInput()
      }
      return
    }
    startVoiceInput('auto')
  }

  function toggleLongVoiceInput() {
    if (disabled && !listening) return
    if (listening && captureMode === 'dictation') {
      const content = finalTextRef.current || value
      submitVoiceText(content)
      setCaptureMode('auto')
      return
    }
    if (listening) stopVoiceInput()
    startVoiceInput('dictation')
  }

  function handlePrimaryClick() {
    if (buttonKind === 'voice') {
      if (voiceOnly || listening || !value.trim()) {
        toggleVoiceInput()
        return
      }
      onSubmit()
      return
    }
    onSubmit()
  }

  function handleForceSubmit() {
    const content = value.trim()
    if (!content || disabled) return
    stopVoiceInput()
    onVoiceSubmit?.(content)
  }

  const primaryDisabled = disabled || (buttonKind !== 'voice' && !value.trim())
  const primaryClass = [
    buttonKind === 'voice' ? 'voice-send-button' : '',
    listening ? 'listening' : '',
  ].filter(Boolean).join(' ')

  return (
    <section className={voiceOnly ? 'bottom-composer immersive-composer' : 'bottom-composer'}>
      <div className="composer-input-row">
        <textarea
          rows={1}
          value={value}
          readOnly={voiceOnly}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={(event) => {
            if (voiceOnly) return
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault()
              onSubmit()
            }
          }}
          placeholder={placeholder}
        />
      </div>
      <div className="composer-tool-row">
        <div className="composer-left-tools">
          {voiceOnly ? <span className={listening ? 'immersive-listening active' : 'immersive-listening'}>{listening ? (listeningText || '麦克风已开') : '麦克风已关'}</span> : null}
          {!voiceOnly && onUpload ? (
            <label className={uploadDisabled ? 'composer-upload-button disabled' : 'composer-upload-button'} title="上传文件" aria-label="上传文件">
              <input
                type="file"
                accept=".pdf,.doc,.docx,.md,.markdown,.html,.htm"
                disabled={uploadDisabled}
                onChange={(event) => {
                  const file = event.target.files?.[0]
                  event.target.value = ''
                  if (file) onUpload(file)
                }}
              />
              <span aria-hidden="true">+</span>
            </label>
          ) : null}
          {!voiceOnly && actions.length ? (
            <div className="composer-action-row">
              {actions.map((action) => (
                <button key={action} type="button" onClick={() => onAction(action)}>{action}</button>
              ))}
            </div>
          ) : null}
        </div>
        <div className="composer-send-group">
          {voiceOnly && actions.includes('结束面试') ? (
            <button
              className="immersive-end-button"
              type="button"
              onClick={() => {
                stopVoiceInput()
                onAction('结束面试')
              }}
            >
              结束面试
            </button>
          ) : null}
          {voiceOnly ? (
            <button
              className={captureMode === 'dictation' && listening ? 'immersive-long-voice active' : 'immersive-long-voice'}
              type="button"
              onClick={toggleLongVoiceInput}
              disabled={disabled && !(captureMode === 'dictation' && listening)}
            >
              {captureMode === 'dictation' && listening ? '完成长回答' : '长文本输入'}
            </button>
          ) : null}
          {voiceOnly ? (
            <button
              className="immersive-force-send"
              type="button"
              onClick={handleForceSubmit}
              disabled={disabled || !value.trim()}
            >
              发送转写
            </button>
          ) : null}
          <button className={primaryClass} type="button" onClick={handlePrimaryClick} disabled={primaryDisabled} aria-label={listening ? '停止语音输入' : button}>
            {buttonKind === 'voice' ? <span className="mic-icon" aria-hidden="true" /> : button}
          </button>
        </div>
      </div>
    </section>
  )
}

function Message({
  role,
  children,
  actions,
  onApproveAction,
  onDismissAction,
}: {
  role: ChatMessage['role']
  children: string
  actions?: AgentToolProposal[]
  onApproveAction: (action: AgentToolProposal) => void
  onDismissAction: (action: AgentToolProposal) => void
}) {
  return (
    <div className={`message-row ${role}`}>
      {role === 'peach' ? <img className="message-avatar-image" src={PEACH_ICON} alt="桃子" /> : null}
      <div className="message-stack">
        <div className="message-bubble">{cleanAssistantText(children)}</div>
        {actions?.length ? (
          <div className="tool-approval-list">
            {actions.map((action) => (
              <ToolApprovalCard
                action={action}
                key={action.id}
                onApprove={() => onApproveAction(action)}
                onDismiss={() => onDismissAction(action)}
              />
            ))}
          </div>
        ) : null}
      </div>
    </div>
  )
}

function ToolApprovalCard({
  action,
  onApprove,
  onDismiss,
}: {
  action: AgentToolProposal
  onApprove: () => void
  onDismiss: () => void
}) {
  const status = action.status ?? 'pending'
  const done = status === 'approved' || status === 'dismissed'
  const [detailOpen, setDetailOpen] = useState(false)
  const draftDetail = useMemo(() => buildPendingToolActionDetail(action), [action])
  const visibleDetail = action.result ?? draftDetail
  const detailLabel = action.result ? '改动' : '草案'
  const statusLabel: Record<AgentActionStatus, string> = {
    pending: '待确认',
    executing: '执行中',
    approved: '已执行',
    dismissed: '已取消',
  }

  return (
    <section className={`tool-approval-card ${status}`}>
      <div>
        <span>{toolLabel(action.tool)}</span>
        <strong>{action.title}</strong>
        <p>{action.summary}</p>
      </div>
      <div className="tool-approval-actions">
        <small>{statusLabel[status]}</small>
        {visibleDetail ? (
          <button type="button" onClick={() => setDetailOpen(true)}>{detailLabel}</button>
        ) : null}
        {!done ? <button type="button" onClick={onDismiss} disabled={status === 'executing'}>取消</button> : null}
        {!done ? <button type="button" className="primary" onClick={onApprove} disabled={status === 'executing'}>{status === 'executing' ? '执行中' : '确认'}</button> : null}
      </div>
      {detailOpen && visibleDetail ? (
        <div className="tool-change-overlay" role="presentation" onClick={() => setDetailOpen(false)}>
          <section className="tool-change-dialog" role="dialog" aria-modal="true" aria-label={action.result ? '改动内容' : '待确认草案'} onClick={(event) => event.stopPropagation()}>
            <header>
              <span>{action.result ? '改动内容' : '待确认草案'}</span>
              <button type="button" onClick={() => setDetailOpen(false)} aria-label="关闭弹窗">×</button>
            </header>
            <strong>{visibleDetail.title}</strong>
            <p>{visibleDetail.summary}</p>
            {visibleDetail.items.length ? (
              <ul>
                {visibleDetail.items.map((item) => <li key={item}>{item}</li>)}
              </ul>
            ) : null}
            {visibleDetail.content ? <pre>{visibleDetail.content}</pre> : null}
          </section>
        </div>
      ) : null}
    </section>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  )
}

function Segmented({
  value,
  options,
  labels,
  onChange,
}: {
  value: string
  options: string[]
  labels?: Record<string, string>
  onChange: (value: string) => void
}) {
  return (
    <div className="segmented">
      {options.map((option) => (
        <button className={value === option ? 'selected' : ''} key={option} type="button" onClick={() => onChange(option)}>
          {labels?.[option] ?? option}
        </button>
      ))}
    </div>
  )
}

function LoadingScreen() {
  return (
    <section className="loading-layout">
      <div className="skeleton-panel" />
      <div className="skeleton-line" />
      <div className="skeleton-line short" />
    </section>
  )
}

function normalizeAgentActions(actions?: AgentToolProposal[]) {
  const allowed: AgentToolName[] = [
    'start_interview',
    'finish_latest_interview',
    'update_profile_fields',
    'update_resume',
    'append_profile_note',
    'add_knowledge_item',
    'update_knowledge_item',
    'delete_knowledge_item',
    'unsupported',
  ]
  return (actions ?? [])
    .filter((action) => action && allowed.includes(action.tool))
    .map((action, index) => ({
      ...action,
      id: `${Date.now()}-${index}-${action.id || action.tool}`,
      status: 'pending' as AgentActionStatus,
      payload: action.payload ?? {},
      approval_required: action.approval_required ?? true,
    }))
}

function buildPendingToolActionDetail(action: AgentToolProposal): ToolActionDetail | null {
  if (action.tool === 'unsupported' || action.tool === 'start_interview' || action.tool === 'finish_latest_interview') return null

  const payload = action.payload ?? {}
  const content = String(payload.preview ?? payload.content ?? '').trim()
  const diff = Array.isArray(payload.diff_summary)
    ? payload.diff_summary.map((item) => String(item)).filter(Boolean)
    : []
  const reason = String(payload.reason ?? '').trim()
  const items = diff.length ? diff : pendingActionItems(action)
  if (!content && !items.length && !reason) return null

  return {
    title: `${action.title}草案`,
    summary: reason || action.summary || '这是桃子本次已经生成好的可保存草案，确认后会直接写入，不再二次生成。',
    items,
    content: content ? excerpt(content, 1200) : '',
  }
}

function pendingActionItems(action: AgentToolProposal) {
  const payload = action.payload ?? {}
  if (action.tool === 'update_profile_fields') {
    return Object.keys(readPayloadFields(payload)).map((key) => `准备更新字段：${key}`)
  }
  if (action.tool === 'update_resume') {
    const mode = String(payload.mode || 'append') === 'replace' ? '替换完整简历' : '追加到完整简历'
    return [mode, `草案字数：${String(payload.content ?? '').trim().length}`]
  }
  if (action.tool === 'append_profile_note') {
    return [`写入分区：${String(payload.title || '个人档案')}`, `新增字数：${String(payload.content ?? '').trim().length}`]
  }
  if (action.tool === 'add_knowledge_item') {
    return [`新增资料：${String(payload.title || '求职资料')}`, `摘要：${String(payload.summary || '暂无摘要')}`]
  }
  if (action.tool === 'update_knowledge_item') {
    return ['更新知识库资料']
  }
  if (action.tool === 'delete_knowledge_item') {
    return [`删除资料 ID：${String(payload.id || '未提供')}`]
  }
  return []
}

function buildToolActionDetail(
  action: AgentToolProposal,
  data: {
    message?: string
    profile?: Profile
    interview?: { id?: string; interview_type: string; interviewer_style: string; company: string; role: string; status: string; report?: InterviewReport }
    opening?: { opening?: string; question?: string }
    report?: InterviewReport
    knowledge?: KnowledgeItem
    deleted_knowledge_id?: string
  },
  beforeProfile: Profile,
  beforeKnowledgeItems: KnowledgeItem[],
): ToolActionDetail {
  const contentFromPayload = String(action.payload.content ?? '').trim()
  const generic: ToolActionDetail = {
    title: data.message || action.title || '动作已完成',
    summary: action.summary || '桃子已经执行了这个动作。',
    items: [],
  }

  if (action.tool === 'start_interview') {
    return {
      title: '已创建模拟面试',
      summary: '桃子已经进入面试模式，并生成了开场和第一题。',
      items: [
        `类型：${data.interview?.interview_type || action.payload.interview_type || '模拟面试'}`,
        `岗位：${data.interview?.role || action.payload.role || beforeProfile.target_role || '未填写'}`,
        `公司：${data.interview?.company || action.payload.company || beforeProfile.target_company || '未填写'}`,
        `面试官风格：${data.interview?.interviewer_style || action.payload.interviewer_style || '温和型'}`,
      ],
      content: [data.opening?.opening, data.opening?.question].filter(Boolean).join('\n\n'),
    }
  }

  if (action.tool === 'finish_latest_interview') {
    return {
      title: '已结束面试',
      summary: '当前面试已收尾，并生成了复盘报告。',
      items: [
        `面试 ID：${data.interview?.id || action.payload.interview_id || '最近一场面试'}`,
        data.report?.overall_score ? `综合分：${data.report.overall_score}` : '综合分：暂无',
      ],
      content: data.report?.summary || data.interview?.report?.summary || '',
    }
  }

  if (action.tool === 'update_profile_fields') {
    const fields = readPayloadFields(action.payload)
    const labels: Record<string, string> = {
      name: '姓名',
      target_role: '目标岗位',
      target_company: '目标公司',
      target_city: '目标城市',
      stage: '求职阶段',
      communication_style: '沟通风格',
    }
    return {
      title: '已修改个人档案',
      summary: '以下基础字段已写入当前账号的个人档案。',
      items: Object.entries(fields)
        .filter(([key]) => key in labels)
        .map(([key, value]) => `${labels[key]}：${displayValue(beforeProfile[key as keyof Profile])} → ${displayValue(value)}`),
    }
  }

  if (action.tool === 'update_resume') {
    const mode = String(action.payload.mode || 'append')
    return {
      title: mode === 'replace' ? '已替换完整简历' : '已追加到完整简历',
      summary: mode === 'replace' ? '完整简历内容已被新版本替换。' : '新内容已追加到完整简历末尾。',
      items: [
        `写入方式：${mode === 'replace' ? '替换原文' : '追加内容'}`,
        `写入字数：${contentFromPayload.length}`,
      ],
      content: excerpt(contentFromPayload, 1200),
    }
  }

  if (action.tool === 'append_profile_note') {
    const title = String(action.payload.title || profileSectionMeta[toProfileSectionId(action.payload.section)].title || '个人档案')
    return {
      title: `已新增${title}`,
      summary: '这段内容已写入个人档案，并会参与后续简历、面试和问答。',
      items: [`新增位置：${title}`, `新增字数：${contentFromPayload.length}`],
      content: excerpt(contentFromPayload, 1200),
    }
  }

  if (action.tool === 'add_knowledge_item') {
    const item = data.knowledge
    return {
      title: '已新增知识库资料',
      summary: '资料已加入个人知识库的默认文件夹。',
      items: [
        `标题：${item?.title || action.payload.title || '求职资料'}`,
        `摘要：${item?.summary || action.payload.summary || '暂无摘要'}`,
      ],
      content: excerpt(item?.content || contentFromPayload, 1200),
    }
  }

  if (action.tool === 'update_knowledge_item') {
    const beforeItem = beforeKnowledgeItems.find((item) => item.id === String(action.payload.id))
    const afterItem = data.knowledge
    const changedKeys = ['title', 'summary', 'content', 'url'].filter((key) => key in action.payload)
    const labels: Record<string, string> = { title: '标题', summary: '摘要', content: '正文', url: '来源链接' }
    return {
      title: '已修改知识库资料',
      summary: `资料「${afterItem?.title || beforeItem?.title || '未命名资料'}」已更新。`,
      items: changedKeys.map((key) => `${labels[key]}：${displayValue(beforeItem?.[key as keyof KnowledgeItem])} → ${displayValue(action.payload[key])}`),
      content: 'content' in action.payload ? excerpt(String(action.payload.content || ''), 1200) : '',
    }
  }

  if (action.tool === 'delete_knowledge_item') {
    const deletedId = String(data.deleted_knowledge_id || action.payload.id || '')
    const deletedItem = beforeKnowledgeItems.find((item) => item.id === deletedId)
    return {
      title: '已删除知识库资料',
      summary: '这条资料已从个人知识库移除。',
      items: [
        `标题：${deletedItem?.title || '未找到标题'}`,
        `资料 ID：${deletedId || '未提供'}`,
      ],
      content: excerpt(deletedItem?.summary || deletedItem?.content || '', 800),
    }
  }

  return generic
}

function readPayloadFields(payload: Record<string, unknown>) {
  const fields = payload.fields
  return fields && typeof fields === 'object' && !Array.isArray(fields) ? fields as Record<string, unknown> : payload
}

function displayValue(value: unknown) {
  const text = String(value ?? '').trim()
  return text ? excerpt(text, 80) : '空'
}

function excerpt(value: string, maxLength: number) {
  const text = cleanAssistantText(value || '').trim()
  return text.length > maxLength ? `${text.slice(0, maxLength)}...` : text
}

function syncProfileSectionsFromAction(
  current: Record<ProfileSectionId, string>,
  action: AgentToolProposal,
  profile: Profile,
) {
  if (action.tool === 'append_profile_note') {
    const section = toProfileSectionId(action.payload.section)
    const content = String(action.payload.content ?? '').trim()
    if (!content) return current
    return {
      ...current,
      [section]: [current[section], content].filter(Boolean).join('\n\n'),
      full: profile.resume_text || current.full,
    }
  }
  if (action.tool === 'update_resume') {
    return { ...current, full: profile.resume_text || current.full }
  }
  return { ...current, full: profile.resume_text || current.full }
}

function toProfileSectionId(value: unknown): ProfileSectionId {
  const candidate = String(value || '')
  if (candidate in profileSectionMeta) return candidate as ProfileSectionId
  return 'full'
}

function flattenResumeFolders(folders: ResumeFolder[]) {
  return folders.flatMap((folder) => {
    const self = folder.sectionId ? [{ id: folder.sectionId, title: folder.title, summary: folder.summary }] : []
    return [...self, ...(folder.children ?? [])]
  })
}

function toolLabel(tool: AgentToolName) {
  const labels: Record<AgentToolName, string> = {
    start_interview: '面试',
    finish_latest_interview: '报告',
    update_profile_fields: '档案',
    update_resume: '简历',
    append_profile_note: '档案',
    add_knowledge_item: '知识库',
    update_knowledge_item: '知识库',
    delete_knowledge_item: '知识库',
    unsupported: '动作',
  }
  return labels[tool]
}

function toKnowledgeDraft(item: KnowledgeItem): KnowledgeDraft {
  return {
    title: item.title,
    summary: item.summary,
    content: item.content || item.summary,
    url: item.url || '',
  }
}

function uniqueKnowledgeItems(items: KnowledgeItem[]) {
  const seen = new Set<string>()
  return items.filter((item) => {
    if (seen.has(item.id)) return false
    seen.add(item.id)
    return true
  })
}

function groupKnowledgeFolders(folders: KnowledgeFolder[]): Record<Exclude<KnowledgeTab, 'discover'>, KnowledgeFolder[]> {
  const grouped: Record<Exclude<KnowledgeTab, 'discover'>, KnowledgeFolder[]> = {
    personal: [],
    saved: [],
  }
  folders.forEach((folder) => {
    const scope = folder.scope === 'saved' ? 'saved' : 'personal'
    grouped[scope].push({ ...folder, scope })
  })
  if (!grouped.personal.length) grouped.personal.push({ id: 'personal-default', name: '默认文件夹', scope: 'personal', item_ids: [] })
  if (!grouped.saved.length) grouped.saved.push({ id: 'saved-default', name: '默认收藏', scope: 'saved', item_ids: [] })
  return grouped
}

function sortFolders(folders: KnowledgeFolder[], mode: SortMode) {
  return [...folders].sort((a, b) => (mode === 'name' ? a.name.localeCompare(b.name, 'zh-CN') : compareUpdatedAt(b, a)))
}

function sortKnowledgeItems(items: KnowledgeItem[], mode: SortMode) {
  return [...items].sort((a, b) => (mode === 'name' ? a.title.localeCompare(b.title, 'zh-CN') : b.id.localeCompare(a.id)))
}

function compareUpdatedAt(a: KnowledgeFolder, b: KnowledgeFolder) {
  const left = Date.parse(a.updated_at || a.created_at || '')
  const right = Date.parse(b.updated_at || b.created_at || '')
  if (Number.isNaN(left) && Number.isNaN(right)) return a.id.localeCompare(b.id)
  if (Number.isNaN(left)) return -1
  if (Number.isNaN(right)) return 1
  return left - right
}

function knowledgeMetaLine(item: KnowledgeItem, index: number) {
  const subscribers = ['2.1万人已订阅', '538人已订阅', '1.2万人已订阅', '7989人已订阅', '6907人已订阅']
  const contents = ['100万+个内容', '729个内容', '164个内容', '4868个内容', '1077个内容']
  return `${subscribers[index % subscribers.length]} | ${contents[index % contents.length]} | @${item.source === 'discover' ? '桃子精选' : '个人资料'}`
}

function discoverKnowledgeFeed(): KnowledgeItem[] {
  return [
    { id: 'feed-ai-pm', title: 'AI 产品经理求职资料库', summary: '覆盖 AI 产品方法论、岗位 JD 拆解、案例题和面试追问。', source: 'discover' },
    { id: 'feed-autumn', title: '互联网秋招节奏库', summary: '按时间线整理提前批、正式批、补录和实习转正准备重点。', source: 'discover' },
    { id: 'feed-resume', title: '产品简历表达库', summary: '收集项目经历、实习经历、量化表达和 STAR 改写样例。', source: 'discover' },
    { id: 'feed-case', title: '商业分析与策略题库', summary: '沉淀市场规模、增长策略、竞品分析和业务拆解题。', source: 'discover' },
    { id: 'feed-boss', title: '大厂面试官追问库', summary: '整理常见深挖方式，帮助候选人准备证据和反问。', source: 'discover' },
    { id: 'feed-tools', title: '求职工具与术语库', summary: '解释 auto-rubric、JD fit、行为面、case interview 等概念。', source: 'discover' },
  ]
}

function summarizeClientText(value: string, limit = 160) {
  const clean = value.replace(/\s+/g, ' ').trim()
  if (!clean) return ''
  return clean.slice(0, limit) + (clean.length > limit ? '...' : '')
}

function isInterviewFinishIntent(value: string) {
  const clean = value.replace(/\s+/g, '')
  if (clean.length > 24) return false
  return ['结束面试', '停止面试', '结束并生成报告', '生成报告', '面试报告'].some((word) => clean.includes(word))
}

function formatInterviewReportMessage(report?: InterviewReport) {
  if (!report) return '这场面试已结束。报告生成完成，可以在个人档案和成长记录里继续复盘。'
  const parts = [
    '这场面试已结束，报告已归档到个人档案的「面试复盘」。',
    report.overall_score ? `综合评价：${report.overall_score} 分，等级 ${report.level || scoreLevel(report.overall_score)}，超过 ${report.percentile ?? scorePercentile(report.overall_score)}% 同类求职者。` : '',
    report.summary || '',
    report.key_improvements?.length ? `优先改进：${report.key_improvements.slice(0, 3).join('；')}` : '',
    report.next_plan?.length ? `下一步：${report.next_plan.slice(0, 3).join('；')}` : '',
  ].filter(Boolean)
  return parts.join('\n\n')
}

function normalizeInterviewReport(report: InterviewReport | undefined, interview: Dashboard['recent_interviews'][number], profile: Profile): Required<InterviewReport> {
  const score = report?.overall_score ?? 78
  return {
    position: report?.position || `${interview.company || profile.target_company || '目标公司'} ${interview.role || profile.target_role}`,
    overall_score: score,
    level: report?.level || scoreLevel(score),
    percentile: report?.percentile ?? scorePercentile(score),
    dimensions: normalizeDimensions(report?.dimensions),
    summary: report?.summary || '这份报告暂时只有基础信息，可以继续补充转文字或重新生成复盘。',
    key_improvements: report?.key_improvements?.length ? report.key_improvements : ['每题先给结论，再展开证据。', '补充可量化结果和个人贡献边界。', '压力追问时先澄清事实，再回应质疑。'],
    next_plan: report?.next_plan?.length ? report.next_plan : ['复练自我介绍', '准备 2 个 STAR 故事', '做一次压力追问'],
    question_review: report?.question_review?.length ? report.question_review : [{
      question: '请做一个 1 分钟自我介绍。',
      assessment_focus: '背景概括、岗位匹配和开场稳定性。',
      candidate_transcript: interview.transcript.find((item) => item.role === 'candidate')?.content || '暂无候选人回答转文字。',
      sample_answer: '建议用“我是谁 + 相关经历 + 结果证据 + 为什么匹配岗位”四段式回答。',
    }],
  }
}

function normalizeDimensions(dimensions?: Array<{ name: string; score: number }>) {
  const defaults = [
    { name: '语言流畅度', score: 78 },
    { name: '语言精简度', score: 72 },
    { name: '自信度', score: 76 },
    { name: '岗位核心能力', score: 80 },
  ]
  const incoming = dimensions?.length ? dimensions : defaults
  const required = ['语言流畅度', '语言精简度', '自信度', '岗位核心能力']
  return required.map((name, index) => incoming.find((item) => item.name === name) ?? incoming[index] ?? defaults[index])
}

function scoreLevel(score: number) {
  if (score >= 90) return 'A'
  if (score >= 82) return 'A-'
  if (score >= 75) return 'B+'
  if (score >= 65) return 'B'
  return 'C'
}

function scorePercentile(score: number) {
  return Math.max(35, Math.min(95, Math.round(score * 0.86)))
}

function formatInterviewReportTitle(interview: Dashboard['recent_interviews'][number], profile: Profile) {
  const date = interview.created_at ? new Date(interview.created_at).toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' }).replace('/', '') : '今日'
  return `${date}${interview.company || profile.target_company || '目标公司'}${interview.role || profile.target_role}`
}

function buildInterviewHistorySummary(interviews: Dashboard['recent_interviews'], profile: Profile) {
  const completed = interviews.filter((item) => item.status === 'completed' || item.report?.summary)
  if (!completed.length) return `还没有面试报告。完成一次${profile.target_role}模拟面试后，报告会自动归档到这里。`
  const avg = Math.round(completed.reduce((sum, item) => sum + (item.report?.overall_score || 0), 0) / completed.length)
  const latest = completed[0]
  return `已归档 ${completed.length} 份面试报告，平均得分 ${avg || '暂无'}。最近一次是 ${formatInterviewReportTitle(latest, profile)}：${latest.report?.summary || '暂无摘要'}`
}

function downloadInterviewReport(interview: Dashboard['recent_interviews'][number], profile: Profile) {
  const report = normalizeInterviewReport(interview.report, interview, profile)
  const html = `
    <html><head><title>${report.position} 面试复盘报告</title><style>
      body{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif;padding:32px;color:#292126;line-height:1.7}
      h1{font-size:28px}.score{display:flex;gap:16px;margin:18px 0}.score div{border:1px solid #f0dfd8;border-radius:14px;padding:12px 18px}
      li{margin:6px 0}.dim{margin:8px 0}.bar{height:10px;background:#ffe2ee;border-radius:999px}.bar i{display:block;height:10px;background:#df4f83;border-radius:999px}
      section{break-inside:avoid;margin-top:22px}
    </style></head><body>
      <h1>${report.position} 面试复盘报告</h1>
      <div class="score"><div>得分 ${report.overall_score}</div><div>等级 ${report.level}</div><div>超过 ${report.percentile}% 同类求职者</div></div>
      <p>${report.summary}</p>
      <section><h2>多维评价</h2>${report.dimensions.map((item) => `<div class="dim">${item.name} ${item.score}<div class="bar"><i style="width:${item.score}%"></i></div></div>`).join('')}</section>
      <section><h2>评价建议</h2><ul>${report.key_improvements.map((item) => `<li>${item}</li>`).join('')}</ul></section>
      <section><h2>问题回顾</h2>${report.question_review.map((item) => `<h3>${item.question}</h3><p><b>考察点：</b>${item.assessment_focus}</p><p><b>回答转文字：</b>${item.candidate_transcript}</p><p><b>示例回答：</b>${item.sample_answer}</p>`).join('')}</section>
      <script>window.print()</script>
    </body></html>`
  const printWindow = window.open('', '_blank', 'width=860,height=960')
  if (!printWindow) return
  printWindow.document.write(html)
  printWindow.document.close()
}

async function responseErrorMessage(response: Response) {
  const text = await response.text()
  try {
    const data = JSON.parse(text) as { detail?: unknown }
    if (typeof data.detail === 'string') return data.detail
    if (Array.isArray(data.detail)) return data.detail.map((item) => item?.msg || JSON.stringify(item)).join('；')
  } catch {
    if (response.status >= 500) return `后端内部错误 ${response.status}`
    return text || response.statusText
  }
  if (response.status >= 500) return `后端内部错误 ${response.status}`
  return text || response.statusText
}

async function fetchJsonWithRetry<T>(url: string, options: RequestInit, retries = 1): Promise<T> {
  try {
    const response = await fetch(url, options)
    if (!response.ok) throw new Error(await responseErrorMessage(response))
    return response.json() as Promise<T>
  } catch (err) {
    if (retries > 0 && isNetworkFetchError(err)) {
      await wait(450)
      return fetchJsonWithRetry<T>(url, options, retries - 1)
    }
    if (isNetworkFetchError(err)) {
      throw new Error(`Failed to fetch ${url}`)
    }
    throw err
  }
}

function isNetworkFetchError(err: unknown) {
  return err instanceof TypeError && /fetch/i.test(err.message)
}

function wait(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

function fileUploadErrorMessage(err: unknown) {
  const detail = err instanceof Error ? err.message : ''
  if (!detail) return '文件上传失败，请确认格式是 pdf、doc、docx、markdown 或 html。'
  if (detail.includes('unsupported file type')) return '文件格式暂不支持，请上传 pdf、doc、docx、markdown 或 html。'
  if (detail.includes('file is too large')) return '文件太大了，当前单个文件最多支持 12MB。'
  if (detail.includes('file parse failed')) return `文件解析失败：${detail.replace('file parse failed: ', '')}`
  return `文件上传失败：${detail}`
}

function buildRecommendations(profile: Profile, dashboard: Dashboard | null) {
  const company = profile.target_company || '字节跳动'
  const role = profile.target_role || '产品经理'
  const weakPoint = dashboard?.growth.weak_points?.[0] ?? profile.weak_points?.[0] ?? '简历深挖题'
  return [
    `再练练${weakPoint}`,
    `${role}方法论是什么`,
    `我这个 bg 什么时候投秋招最好`,
    `模拟面试${company} AIGC 策略产品经理岗位`,
  ]
}

function parseRecommendationReply(value: string) {
  return cleanAssistantText(value)
    .split('\n')
    .map((line) => line.replace(/^\s*(\d+[.)、]|•|-)\s*/, '').trim())
    .map(cleanRecommendationText)
    .filter(Boolean)
    .slice(0, 4)
}

function cleanRecommendationText(value: string) {
  const cleaned = value
    .replace(/^["“”'「」]+|["“”'「」]+$/g, '')
    .replace(/^我在[。,.，\s]*/g, '')
    .replace(/\s+/g, ' ')
    .trim()
  if (!cleaned) return ''
  if (cleaned.length > 28) return ''
  if (/[。！？!?]/.test(cleaned.slice(0, -1))) return ''
  return cleaned
}

function safeRecommendations(source: string[], fallback: string[]) {
  const cleaned = uniqueStrings(source.map(cleanRecommendationText).filter(Boolean))
  if (cleaned.length >= 3) return cleaned.slice(0, 4)
  return uniqueStrings([...cleaned, ...fallback.map(cleanRecommendationText).filter(Boolean)]).slice(0, 4)
}

function uniqueStrings(values: string[]) {
  return Array.from(new Set(values.map((value) => value.trim()).filter(Boolean)))
}

function buildInitialProfileSections(profile: Profile, dashboard: Dashboard | null): Record<ProfileSectionId, string> {
  const reviewSummary = dashboard?.recent_practices
    .filter((item) => item.tags.includes('面试复盘'))
    .map((item) => item.feedback?.archive || item.feedback?.summary || item.answer)
    .filter(Boolean)
    .join('\n\n')
  const interviewSummary = dashboard?.recent_interviews
    .map((item) => `${item.company || profile.target_company || '目标公司'} ${item.role || profile.target_role}：${item.report?.summary || '暂无报告'}`)
    .join('\n')

  return {
    ...initialProfileSections,
    reviews: [reviewSummary, interviewSummary].filter(Boolean).join('\n\n'),
    full: profile.resume_text || '',
  }
}

function composeProfileResumeText(sections: Record<ProfileSectionId, string>) {
  const ordered: ProfileSectionId[] = ['full', 'internship', 'project', 'education', 'skills', 'competition', 'reviews']
  return ordered
    .map((id) => {
      const content = sections[id].trim()
      if (!content) return ''
      return `【${profileSectionMeta[id].title}】\n${content}`
    })
    .filter(Boolean)
    .join('\n\n')
}

function summarizeSection(id: ProfileSectionId, content: string) {
  const clean = content.replace(/\s+/g, ' ').trim()
  if (!clean) return profileSectionMeta[id].summary
  return clean.length > 82 ? `${clean.slice(0, 82)}...` : clean
}

function buildResumeFolders(profile: Profile, dashboard: Dashboard | null, sections: Record<ProfileSectionId, string>): ResumeFolder[] {
  const reviewSummary = dashboard?.recent_practices.find((item) => item.tags.includes('面试复盘'))?.feedback?.archive
  return [
    {
      id: 'reviews',
      title: '面试复盘',
      sectionId: 'reviews',
      summary: summarizeSection('reviews', sections.reviews || reviewSummary || ''),
    },
    {
      id: 'resume',
      title: '个人简历',
      summary: profile.resume_text ? profile.resume_text.slice(0, 72) : '还没有完整简历内容，可以先补充经历摘要。',
      children: [
        { id: 'full', title: '完整简历', summary: summarizeSection('full', sections.full || profile.resume_text || '') },
        { id: 'internship', title: '实习经历', summary: summarizeSection('internship', sections.internship) },
        { id: 'project', title: '项目经历', summary: summarizeSection('project', sections.project) },
        { id: 'education', title: '教育背景', summary: summarizeSection('education', sections.education) },
        { id: 'skills', title: '个人技能', summary: summarizeSection('skills', sections.skills) },
        { id: 'competition', title: '竞赛经历', summary: summarizeSection('competition', sections.competition) },
      ],
    },
  ]
}

function buildKnowledgeItems(profile: Profile): KnowledgeItem[] {
  return [
    {
      id: 'personal-resume',
      title: `${profile.target_role}简历要点`,
      summary: '从个人档案中沉淀出的简历表达、项目证据和面试追问材料。',
      source: 'personal',
    },
  ]
}

function sortResumeFiles(files: ParsedUpload[], mode: 'time' | 'role') {
  const values = [...files]
  if (mode === 'role') return values.sort((a, b) => a.title.localeCompare(b.title, 'zh-CN'))
  return values
}

function extractExperienceNames(content: string) {
  return content
    .split('\n')
    .map((line) => line.replace(/^#+\s*/, '').replace(/^【|】$/g, '').trim())
    .filter((line) => line && line.length <= 36)
    .filter((line) => /(实习|项目|产品|平台|系统|增长|策略|运营|分析|大模型|AI|AIGC)/i.test(line))
    .slice(0, 8)
}

function personalGreeting(profile: Profile) {
  if (!profile.name || profile.name === '同学') return '你好，我是桃子'
  return `${profile.name}，我是桃子`
}

function moduleNotice(module: PrimaryModule) {
  if (module === 'peach') return '已进入桃子。'
  if (module === 'profile') return '已进入个人档案。'
  return '已进入求职知识库。'
}

function workspaceKicker(module: PrimaryModule, panel: PeachPanel) {
  if (module === 'profile') return '个人档案'
  if (module === 'knowledge') return '求职知识库'
  if (panel === 'interview-setup') return '模拟面试'
  if (panel === 'question-bank-setup') return '面试题库练习'
  if (panel === 'live-interview') return '实时对话'
  return '桃子'
}

function workspaceTitle(module: PrimaryModule, panel: PeachPanel) {
  if (module === 'profile') return '简历、经历和复盘都在这里'
  if (module === 'knowledge') return '管理你的求职资料和收藏'
  if (panel === 'interview-setup') return '配置一场真实感面试'
  if (panel === 'question-bank-setup') return '按题库连续练习'
  if (panel === 'live-interview') return '面试正在进行'
  return '你好，我是桃子'
}

function ttsRateValue(mode: TtsRateMode) {
  if (mode === 'slow') return 0.92
  if (mode === 'fast') return 1.32
  return 1.12
}

function ttsRateIndex(mode: TtsRateMode) {
  if (mode === 'slow') return 0
  if (mode === 'fast') return 2
  return 1
}

function ttsRateFromIndex(index: number): TtsRateMode {
  if (index <= 0) return 'slow'
  if (index >= 2) return 'fast'
  return 'medium'
}

function ttsRateLabel(mode: TtsRateMode) {
  if (mode === 'slow') return '慢'
  if (mode === 'fast') return '快'
  return '中'
}

function normalizeVoiceAnswer(value: string) {
  const text = value
    .replace(/\s+/g, ' ')
    .replace(/([，。！？、,.!?])\1+/g, '$1')
    .trim()
  if (!text) return ''
  const chunks = text.split(' ')
  if (chunks.length >= 2 && chunks[chunks.length - 1] === chunks[chunks.length - 2]) {
    return chunks.slice(0, -1).join(' ')
  }
  return text
}

function formatTime(value: number) {
  const minutes = Math.floor(value / 60).toString().padStart(2, '0')
  const seconds = (value % 60).toString().padStart(2, '0')
  return `${minutes}:${seconds}`
}

function cleanAssistantText(value: string) {
  return value
    .replace(/[\u2014\u2013]/g, '，')
    .replace(/```[\s\S]*?```/g, (block) => block.replace(/```/g, ''))
    .replace(/\*\*(.*?)\*\*/g, '$1')
    .replace(/__(.*?)__/g, '$1')
    .replace(/^\s{0,3}#{1,6}\s+/gm, '')
    .replace(/^\s*[-*]\s+/gm, '• ')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

export default App
