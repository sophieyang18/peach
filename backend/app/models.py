from datetime import datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db import Base


def uuid_pk() -> str:
    return str(uuid4())


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_pk)
    username: Mapped[str] = mapped_column(String(80), default="demo", index=True, unique=True)
    name: Mapped[str] = mapped_column(String(80), default="同学")
    target_role: Mapped[str] = mapped_column(String(120), default="产品经理")
    target_company: Mapped[str] = mapped_column(String(120), default="")
    target_city: Mapped[str] = mapped_column(String(80), default="")
    stage: Mapped[str] = mapped_column(String(40), default="投递期")
    resume_text: Mapped[str] = mapped_column(Text, default="")
    communication_style: Mapped[str] = mapped_column(String(80), default="温暖直接")
    strengths: Mapped[list[str]] = mapped_column(JSON, default=list)
    weak_points: Mapped[list[str]] = mapped_column(JSON, default=list)
    plan: Mapped[list[dict]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    practices: Mapped[list["PracticeRecord"]] = relationship(back_populates="user")
    interviews: Mapped[list["InterviewSession"]] = relationship(back_populates="user")
    memories: Mapped[list["AgentMemory"]] = relationship(back_populates="user")
    resume_versions: Mapped[list["ResumeVersion"]] = relationship(back_populates="user")


class ResumeVersion(Base):
    __tablename__ = "resume_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_pk)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_profiles.id"), index=True)
    title: Mapped[str] = mapped_column(String(180), default="完整简历")
    filename: Mapped[str] = mapped_column(String(260), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(60), default="manual")
    target_role: Mapped[str] = mapped_column(String(120), default="")
    version_no: Mapped[int] = mapped_column(Integer, default=1)
    optimized: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[UserProfile] = relationship(back_populates="resume_versions")


class PracticeRecord(Base):
    __tablename__ = "practice_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_pk)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_profiles.id"))
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text, default="")
    feedback: Mapped[dict] = mapped_column(JSON, default=dict)
    score: Mapped[int] = mapped_column(Integer, default=0)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[UserProfile] = relationship(back_populates="practices")


class InterviewSession(Base):
    __tablename__ = "interview_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_pk)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_profiles.id"))
    interview_type: Mapped[str] = mapped_column(String(80))
    interviewer_style: Mapped[str] = mapped_column(String(80))
    company: Mapped[str] = mapped_column(String(120), default="")
    role: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(40), default="active")
    transcript: Mapped[list[dict]] = mapped_column(JSON, default=list)
    report: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[UserProfile] = relationship(back_populates="interviews")


class KnowledgeResource(Base):
    __tablename__ = "knowledge_resources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_pk)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_profiles.id"))
    title: Mapped[str] = mapped_column(String(160))
    summary: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(40), default="personal")
    url: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class KnowledgeFolder(Base):
    __tablename__ = "knowledge_folders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_pk)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_profiles.id"))
    name: Mapped[str] = mapped_column(String(120))
    scope: Mapped[str] = mapped_column(String(40), default="personal")
    item_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AgentMemory(Base):
    __tablename__ = "agent_memories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_pk)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_profiles.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40), default="semantic", index=True)
    content: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(80), default="chat")
    confidence: Mapped[int] = mapped_column(Integer, default=70)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    memory_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    use_count: Mapped[int] = mapped_column(Integer, default=0)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[UserProfile] = relationship(back_populates="memories")


class AgentMemoryEvent(Base):
    __tablename__ = "agent_memory_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_pk)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_profiles.id"), index=True)
    memory_id: Mapped[str] = mapped_column(String(36), index=True)
    event: Mapped[str] = mapped_column(String(24), default="ADD", index=True)
    old_content: Mapped[str] = mapped_column(Text, default="")
    new_content: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(80), default="memory")
    reason: Mapped[str] = mapped_column(Text, default="")
    event_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ActionState(Base):
    __tablename__ = "action_states"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_pk)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_profiles.id"), index=True)
    action_type: Mapped[str] = mapped_column(String(80), default="targeted_interview_training", index=True)
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    target_issue_id: Mapped[str] = mapped_column(String(36), default="", index=True)
    target_ability: Mapped[str] = mapped_column(String(80), default="", index=True)
    related_experience_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    priority: Mapped[int] = mapped_column(Integer, default=2)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UserAbilityScore(Base):
    __tablename__ = "user_ability_scores"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_pk)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_profiles.id"), index=True)
    ability_dimension: Mapped[str] = mapped_column(String(80), index=True)
    current_score: Mapped[int] = mapped_column(Integer, default=60)
    target_score: Mapped[int] = mapped_column(Integer, default=80)
    confidence_level: Mapped[str] = mapped_column(String(24), default="low")
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AbilityScoreHistory(Base):
    __tablename__ = "ability_score_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_pk)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_profiles.id"), index=True)
    ability_dimension: Mapped[str] = mapped_column(String(80), index=True)
    score: Mapped[int] = mapped_column(Integer, default=60)
    source_type: Mapped[str] = mapped_column(String(80), default="mock_interview")
    source_id: Mapped[str] = mapped_column(String(36), default="", index=True)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GrowthIssue(Base):
    __tablename__ = "growth_issues"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_pk)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_profiles.id"), index=True)
    issue_key: Mapped[str] = mapped_column(String(120), index=True)
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    ability_dimension: Mapped[str] = mapped_column(String(80), default="", index=True)
    status: Mapped[str] = mapped_column(String(32), default="new", index=True)
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    first_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class GrowthInsight(Base):
    __tablename__ = "growth_insights"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_pk)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_profiles.id"), index=True)
    insight_type: Mapped[str] = mapped_column(String(40), default="recommendation", index=True)
    content: Mapped[str] = mapped_column(Text)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    confidence: Mapped[int] = mapped_column(Integer, default=70)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class HomeRecommendation(Base):
    __tablename__ = "home_recommendations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_pk)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_profiles.id"), index=True)
    text: Mapped[str] = mapped_column(String(160))
    reason: Mapped[str] = mapped_column(Text, default="")
    source_type: Mapped[str] = mapped_column(String(80), default="", index=True)
    source_id: Mapped[str] = mapped_column(String(36), default="", index=True)
    action_type: Mapped[str] = mapped_column(String(80), default="chat")
    priority: Mapped[int] = mapped_column(Integer, default=3)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    trigger_reason: Mapped[str] = mapped_column(String(120), default="", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
