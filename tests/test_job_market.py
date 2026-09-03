from backend.app.models import UserProfile
from backend.app.services.job_market import recommend_jobs_for_profile, search_job_library


def test_job_library_search_reads_autumn_recruitment_csv():
    result = search_job_library(query="产品", limit=5)

    assert result["total"] > 0
    assert len(result["items"]) <= 5
    assert {"industries", "batches", "company_types"} <= set(result["facets"])
    assert all(item["company"] or item["position"] for item in result["items"])


def test_job_recommendations_use_profile_signals():
    profile = UserProfile(
        id="u-job-market",
        username="job-market",
        name="杨诗卉",
        target_role="AI产品经理",
        target_city="北京",
        resume_text="27届 北京 AI 产品 数据分析 AIGC 项目经历",
    )

    result = recommend_jobs_for_profile(profile, limit=5)
    scores = [item["match_score"] for item in result["items"]]

    assert result["items"]
    assert scores == sorted(scores, reverse=True)
    assert any(item["match_reasons"] for item in result["items"])


def test_job_recommendations_weight_natural_language_preferences():
    profile = UserProfile(
        id="u-job-market-query",
        username="job-market-query",
        name="杨诗卉",
        target_role="产品经理",
        resume_text="27届 产品经理 数据分析 AIGC 项目经历",
    )

    result = recommend_jobs_for_profile(profile, limit=5, query="想要大厂、中台、偏算法或 AI 数据方向")
    reasons = " ".join(" ".join(item["match_reasons"]) for item in result["items"])

    assert result["items"]
    assert "算法/AI/数据" in reasons or "大厂/头部平台" in reasons or "中台/平台" in reasons
