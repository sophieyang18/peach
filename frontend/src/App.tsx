import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent } from 'react'
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
  const [knowledgeInput, setKnowledgeInput] = useState('')
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
  const [seconds, setSeconds] = useState(0)
  const [paused, setPaused] = useState(false)
  const [subtitleCollapsed, setSubtitleCollapsed] = useState(false)
  const [timerCollapsed, setTimerCollapsed] = useState(false)
  const [mediaStream, setMediaStream] = useState<MediaStream | null>(null)
  const [mediaReady, setMediaReady] = useState(false)
  const [knowledgeTab, setKnowledgeTab] = useState<'personal' | 'saved' | 'discover'>('personal')
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
  const knowledgeItems = useMemo(() => [...personalKnowledge, ...buildKnowledgeItems(profile)], [personalKnowledge, profile])

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
    begin('chat', `正在执行${action.title}`)
    try {
      const data = await api<{
        message?: string
        profile?: Profile
        interview?: { id: string; interview_type: string; interviewer_style: string; company: string; role: string; status: string; report?: { summary?: string } }
        report?: { summary?: string; overall_score?: number }
        knowledge?: KnowledgeItem
        deleted_knowledge_id?: string
      }>('/api/agent/actions/execute', {
        method: 'POST',
        body: JSON.stringify({ tool: action.tool, payload: action.payload }),
      })

      markActionStatus(action.id, 'approved')
      applyToolResult(action, data)
      appendMessage({ role: 'system', content: data.message || '动作已完成。' })
      void refreshDashboard()
    } catch (err) {
      markActionStatus(action.id, 'pending')
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
      interview?: { interview_type: string; interviewer_style: string; company: string; role: string; status: string; report?: { summary?: string } }
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
      setPeachPanel('interview-setup')
    }
    if (action.tool === 'finish_latest_interview') {
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
      setLiveKind(kind)
      setPeachPanel('live-interview')
      appendMessage({ role: 'peach', content: kind === 'question-bank' ? '题库练习开始。我们按题库顺序来，我会根据你的回答追问。' : '模拟面试开始。先稳住节奏，按真实面试来。' })

      void api('/api/interviews', {
        method: 'POST',
        body: JSON.stringify({
          interview_type: kind === 'question-bank' ? '题库练习' : '模拟面试',
          interviewer_style: settings.style,
          company: profile.target_company,
          role: profile.target_role,
        }),
      }).catch(() => undefined)

      setNotice('实时面试已开始。')
    } catch (err) {
      setMediaReady(false)
      setError(settings.mode === 'video' ? '摄像头或麦克风权限未开启，无法进入视频面试。' : '麦克风权限未开启，无法进入语音面试。')
      console.error(err)
    } finally {
      end('interviewStart')
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

  function submitProfileNote(event: FormEvent) {
    event.preventDefault()
    if (!profileInput.trim()) return
    const nextSections = {
      ...profileSections,
      [activeProfileSection]: [profileSections[activeProfileSection], profileInput.trim()].filter(Boolean).join('\n\n'),
    }
    setProfileSections(nextSections)
    setNotice(`已补充到${profileSectionMeta[activeProfileSection].title}。`)
    setProfileInput('')
  }

  async function submitKnowledge(event: FormEvent) {
    event.preventDefault()
    if (!knowledgeInput.trim()) return
    begin('knowledge', '正在添加个人知识库')
    try {
      const data = await api<{ item: KnowledgeItem }>('/api/knowledge', {
        method: 'POST',
        body: JSON.stringify({
          title: buildKnowledgeTitle(knowledgeInput.trim()),
          summary: summarizeClientText(knowledgeInput.trim(), 160),
          content: knowledgeInput.trim(),
          source: 'personal',
          url: looksLikeUrl(knowledgeInput.trim()) ? knowledgeInput.trim() : '',
        }),
      })
      setPersonalKnowledge((current) => [data.item, ...current])
      setActiveKnowledgeId(data.item.id)
      setKnowledgeDraft(toKnowledgeDraft(data.item))
      setKnowledgeTab('personal')
      setKnowledgeInput('')
      setNotice('已添加到个人知识库。')
    } catch (err) {
      setError('知识库添加失败，稍后再试一次。')
      console.error(err)
    } finally {
      end('knowledge')
    }
  }

  const appClass = `app-shell module-${module}`

  return (
    <main className={appClass}>
      <aside className="main-nav" aria-label="主导航栏">
        <div className="brand-block">
          <div className="brand-mark">桃</div>
          <div>
            <strong>桃子</strong>
            <span>求职陪练 Agent</span>
          </div>
        </div>
        <nav className="main-nav-list">
          <button className={module === 'peach' ? 'main-nav-item active' : 'main-nav-item'} type="button" onClick={() => openModule('peach')}>
            <strong>桃子</strong>
            <span>对话和面试</span>
          </button>
          <button className={module === 'profile' ? 'main-nav-item active' : 'main-nav-item'} type="button" onClick={() => openModule('profile')}>
            <strong>个人档案</strong>
            <span>简历和复盘</span>
          </button>
          <button className={module === 'knowledge' ? 'main-nav-item active' : 'main-nav-item'} type="button" onClick={() => openModule('knowledge')}>
            <strong>求职知识库</strong>
            <span>资料和收藏</span>
          </button>
        </nav>
        <div className="nav-profile">
          <span>{profile.stage}</span>
          <strong>{profile.target_role}</strong>
          <p>{profile.target_company || '还没有目标公司'}</p>
        </div>
      </aside>

      {module === 'peach' ? (
        <PeachSubNav
          activePanel={peachPanel}
          conversations={conversations}
          activeConversationId={activeConversationId}
          onNew={createConversation}
          onInterview={() => setPeachPanel('interview-setup')}
          onOpenHistory={openConversation}
        />
      ) : null}

      <section className="workspace" aria-label="工作区">
        <header className="workspace-topbar">
          <div>
            <p>{workspaceKicker(module, peachPanel)}</p>
            <h1>{workspaceTitle(module, peachPanel)}</h1>
          </div>
          <div className={busyText ? 'status-pill busy' : 'status-pill'}>{busyText || notice}</div>
        </header>

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
            onSend={() => void sendPrompt(input)}
            onQuickSend={(value) => void sendPrompt(value)}
            onAction={runComposerAction}
            onSettingsChange={setSettings}
            onStartInterview={() => void startLiveInterview('interview')}
            onStartQuestionBank={() => void startLiveInterview('question-bank')}
            onUploadInterviewFile={(file, target) => void uploadInterviewFile(file, target)}
            onUploadChatFile={(file) => void uploadChatFile(file)}
            onPauseToggle={() => setPaused((value) => !value)}
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
            query={knowledgeQuery}
            value={knowledgeInput}
            items={knowledgeItems}
            savedIds={savedKnowledge}
            activeId={activeKnowledgeId}
            draft={knowledgeDraft}
            busy={Boolean(busy.knowledge || busy.upload)}
            onTab={setKnowledgeTab}
            onQuery={setKnowledgeQuery}
            onValue={setKnowledgeInput}
            onSubmit={submitKnowledge}
            onSave={saveKnowledge}
            onSelect={selectKnowledgeItem}
            onDraft={setKnowledgeDraft}
            onSaveDraft={() => void saveKnowledgeDraft()}
            onNew={createKnowledgeDraft}
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
  onNew,
  onInterview,
  onOpenHistory,
}: {
  activePanel: PeachPanel
  conversations: Conversation[]
  activeConversationId: string
  onNew: () => void
  onInterview: () => void
  onOpenHistory: (id: string) => void
}) {
  return (
    <aside className="sub-nav" aria-label="桃子副导航栏">
      <div className="sub-nav-actions">
        <button className={activePanel === 'new-chat' ? 'sub-action active' : 'sub-action'} type="button" onClick={onNew}>
          新建对话
        </button>
        <button className={activePanel.includes('interview') ? 'sub-action active' : 'sub-action'} type="button" onClick={onInterview}>
          模拟面试
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
      <section className={hasStartedChat ? 'greeting-panel compact' : 'greeting-panel'}>
        <div className="greeting-copy">
          <h2>{personalGreeting(props.profile)}</h2>
          {!hasStartedChat ? <p>我可以陪你模拟面试、打磨简历、整理投递节奏，也能把每次练习沉淀进个人档案。</p> : null}
        </div>
        <div className="bubble-group">
          {!hasStartedChat ? <div className="bubble-title">核心功能</div> : null}
          <div className="bubble-grid fixed-bubbles">
            {(hasStartedChat ? fixedBubbles.slice(0, 4) : fixedBubbles).map((item) => (
              <button key={item} type="button" onClick={() => props.onQuickSend(item)}>{item}</button>
            ))}
          </div>
        </div>
        <div className={hasStartedChat ? 'bubble-group recommendation-group compact-only-hidden' : 'bubble-group recommendation-group'}>
          <div className="bubble-title">为你推荐</div>
          <div className="bubble-grid recommendation-bubbles">
            {props.recommendations.map((item) => (
              <button key={item} type="button" onClick={() => props.onQuickSend(item)}>{item}</button>
            ))}
          </div>
        </div>
      </section>

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
        button={props.busy.chat ? '回复中' : '发送'}
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
  onSubtitleToggle,
  onTimerToggle,
  onBackToSetup,
}: Parameters<typeof PeachWorkspace>[0]) {
  const liveTitle = liveKind === 'question-bank' ? '题库练习进行中' : '模拟面试进行中'

  return (
    <section className="live-stage">
      <div className="live-main">
        <div className="avatar-stage" aria-label="桃子的半身形象">
          <div className="peach-avatar">
            <div className="avatar-face">桃</div>
            <div className="avatar-body">
              <strong>{liveTitle}</strong>
              <span>{settings.mode === 'video' ? '视频面试' : '语音面试'} / {settings.style}</span>
            </div>
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
              onApproveAction={() => undefined}
              onDismissAction={() => undefined}
            >
              {message.content}
            </Message>
          ))}
        </section>

        <ChatComposer
          value={input}
          placeholder={paused ? '面试暂停中，点击继续后再回答' : '输入你的回答，也可以后续接入语音转写'}
          actions={[]}
          disabled={paused || Boolean(busy.chat)}
          button={busy.chat ? '发送中' : '发送'}
          onChange={onInput}
          onSubmit={onSend}
          onAction={() => undefined}
          onUpload={onUploadChatFile}
          uploadDisabled={paused || Boolean(busy.upload || busy.chat)}
        />
      </div>

      <aside className="live-side">
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
              <p>{mediaReady ? '桃子：请先做一个 1 分钟自我介绍。' : '等待媒体权限开启。'}</p>
              <p>{paused ? '面试已暂停。' : '字幕模块会在接入语音识别后实时更新。'}</p>
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
  isSaving: boolean
  value: string
  onSelectSection: (id: ProfileSectionId) => void
  onSectionContent: (value: string) => void
  onValue: (value: string) => void
  onSubmit: (event: FormEvent) => void
  onSave: () => void
  onAction: (action: string) => void
  onAcceptResult: () => void
  onUploadFile: (file: File) => void
}) {
  const current = profileSectionMeta[activeSection]
  const sectionItems = flattenResumeFolders(folders)
  const filledCount = sectionItems.filter((item) => sections[item.id]?.trim()).length
  const activeSummary = sectionItems.find((item) => item.id === activeSection)?.summary ?? current.summary

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
              <p>{activeSummary}</p>
            </div>
            <button type="button" onClick={onSave} disabled={isSaving}>
              {isSaving ? '保存中' : '保存档案'}
            </button>
          </div>

          <div className="profile-helper-note">{current.helper}</div>

          <textarea
            className="profile-editor"
            value={sectionContent}
            onChange={(event) => onSectionContent(event.target.value)}
            placeholder={`在这里整理${current.title}。桃子会基于这些内容帮你生成简历、优化表达和准备追问题。`}
            rows={10}
          />

          <div className="profile-assist-strip">
            <span>桃子可以帮你</span>
            {['简历生成', '经历生成', '简历优化', '面试深挖'].map((item) => (
              <button key={item} type="button" onClick={() => onAction(item)} disabled={isSaving}>
                {item}
              </button>
            ))}
            <label className="inline-upload-button">
              <input type="file" accept=".pdf,.doc,.docx,.md,.markdown,.html,.htm" onChange={(event) => event.target.files?.[0] && onUploadFile(event.target.files[0])} />
              <span>上传材料</span>
            </label>
          </div>

          {actionResult ? (
            <section className="profile-action-result">
              <div className="profile-action-head">
                <strong>桃子的建议</strong>
                <button type="button" onClick={onAcceptResult}>采纳到当前文件</button>
              </div>
              <p>{actionResult}</p>
            </section>
          ) : (
            <section className="profile-empty-hint">
              <strong>{current.summary}</strong>
              <p>{sectionContent.trim() ? '可以继续补证据，或让桃子帮你改成更适合面试的表达。' : '先写几句也可以，不需要一次填完整。底部输入会直接追加到当前分区。'}</p>
            </section>
          )}
        </section>
      </div>
      <form className="bottom-composer profile-composer" onSubmit={onSubmit}>
        <textarea value={value} onChange={(event) => onValue(event.target.value)} placeholder="补充个人档案" rows={2} />
        <div className="composer-footer">
          <div className="composer-action-row">
            {['简历生成', '经历生成', '简历优化', '面试深挖'].map((item) => (
              <button key={item} type="button" onClick={() => onAction(item)} disabled={isSaving}>{item}</button>
            ))}
          </div>
          <button type="submit" disabled={!value.trim()}>保存补充</button>
        </div>
      </form>
    </section>
  )
}

function KnowledgeWorkspace({
  tab,
  query,
  value,
  items,
  savedIds,
  activeId,
  draft,
  busy,
  onTab,
  onQuery,
  onValue,
  onSubmit,
  onSave,
  onSelect,
  onDraft,
  onSaveDraft,
  onNew,
  onDelete,
  onUpload,
  onAsk,
  onUseInProfile,
}: {
  tab: 'personal' | 'saved' | 'discover'
  query: string
  value: string
  items: KnowledgeItem[]
  savedIds: string[]
  activeId: string
  draft: KnowledgeDraft
  busy: boolean
  onTab: (tab: 'personal' | 'saved' | 'discover') => void
  onQuery: (value: string) => void
  onValue: (value: string) => void
  onSubmit: (event: FormEvent) => void
  onSave: (id: string) => void
  onSelect: (item: KnowledgeItem) => void
  onDraft: (draft: KnowledgeDraft) => void
  onSaveDraft: () => void
  onNew: () => void
  onDelete: (id: string) => void
  onUpload: (file: File) => void
  onAsk: (item: KnowledgeItem) => void
  onUseInProfile: (item: KnowledgeItem) => void
}) {
  const visibleItems = items.filter((item) => {
    if (tab === 'personal') return item.source === 'personal'
    if (tab === 'saved') return savedIds.includes(item.id)
    return item.source === 'discover'
  }).filter((item) => {
    const keyword = query.trim().toLowerCase()
    if (!keyword) return true
    return [item.title, item.summary, item.content, item.url].some((part) => part?.toLowerCase().includes(keyword))
  })
  const activeItem = items.find((item) => item.id === activeId)
  const canEdit = !activeItem || activeItem.source === 'personal'
  const isCreating = canEdit && !activeItem

  return (
    <section className="knowledge-workspace">
      <form className="knowledge-ingest" onSubmit={onSubmit}>
        <div>
          <h2>求职知识库</h2>
          <p>存简历、题库、JD、复盘和资料。桃子会在对话、简历生成和经历深挖里引用它们。</p>
        </div>
        <div className="ingest-row">
          <input value={value} onChange={(event) => onValue(event.target.value)} placeholder="粘贴链接、资料摘录或待整理笔记" />
          <label className="knowledge-upload">
            <input type="file" accept=".pdf,.doc,.docx,.md,.markdown,.html,.htm" onChange={(event) => event.target.files?.[0] && onUpload(event.target.files[0])} />
            <span>上传文件</span>
          </label>
          <button type="submit" disabled={!value.trim() || busy}>添加</button>
        </div>
      </form>

      <div className="knowledge-toolbar">
        <div className="knowledge-tabs">
          <button className={tab === 'personal' ? 'active' : ''} type="button" onClick={() => onTab('personal')}>个人知识库</button>
          <button className={tab === 'saved' ? 'active' : ''} type="button" onClick={() => onTab('saved')}>收藏知识库</button>
          <button className={tab === 'discover' ? 'active' : ''} type="button" onClick={() => onTab('discover')}>发现知识库</button>
        </div>
        <div className="knowledge-search-row">
          <input value={query} onChange={(event) => onQuery(event.target.value)} placeholder="搜索标题、摘要、正文" />
          <button type="button" onClick={onNew}>新建资料</button>
        </div>
      </div>

      <div className="knowledge-layout">
        <div className="knowledge-list">
          {visibleItems.length ? visibleItems.map((item) => (
            <button
              className={item.id === activeId ? 'knowledge-list-item active' : 'knowledge-list-item'}
              key={item.id}
              type="button"
              onClick={() => onSelect(item)}
            >
              <span>{knowledgeSourceLabel(item.source)}</span>
              <strong>{item.title}</strong>
              <p>{item.summary}</p>
            </button>
          )) : (
            <section className="knowledge-empty">
              <strong>这里还没有资料</strong>
              <p>上传文件、粘贴链接，或从发现知识库收藏一份资料。</p>
            </section>
          )}
        </div>

        <section className="knowledge-detail">
          <div className="knowledge-detail-head">
            <div>
              <span>{canEdit ? '可编辑资料' : '发现资料'}</span>
              <h2>{activeItem ? activeItem.title : '新建资料'}</h2>
            </div>
            <div className="knowledge-detail-actions">
              {activeItem?.source === 'discover' ? (
                <button type="button" onClick={() => onSave(activeItem.id)} disabled={savedIds.includes(activeItem.id)}>
                  {savedIds.includes(activeItem.id) ? '已收藏' : '收藏'}
                </button>
              ) : null}
              {activeItem ? <button type="button" onClick={() => onAsk(activeItem)}>问桃子</button> : null}
              {activeItem ? <button type="button" onClick={() => onUseInProfile(activeItem)}>沉淀到档案</button> : null}
            </div>
          </div>

          {canEdit ? (
            <div className="knowledge-editor">
              <label>
                <span>标题</span>
                <input value={draft.title} onChange={(event) => onDraft({ ...draft, title: event.target.value })} />
              </label>
              <label>
                <span>摘要</span>
                <textarea rows={3} value={draft.summary} onChange={(event) => onDraft({ ...draft, summary: event.target.value })} placeholder="可选。留空时会自动从正文生成摘要。" />
              </label>
              <label>
                <span>正文</span>
                <textarea rows={8} value={draft.content} onChange={(event) => onDraft({ ...draft, content: event.target.value })} placeholder="粘贴资料正文、JD、题库、复盘、课程笔记或链接说明。" />
              </label>
              <label>
                <span>来源链接</span>
                <input value={draft.url} onChange={(event) => onDraft({ ...draft, url: event.target.value })} placeholder="可选" />
              </label>
              <div className="knowledge-editor-actions">
                {activeItem?.source === 'personal' ? <button type="button" className="secondary-danger" onClick={() => onDelete(activeItem.id)}>删除</button> : null}
                <button type="button" onClick={onSaveDraft} disabled={busy || !draft.title.trim() || !draft.content.trim()}>
                  {busy ? '保存中' : isCreating ? '新建资料' : '保存修改'}
                </button>
              </div>
            </div>
          ) : (
            <div className="knowledge-preview">
              <p>{activeItem?.content || activeItem?.summary || '选择一条资料查看详情。'}</p>
            </div>
          )}
        </section>
      </div>
    </section>
  )
}

function ChatComposer({
  value,
  placeholder,
  actions,
  disabled,
  button,
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
  uploadDisabled?: boolean
  onChange: (value: string) => void
  onSubmit: () => void
  onAction: (action: string) => void
  onUpload?: (file: File) => void
}) {
  return (
    <section className="bottom-composer">
      {actions.length ? (
        <div className="composer-action-row">
          {actions.map((action) => (
            <button key={action} type="button" onClick={() => onAction(action)}>{action}</button>
          ))}
        </div>
      ) : null}
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
        <div className="composer-send-group">
          {onUpload ? (
            <label className={uploadDisabled ? 'composer-upload-button disabled' : 'composer-upload-button'} title="上传文件">
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
              <span>上传</span>
            </label>
          ) : null}
          <button type="button" onClick={onSubmit} disabled={disabled || !value.trim()}>{button}</button>
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

function summarizeClientText(value: string, limit = 160) {
  const clean = value.replace(/\s+/g, ' ').trim()
  if (!clean) return ''
  return clean.slice(0, limit) + (clean.length > limit ? '...' : '')
}

function looksLikeUrl(value: string) {
  try {
    const url = new URL(value)
    return ['http:', 'https:'].includes(url.protocol)
  } catch {
    return false
  }
}

function buildKnowledgeTitle(value: string) {
  if (looksLikeUrl(value)) {
    try {
      const url = new URL(value)
      return url.hostname.replace(/^www\./, '') || '链接资料'
    } catch {
      return '链接资料'
    }
  }
  const firstLine = value.split(/\n/).find((line) => line.trim())
  return summarizeClientText(firstLine || value, 48) || '个人资料'
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

function knowledgeSourceLabel(source: string) {
  if (source === 'personal') return '个人知识库'
  if (source === 'discover') return '发现知识库'
  return '收藏知识库'
}

function formatTime(value: number) {
  const minutes = Math.floor(value / 60).toString().padStart(2, '0')
  const seconds = (value % 60).toString().padStart(2, '0')
  return `${minutes}:${seconds}`
}

function cleanAssistantText(value: string) {
  return value
    .replace(/```[\s\S]*?```/g, (block) => block.replace(/```/g, ''))
    .replace(/\*\*(.*?)\*\*/g, '$1')
    .replace(/__(.*?)__/g, '$1')
    .replace(/^\s{0,3}#{1,6}\s+/gm, '')
    .replace(/^\s*[-*]\s+/gm, '• ')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

export default App
