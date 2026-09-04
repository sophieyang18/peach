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


class CandidateProfilePatchIn(BaseModel):
    basics: dict = Field(default_factory=dict)
    education: list[dict] = Field(default_factory=list)
    experiences: list[dict] = Field(default_factory=list)
    projects: list[dict] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    target_preferences: dict = Field(default_factory=dict)
    field_statuses: dict = Field(default_factory=dict)


class ConversationMessageIn(BaseModel):
    role: str
    content: str = ""
    actions: list[dict] = Field(default_factory=list)


class ConversationIn(BaseModel):
    id: str
    title: str = "新建对话"
    updatedAt: str = ""
    messages: list[ConversationMessageIn] = Field(default_factory=list)


class ConversationSyncIn(BaseModel):
    conversations: list[ConversationIn] = Field(default_factory=list)
    activeConversationId: str = ""


class ProductEventIn(BaseModel):
    event_name: str
    anonymous_id: str = ""
    session_id: str = ""
    page: str = ""
    module: str = ""
    source: str = ""
    properties: dict = Field(default_factory=dict)
    client_version: str = ""
    device_type: str = ""
    browser: str = ""
    referrer: str = ""


class CopilotFormFieldIn(BaseModel):
    id: str = ""
    tagName: str = ""
    inputType: str = ""
    label: str = ""
    placeholder: str = ""
    name: str = ""
    ariaLabel: str = ""
    nearbyText: str = ""
    required: bool = False
    selector: str = ""
    options: list[str] = Field(default_factory=list)
    currentValue: str = ""


class CopilotRepeaterIn(BaseModel):
    id: str = ""
    label: str = ""
    selector: str = ""
    section: str = ""
    nearbyText: str = ""


class CopilotMapIn(BaseModel):
    url: str = ""
    domain: str = ""
    fields: list[CopilotFormFieldIn] = Field(default_factory=list)
    repeaters: list[CopilotRepeaterIn] = Field(default_factory=list)
    use_agent: bool = True


class CopilotOpenAnswerIn(BaseModel):
    question: str
    jd: str = ""
    company: str = ""
    role: str = ""
    candidate_path: str = ""
    repeat_section: str = ""
    repeat_index: int | None = None
    field_key: str = ""


class CopilotConfirmApplicationIn(BaseModel):
    company: str = ""
    role: str = ""
    jd_text: str = ""
    source_url: str = ""
    notes: str = ""
    resume_version_id: str = ""


class ApplicationIn(BaseModel):
    company: str = ""
    role: str = ""
    jd_text: str = ""
    source_url: str = ""
    resume_version_id: str = ""
    status: str = "draft"
    source: str = "manual"
    notes: str = ""


class ApplicationPatchIn(BaseModel):
    company: str | None = None
    role: str | None = None
    jd_text: str | None = None
    source_url: str | None = None
    resume_version_id: str | None = None
    status: str | None = None
    source: str | None = None
    notes: str | None = None


class JobResumeGenerateIn(BaseModel):
    company: str = ""
    position: str = ""
    industry: str = ""
    batch: str = ""
    cities: str = ""
    education: str = ""
    company_type: str = ""
    target_graduates: str = ""
    notes: str = ""
    application_url: str = ""
    announcement_url: str = ""
    match_reasons: list[str] = Field(default_factory=list)


class DailyActionPatchIn(BaseModel):
    status: str


class InterviewExperienceIn(BaseModel):
    company: str = ""
    role: str = ""
    department: str = ""
    interview_stage: str = ""
    interview_date: str = ""
    raw_content: str
    source_type: str = "manual"
    source_name: str = ""
    source_url: str = ""
    published_at: str = ""


class QuestionSetBuildIn(BaseModel):
    company: str = ""
    role: str = ""
    interview_stage: str = ""
    jd: str = ""
    limit: int = 10


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
    question_set_id: str = ""


class InterviewAnswerIn(BaseModel):
    answer: str


class ReviewIn(BaseModel):
    company: str = ""
    role: str = ""
    feeling: str = ""
    questions: str = ""
    reflection: str = ""
