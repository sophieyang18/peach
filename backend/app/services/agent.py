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
不要使用 Markdown 格式，不要用 **加粗**、标题符号、代码块或表格。
除非用户明确要求详细方案，否则每次回复控制在 3-6 个短段，每段 1-3 句话。
可以给清单，但清单最多 3 项，且用自然语言，不要堆格式。
"""


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

    async def start_interview(self, profile: UserProfile, session: InterviewSession) -> dict[str, Any]:
        resume_text = profile.resume_text or ""
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
