from pydantic import BaseModel, Field


class AccountIn(BaseModel):
    username: str


class ProfileIn(BaseModel):
    name: str = "同学"
    target_role: str = "产品经理"
    target_company: str = ""
    target_city: str = ""
    stage: str = "投递期"
    resume_text: str = ""
    communication_style: str = "温暖直接"


class ProfileOut(ProfileIn):
    id: str
    strengths: list[str]
    weak_points: list[str]
    plan: list[dict]


class ChatIn(BaseModel):
    message: str


class AgentActionIn(BaseModel):
    message: str
    context: dict = Field(default_factory=dict)


class AgentToolExecuteIn(BaseModel):
    tool: str
    payload: dict = Field(default_factory=dict)


class KnowledgeIn(BaseModel):
    title: str
    summary: str = ""
    content: str = ""
    source: str = "personal"
    url: str = ""
    folder_id: str = ""


class KnowledgeLinkIn(BaseModel):
    url: str
    folder_id: str = ""


class KnowledgeFolderIn(BaseModel):
    name: str
    scope: str = "personal"
    item_ids: list[str] = Field(default_factory=list)
    cover: str = ""
    description: str = ""
    recommended_questions: list[str] = Field(default_factory=list)
    sort_order: int = 0


class PracticeIn(BaseModel):
    question: str
    answer: str
    tags: list[str] = Field(default_factory=list)


class InterviewStartIn(BaseModel):
    interview_type: str = "产品思维"
    interviewer_style: str = "温和型"
    company: str = ""
    role: str = ""
    jd: str = ""
    question_bank: str = ""


class InterviewAnswerIn(BaseModel):
    answer: str


class ReviewIn(BaseModel):
    company: str = ""
    role: str = ""
    feeling: str = ""
    questions: str = ""
    reflection: str = ""
