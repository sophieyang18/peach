import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import './App.css'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'

type PrimaryModule = 'peach' | 'profile' | 'knowledge'
type PeachPanel = 'new-chat' | 'interview-setup' | 'question-bank-setup' | 'live-interview'
type InterviewMode = 'voice' | 'video'
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
type AgentToolProposal = {
  id: string
  tool: AgentToolName
  title: string
  summary: string
  payload: Record<string, unknown>
  approval_required: boolean
  status?: AgentActionStatus
}
type ChatMessage = { role: 'peach' | 'user' | 'system'; content: string; actions?: AgentToolProposal[] }
type Conversation = { id: string; title: string; updatedAt: string; messages: ChatMessage[] }
type BusyKey = 'refresh' | 'recommend' | 'chat' | 'interviewStart' | 'profile' | 'knowledge' | 'upload'

type Profile = {
  id: string
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
    report: { summary?: string; overall_score?: number }
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
type KnowledgeFolder = { id: string; name: string; scope: Exclude<KnowledgeTab, 'discover'>; collapsed?: boolean }
type SortMode = 'updated' | 'name'

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

const defaultMessages: ChatMessage[] = [
  { role: 'peach', content: '你好，我是桃子' },
]

const fixedBubbles = ['帮我模拟面试', '帮我写简历', '帮我改简历', '我能投哪些岗位']
const composerActions = ['模拟面试', '题库练习', '简历优化', '简历撰写', '投递动态']
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
    messages: defaultMessages,
  },
  {
    id: 'chat-resume',
    title: '简历深挖准备',
    updatedAt: '昨天',
    messages: [
      { role: 'peach', content: '我们上次聊到项目经历还缺少量化结果，可以继续把那段经历打磨成面试答案。' },
    ],
  },
  {
    id: 'chat-autumn',
    title: '秋招节奏规划',
    updatedAt: '3 天前',
    messages: [
      { role: 'peach', content: '你适合先投产品实习和 AIGC 策略方向，节奏上要提前准备简历深挖题。' },
    ],
  },
]

function App() {
  const [module, setModule] = useState<PrimaryModule>('peach')
  const [peachPanel, setPeachPanel] = useState<PeachPanel>('new-chat')
  const [dashboard, setDashboard] = useState<Dashboard | null>(null)
  const [busy, setBusy] = useState<Partial<Record<BusyKey, string>>>({ refresh: '正在同步个人档案' })
  const [notice, setNotice] = useState('准备好了就开始。')
  const [error, setError] = useState('')
  const [input, setInput] = useState('')
  const [profileInput, setProfileInput] = useState('')
  const [activeProfileSection, setActiveProfileSection] = useState<ProfileSectionId>('full')
  const [profileSections, setProfileSections] = useState<Record<ProfileSectionId, string>>(initialProfileSections)
  const [profileActionResult, setProfileActionResult] = useState('')
  const [resumeFiles, setResumeFiles] = useState<ParsedUpload[]>([])
  const [knowledgeQuestion, setKnowledgeQuestion] = useState('')
  const [knowledgeMessages, setKnowledgeMessages] = useState<ChatMessage[]>([])
  const [personalKnowledge, setPersonalKnowledge] = useState<KnowledgeItem[]>([])
  const [activeKnowledgeId, setActiveKnowledgeId] = useState('')
  const [knowledgeQuery, setKnowledgeQuery] = useState('')
  const [knowledgeDraft, setKnowledgeDraft] = useState<KnowledgeDraft>({
    title: '',
    summary: '',
    content: '',
    url: '',
  })
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
  const [subNavCollapsed, setSubNavCollapsed] = useState(false)
  const [knowledgeTab, setKnowledgeTab] = useState<KnowledgeTab>('personal')
  const [knowledgeFolderSort, setKnowledgeFolderSort] = useState<SortMode>('updated')
  const [knowledgeFileSort, setKnowledgeFileSort] = useState<SortMode>('updated')
  const [knowledgeFolders, setKnowledgeFolders] = useState<Record<Exclude<KnowledgeTab, 'discover'>, KnowledgeFolder[]>>({
    personal: [{ id: 'personal-default', name: '默认文件夹', scope: 'personal' }],
    saved: [{ id: 'saved-default', name: '默认收藏', scope: 'saved' }],
  })
  const [activeKnowledgeFolderId, setActiveKnowledgeFolderId] = useState('personal-default')
  const [savedKnowledge, setSavedKnowledge] = useState<string[]>(['pm-method'])

  const chatScrollRef = useRef<HTMLElement | null>(null)
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const recommendationsHydratedRef = useRef(false)
  const profileHydratedRef = useRef(false)
  const knowledgeHydratedRef = useRef(false)

  const profile = dashboard?.profile ?? defaultProfile
  const activeConversation = conversations.find((item) => item.id === activeConversationId) ?? conversations[0]
  const busyText = Object.values(busy)[0]
  const fallbackRecommendations = useMemo(() => buildRecommendations(profile, dashboard), [profile, dashboard])
  const visibleRecommendations = recommendations.length ? recommendations : fallbackRecommendations
  const resumeFolders = useMemo(() => buildResumeFolders(profile, dashboard, profileSections), [profile, dashboard, profileSections])
  const knowledgeItems = useMemo(() => [...personalKnowledge, ...buildKnowledgeItems(profile), ...discoverKnowledgeFeed()], [personalKnowledge, profile])

  const api = useCallback(async <T,>(path: string, options?: RequestInit): Promise<T> => {
    setError('')
    const response = await fetch(`${API_BASE}${path}`, {
      headers: { 'Content-Type': 'application/json', ...(options?.headers ?? {}) },
      ...options,
    })
    if (!response.ok) throw new Error(await responseErrorMessage(response))
    return response.json()
  }, [])

  const uploadApi = useCallback(async <T,>(path: string, file: File): Promise<T> => {
    setError('')
    const body = new FormData()
    body.append('file', file)
    const response = await fetch(`${API_BASE}${path}`, { method: 'POST', body })
    if (!response.ok) throw new Error(await responseErrorMessage(response))
    return response.json()
  }, [])

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

  useEffect(() => {
    void refreshDashboard()
  }, [refreshDashboard])

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
        const data = await api<{ items: KnowledgeItem[] }>('/api/knowledge')
        setPersonalKnowledge(data.items)
      } catch (err) {
        console.error(err)
      }
    }

    void hydrateKnowledge()
  }, [api, dashboard])

  useEffect(() => {
    if (activeKnowledgeId || !knowledgeItems.length) return
    const first = knowledgeItems[0]
    setActiveKnowledgeId(first.id)
    setKnowledgeDraft(toKnowledgeDraft(first))
  }, [activeKnowledgeId, knowledgeItems])

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

  function markActionStatus(actionId: string, status: AgentActionStatus) {
    updateConversation(activeConversationId, (conversation) => ({
      ...conversation,
      messages: conversation.messages.map((message) => ({
        ...message,
        actions: message.actions?.map((action) => (action.id === actionId ? { ...action, status } : action)),
      })),
    }))
  }

  function openModule(nextModule: PrimaryModule) {
    setModule(nextModule)
    if (nextModule === 'peach') setPeachPanel('new-chat')
    if (nextModule === 'knowledge') {
      setKnowledgeTab('personal')
      setActiveKnowledgeFolderId('personal-default')
    }
    setSubNavCollapsed(false)
    setNotice(moduleNotice(nextModule))
  }

  function createConversation() {
    const id = `chat-${Date.now()}`
    setConversations((current) => [
      { id, title: '新建对话', updatedAt: '刚刚', messages: defaultMessages },
      ...current,
    ])
    setActiveConversationId(id)
    setPeachPanel('new-chat')
    setNotice('已新建对话。')
  }

  function openConversation(id: string) {
    setActiveConversationId(id)
    setPeachPanel('new-chat')
    setNotice('已切回历史对话。')
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
      const data = await api<{ reply: string; actions?: AgentToolProposal[] }>('/api/agent/actions', {
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
      setNotice('回复已生成。')
    } catch (err) {
      removeSystemMessage('桃子正在回复。')
      setInput(snapshot)
      setError('桃子刚刚掉线了一下，内容已经放回输入框。')
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
      setPeachPanel('live-interview')
      appendMessage({ role: 'system', content: '正在生成第一题。' })
    }
    begin('chat', `正在执行${action.title}`)
    try {
      const data = await api<{
        message?: string
        profile?: Profile
        interview?: { id: string; interview_type: string; interviewer_style: string; company: string; role: string; status: string; report?: { summary?: string } }
        opening?: { opening?: string; question?: string }
        progress?: InterviewProgress
        report?: { summary?: string; overall_score?: number }
        knowledge?: KnowledgeItem
        deleted_knowledge_id?: string
      }>('/api/agent/actions/execute', {
        method: 'POST',
        body: JSON.stringify({ tool: action.tool, payload: action.payload }),
      })

      markActionStatus(action.id, 'approved')
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
      interview?: { id?: string; interview_type: string; interviewer_style: string; company: string; role: string; status: string; report?: { summary?: string } }
      opening?: { opening?: string; question?: string }
      progress?: InterviewProgress
      report?: { summary?: string; overall_score?: number }
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
      setPeachPanel('live-interview')
      if (data.opening?.opening || data.opening?.question) {
        appendMessage({ role: 'peach', content: cleanAssistantText([data.opening.opening, data.opening.question].filter(Boolean).join('\n\n')) })
      }
    }
    if (action.tool === 'finish_latest_interview') {
      setActiveInterviewId('')
      setInterviewProgress(defaultInterviewProgress)
      setFinishSuggestionShown(false)
      setPeachPanel('new-chat')
      if (data.report?.summary) appendMessage({ role: 'peach', content: `这场面试我已经收尾了。${data.report.summary}` })
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
      投递动态: '帮我整理接下来一周的投递节奏和优先级。',
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
          interviewer_style: settings.style,
          company: profile.target_company,
          role: profile.target_role,
          jd: settings.jd,
          question_bank: kind === 'question-bank' ? settings.questionBank : '',
        }),
      })

      setActiveInterviewId(data.interview.id)
      setInterviewProgress(data.progress ?? defaultInterviewProgress)
      setPeachPanel('live-interview')
      appendMessage({ role: 'peach', content: cleanAssistantText(`${data.opening.opening}\n\n${data.opening.question}`) })

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
    const answer = input.trim()
    if (!answer || paused || busy.chat) return
    if (!activeInterviewId) {
      setError('当前没有连接到进行中的面试，请回到设置页重新开始。')
      return
    }
    if (isInterviewFinishIntent(answer)) {
      setInput('')
      appendMessage({ role: 'user', content: answer })
      await finishActiveInterview()
      return
    }
    const interviewId = activeInterviewId
    setInput('')
    appendMessage({ role: 'user', content: answer })
    appendMessage({ role: 'system', content: '面试官正在追问。' })
    begin('chat', '面试官正在追问')
    try {
      const data = await api<{
        interview: { id: string; status: string; report?: { summary?: string; overall_score?: number } }
        next: { micro_feedback?: string; next_question?: string; hint?: string; should_finish?: boolean }
        report?: { summary?: string; overall_score?: number; key_improvements?: string[]; next_plan?: string[] }
        progress?: InterviewProgress
      }>(`/api/interviews/${interviewId}/answer`, {
        method: 'POST',
        body: JSON.stringify({ answer }),
      })
      removeSystemMessage('面试官正在追问。')
      const reply = [
        data.next.micro_feedback,
        data.next.next_question,
        data.next.hint ? `提示：${data.next.hint}` : '',
      ].filter(Boolean).join('\n\n')
      appendMessage({ role: 'peach', content: cleanAssistantText(reply || '收到，我们继续下一题。') })
      const nextProgress = data.progress ?? interviewProgress
      setInterviewProgress(nextProgress)
      if (data.interview.status === 'completed') {
        setActiveInterviewId('')
        setInterviewProgress(defaultInterviewProgress)
        setFinishSuggestionShown(false)
        setPeachPanel('new-chat')
        appendMessage({ role: 'peach', content: formatInterviewReportMessage(data.report || data.interview.report) })
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
      setNotice('已退出面试。')
      return
    }
    begin('chat', '正在结束面试并生成报告')
    appendMessage({ role: 'system', content: '正在生成面试报告。' })
    try {
      const data = await api<{
        interview: { id: string; status: string; report?: { summary?: string; overall_score?: number } }
        report?: { summary?: string; overall_score?: number; key_improvements?: string[]; next_plan?: string[] }
      }>(`/api/interviews/${activeInterviewId}/finish`, { method: 'POST' })
      removeSystemMessage('正在生成面试报告。')
      setActiveInterviewId('')
      setPaused(false)
      setInterviewProgress(defaultInterviewProgress)
      setFinishSuggestionShown(false)
      setPeachPanel('new-chat')
      appendMessage({ role: 'peach', content: formatInterviewReportMessage(data.report || data.interview.report) })
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

  function saveKnowledge(id: string) {
    setSavedKnowledge((current) => (current.includes(id) ? current : [...current, id]))
  }

  function selectKnowledgeItem(item: KnowledgeItem) {
    setActiveKnowledgeId(item.id)
    setKnowledgeDraft(toKnowledgeDraft(item))
    setNotice(`正在查看${item.title}。`)
  }

  function createKnowledgeDraft() {
    setActiveKnowledgeId('')
    setKnowledgeDraft({ title: '', summary: '', content: '', url: '' })
    setKnowledgeTab('personal')
    setNotice('可以新增一条个人知识。')
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
        setNotice('知识库已保存。')
      } else {
        const data = await api<{ item: KnowledgeItem }>('/api/knowledge', {
          method: 'POST',
          body: JSON.stringify(payload),
        })
        setPersonalKnowledge((current) => [data.item, ...current])
        setActiveKnowledgeId(data.item.id)
        setKnowledgeDraft(toKnowledgeDraft(data.item))
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
      setNotice('知识库资料已删除。')
    } catch (err) {
      setError('知识库删除失败，稍后再试一次。')
      console.error(err)
    } finally {
      end('knowledge')
    }
  }

  function createKnowledgeFolder(scope: Exclude<KnowledgeTab, 'discover'>) {
    const name = window.prompt('文件夹名称', scope === 'personal' ? '求职资料' : '收藏资料')
    if (!name?.trim()) return
    const folder: KnowledgeFolder = { id: `${scope}-${Date.now()}`, name: name.trim(), scope }
    setKnowledgeFolders((current) => ({ ...current, [scope]: [...current[scope], folder] }))
    setActiveKnowledgeFolderId(folder.id)
    setKnowledgeTab(scope)
  }

  function renameKnowledgeFolder(scope: Exclude<KnowledgeTab, 'discover'>, folderId: string) {
    const folder = knowledgeFolders[scope].find((item) => item.id === folderId)
    const name = window.prompt('重命名文件夹', folder?.name ?? '')
    if (!name?.trim()) return
    setKnowledgeFolders((current) => ({
      ...current,
      [scope]: current[scope].map((item) => (item.id === folderId ? { ...item, name: name.trim() } : item)),
    }))
  }

  function deleteKnowledgeFolder(scope: Exclude<KnowledgeTab, 'discover'>, folderId: string) {
    setKnowledgeFolders((current) => {
      if (current[scope].length <= 1) return current
      const nextFolders = current[scope].filter((item) => item.id !== folderId)
      if (activeKnowledgeFolderId === folderId) setActiveKnowledgeFolderId(nextFolders[0]?.id ?? `${scope}-default`)
      return { ...current, [scope]: nextFolders }
    })
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
      const data = await api<{ item: KnowledgeItem }>('/api/knowledge', {
        method: 'POST',
        body: JSON.stringify({
          title: titleFromUrl(url.trim()),
          summary: `链接资料：${url.trim()}`,
          content: `链接：${url.trim()}\n\n可以在这里继续补充网页重点，桃子会在知识库问答里参考它。`,
          source: 'personal',
          url: url.trim(),
        }),
      })
      setPersonalKnowledge((current) => [data.item, ...current])
      setActiveKnowledgeId(data.item.id)
      setKnowledgeDraft(toKnowledgeDraft(data.item))
      setKnowledgeTab('personal')
      setNotice('链接已加入个人知识库。')
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
      const data = await uploadApi<{ item: KnowledgeItem; file: ParsedUpload }>('/api/knowledge/upload', file)
      setPersonalKnowledge((current) => [data.item, ...current])
      setActiveKnowledgeId(data.item.id)
      setKnowledgeDraft(toKnowledgeDraft(data.item))
      setKnowledgeTab('personal')
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

  function submitProfileNote() {
    if (!profileInput.trim()) return
    const nextSections = {
      ...profileSections,
      [activeProfileSection]: [profileSections[activeProfileSection], profileInput.trim()].filter(Boolean).join('\n\n'),
    }
    setProfileSections(nextSections)
    setNotice(`已补充到${profileSectionMeta[activeProfileSection].title}。`)
    setProfileInput('')
  }

  async function askKnowledgeQuestion() {
    const question = knowledgeQuestion.trim()
    if (!question || busy.chat) return
    const sourceItems = knowledgeItems
      .filter((item) => {
        if (knowledgeTab === 'personal') return item.source === 'personal'
        if (knowledgeTab === 'saved') return savedKnowledge.includes(item.id)
        return item.source === 'discover'
      })
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
  const appClass = `app-shell module-${module} ${hasSubNav ? 'has-sub-nav' : 'no-sub-nav'} ${subNavCollapsed ? 'subnav-collapsed' : ''}`

  return (
    <main className={appClass}>
      <aside className="main-nav" aria-label="主导航栏">
        <nav className="main-nav-list">
          <button className={module === 'peach' ? 'main-nav-item active' : 'main-nav-item'} type="button" onClick={() => openModule('peach')}>
            <span className="nav-icon">桃</span>
            <strong>桃子</strong>
          </button>
          <button className={module === 'profile' ? 'main-nav-item active' : 'main-nav-item'} type="button" onClick={() => openModule('profile')}>
            <span className="nav-icon">档</span>
            <strong>个人档案</strong>
          </button>
          <button className={module === 'knowledge' ? 'main-nav-item active' : 'main-nav-item'} type="button" onClick={() => openModule('knowledge')}>
            <span className="nav-icon">库</span>
            <strong>求职知识库</strong>
          </button>
        </nav>
      </aside>

      {module === 'peach' ? (
        <PeachSubNav
          activePanel={peachPanel}
          conversations={conversations}
          activeConversationId={activeConversationId}
          collapsed={subNavCollapsed}
          onNew={createConversation}
          onOpenHistory={openConversation}
          onToggle={() => setSubNavCollapsed((value) => !value)}
        />
      ) : null}

      {module === 'knowledge' ? (
        <KnowledgeSubNav
          collapsed={subNavCollapsed}
          tab={knowledgeTab}
          query={knowledgeQuery}
          items={knowledgeItems}
          savedIds={savedKnowledge}
          activeId={activeKnowledgeId}
          folders={knowledgeFolders}
          activeFolderId={activeKnowledgeFolderId}
          folderSort={knowledgeFolderSort}
          fileSort={knowledgeFileSort}
          onToggle={() => setSubNavCollapsed((value) => !value)}
          onTab={(tab) => {
            setKnowledgeTab(tab)
            if (tab === 'personal') setActiveKnowledgeFolderId(knowledgeFolders.personal[0]?.id ?? 'personal-default')
            if (tab === 'saved') setActiveKnowledgeFolderId(knowledgeFolders.saved[0]?.id ?? 'saved-default')
          }}
          onQuery={setKnowledgeQuery}
          onSelectFolder={setActiveKnowledgeFolderId}
          onFolderSort={setKnowledgeFolderSort}
          onFileSort={setKnowledgeFileSort}
          onCreateFolder={createKnowledgeFolder}
          onRenameFolder={renameKnowledgeFolder}
          onDeleteFolder={deleteKnowledgeFolder}
          onSelectItem={selectKnowledgeItem}
          onNewItem={createKnowledgeDraft}
          onRenameItem={(item) => void renameKnowledgeItem(item)}
          onDeleteItem={(id) => void deleteKnowledgeItem(id)}
          onParseLink={() => void parseKnowledgeLink()}
          onUpload={(file) => void uploadKnowledgeFile(file)}
        />
      ) : null}

      <section className="workspace" aria-label="工作区">
        {module === 'profile' || (module === 'peach' && peachPanel !== 'new-chat') ? (
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
            subtitleCollapsed={subtitleCollapsed}
            timerCollapsed={timerCollapsed}
            videoRef={videoRef}
            chatScrollRef={chatScrollRef}
            busy={busy}
            onInput={setInput}
            onSend={() => (peachPanel === 'live-interview' ? void sendInterviewAnswer() : void sendPrompt(input))}
            onQuickSend={(value) => void sendPrompt(value)}
            onAction={runComposerAction}
            onSettingsChange={setSettings}
            onStartInterview={() => void startLiveInterview('interview')}
            onStartQuestionBank={() => void startLiveInterview('question-bank')}
            onUploadInterviewFile={(file, target) => void uploadInterviewFile(file, target)}
            onUploadChatFile={(file) => void uploadChatFile(file)}
            onPauseToggle={() => setPaused((value) => !value)}
            onFinishInterview={() => void finishActiveInterview()}
            onSubtitleToggle={() => setSubtitleCollapsed((value) => !value)}
            onTimerToggle={() => setTimerCollapsed((value) => !value)}
            onBackToSetup={() => setPeachPanel(liveKind === 'question-bank' ? 'question-bank-setup' : 'interview-setup')}
            onApproveAction={(action) => void approveAgentAction(action)}
            onDismissAction={dismissAgentAction}
          />
        ) : null}

        {module === 'profile' ? (
          <ProfileWorkspace
            folders={resumeFolders}
            activeSection={activeProfileSection}
            sectionContent={profileSections[activeProfileSection]}
            sections={profileSections}
            actionResult={profileActionResult}
            resumeFiles={resumeFiles}
            isSaving={Boolean(busy.profile)}
            value={profileInput}
            onSelectSection={selectProfileSection}
            onSectionContent={(content) => updateProfileSection(activeProfileSection, content)}
            onValue={setProfileInput}
            onSubmit={submitProfileNote}
            onSave={() => void saveProfileSections()}
            onAction={(action) => void runProfileAction(action)}
            onAcceptResult={acceptProfileActionResult}
            onUploadFile={(file) => void uploadProfileFile(file)}
          />
        ) : null}

        {module === 'knowledge' ? (
          <KnowledgeWorkspace
            tab={knowledgeTab}
            question={knowledgeQuestion}
            messages={knowledgeMessages}
            items={knowledgeItems}
            savedIds={savedKnowledge}
            activeId={activeKnowledgeId}
            draft={knowledgeDraft}
            busy={Boolean(busy.knowledge || busy.upload)}
            onQuestion={setKnowledgeQuestion}
            onAskQuestion={() => void askKnowledgeQuestion()}
            onSave={saveKnowledge}
            onDraft={setKnowledgeDraft}
            onSaveDraft={() => void saveKnowledgeDraft()}
            onDelete={(id) => void deleteKnowledgeItem(id)}
            onUpload={(file) => void uploadKnowledgeFile(file)}
            onAsk={sendKnowledgeToPeach}
            onUseInProfile={addKnowledgeToProfile}
          />
        ) : null}
      </section>
    </main>
  )
}

function PeachSubNav({
  activePanel,
  conversations,
  activeConversationId,
  collapsed,
  onNew,
  onOpenHistory,
  onToggle,
}: {
  activePanel: PeachPanel
  conversations: Conversation[]
  activeConversationId: string
  collapsed: boolean
  onNew: () => void
  onOpenHistory: (id: string) => void
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
        <button className={activePanel === 'new-chat' ? 'sub-action active' : 'sub-action'} type="button" onClick={onNew}>
          新建对话
        </button>
      </div>
      <div className="history-section">
        <div className="section-label">历史对话</div>
        <div className="history-list">
          {conversations.map((conversation) => (
            <button
              className={conversation.id === activeConversationId ? 'history-item active' : 'history-item'}
              key={conversation.id}
              type="button"
              onClick={() => onOpenHistory(conversation.id)}
            >
              <strong>{conversation.title}</strong>
              <span>{conversation.updatedAt}</span>
            </button>
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
  items,
  savedIds,
  activeId,
  folders,
  activeFolderId,
  folderSort,
  fileSort,
  onToggle,
  onTab,
  onQuery,
  onSelectFolder,
  onFolderSort,
  onFileSort,
  onCreateFolder,
  onRenameFolder,
  onDeleteFolder,
  onSelectItem,
  onNewItem,
  onRenameItem,
  onDeleteItem,
  onParseLink,
  onUpload,
}: {
  collapsed: boolean
  tab: KnowledgeTab
  query: string
  items: KnowledgeItem[]
  savedIds: string[]
  activeId: string
  folders: Record<Exclude<KnowledgeTab, 'discover'>, KnowledgeFolder[]>
  activeFolderId: string
  folderSort: SortMode
  fileSort: SortMode
  onToggle: () => void
  onTab: (tab: KnowledgeTab) => void
  onQuery: (value: string) => void
  onSelectFolder: (id: string) => void
  onFolderSort: (mode: SortMode) => void
  onFileSort: (mode: SortMode) => void
  onCreateFolder: (scope: Exclude<KnowledgeTab, 'discover'>) => void
  onRenameFolder: (scope: Exclude<KnowledgeTab, 'discover'>, id: string) => void
  onDeleteFolder: (scope: Exclude<KnowledgeTab, 'discover'>, id: string) => void
  onSelectItem: (item: KnowledgeItem) => void
  onNewItem: () => void
  onRenameItem: (item: KnowledgeItem) => void
  onDeleteItem: (id: string) => void
  onParseLink: () => void
  onUpload: (file: File) => void
}) {
  const scope = tab === 'saved' ? 'saved' : 'personal'
  const scopedFolders = sortFolders(folders[scope], folderSort)
  const scopedItems = sortKnowledgeItems(items.filter((item) => {
    if (tab === 'personal') return item.source === 'personal'
    if (tab === 'saved') return savedIds.includes(item.id)
    return false
  }).filter((item) => {
    const keyword = query.trim().toLowerCase()
    if (!keyword) return true
    return [item.title, item.summary, item.content, item.url].some((part) => part?.toLowerCase().includes(keyword))
  }), fileSort)

  return (
    <aside className={collapsed ? 'sub-nav knowledge-sub-nav collapsed' : 'sub-nav knowledge-sub-nav'} aria-label="知识库副导航栏">
      <button className="sub-nav-toggle" type="button" onClick={onToggle} aria-label={collapsed ? '展开副导航' : '收起副导航'}>
        <span>{collapsed ? '›' : '‹'}</span>
      </button>
      {collapsed ? null : (
        <>
          <div className="knowledge-nav-tabs">
            {(['personal', 'saved', 'discover'] as KnowledgeTab[]).map((item) => (
              <button className={tab === item ? 'active' : ''} key={item} type="button" onClick={() => onTab(item)}>
                {knowledgeTabLabel(item)}
              </button>
            ))}
          </div>

          {tab === 'discover' ? (
            <div className="knowledge-side-note">
              <strong>发现知识库</strong>
              <p>浏览精选和推荐内容，收藏后会进入收藏知识库。</p>
            </div>
          ) : (
            <div className="knowledge-tree">
              <input value={query} onChange={(event) => onQuery(event.target.value)} placeholder="搜索知识库" />
              <div className="tree-toolbar">
                <button type="button" onClick={() => onCreateFolder(scope)}>新建文件夹</button>
                <select value={folderSort} onChange={(event) => onFolderSort(event.target.value as SortMode)}>
                  <option value="updated">最近更新</option>
                  <option value="name">名称排序</option>
                </select>
              </div>

              <div className="folder-list">
                {scopedFolders.map((folder) => (
                  <section className={folder.id === activeFolderId ? 'folder-block active' : 'folder-block'} key={folder.id}>
                    <button className="folder-title" type="button" onClick={() => onSelectFolder(folder.id)}>
                      <span>{folder.id === activeFolderId ? '⌄' : '›'}</span>
                      <strong>{folder.name}</strong>
                    </button>
                    <div className="folder-actions">
                      <button type="button" onClick={() => onRenameFolder(scope, folder.id)}>重命名</button>
                      <button type="button" onClick={() => onDeleteFolder(scope, folder.id)}>删除</button>
                    </div>
                    {folder.id === activeFolderId ? (
                      <div className="file-list">
                        <div className="tree-toolbar file-toolbar">
                          <button type="button" onClick={onNewItem}>新建</button>
                          <button type="button" onClick={onParseLink}>链接</button>
                          <label>
                            <input type="file" accept=".pdf,.doc,.docx,.md,.markdown,.html,.htm" onChange={(event) => event.target.files?.[0] && onUpload(event.target.files[0])} />
                            <span>上传</span>
                          </label>
                          <select value={fileSort} onChange={(event) => onFileSort(event.target.value as SortMode)}>
                            <option value="updated">最近</option>
                            <option value="name">名称</option>
                          </select>
                        </div>
                        {scopedItems.length ? scopedItems.map((item) => (
                          <div className={item.id === activeId ? 'file-row active' : 'file-row'} key={item.id}>
                            <button type="button" onClick={() => onSelectItem(item)}>
                              <span>{item.title}</span>
                            </button>
                            <div>
                              <button type="button" onClick={() => onRenameItem(item)}>改名</button>
                              {item.source === 'personal' ? <button type="button" onClick={() => onDeleteItem(item.id)}>删除</button> : null}
                            </div>
                          </div>
                        )) : <p className="tree-empty">这个文件夹还没有文件。</p>}
                      </div>
                    ) : null}
                  </section>
                ))}
              </div>
            </div>
          )}
        </>
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
  subtitleCollapsed: boolean
  timerCollapsed: boolean
  videoRef: React.RefObject<HTMLVideoElement | null>
  chatScrollRef: React.RefObject<HTMLElement | null>
  busy: Partial<Record<BusyKey, string>>
  onInput: (value: string) => void
  onSend: () => void
  onQuickSend: (value: string) => void
  onAction: (value: string) => void
  onSettingsChange: (value: InterviewSettings) => void
  onStartInterview: () => void
  onStartQuestionBank: () => void
  onUploadInterviewFile: (file: File, target: 'resume' | 'questionBank') => void
  onUploadChatFile: (file: File) => void
  onPauseToggle: () => void
  onFinishInterview: () => void
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

  const hasStartedChat = props.conversation.messages.some((message) => message.role === 'user')

  return (
    <div className={hasStartedChat ? 'chat-home chatting' : 'chat-home'}>
      {!hasStartedChat ? <section className="greeting-panel">
        <div className="greeting-copy">
          <h2>{personalGreeting(props.profile)}</h2>
          <p>我是专属于你的求职搭子</p>
        </div>
        <div className="bubble-group">
          <div className="bubble-grid fixed-bubbles">
            {[...fixedBubbles, ...props.recommendations].map((item) => (
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
        <Field label="面试官性别">
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
  subtitleCollapsed,
  timerCollapsed,
  videoRef,
  chatScrollRef,
  busy,
  onInput,
  onSend,
  onUploadChatFile,
  onPauseToggle,
  onFinishInterview,
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
            <div className="avatar-face">
              <span>桃</span>
            </div>
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
          placeholder={paused ? '面试暂停中，点击继续后再回答' : '输入你的回答，也可以后续接入语音转写'}
          actions={[paused ? '继续面试' : '暂停面试', '结束面试']}
          disabled={paused || Boolean(busy.chat)}
          button={busy.chat ? '发送中' : '语音输入'}
          buttonKind="voice"
          onChange={onInput}
          onSubmit={onSend}
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
  folders,
  activeSection,
  sectionContent,
  sections,
  actionResult,
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
}: {
  folders: ResumeFolder[]
  activeSection: ProfileSectionId
  sectionContent: string
  sections: Record<ProfileSectionId, string>
  actionResult: string
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
}) {
  const current = profileSectionMeta[activeSection]
  const sectionItems = flattenResumeFolders(folders)
  const filledCount = sectionItems.filter((item) => sections[item.id]?.trim()).length

  return (
    <section className="profile-workspace">
      <div className="profile-layout">
        <aside className="profile-overview-panel" aria-label="个人档案分区">
          <div className="profile-overview-head">
            <strong>个人档案</strong>
            <p>{filledCount} 个分区已有内容。先补经历，桃子再帮你变成简历和面试答案。</p>
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

        <section className="profile-detail-panel">
          <div className="profile-detail-head">
            <div>
              <span>正在编辑</span>
              <h2>{current.title}</h2>
            </div>
            <button type="button" onClick={onSave} disabled={isSaving}>
              {isSaving ? '保存中' : '保存档案'}
            </button>
          </div>

          {activeSection === 'full' ? (
            <div className="resume-file-strip">
              <label className="resume-upload-card">
                <input type="file" accept=".pdf,.doc,.docx,.md,.markdown,.html,.htm" onChange={(event) => event.target.files?.[0] && onUploadFile(event.target.files[0])} />
                <span>+</span>
                <strong>上传简历附件</strong>
              </label>
              <div className="resume-file-list">
                {resumeFiles.length ? resumeFiles.map((file) => (
                  <button type="button" key={file.filename} onClick={() => onSectionContent([sectionContent, `【${file.title}】\n${file.content}`].filter(Boolean).join('\n\n'))}>
                    <strong>{file.filename}</strong>
                    <span>{file.summary || '已解析'}</span>
                  </button>
                )) : <p>还没有上传简历文件。</p>}
              </div>
            </div>
          ) : null}

          <textarea
            className="profile-editor"
            value={sectionContent}
            onChange={(event) => onSectionContent(event.target.value)}
            placeholder={`在这里整理${current.title}。桃子会基于这些内容帮你生成简历、优化表达和准备追问题。`}
            rows={10}
          />

          {actionResult ? (
            <section className="profile-action-result">
              <div className="profile-action-head">
                <strong>桃子的建议</strong>
                <button type="button" onClick={onAcceptResult}>采纳到当前文件</button>
              </div>
              <p>{actionResult}</p>
            </section>
          ) : (
            <section className="profile-empty-hint" aria-label="当前分区状态">
              <strong>{sectionContent.trim() ? '当前文件已可用于对话和面试。' : '当前文件暂无内容。'}</strong>
            </section>
          )}
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

function KnowledgeWorkspace({
  tab,
  question,
  messages,
  items,
  savedIds,
  activeId,
  draft,
  busy,
  onQuestion,
  onAskQuestion,
  onSave,
  onDraft,
  onSaveDraft,
  onDelete,
  onUpload,
  onAsk,
  onUseInProfile,
}: {
  tab: KnowledgeTab
  question: string
  messages: ChatMessage[]
  items: KnowledgeItem[]
  savedIds: string[]
  activeId: string
  draft: KnowledgeDraft
  busy: boolean
  onQuestion: (value: string) => void
  onAskQuestion: () => void
  onSave: (id: string) => void
  onDraft: (draft: KnowledgeDraft) => void
  onSaveDraft: () => void
  onDelete: (id: string) => void
  onUpload: (file: File) => void
  onAsk: (item: KnowledgeItem) => void
  onUseInProfile: (item: KnowledgeItem) => void
}) {
  const activeItem = items.find((item) => item.id === activeId)
  const canEdit = !activeItem || activeItem.source === 'personal'
  const isCreating = canEdit && !activeItem
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
            {discoverKnowledgeFeed().map((item, index) => (
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
        <section className="knowledge-qa">
          <div className="knowledge-qa-empty">
            <h2>基于知识库问答</h2>
            {!messages.length ? (
              <p>{tab === 'personal' ? '可以围绕个人知识库梳理经历、准备面试题和整理投递策略。' : '可以围绕收藏知识库解释概念、拆解方法论和迁移到你的求职场景。'}</p>
            ) : null}
          </div>
          <div className="knowledge-chat-thread">
            {messages.map((message, index) => (
              <Message
                key={`${message.role}-${index}`}
                role={message.role}
                actions={message.actions}
                onApproveAction={() => undefined}
                onDismissAction={() => undefined}
              >
                {message.content}
              </Message>
            ))}
          </div>

          {activeItem ? (
            <section className="knowledge-inline-editor">
              <div className="knowledge-detail-head">
                <div>
                  <span>{canEdit ? '当前资料' : '已选资料'}</span>
                  <h2>{activeItem.title}</h2>
                </div>
                <div className="knowledge-detail-actions">
                  {activeItem.source === 'discover' ? (
                    <button type="button" onClick={() => onSave(activeItem.id)} disabled={savedIds.includes(activeItem.id)}>
                      {savedIds.includes(activeItem.id) ? '已收藏' : '收藏'}
                    </button>
                  ) : null}
                  <button type="button" onClick={() => onAsk(activeItem)}>问桃子</button>
                  <button type="button" onClick={() => onUseInProfile(activeItem)}>沉淀到档案</button>
                </div>
              </div>
              {canEdit ? (
                <div className="knowledge-editor compact">
                  <label>
                    <span>标题</span>
                    <input value={draft.title} onChange={(event) => onDraft({ ...draft, title: event.target.value })} />
                  </label>
                  <label>
                    <span>摘要</span>
                    <textarea rows={2} value={draft.summary} onChange={(event) => onDraft({ ...draft, summary: event.target.value })} />
                  </label>
                  <label>
                    <span>正文</span>
                    <textarea rows={5} value={draft.content} onChange={(event) => onDraft({ ...draft, content: event.target.value })} />
                  </label>
                  <div className="knowledge-editor-actions">
                    {activeItem.source === 'personal' ? <button type="button" className="secondary-danger" onClick={() => onDelete(activeItem.id)}>删除</button> : null}
                    <button type="button" onClick={onSaveDraft} disabled={busy || !draft.title.trim() || !draft.content.trim()}>
                      {busy ? '保存中' : isCreating ? '新建资料' : '保存修改'}
                    </button>
                  </div>
                </div>
              ) : <p className="knowledge-preview-text">{activeItem.content || activeItem.summary}</p>}
            </section>
          ) : null}

          <ChatComposer
            value={question}
            placeholder={tab === 'personal' ? '基于知识库向桃子提问，如基于个人知识库，梳理一下我在快手 AI 产品经理岗位的求职经历' : '基于知识库向桃子提问，如基于所收藏知识库，解释一下 auto-rubric 是什么意思'}
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
      )}
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
      <div className="feed-cover" style={{ backgroundImage: `url(https://picsum.photos/seed/peach-knowledge-${index}/160/160)` }} />
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
  uploadDisabled,
  onChange,
  onSubmit,
  onAction,
  onUpload,
}: {
  value: string
  placeholder: string
  actions: string[]
  disabled: boolean
  button: string
  buttonKind?: 'send' | 'voice'
  uploadDisabled?: boolean
  onChange: (value: string) => void
  onSubmit: () => void
  onAction: (action: string) => void
  onUpload?: (file: File) => void
}) {
  return (
    <section className="bottom-composer">
      <div className="composer-input-row">
        <textarea
          rows={1}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={(event) => {
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
          {onUpload ? (
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
          {actions.length ? (
            <div className="composer-action-row">
              {actions.map((action) => (
                <button key={action} type="button" onClick={() => onAction(action)}>{action}</button>
              ))}
            </div>
          ) : null}
        </div>
        <div className="composer-send-group">
          <button className={buttonKind === 'voice' ? 'voice-send-button' : ''} type="button" onClick={onSubmit} disabled={disabled || !value.trim()} aria-label={button}>
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
        {!done ? <button type="button" onClick={onDismiss} disabled={status === 'executing'}>取消</button> : null}
        {!done ? <button type="button" className="primary" onClick={onApprove} disabled={status === 'executing'}>{status === 'executing' ? '执行中' : '确认'}</button> : null}
      </div>
    </section>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
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

function sortFolders(folders: KnowledgeFolder[], mode: SortMode) {
  return [...folders].sort((a, b) => (mode === 'name' ? a.name.localeCompare(b.name, 'zh-CN') : b.id.localeCompare(a.id)))
}

function sortKnowledgeItems(items: KnowledgeItem[], mode: SortMode) {
  return [...items].sort((a, b) => (mode === 'name' ? a.title.localeCompare(b.title, 'zh-CN') : b.id.localeCompare(a.id)))
}

function knowledgeTabLabel(tab: KnowledgeTab) {
  const labels: Record<KnowledgeTab, string> = {
    personal: '个人知识库',
    saved: '收藏知识库',
    discover: '发现知识库',
  }
  return labels[tab]
}

function knowledgeMetaLine(item: KnowledgeItem, index: number) {
  const subscribers = ['2.1万人已订阅', '538人已订阅', '1.2万人已订阅', '7989人已订阅', '6907人已订阅']
  const contents = ['100万+个内容', '729个内容', '164个内容', '4868个内容', '1077个内容']
  return `${subscribers[index % subscribers.length]} | ${contents[index % contents.length]} | @${item.source === 'discover' ? '桃子精选' : '个人资料'}`
}

function titleFromUrl(value: string) {
  try {
    const url = new URL(value)
    return url.hostname.replace(/^www\./, '') || '链接资料'
  } catch {
    return value.slice(0, 48) || '链接资料'
  }
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

function formatInterviewReportMessage(report?: {
  summary?: string
  overall_score?: number
  key_improvements?: string[]
  next_plan?: string[]
}) {
  if (!report) return '这场面试已结束。报告生成完成，可以在个人档案和成长记录里继续复盘。'
  const parts = [
    '这场面试已结束，我先给你一版简短复盘。',
    report.overall_score ? `综合表现：${report.overall_score} 分。` : '',
    report.summary || '',
    report.key_improvements?.length ? `优先改进：${report.key_improvements.slice(0, 3).join('；')}` : '',
    report.next_plan?.length ? `下一步：${report.next_plan.slice(0, 3).join('；')}` : '',
  ].filter(Boolean)
  return parts.join('\n\n')
}

async function responseErrorMessage(response: Response) {
  const text = await response.text()
  try {
    const data = JSON.parse(text) as { detail?: unknown }
    if (typeof data.detail === 'string') return data.detail
    if (Array.isArray(data.detail)) return data.detail.map((item) => item?.msg || JSON.stringify(item)).join('；')
  } catch {
    return text || response.statusText
  }
  return text || response.statusText
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
    .map((line) => line.replace(/^\s*(\d+[.)、]|•)\s*/, '').trim())
    .filter(Boolean)
    .slice(0, 4)
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
    {
      id: 'pm-method',
      title: '产品经理方法论题库',
      summary: '覆盖用户洞察、需求判断、优先级、指标拆解和复盘表达。',
      source: 'discover',
    },
    {
      id: 'aigc-strategy',
      title: 'AIGC 策略产品面试资料',
      summary: '整理大模型产品、内容生态、商业化和评估指标相关问题。',
      source: 'discover',
    },
    {
      id: 'delivery-plan',
      title: '秋招投递节奏清单',
      summary: '按时间、岗位和公司梯队拆解投递节奏。',
      source: 'discover',
    },
  ]
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
