from pydantic import BaseModel, Field


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


class PracticeIn(BaseModel):
    question: str
    answer: str
    tags: list[str] = Field(default_factory=list)


class InterviewStartIn(BaseModel):
    interview_type: str = "产品思维"
    interviewer_style: str = "温和型"
    company: str = ""
    role: str = ""


class InterviewAnswerIn(BaseModel):
    answer: str


class ReviewIn(BaseModel):
    company: str = ""
    role: str = ""
    feeling: str = ""
    questions: str = ""
    reflection: str = ""
