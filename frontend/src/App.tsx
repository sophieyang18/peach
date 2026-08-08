import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import './App.css'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'

type View = 'today' | 'interview' | 'review' | 'growth' | 'profile'
type BusyKey = 'refresh' | 'profile' | 'practice' | 'interviewStart' | 'interviewAnswer' | 'report' | 'review' | 'chat'
type ChatMessage = { role: 'peach' | 'user' | 'system'; content: string }
type ToolMessages = Record<View, ChatMessage[]>
type Conversation = { id: string; title: string; updatedAt: string; messages: ChatMessage[] }
type ToolConversations = Record<View, Conversation[]>

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

type PracticeFeedback = {
  summary?: string
  highlights?: string[]
  improvements?: string[]
  reference_answer?: string
  next_task?: string
  archive?: string
}

type Practice = {
  id: string
  question: string
  answer: string
  score: number
  tags: string[]
  feedback: PracticeFeedback
}

type InterviewReport = {
  overall_score?: number
  summary?: string
  dimensions?: Array<{ name: string; score: number }>
  key_improvements?: string[]
  next_plan?: string[]
}

type Interview = {
  id: string
  interview_type: string
  interviewer_style: string
  company: string
  role: string
  status: string
  transcript: Array<{ role: string; content: string }>
  report: InterviewReport
}

type ReviewFeedback = {
  comfort?: string
  what_went_well?: string[]
  to_improve?: string[]
  archive?: string
  next_actions?: string[]
}

type Dashboard = {
  profile: Profile
  checkin: {
    message: string
    task: { title: string; question: string; duration: string; focus: string }
  }
  recent_practices: Practice[]
  recent_interviews: Interview[]
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

const emptyProfile = {
  name: '同学',
  target_role: '产品经理',
  target_company: '',
  target_city: '',
  stage: '投递期',
  resume_text: '',
  communication_style: '温暖直接',
}

const navItems: Array<{ id: View; label: string; hint: string }> = [
  { id: 'today', label: '今日陪伴', hint: '每日 check-in' },
  { id: 'interview', label: '模拟面试', hint: '沉浸式追问' },
  { id: 'review', label: '面后复盘', hint: '先情绪后复盘' },
  { id: 'growth', label: '成长档案', hint: '长期记忆' },
  { id: 'profile', label: '求职画像', hint: '简历与目标' },
]

const initialMessages: ToolMessages = {
  today: [{ role: 'peach', content: '今天我们先练一题。你直接在底部输入框回答，我来给你反馈。' }],
  interview: [{ role: 'peach', content: '这里是模拟面试间。先选类型和面试官风格，然后我们一问一答往下走。' }],
  review: [{ role: 'peach', content: '面完先别急着否定自己。把感受、题目和卡住的地方发给我，我们慢慢拆。' }],
  growth: [{ role: 'peach', content: '这是我目前记住的成长档案。你可以问我某个薄弱点该怎么练。' }],
  profile: [{ role: 'peach', content: '这里管理你的目标、简历和备战计划。资料越清楚，我越能个性化地陪你练。' }],
}

const initialConversations: ToolConversations = {
  today: [{ id: 'today-default', title: '今日一练', updatedAt: '刚刚', messages: initialMessages.today }],
  interview: [{ id: 'interview-default', title: '模拟面试准备', updatedAt: '刚刚', messages: initialMessages.interview }],
  review: [{ id: 'review-default', title: '面后复盘', updatedAt: '刚刚', messages: initialMessages.review }],
  growth: [{ id: 'growth-default', title: '成长档案问答', updatedAt: '刚刚', messages: initialMessages.growth }],
  profile: [{ id: 'profile-default', title: '求职画像调整', updatedAt: '刚刚', messages: initialMessages.profile }],
}

const initialActiveConversationIds: Record<View, string> = {
  today: 'today-default',
  interview: 'interview-default',
  review: 'review-default',
  growth: 'growth-default',
  profile: 'profile-default',
}

function App() {
  const [activeView, setActiveView] = useState<View>('growth')
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [toolChatOpen, setToolChatOpen] = useState<Record<View, boolean>>({
    today: false,
    interview: false,
    review: false,
    growth: false,
    profile: false,
  })
  const [contextExpanded, setContextExpanded] = useState(false)
  const [dashboard, setDashboard] = useState<Dashboard | null>(null)
  const [profileForm, setProfileForm] = useState(emptyProfile)
  const profileHydratedRef = useRef(false)
  const [practiceAnswer, setPracticeAnswer] = useState('')
  const [practiceFeedback, setPracticeFeedback] = useState<PracticeFeedback | null>(null)
  const [activeInterview, setActiveInterview] = useState<Interview | null>(null)
  const [interviewAnswer, setInterviewAnswer] = useState('')
  const [interviewConfig, setInterviewConfig] = useState({ interview_type: '产品思维', interviewer_style: '温和型' })
  const [reviewDraft, setReviewDraft] = useState('')
  const [reviewResult, setReviewResult] = useState<ReviewFeedback | null>(null)
  const [profileDraftOpen, setProfileDraftOpen] = useState(false)
  const [chatInput, setChatInput] = useState('')
  const [conversations, setConversations] = useState<ToolConversations>(initialConversations)
  const [activeConversationIds, setActiveConversationIds] = useState<Record<View, string>>(initialActiveConversationIds)
  const [busy, setBusy] = useState<Partial<Record<BusyKey, string>>>({ refresh: '桃子正在同步本地成长档案...' })
  const [notice, setNotice] = useState('准备好了就开始。')
  const [error, setError] = useState('')
  const chatScrollRef = useRef<HTMLElement | null>(null)

  const busyText = Object.values(busy)[0]
  const isBusy = (key: BusyKey) => Boolean(busy[key])
  const task = dashboard?.checkin.task
  const progressWidth = useMemo(() => `${Math.max(6, Math.min(dashboard?.growth.avg_score ?? 0, 100))}%`, [dashboard])
  const panelFirst = isPanelFirstView(activeView)
  const chatOpen = !panelFirst || toolChatOpen[activeView]
  const activeConversationId = activeConversationIds[activeView]
  const activeMessages = useMemo(
    () => conversations[activeView].find((item) => item.id === activeConversationId)?.messages ?? [],
    [activeConversationId, activeView, conversations],
  )

  const appendMessage = useCallback((view: View, message: ChatMessage) => {
    setConversations((current) => ({
      ...current,
      [view]: current[view].map((conversation) => {
        if (conversation.id !== activeConversationIds[view]) return conversation
        const shouldRetitle = message.role === 'user' && conversation.messages.filter((item) => item.role === 'user').length === 0
        return {
          ...conversation,
          title: shouldRetitle ? message.content.slice(0, 18) || conversation.title : conversation.title,
          updatedAt: '刚刚',
          messages: [...conversation.messages, message],
        }
      }),
    }))
  }, [activeConversationIds])

  const removeToolMessage = useCallback((view: View, content: string) => {
    setConversations((current) => ({
      ...current,
      [view]: current[view].map((conversation) => (
        conversation.id === activeConversationIds[view]
          ? { ...conversation, messages: conversation.messages.filter((item) => item.content !== content) }
          : conversation
      )),
    }))
  }, [activeConversationIds])

  const api = useCallback(async <T,>(path: string, options?: RequestInit): Promise<T> => {
    setError('')
    const response = await fetch(`${API_BASE}${path}`, {
      headers: { 'Content-Type': 'application/json', ...(options?.headers ?? {}) },
      ...options,
    })
    if (!response.ok) throw new Error(await response.text())
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

  const refreshDashboard = useCallback(async (silent = false) => {
    try {
      if (!silent) begin('refresh', '桃子正在同步本地成长档案...')
      const data = await api<Dashboard>('/api/dashboard')
      setDashboard(data)
      if (!profileHydratedRef.current) {
        setProfileForm(toProfileForm(data.profile))
        profileHydratedRef.current = true
      }
      if (!silent) setNotice('档案同步完成。')
    } catch (err) {
      setError('后端暂时没有连上。确认 FastAPI 在 8000 端口运行后再刷新。')
      console.error(err)
    } finally {
      if (!silent) end('refresh')
    }
  }, [api, begin, end])

  useEffect(() => {
    void refreshDashboard()
  }, [refreshDashboard])

  useEffect(() => {
    if (!chatOpen) return
    const node = chatScrollRef.current
    if (!node) return
    requestAnimationFrame(() => {
      node.scrollTo({ top: node.scrollHeight, behavior: 'smooth' })
    })
  }, [activeMessages, activeInterview?.transcript, activeView, chatOpen])

  function switchTool(view: View) {
    setActiveView(view)
    setContextExpanded(false)
    setToolChatOpen((current) => ({ ...current, [view]: false }))
    setNotice(`已切换到「${navItems.find((item) => item.id === view)?.label}」。`)
  }

  function createConversation(view = activeView) {
    const id = `${view}-${Date.now()}`
    const title = navItems.find((item) => item.id === view)?.label ?? '新对话'
    setConversations((current) => ({
      ...current,
      [view]: [
        { id, title: `${title}新对话`, updatedAt: '刚刚', messages: initialMessages[view] },
        ...current[view],
      ],
    }))
    setActiveConversationIds((current) => ({ ...current, [view]: id }))
    setToolChatOpen((current) => ({ ...current, [view]: true }))
    setContextExpanded(false)
    if (view === 'interview') setActiveInterview(null)
    if (view === 'today') setPracticeFeedback(null)
    if (view === 'review') setReviewResult(null)
  }

  function openConversation(view: View, id: string) {
    setActiveConversationIds((current) => ({ ...current, [view]: id }))
    setToolChatOpen((current) => ({ ...current, [view]: true }))
    setContextExpanded(false)
  }

  async function saveProfile(event?: FormEvent) {
    event?.preventDefault()
    begin('profile', '已收到画像，桃子正在生成备战计划...')
    appendMessage('profile', { role: 'system', content: '画像已提交。生成计划时你可以继续看页面，不会卡住。' })
    try {
      const data = await api<{ greeting: string }>('/api/profile', {
        method: 'POST',
        body: JSON.stringify(profileForm),
      })
      appendMessage('profile', { role: 'peach', content: cleanAssistantText(data.greeting) })
      setNotice('备战计划已更新。')
      setProfileDraftOpen(false)
      await refreshDashboard(true)
    } catch (err) {
      setError('保存画像失败。你写的内容还在，可以稍后再试。')
      console.error(err)
    } finally {
      end('profile')
    }
  }

  async function submitPractice() {
    if (!task || !practiceAnswer.trim()) return
    const answerSnapshot = practiceAnswer
    setPracticeAnswer('')
    setToolChatOpen((current) => ({ ...current, today: true }))
    setContextExpanded(false)
    appendMessage('today', { role: 'user', content: answerSnapshot })
    appendMessage('today', { role: 'system', content: '回答已收到，桃子正在拆亮点和改进点。' })
    setPracticeFeedback({ summary: '桃子已收到你的回答，正在按“先肯定再建议”的方式拆解。' })
    begin('practice', '正在生成练习反馈...')
    try {
      const data = await api<{ feedback: PracticeFeedback }>('/api/practice', {
        method: 'POST',
        body: JSON.stringify({
          question: task.question,
          answer: answerSnapshot,
          tags: ['每日一练', dashboard?.profile.target_role],
        }),
      })
      setPracticeFeedback(data.feedback)
      removeToolMessage('today', '回答已收到，桃子正在拆亮点和改进点。')
      appendMessage('today', { role: 'peach', content: cleanAssistantText(data.feedback.summary ?? '反馈好了，我们再来一次也没问题。') })
      setNotice('练习反馈已沉淀到成长档案。')
      await refreshDashboard(true)
    } catch (err) {
      setPracticeAnswer(answerSnapshot)
      setError('练习提交失败，刚才的回答已经放回输入框。')
      console.error(err)
    } finally {
      end('practice')
    }
  }

  async function startInterview() {
    begin('interviewStart', '正在搭建模拟面试现场...')
    setActiveInterview(null)
    setToolChatOpen((current) => ({ ...current, interview: true }))
    setContextExpanded(false)
    try {
      const data = await api<{ interview: Interview }>('/api/interviews', {
        method: 'POST',
        body: JSON.stringify({
          ...interviewConfig,
          company: dashboard?.profile.target_company,
          role: dashboard?.profile.target_role,
        }),
      })
      setActiveInterview(data.interview)
      appendMessage('interview', { role: 'peach', content: '模拟面试开始。先稳住节奏，按真实面试来就好。' })
      setNotice('模拟面试已开始。')
      await refreshDashboard(true)
    } catch (err) {
      setError('模拟面试启动失败。')
      console.error(err)
    } finally {
      end('interviewStart')
    }
  }

  async function answerInterview() {
    if (!activeInterview || !interviewAnswer.trim()) return
    const answerSnapshot = interviewAnswer
    setInterviewAnswer('')
    setToolChatOpen((current) => ({ ...current, interview: true }))
    setContextExpanded(false)
    setActiveInterview({
      ...activeInterview,
      transcript: [
        ...activeInterview.transcript,
        { role: 'candidate', content: answerSnapshot },
        { role: 'interviewer', content: '收到，我在准备下一轮追问。' },
      ],
    })
    begin('interviewAnswer', '面试官正在追问...')
    try {
      const data = await api<{ interview: Interview }>(`/api/interviews/${activeInterview.id}/answer`, {
        method: 'POST',
        body: JSON.stringify({ answer: answerSnapshot }),
      })
      setActiveInterview(data.interview)
      await refreshDashboard(true)
    } catch (err) {
      setInterviewAnswer(answerSnapshot)
      setError('提交面试回答失败，刚才的回答已经放回输入框。')
      console.error(err)
    } finally {
      end('interviewAnswer')
    }
  }

  async function finishInterview() {
    if (!activeInterview) return
    begin('report', '正在生成完整面试报告...')
    try {
      const data = await api<{ interview: Interview }>(`/api/interviews/${activeInterview.id}/finish`, { method: 'POST' })
      setActiveInterview(data.interview)
      setNotice('报告生成好了。')
      await refreshDashboard(true)
    } catch (err) {
      setError('生成报告失败。')
      console.error(err)
    } finally {
      end('report')
    }
  }

  async function submitReview() {
    if (!reviewDraft.trim()) return
    const snapshot = reviewDraft
    setReviewDraft('')
    setToolChatOpen((current) => ({ ...current, review: true }))
    setContextExpanded(false)
    setReviewResult({ comfort: '收到。先缓口气，这里不会急着评判你。桃子正在把情绪、问题和下一步分开整理。' })
    appendMessage('review', { role: 'user', content: snapshot })
    appendMessage('review', { role: 'system', content: '桃子正在整理这场复盘...' })
    begin('review', '桃子先接住你的情绪，再帮你复盘...')
    try {
      const data = await api<{ review: ReviewFeedback }>('/api/review', {
        method: 'POST',
        body: JSON.stringify({
          company: dashboard?.profile.target_company,
          role: dashboard?.profile.target_role,
          feeling: snapshot,
          questions: snapshot,
          reflection: snapshot,
        }),
      })
      setReviewResult(data.review)
      removeToolMessage('review', '桃子正在整理这场复盘...')
      appendMessage('review', { role: 'peach', content: formatReviewReply(data.review) })
      setNotice('这次面试复盘已沉淀。')
      await refreshDashboard(true)
    } catch (err) {
      setReviewDraft(snapshot)
      removeToolMessage('review', '桃子正在整理这场复盘...')
      setError('复盘提交失败，内容已经放回输入框。')
      console.error(err)
    } finally {
      end('review')
    }
  }

  async function sendChat() {
    if (!chatInput.trim()) return
    const userMessage = chatInput
    setChatInput('')
    const targetView = activeView
    if (isPanelFirstView(targetView)) {
      setToolChatOpen((current) => ({ ...current, [targetView]: true }))
      setContextExpanded(false)
    }
    appendMessage(targetView, { role: 'user', content: userMessage })
    appendMessage(targetView, { role: 'system', content: '桃子正在回复。' })
    begin('chat', '桃子正在回复...')
    try {
      const data = await api<{ reply: string }>('/api/chat', {
        method: 'POST',
        body: JSON.stringify({ message: userMessage }),
      })
      removeToolMessage(targetView, '桃子正在回复。')
      appendMessage(targetView, { role: 'peach', content: cleanAssistantText(data.reply) })
    } catch (err) {
      setError('桃子刚刚掉线了一下，等后端恢复再聊。')
      console.error(err)
    } finally {
      end('chat')
    }
  }

  const composer = getComposer(activeView, {
    hasActiveInterview: Boolean(activeInterview && activeInterview.status !== 'completed'),
    practiceAnswer,
    interviewAnswer,
    reviewDraft,
    chatInput,
    isPracticeBusy: isBusy('practice'),
    isInterviewBusy: isBusy('interviewAnswer'),
    isReviewBusy: isBusy('review'),
    isChatBusy: isBusy('chat'),
    setPracticeAnswer,
    setInterviewAnswer,
    setReviewDraft,
    setChatInput,
    submitPractice,
    answerInterview,
    submitReview,
    sendChat,
  })

  function editMessageToComposer(content: string) {
    const text = cleanAssistantText(content)
    if (activeView === 'today') {
      setPracticeAnswer(text)
    } else if (activeView === 'interview' && activeInterview?.status !== 'completed') {
      setInterviewAnswer(text)
    } else if (activeView === 'review') {
      setReviewDraft(text)
    } else {
      setChatInput(text)
      if (isPanelFirstView(activeView)) {
        setToolChatOpen((current) => ({ ...current, [activeView]: true }))
        setContextExpanded(false)
      }
    }
  }

  return (
    <main className={sidebarCollapsed ? 'doubao-shell sidebar-collapsed' : 'doubao-shell'}>
      <aside className="tool-sidebar">
        <div className="brand-mini">
          <div className="brand-dot">桃</div>
          <div>
            <strong>桃子</strong>
            <span>求职陪练</span>
          </div>
          <button
            type="button"
            className="sidebar-toggle"
            onClick={() => setSidebarCollapsed(true)}
            aria-label="收起侧边栏"
          >
            收起
          </button>
        </div>
        <nav className="tool-list">
          {navItems.map((item) => (
            <button className={activeView === item.id ? 'tool-button active' : 'tool-button'} key={item.id} type="button" onClick={() => switchTool(item.id)}>
              <strong>{item.label}</strong>
              <span>{item.hint}</span>
            </button>
          ))}
        </nav>
        {dashboard ? (
          <ConversationRail
            activeView={activeView}
            conversations={conversations[activeView]}
            activeConversationId={activeConversationId}
            onNew={() => createConversation(activeView)}
            onOpen={(id) => openConversation(activeView, id)}
          />
        ) : null}
      </aside>

      <section className="chat-stage">
        {sidebarCollapsed ? (
          <button
            type="button"
            className="sidebar-expand"
            onClick={() => setSidebarCollapsed(false)}
            aria-label="展开侧边栏"
          >
            展开侧栏
          </button>
        ) : null}
        <header className="chat-topbar">
          <div>
            <p>{navItems.find((item) => item.id === activeView)?.hint}</p>
            <h1>{headerTitle(activeView, dashboard?.profile.name)}</h1>
          </div>
          <div className={busyText ? 'status-chip busy' : 'status-chip'}>{busyText || notice}</div>
        </header>

        {error && <div className="chat-error">{error}</div>}

        <section className={chatOpen ? 'stage-body chat-mode' : 'stage-body panel-mode'}>
          <div className={chatOpen ? 'stage-main chat-main' : 'stage-main panel-main'}>
            {!dashboard ? (
              <LoadingScreen />
            ) : !chatOpen ? (
              <WorkspacePanel
                activeView={activeView}
                dashboard={dashboard}
                progressWidth={progressWidth}
                practiceFeedback={practiceFeedback}
                activeInterview={activeInterview}
                interviewConfig={interviewConfig}
                profileForm={profileForm}
                profileDraftOpen={profileDraftOpen}
                reviewResult={reviewResult}
                isStarting={isBusy('interviewStart')}
                isReporting={isBusy('report')}
                isSavingProfile={isBusy('profile')}
                onConfigChange={setInterviewConfig}
                onStartInterview={startInterview}
                onFinishInterview={finishInterview}
                onProfileChange={setProfileForm}
                onSaveProfile={saveProfile}
                onOpenProfile={() => setProfileDraftOpen((value) => !value)}
              />
            ) : (
              <>
                <ContextStrip
                  activeView={activeView}
                  dashboard={dashboard}
                  expanded={contextExpanded}
                  progressWidth={progressWidth}
                  practiceFeedback={practiceFeedback}
                  activeInterview={activeInterview}
                  interviewConfig={interviewConfig}
                  profileForm={profileForm}
                  profileDraftOpen={profileDraftOpen}
                  reviewResult={reviewResult}
                  isStarting={isBusy('interviewStart')}
                  isReporting={isBusy('report')}
                  isSavingProfile={isBusy('profile')}
                  onToggleExpanded={() => setContextExpanded((value) => !value)}
                  onExitChat={panelFirst ? () => {
                    setToolChatOpen((current) => ({ ...current, [activeView]: false }))
                    setContextExpanded(false)
                  } : undefined}
                  onConfigChange={setInterviewConfig}
                  onStartInterview={startInterview}
                  onFinishInterview={finishInterview}
                  onProfileChange={setProfileForm}
                  onSaveProfile={saveProfile}
                  onOpenProfile={() => setProfileDraftOpen((value) => !value)}
                />
                <section className="chat-scroll" ref={chatScrollRef}>
                {activeMessages.map((item, index) => (
                  <Message
                    role={item.role}
                    messageKey={`${activeView}-${activeConversationId}-${index}`}
                    key={`${activeView}-${item.role}-${index}`}
                    onEdit={item.role === 'user' ? () => editMessageToComposer(item.content) : undefined}
                  >
                    {item.content}
                  </Message>
                ))}
                {activeView === 'interview' && activeInterview?.transcript.map((item, index) => (
                  <Message
                    role={item.role === 'candidate' ? 'user' : 'peach'}
                    messageKey={`interview-transcript-${index}`}
                    key={`${item.role}-${index}`}
                    onEdit={item.role === 'candidate' ? () => editMessageToComposer(item.content) : undefined}
                  >
                    {item.content}
                  </Message>
                ))}
                </section>
              </>
            )}
          </div>
        </section>

        <section className="composer-wrap">
          {!dashboard || (
            <>
              <div className="composer-tools">
                <span>{composer.caption}</span>
                {panelFirst && !chatOpen ? (
                  <button
                    type="button"
                    className="ghost-action"
                    onClick={() => {
                      setToolChatOpen((current) => ({ ...current, [activeView]: true }))
                      setContextExpanded(false)
                    }}
                  >
                    进入聊天模式
                  </button>
                ) : null}
                {activeView === 'interview' && activeInterview?.status !== 'completed' ? (
                  <button type="button" className="ghost-action" onClick={finishInterview} disabled={isBusy('report')}>
                    {isBusy('report') ? '报告生成中' : '结束并生成报告'}
                  </button>
                ) : null}
              </div>
              <div className="composer">
                <textarea rows={1} value={composer.value} onChange={(event) => composer.onChange(event.target.value)} onKeyDown={(event) => {
                  if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault()
                    void composer.onSubmit()
                  }
                }} placeholder={composer.placeholder} />
                <button type="button" onClick={composer.onSubmit} disabled={composer.disabled}>{composer.button}</button>
              </div>
            </>
          )}
        </section>
      </section>
    </main>
  )
}

function ToolCard({
  activeView,
  dashboard,
  progressWidth,
  practiceFeedback,
  activeInterview,
  interviewConfig,
  profileForm,
  profileDraftOpen,
  reviewResult,
  isStarting,
  isReporting,
  isSavingProfile,
  onConfigChange,
  onStartInterview,
  onFinishInterview,
  onProfileChange,
  onSaveProfile,
  onOpenProfile,
}: {
  activeView: View
  dashboard: Dashboard
  progressWidth: string
  practiceFeedback: PracticeFeedback | null
  activeInterview: Interview | null
  interviewConfig: { interview_type: string; interviewer_style: string }
  profileForm: typeof emptyProfile
  profileDraftOpen: boolean
  reviewResult: ReviewFeedback | null
  isStarting: boolean
  isReporting: boolean
  isSavingProfile: boolean
  onConfigChange: (value: { interview_type: string; interviewer_style: string }) => void
  onStartInterview: () => void
  onFinishInterview: () => void
  onProfileChange: (value: typeof emptyProfile) => void
  onSaveProfile: (event?: FormEvent) => void
  onOpenProfile: () => void
}) {
  if (activeView === 'today') {
    const task = dashboard.checkin.task
    const recentPractice = dashboard.recent_practices[0]
    return (
      <article className="tool-card rich-card today-panel">
        <div className="panel-hero">
          <div>
            <span>今日任务 · {task.duration}</span>
            <h2>{task.title}</h2>
            <p>{task.focus}</p>
          </div>
          <div className="hero-metric">
            <strong>{dashboard.growth.avg_score || '--'}</strong>
            <span>平均分</span>
          </div>
        </div>
        <div className="prompt-card prompt-card-large">{task.question}</div>
        <div className="panel-grid two-cols">
          <section className="detail-panel">
            <div className="mini-head">
              <span>陪练节奏</span>
              <Pill>{dashboard.profile.target_role}</Pill>
            </div>
            <div className="timeline-list">
              <div><span>01</span><strong>先给结论</strong><p>开头 15 秒把态度和判断讲清楚。</p></div>
              <div><span>02</span><strong>补一个证据</strong><p>用项目、数据或真实场景托住观点。</p></div>
              <div><span>03</span><strong>落到岗位</strong><p>收尾主动连接目标岗位和公司语境。</p></div>
            </div>
          </section>
          <section className="detail-panel soft-panel">
            <div className="mini-head">
              <span>成长信号</span>
              <Pill>{`${dashboard.growth.practice_count} 次练习`}</Pill>
            </div>
            <div className="mini-metrics">
              <Metric label="模拟" value={dashboard.growth.interview_count} />
              <Metric label="报告" value={dashboard.growth.completed_interview_count} />
            </div>
            <p className="tool-note">
              {recentPractice ? `最近一次练习：${recentPractice.question.slice(0, 42)}` : '完成一次今日陪练后，这里会显示最新反馈。'}
            </p>
          </section>
        </div>
        {practiceFeedback && <Feedback feedback={practiceFeedback} />}
      </article>
    )
  }

  if (activeView === 'interview') {
    const transcriptCount = activeInterview?.transcript.length ?? 0
    return (
      <article className="tool-card rich-card interview-panel">
        <div className="panel-hero interview-hero">
          <div>
            <span>模拟面试设置</span>
            <h2>先选类型和面试官风格</h2>
            <p>{dashboard.profile.target_company || '未指定公司'} · {dashboard.profile.target_role} · {dashboard.profile.stage}</p>
          </div>
          <button type="button" onClick={onStartInterview} disabled={isStarting}>{isStarting ? '生成中' : activeInterview ? '重新开始' : '开始模拟'}</button>
        </div>
        <div className="panel-grid two-cols">
          <section className="detail-panel settings-panel">
            <SegmentedControl label="面试类型" value={interviewConfig.interview_type} options={['行为面试', '产品思维', '业务分析', '群面模拟']} onChange={(interview_type) => onConfigChange({ ...interviewConfig, interview_type })} />
            <SegmentedControl label="面试官风格" value={interviewConfig.interviewer_style} options={['温和型', '专业型', '压力型']} onChange={(interviewer_style) => onConfigChange({ ...interviewConfig, interviewer_style })} />
          </section>
          <section className="detail-panel soft-panel">
            <div className="mini-head">
              <span>当前进度</span>
              <Pill>{activeInterview?.status === 'completed' ? '已完成' : activeInterview ? '进行中' : '未开始'}</Pill>
            </div>
            <div className="mini-metrics">
              <Metric label="轮次" value={Math.max(0, Math.floor(transcriptCount / 2))} />
              <Metric label="风格" value={interviewConfig.interviewer_style} />
            </div>
            <div className="radar-tags">
              {interviewFocus(interviewConfig.interview_type).map((item) => <span key={item}>{item}</span>)}
            </div>
          </section>
        </div>
        <section className="detail-panel candidate-panel">
          <div className="mini-head">
            <span>候选人快照</span>
            <Pill>{dashboard.profile.stage}</Pill>
          </div>
          <div className="profile-pills">
            <Pill>{dashboard.profile.target_role}</Pill>
            {dashboard.profile.target_company ? <Pill>{dashboard.profile.target_company}</Pill> : null}
            {(dashboard.profile.weak_points ?? []).slice(0, 2).map((item) => <span className="tag warm" key={item}>{item}</span>)}
          </div>
        </section>
        {activeInterview?.status === 'completed' ? <Report report={activeInterview.report} /> : null}
        {activeInterview && activeInterview.status !== 'completed' ? <button type="button" className="ghost-action" onClick={onFinishInterview} disabled={isReporting}>{isReporting ? '报告生成中' : '结束并生成报告'}</button> : null}
      </article>
    )
  }

  if (activeView === 'review') {
    const recentReview = dashboard.recent_practices.find((item) => item.tags.includes('面试复盘'))
    return (
      <article className="tool-card rich-card review-panel">
        <div className="panel-hero review-hero">
          <div>
            <span>面后复盘</span>
            <h2>把刚面完的混乱感，变成下一场的准备清单</h2>
            <p>{dashboard.profile.target_company || '目标公司待定'} · {dashboard.profile.target_role}</p>
          </div>
          <div className="hero-metric">
            <strong>{dashboard.growth.completed_interview_count}</strong>
            <span>份报告</span>
          </div>
        </div>
        <div className="review-lanes">
          <section>
            <span>情绪</span>
            <strong>先把状态放下来</strong>
            <p>紧张、懊恼、兴奋都可以直接写。</p>
          </section>
          <section>
            <span>题目</span>
            <strong>抓住卡点</strong>
            <p>记录被追问、没答顺、没证据的题。</p>
          </section>
          <section>
            <span>行动</span>
            <strong>沉淀下一步</strong>
            <p>把下一场能练的动作拆出来。</p>
          </section>
        </div>
        <section className="detail-panel soft-panel">
          <div className="mini-head">
            <span>最近沉淀</span>
            <Pill>{recentReview ? '已记录' : '等待复盘'}</Pill>
          </div>
          <p className="tool-note">
            {recentReview?.feedback?.archive ?? '提交一次复盘后，这里会留下可复用的面试经验。'}
          </p>
        </section>
        {reviewResult ? (
          <div className="feedback-box">
            <strong>{reviewResult.comfort}</strong>
            <ListBlock title="做得好的地方" items={reviewResult.what_went_well} />
            <ListBlock title="下一步改进" items={reviewResult.to_improve} />
            <ListBlock title="明天怎么练" items={reviewResult.next_actions} />
          </div>
        ) : null}
      </article>
    )
  }

  if (activeView === 'growth') {
    return (
      <article className="tool-card">
        <div className="growth-chat-grid">
          <div>
            <span>成长档案</span>
            <h2>{dashboard.growth.avg_score || '--'} 分</h2>
            <p className="tool-note">平均练习分。每次练习、模拟和复盘都会沉淀到这里。</p>
            <div className="progress-track"><div style={{ width: progressWidth }} /></div>
          </div>
          <div className="metric-grid">
            <Metric label="练习" value={dashboard.growth.practice_count} />
            <Metric label="模拟" value={dashboard.growth.interview_count} />
            <Metric label="报告" value={dashboard.growth.completed_interview_count} />
          </div>
        </div>
        <MemoryGroup title="优势" items={dashboard.growth.strengths} />
        <MemoryGroup title="待提升" items={dashboard.growth.weak_points} tone="warm" />
      </article>
    )
  }

  return (
    <article className="tool-card">
      <div className="tool-card-head">
        <div>
          <span>求职画像</span>
          <h2>告诉桃子你的目标和经历</h2>
        </div>
        <button type="button" className="ghost-action" onClick={onOpenProfile}>{profileDraftOpen ? '收起' : '编辑画像'}</button>
      </div>
      <div className="profile-pills">
        <Pill>{dashboard.profile.stage}</Pill>
        <Pill>{dashboard.profile.target_role}</Pill>
        {dashboard.profile.target_company && <Pill>{dashboard.profile.target_company}</Pill>}
      </div>
      {profileDraftOpen ? (
        <form className="profile-form compact" onSubmit={onSaveProfile}>
          <div className="form-grid">
            <label>昵称<input value={profileForm.name} onChange={(event) => onProfileChange({ ...profileForm, name: event.target.value })} /></label>
            <label>目标岗位<input value={profileForm.target_role} onChange={(event) => onProfileChange({ ...profileForm, target_role: event.target.value })} /></label>
            <label>目标公司<input value={profileForm.target_company} onChange={(event) => onProfileChange({ ...profileForm, target_company: event.target.value })} /></label>
            <label>求职阶段<select value={profileForm.stage} onChange={(event) => onProfileChange({ ...profileForm, stage: event.target.value })}><option>投递期</option><option>面试期</option><option>offer期</option></select></label>
          </div>
          <label>简历 / 经历摘要<textarea rows={7} value={profileForm.resume_text} onChange={(event) => onProfileChange({ ...profileForm, resume_text: event.target.value })} /></label>
          <button type="submit" disabled={isSavingProfile}>{isSavingProfile ? '生成中' : '保存并生成备战计划'}</button>
        </form>
      ) : (
        <div className="plan-list">
          {dashboard.profile.plan.map((item) => <div className="plan-item" key={`${item.day}-${item.title}`}><span>Day {item.day}</span><strong>{item.title}</strong><p>{item.focus}</p></div>)}
        </div>
      )}
    </article>
  )
}

function WorkspacePanel(props: Parameters<typeof ToolCard>[0]) {
  return (
    <div className="workspace-panel">
      <ToolCard {...props} />
    </div>
  )
}

function ConversationRail({
  activeView,
  conversations,
  activeConversationId,
  onNew,
  onOpen,
}: {
  activeView: View
  conversations: Conversation[]
  activeConversationId: string
  onNew: () => void
  onOpen: (id: string) => void
}) {
  return (
    <aside className="conversation-rail">
      <div className="conversation-rail-head">
        <span>历史对话</span>
        <button type="button" onClick={onNew}>新建</button>
      </div>
      <div className="conversation-list">
        {conversations.map((conversation) => (
          <button
            className={conversation.id === activeConversationId ? 'conversation-item active' : 'conversation-item'}
            key={conversation.id}
            type="button"
            onClick={() => onOpen(conversation.id)}
          >
            <strong>{conversation.title}</strong>
            <span>{conversation.updatedAt} · {navItems.find((item) => item.id === activeView)?.label}</span>
          </button>
        ))}
      </div>
    </aside>
  )
}

function ContextStrip({
  expanded,
  onToggleExpanded,
  onExitChat,
  ...toolProps
}: Parameters<typeof ToolCard>[0] & {
  expanded: boolean
  onToggleExpanded: () => void
  onExitChat?: () => void
}) {
  return (
    <section className={expanded ? 'context-strip expanded' : 'context-strip'}>
      <div
        className="context-summary"
        role="button"
        tabIndex={0}
        onClick={onExitChat ?? onToggleExpanded}
        onKeyDown={(event) => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault()
            ;(onExitChat ?? onToggleExpanded)()
          }
        }}
      >
        <div>
          <span>{navItems.find((item) => item.id === toolProps.activeView)?.label}</span>
          <strong>{contextSummary(toolProps.activeView, toolProps.dashboard)}</strong>
        </div>
        <div className="context-actions">
          <button type="button" className="ghost-action" onClick={(event) => {
            event.stopPropagation()
            onToggleExpanded()
          }}>
            {expanded ? '收起面板' : '展开面板'}
          </button>
          {onExitChat ? (
            <button type="button" className="ghost-action" onClick={(event) => {
              event.stopPropagation()
              onExitChat()
            }}>回到面板</button>
          ) : null}
        </div>
      </div>
      {expanded ? <ToolCard {...toolProps} /> : null}
    </section>
  )
}

function getComposer(view: View, params: {
  hasActiveInterview: boolean
  practiceAnswer: string
  interviewAnswer: string
  reviewDraft: string
  chatInput: string
  isPracticeBusy: boolean
  isInterviewBusy: boolean
  isReviewBusy: boolean
  isChatBusy: boolean
  setPracticeAnswer: (value: string) => void
  setInterviewAnswer: (value: string) => void
  setReviewDraft: (value: string) => void
  setChatInput: (value: string) => void
  submitPractice: () => Promise<void>
  answerInterview: () => Promise<void>
  submitReview: () => Promise<void>
  sendChat: () => Promise<void>
}) {
  if (view === 'today') return {
    value: params.practiceAnswer,
    onChange: params.setPracticeAnswer,
    onSubmit: params.submitPractice,
    placeholder: '像真实面试一样回答今天这道题...',
    button: params.isPracticeBusy ? '反馈中' : '提交练习',
    disabled: params.isPracticeBusy || !params.practiceAnswer.trim(),
    caption: 'Shift + Enter 换行，Enter 提交',
  }
  if (view === 'interview' && params.hasActiveInterview) {
    return {
      value: params.interviewAnswer,
      onChange: params.setInterviewAnswer,
      onSubmit: params.answerInterview,
      placeholder: '回答面试官的问题...',
      button: params.isInterviewBusy ? '追问中' : '发送回答',
      disabled: params.isInterviewBusy || !params.interviewAnswer.trim(),
      caption: '模拟面试模式',
    }
  }
  if (view === 'interview') {
    return {
      value: params.chatInput,
      onChange: params.setChatInput,
      onSubmit: params.sendChat,
      placeholder: '可以先问桃子怎么准备这场模拟，或点击上方开始模拟...',
      button: params.isChatBusy ? '回复中' : '发送',
      disabled: params.isChatBusy || !params.chatInput.trim(),
      caption: '未开始模拟时，这里是普通聊天',
    }
  }
  if (view === 'review') return {
    value: params.reviewDraft,
    onChange: params.setReviewDraft,
    onSubmit: params.submitReview,
    placeholder: '面完感觉怎么样？问了什么？哪里卡住了？',
    button: params.isReviewBusy ? '复盘中' : '提交复盘',
    disabled: params.isReviewBusy || !params.reviewDraft.trim(),
    caption: '先情绪，后复盘',
  }
  return {
    value: params.chatInput,
    onChange: params.setChatInput,
    onSubmit: params.sendChat,
    placeholder: '问桃子任何求职、面试、情绪相关的问题...',
    button: params.isChatBusy ? '回复中' : '发送',
    disabled: params.isChatBusy || !params.chatInput.trim(),
    caption: view === 'growth' ? '可以追问某个薄弱点怎么练' : '可以让桃子帮你改画像或生成计划',
  }
}

function Message({
  role,
  children,
  messageKey,
  onEdit,
}: {
  role: ChatMessage['role']
  children: string
  messageKey: string
  onEdit?: () => void
}) {
  const text = cleanAssistantText(children)

  async function copyMessage() {
    try {
      await navigator.clipboard.writeText(text)
    } catch {
      // Clipboard may be blocked in some browsers; selection still works.
    }
  }

  return (
    <div className={`message-row ${role}`} data-message-key={messageKey}>
      <div className="message-stack">
        <div className="message-bubble">{text}</div>
        <div className="message-actions">
          <button type="button" onClick={copyMessage}>复制</button>
          {onEdit ? <button type="button" onClick={onEdit}>编辑</button> : null}
        </div>
      </div>
    </div>
  )
}

function Feedback({ feedback }: { feedback: PracticeFeedback }) {
  return (
    <div className="feedback-box">
      <strong>{feedback.summary}</strong>
      <ListBlock title="亮点" items={feedback.highlights} />
      <ListBlock title="再上一层楼" items={feedback.improvements} />
      {feedback.reference_answer && <p className="reference">{feedback.reference_answer}</p>}
      {feedback.next_task && <p className="next-task">{feedback.next_task}</p>}
    </div>
  )
}

function Report({ report }: { report: InterviewReport }) {
  return (
    <div className="report">
      <h2>完整报告 · {report.overall_score ?? '--'} 分</h2>
      <p>{report.summary}</p>
      <div className="dimension-grid">{(report.dimensions ?? []).map((item) => <Metric key={item.name} label={item.name} value={item.score} />)}</div>
      <ListBlock title="重点提升" items={report.key_improvements} />
      <ListBlock title="后续计划" items={report.next_plan} />
    </div>
  )
}

function SegmentedControl({ label, value, options, onChange }: { label: string; value: string; options: string[]; onChange: (value: string) => void }) {
  return (
    <div className="segmented-field">
      <span>{label}</span>
      <div className="segmented-control">{options.map((option) => <button className={value === option ? 'selected' : ''} key={option} type="button" onClick={() => onChange(option)}>{option}</button>)}</div>
    </div>
  )
}

function ListBlock({ title, items }: { title: string; items?: string[] }) {
  if (!items?.length) return null
  return <div className="list-block"><h4>{title}</h4><ul>{items.map((item) => <li key={item}>{item}</li>)}</ul></div>
}

function MemoryGroup({ title, items, tone }: { title: string; items: string[]; tone?: 'warm' }) {
  return <div className="memory-group"><h3>{title}</h3><div className="tag-list">{items.length ? items.map((item) => <span className={tone === 'warm' ? 'tag warm' : 'tag'} key={item}>{item}</span>) : <p>还没有记录</p>}</div></div>
}

function Metric({ label, value }: { label: string; value: number | string }) {
  return <div className="metric"><strong>{value}</strong><span>{label}</span></div>
}

function Pill({ children }: { children: string | number }) {
  return <span className="pill">{children}</span>
}

function LoadingScreen() {
  return <div className="loading-screen"><div className="loader" /><strong>桃子正在整理今天的陪练节奏</strong><p>首屏只读取本地成长档案。</p></div>
}

function headerTitle(view: View, name = '同学') {
  const titles: Record<View, string> = {
    today: `${name}的今日陪练`,
    interview: '模拟面试',
    review: '面后复盘',
    growth: '成长档案',
    profile: '求职画像',
  }
  return titles[view]
}

function isPanelFirstView(view: View) {
  return ['today', 'interview', 'review', 'growth', 'profile'].includes(view)
}

function contextSummary(view: View, dashboard: Dashboard) {
  if (view === 'growth') {
    return `${dashboard.growth.avg_score || 0} 分 · ${dashboard.growth.practice_count} 次练习 · ${dashboard.growth.interview_count} 次模拟`
  }
  if (view === 'profile') {
    const company = dashboard.profile.target_company ? ` · ${dashboard.profile.target_company}` : ''
    return `${dashboard.profile.stage} · ${dashboard.profile.target_role}${company}`
  }
  if (view === 'today') {
    return dashboard.checkin.task.title
  }
  if (view === 'interview') {
    return dashboard.profile.target_role
  }
  return '面试后的情绪和经验沉淀'
}

function interviewFocus(type: string) {
  const focus: Record<string, string[]> = {
    行为面试: ['STAR 结构', '冲突沟通', '结果量化'],
    产品思维: ['用户洞察', '需求判断', '方案取舍'],
    业务分析: ['指标拆解', '增长假设', '商业判断'],
    群面模拟: ['角色定位', '推进节奏', '协作表达'],
  }
  return focus[type] ?? ['表达逻辑', '岗位匹配', '临场稳定']
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

function formatReviewReply(review: ReviewFeedback) {
  const sections = [
    review.comfort,
    formatSection('做得好的地方', review.what_went_well),
    formatSection('下一步改进', review.to_improve),
    review.archive ? `这次可以沉淀成：${review.archive}` : '',
    formatSection('明天怎么练', review.next_actions),
  ].filter(Boolean)

  return cleanAssistantText(sections.join('\n\n') || '复盘好了。我们把这次面试拆成了情绪、经验和下一步行动。')
}

function formatSection(title: string, items?: string[]) {
  if (!items?.length) return ''
  return `${title}\n${items.map((item) => `• ${item}`).join('\n')}`
}

function toProfileForm(profile: Profile) {
  return {
    name: profile.name,
    target_role: profile.target_role,
    target_company: profile.target_company,
    target_city: profile.target_city,
    stage: profile.stage,
    resume_text: profile.resume_text,
    communication_style: profile.communication_style,
  }
}

export default App
