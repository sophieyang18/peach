import json
from typing import Any

from openai import AsyncOpenAI

from backend.app.core.config import get_settings
from backend.app.models import InterviewSession, UserProfile


PEACH_PERSONA = """
你是「桃子」，一个刚上岸大厂的求职面试搭子。你温暖、靠谱、有点幽默，像朋友聊天。
你会先保护用户信心，再指出清晰可执行的改进点；用户焦虑或失落时，先共情再复盘。
不要使用“您好”“请问”这种客服腔。可以自然使用“冲”“没问题的”“我们再来一次”。
输出要具体，避免空泛鸡汤。面试反馈必须包含亮点、可改进点、下一步练习。
聊天回复必须像即时对话，不要写成公众号文章或长篇报告。
不要使用 Markdown 格式，不要用加粗标记、标题符号、代码块或表格。
除非用户明确要求详细方案，否则每次回复控制在 3-6 个短段，每段 1-3 句话。
可以给清单，但清单最多 3 项，且用自然语言，不要堆格式。
"""

AGENT_TOOLS = [
    {
        "tool": "start_interview",
        "description": "创建一场模拟面试或题库练习。适合用户说想针对某家公司、岗位、JD、题库、简历做面试。需要用户审批。",
        "payload": {
            "interview_type": "模拟面试",
            "interviewer_style": "温和型",
            "company": "",
            "role": "",
            "jd": "",
            "question_bank": "",
        },
    },
    {
        "tool": "finish_latest_interview",
        "description": "结束最近一场进行中的面试并生成报告。需要用户审批。",
        "payload": {},
    },
    {
        "tool": "update_profile_fields",
        "description": "更新姓名、目标岗位、目标公司、城市、阶段、沟通偏好。需要用户审批。",
        "payload": {"fields": {"target_role": "产品经理"}},
    },
    {
        "tool": "update_resume",
        "description": "替换或追加完整简历文本。适合用户明确要求写简历、优化简历、把上传简历作为主简历。payload.content 应直接给出可保存的简历正文。需要用户审批。",
        "payload": {"mode": "append", "content": "", "reason": ""},
    },
    {
        "tool": "append_profile_note",
        "description": "把一段内容沉淀到个人档案的某个分区。section 可选 reviews/full/internship/project/education/skills/competition。payload.content 应是整理后的可保存内容。需要用户审批。",
        "payload": {"section": "project", "title": "项目经历", "content": "", "reason": ""},
    },
    {
        "tool": "add_knowledge_item",
        "description": "向个人知识库添加一条求职资料、论文、JD、题库、链接或笔记。适合用户上传文件后希望留作知识载体。需要用户审批。",
        "payload": {"title": "", "summary": "", "content": "", "url": "", "reason": ""},
    },
    {
        "tool": "update_knowledge_item",
        "description": "更新个人知识库里已有的一条资料。需要用户审批。",
        "payload": {"id": "", "title": "", "summary": "", "content": "", "url": ""},
    },
    {
        "tool": "delete_knowledge_item",
        "description": "删除个人知识库里已有的一条资料。需要用户审批。",
        "payload": {"id": ""},
    },
]


class PeachAgent:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.client: AsyncOpenAI | None = None

    def get_client(self) -> AsyncOpenAI | None:
        if not self.settings.deepseek_api_key:
            return None
        if self.client:
            return self.client
        try:
            self.client = AsyncOpenAI(
                api_key=self.settings.deepseek_api_key,
                base_url=self.settings.deepseek_base_url,
            )
        except ImportError:
            self.client = None
        return self.client

    async def complete(self, messages: list[dict[str, str]], fallback: str) -> str:
        client = self.get_client()
        if not client:
            return fallback

        try:
            response = await client.chat.completions.create(
                model=self.settings.deepseek_model,
                messages=[{"role": "system", "content": PEACH_PERSONA}, *messages],
                temperature=0.7,
            )
            return response.choices[0].message.content or fallback
        except Exception:
            return fallback

    async def json_complete(
        self,
        messages: list[dict[str, str]],
        fallback: dict[str, Any],
    ) -> dict[str, Any]:
        content = await self.complete(
            [
                *messages,
                {
                    "role": "user",
                    "content": "请只输出严格 JSON，不要 markdown 代码块，不要额外解释。",
                },
            ],
            json.dumps(fallback, ensure_ascii=False),
        )
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return fallback

    async def initialize_profile(self, profile: UserProfile) -> dict[str, Any]:
        resume_text = profile.resume_text or ""
        fallback = {
            "strengths": ["表达愿望明确", "目标岗位聚焦", "愿意持续练习"],
            "weak_points": ["简历亮点需要进一步量化", "回答结构需要稳定", "面试前容易紧张"],
            "plan": [
                {"day": 1, "title": "30 秒自我介绍", "focus": "把经历、目标和岗位连接起来"},
                {"day": 2, "title": "STAR 行为题", "focus": "用结果和数据支撑故事"},
                {"day": 3, "title": "产品思维题", "focus": "先框架后细节，避免想到哪说到哪"},
            ],
            "greeting": f"{profile.name}，我是桃子。接下来这段求职季我陪你一起冲，我们先把节奏稳住。",
        }
        prompt = f"""
基于下面用户资料，生成求职陪练初始化结果。
姓名：{profile.name}
目标岗位：{profile.target_role}
目标公司：{profile.target_company}
城市：{profile.target_city}
阶段：{profile.stage}
沟通偏好：{profile.communication_style}
简历：{resume_text[:3000]}

JSON 字段：strengths(list[str]), weak_points(list[str]), plan(list[{{day,title,focus}}]), greeting(str)
"""
        return await self.json_complete([{"role": "user", "content": prompt}], fallback)

    async def daily_checkin(self, profile: UserProfile, recent_records: list[Any]) -> dict[str, Any]:
        fallback = {
            "message": f"{profile.name}，今天状态怎么样？我们用 8 分钟练一道和{profile.target_role}有关的题，轻轻启动一下。",
            "task": {
                "title": "每日一练：自我介绍开场",
                "question": f"请用 1 分钟介绍你自己，并说明为什么你适合{profile.target_role}。",
                "duration": "5-10 分钟",
                "focus": "开头 30 秒要稳：身份、亮点、岗位匹配三件事讲清楚。",
            },
        }
        recent = "\n".join(
            f"- {item.question[:80]} / {item.score}分 / {item.feedback}" for item in recent_records
        )
        prompt = f"""
为用户生成今天的陪伴式 check-in 和一个练习任务。
用户：{profile.name}，目标：{profile.target_role}，公司：{profile.target_company}，阶段：{profile.stage}
优势：{profile.strengths or []}
薄弱点：{profile.weak_points or []}
近期练习：{recent or "暂无"}

JSON 字段：message(str), task({{title, question, duration, focus}})
"""
        return await self.json_complete([{"role": "user", "content": prompt}], fallback)

    async def evaluate_practice(self, profile: UserProfile, question: str, answer: str) -> dict[str, Any]:
        fallback = {
            "score": 78,
            "summary": "整体方向是对的，信息也够真诚。下一步要把表达压得更有结构。",
            "highlights": ["能回应题目核心", "有个人经历支撑", "语气比较自然"],
            "improvements": ["补充可量化结果", "先给结论再展开", "收尾时主动连接目标岗位"],
            "reference_answer": "我会先用一句话给出结论，再用一个经历证明能力，最后落到目标岗位的匹配点。",
            "next_task": "再练一次同题，把回答控制在 90 秒内，并至少加入一个数字结果。",
        }
        prompt = f"""
请以桃子的语气评估一次面试练习。先肯定，再给建议。
用户目标岗位：{profile.target_role}
薄弱点：{profile.weak_points or []}
题目：{question}
用户回答：{answer}

JSON 字段：score(int 0-100), summary(str), highlights(list[str]), improvements(list[str]), reference_answer(str), next_task(str)
"""
        return await self.json_complete([{"role": "user", "content": prompt}], fallback)

    async def start_interview(
        self,
        profile: UserProfile,
        session: InterviewSession,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        resume_text = profile.resume_text or ""
        context = context or {}
        fallback = {
            "opening": f"好，我们开始一场{session.interviewer_style}的{session.interview_type}模拟。先别急，按真实面试来就行。",
            "question": f"请先做一个 1 分钟自我介绍，并重点讲讲你和{session.role or profile.target_role}最匹配的一段经历。",
            "rubric": ["表达逻辑", "岗位匹配", "经历可信度", "临场稳定性"],
        }
        prompt = f"""
生成模拟面试开场和第一题。
用户目标：{profile.target_role}，目标公司：{session.company or profile.target_company}
面试类型：{session.interview_type}
面试官风格：{session.interviewer_style}
简历：{resume_text[:2200]}
岗位 JD：{str(context.get("jd") or "")[:2200]}
题库材料：{str(context.get("question_bank") or "")[:2200]}
薄弱点：{profile.weak_points or []}

JSON 字段：opening(str), question(str), rubric(list[str])
"""
        return await self.json_complete([{"role": "user", "content": prompt}], fallback)

    async def continue_interview(self, profile: UserProfile, session: InterviewSession, answer: str) -> dict[str, Any]:
        fallback = {
            "micro_feedback": "这题你没有跑偏，经历也讲出来了。下一轮我们把追问压力稍微加一点。",
            "next_question": "如果面试官质疑这个项目结果不是你主导的，你会怎么回应？",
            "hint": "可以按事实边界、个人贡献、协作价值三个层次回答。",
            "should_finish": len(session.transcript) >= 5,
        }
        prompt = f"""
继续一场模拟面试。根据用户刚才回答，给一句短反馈，再追问下一题。
用户目标：{profile.target_role}
面试风格：{session.interviewer_style}
历史对话：{(session.transcript or [])[-6:]}
用户最新回答：{answer}

JSON 字段：micro_feedback(str), next_question(str), hint(str), should_finish(bool)
"""
        return await self.json_complete([{"role": "user", "content": prompt}], fallback)

    async def interview_report(self, profile: UserProfile, session: InterviewSession) -> dict[str, Any]:
        fallback = {
            "overall_score": 80,
            "dimensions": [
                {"name": "表达逻辑", "score": 82},
                {"name": "专业深度", "score": 76},
                {"name": "应变能力", "score": 78},
                {"name": "岗位匹配", "score": 84},
            ],
            "summary": "整体表现稳定，回答有真实经历支撑。继续强化结构化表达和追问应对，会更像真实候选人。",
            "key_improvements": ["每题先给结论", "把项目结果数字化", "压力追问时先稳住事实边界"],
            "next_plan": ["复练自我介绍", "准备 2 个 STAR 故事", "做一次压力型追问练习"],
        }
        prompt = f"""
为这场模拟面试生成完整报告。
用户目标：{profile.target_role}
会话：{session.transcript}

JSON 字段：overall_score(int), dimensions(list[{{name,score}}]), summary(str), key_improvements(list[str]), next_plan(list[str])
"""
        return await self.json_complete([{"role": "user", "content": prompt}], fallback)

    async def post_interview_review(self, profile: UserProfile, payload: dict[str, str]) -> dict[str, Any]:
        fallback = {
            "comfort": "面完先歇口气，能把这场走下来就已经很不容易了。我们慢慢拆，不急着否定自己。",
            "what_went_well": ["你能记住关键问题，说明临场注意力在线", "愿意复盘，这本身就会让下一场更稳"],
            "to_improve": ["把卡住的问题整理成固定答题框架", "补齐岗位相关案例和数据"],
            "archive": "这次面试沉淀为：重点复盘问题、回答卡点、下一场要提前准备的证据。",
            "next_actions": ["今天只整理问题清单", "明天复练最卡的一题", "后天做一次 20 分钟模拟"],
        }
        prompt = f"""
用户真实面试后找桃子复盘。请先情绪疏导，再复盘。
用户目标：{profile.target_role}
面试信息：{payload}

JSON 字段：comfort(str), what_went_well(list[str]), to_improve(list[str]), archive(str), next_actions(list[str])
"""
        return await self.json_complete([{"role": "user", "content": prompt}], fallback)

    async def chat(self, profile: UserProfile, message: str) -> str:
        fallback = f"我在。你刚刚说“{message[:60]}”，我们先把这件事拆小一点：你现在最想解决的是准备题目、复盘表现，还是先缓一缓情绪？"
        prompt = f"""
用户正在和求职搭子桃子聊天。
用户：{profile.name}，目标：{profile.target_role}，阶段：{profile.stage}
优势：{profile.strengths or []}
薄弱点：{profile.weak_points or []}
用户消息：{message}
"""
        return await self.complete([{"role": "user", "content": prompt}], fallback)

    async def plan_actions(self, profile: UserProfile, message: str, context: dict[str, Any]) -> dict[str, Any]:
        fallback = local_action_plan(profile, message, context)
        uploaded_file = context.get("uploaded_file") if isinstance(context, dict) else None
        prompt = f"""
你正在和用户聊天。你可以正常回复，也可以在确实有帮助时提出待用户审批的工具动作。
所有工具动作必须先让用户确认，不能直接执行。
不要为了显得智能而乱提动作。只有当用户明确表达要开始面试、结束面试、改档案、改简历、添加知识资料，或上传文件且意图明显时才提出动作。
如果用户上传了文件，你要先判断文件更适合作为知识库资料、简历、项目/实习经历、面试题库还是 JD。可以同时提出 1-3 个动作，但必须解释每个动作会改哪里。
当用户说“优化简历”“帮我改简历”，payload.content 要给出整理后的可保存简历内容，而不是只把原话塞进去。
当用户说“针对某家公司/某类公司/某岗位模拟面试”，尽量从用户话里提取 company、role、interviewer_style、interview_type、jd，并提出 start_interview。
当用户说“把这个存起来”“以后参考”“加入知识库”，优先提出 add_knowledge_item。
当用户说“补到项目/实习/教育/技能/竞赛/复盘”，优先提出 append_profile_note 并选择正确 section。

可用工具：
{json.dumps(AGENT_TOOLS, ensure_ascii=False)}

用户档案：
姓名：{profile.name}
目标岗位：{profile.target_role}
目标公司：{profile.target_company}
城市：{profile.target_city}
阶段：{profile.stage}
沟通偏好：{profile.communication_style}
优势：{profile.strengths or []}
薄弱点：{profile.weak_points or []}
当前完整简历片段：
{(profile.resume_text or "")[:2600] or "暂无"}

本次上传文件：
{json.dumps(uploaded_file, ensure_ascii=False)[:8000] if uploaded_file else "无"}

前端上下文：
{json.dumps(context, ensure_ascii=False)[:2600]}

用户消息：
{message}

请输出 JSON：
reply: string, 像桃子一样自然回复，简短说明建议
actions: list, 每个动作包含 tool, title, summary, payload, approval_required
"""
        data = await self.json_complete([{"role": "user", "content": prompt}], fallback)
        if not isinstance(data.get("actions"), list):
            data["actions"] = []
        data["actions"] = hydrate_uploaded_file_actions(data["actions"], uploaded_file)
        return data


def local_action_plan(profile: UserProfile, message: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    text = message.strip()
    actions: list[dict[str, Any]] = []
    context = context or {}
    uploaded = context.get("uploaded_file")
    file_title = ""
    file_summary = ""
    file_content = ""
    if isinstance(uploaded, dict):
        file_title = str(uploaded.get("title") or uploaded.get("filename") or "上传文件")
        file_summary = str(uploaded.get("summary") or "")
        file_content = str(uploaded.get("content") or "")

    material = file_content or text
    lower = text.lower()

    if any(word in text for word in ["结束面试", "生成报告", "面试报告"]):
        actions.append(
            {
                "tool": "finish_latest_interview",
                "title": "结束最近一场面试",
                "summary": "结束进行中的模拟面试，并生成一份复盘报告。",
                "payload": {},
                "approval_required": True,
            }
        )
    elif "面试" in text and any(word in text for word in ["开始", "来一场", "模拟", "练", "针对"]):
        company = infer_company(text, profile.target_company or "")
        role = infer_role(text, profile.target_role)
        actions.append(
            {
                "tool": "start_interview",
                "title": "创建模拟面试",
                "summary": f"按{company or '目标公司'}、{role}方向创建一场模拟面试。",
                "payload": {
                    "interview_type": "模拟面试",
                    "interviewer_style": infer_interviewer_style(text),
                    "company": company,
                    "role": role,
                    "jd": file_content[:4000] if file_content and any(word in text for word in ["jd", "JD", "岗位", "招聘"]) else "",
                    "question_bank": file_content[:4000] if file_content and any(word in text for word in ["题库", "题目"]) else "",
                },
                "approval_required": True,
            }
        )
    elif any(word in text for word in ["改简历", "优化简历", "写简历"]):
        actions.append(
            {
                "tool": "update_resume",
                "title": "更新完整简历",
                "summary": "把当前材料整理进完整简历草稿，确认后会更新个人档案里的完整简历。",
                "payload": {
                    "mode": "replace" if file_content else "append",
                    "content": material[:12000],
                    "reason": "用户要求优化或撰写简历",
                },
                "approval_required": True,
            }
        )
    elif file_content and any(word in text for word in ["项目", "实习", "教育", "技能", "竞赛", "复盘", "档案", "经历"]):
        section, title = infer_profile_section(text)
        actions.append(
            {
                "tool": "append_profile_note",
                "title": f"补充{title}",
                "summary": f"把上传文件整理后加入{title}，之后简历生成和面试会参考它。",
                "payload": {"section": section, "title": title, "content": material[:12000], "reason": "用户上传材料用于补充档案"},
                "approval_required": True,
            }
        )
    elif any(word in text for word in ["档案", "记录一下", "沉淀"]):
        actions.append(
            {
                "tool": "append_profile_note",
                "title": "补充个人档案",
                "summary": "把这段内容加入个人档案，后续模拟和推荐会参考它。",
                "payload": {"section": "full", "title": "完整简历", "content": material[:12000], "reason": "用户要求沉淀到档案"},
                "approval_required": True,
            }
        )
    elif "删除" in text and "知识库" in text:
        actions.append(
            {
                "tool": "delete_knowledge_item",
                "title": "删除知识库资料",
                "summary": "删除前会再次让你确认，避免误删资料。",
                "payload": {"id": ""},
                "approval_required": True,
            }
        )
    elif file_content or any(word in text for word in ["知识库", "资料", "链接", "保存", "存起来", "以后参考"]):
        actions.append(
            {
                "tool": "add_knowledge_item",
                "title": "添加到个人知识库",
                "summary": "把这条资料放进个人知识库，之后可以在对话中引用。",
                "payload": {
                    "title": file_title or text[:30] or "求职资料",
                    "summary": file_summary or text[:160],
                    "content": material[:20000],
                    "url": text if lower.startswith(("http://", "https://")) else "",
                    "reason": "用户上传或提供了可复用资料",
                },
                "approval_required": True,
            }
        )

    return {
        "reply": "我读完了，先给你整理成可确认的动作。你点确认后我再真正修改档案、简历或知识库。",
        "actions": actions,
    }


def infer_interviewer_style(text: str) -> str:
    if any(word in text for word in ["压力", "严格", "拷打", "挑战"]):
        return "压力型"
    if any(word in text for word in ["专业", "深挖", "资深"]):
        return "专业深挖型"
    if any(word in text for word in ["温和", "友好", "基础"]):
        return "温和型"
    return "温和型"


def infer_company(text: str, fallback: str) -> str:
    for marker in ["针对", "模拟", "面试", "公司"]:
        text = text.replace(marker, " ")
    candidates = ["字节跳动", "腾讯", "阿里", "百度", "美团", "快手", "小红书", "京东", "拼多多", "华为", "米哈游"]
    for company in candidates:
        if company in text:
            return company
    if "大厂" in text:
        return "互联网大厂"
    if "外企" in text:
        return "外企"
    if "创业" in text:
        return "创业公司"
    return fallback


def infer_role(text: str, fallback: str) -> str:
    role_keywords = ["产品经理", "策略产品", "AIGC 产品", "AI 产品", "数据产品", "运营", "算法", "前端", "后端", "数据分析"]
    for role in role_keywords:
        if role in text:
            return role
    return fallback


def infer_profile_section(text: str) -> tuple[str, str]:
    if "复盘" in text:
        return "reviews", "面试复盘"
    if "实习" in text:
        return "internship", "实习经历"
    if "项目" in text:
        return "project", "项目经历"
    if "教育" in text or "学校" in text:
        return "education", "教育背景"
    if "技能" in text:
        return "skills", "个人技能"
    if "竞赛" in text or "比赛" in text:
        return "competition", "竞赛经历"
    return "full", "完整简历"


def hydrate_uploaded_file_actions(actions: list[Any], uploaded_file: Any) -> list[Any]:
    if not isinstance(uploaded_file, dict):
        return actions
    content = str(uploaded_file.get("content") or "").strip()
    if not content:
        return actions
    title = str(uploaded_file.get("title") or uploaded_file.get("filename") or "上传文件")
    summary = str(uploaded_file.get("summary") or content[:300])
    hydrated: list[Any] = []
    for action in actions:
        if not isinstance(action, dict):
            hydrated.append(action)
            continue
        payload = action.get("payload")
        if not isinstance(payload, dict):
            payload = {}
        tool = str(action.get("tool") or "")
        if tool == "add_knowledge_item":
            payload = {
                **payload,
                "title": str(payload.get("title") or title)[:160],
                "summary": str(payload.get("summary") or summary)[:600],
                "content": content,
            }
        elif tool == "append_profile_note" and len(str(payload.get("content") or "")) < 300:
            payload = {
                **payload,
                "title": str(payload.get("title") or title),
                "content": content,
            }
        elif tool == "start_interview":
            lower_title = title.lower()
            if any(word in lower_title for word in ["jd", "岗位", "招聘"]):
                payload = {**payload, "jd": str(payload.get("jd") or content[:6000])}
            if any(word in lower_title for word in ["题库", "question", "面试题"]):
                payload = {**payload, "question_bank": str(payload.get("question_bank") or content[:6000])}
        action["payload"] = payload
        hydrated.append(action)
    return hydrated
