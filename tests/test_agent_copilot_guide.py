from backend.app.models import UserProfile
from backend.app.services.agent import application_copilot_guide, local_action_plan


def test_application_copilot_request_returns_deterministic_guide():
    profile = UserProfile(id="u-copilot-guide", username="copilot-guide", name="同学", target_role="产品经理")

    result = local_action_plan(profile, "帮我投递岗位并自动网申")

    assert result["actions"] == []
    assert "桃子 Chrome 插件" in result["reply"]
    assert "不会填写密码、验证码、隐藏字段" in result["reply"]
    assert result["reply"] == application_copilot_guide()
