"""测试 AlertManager 客户端和重构后的 alert_tools"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestAlertManagerClient:
    """AlertManager 客户端测试"""

    def test_not_available_without_url(self):
        """未配置 URL → is_available 为 False"""
        from app.integrations.alertmanager.client import AlertManagerClient

        with patch("app.integrations.alertmanager.client.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock()
            mock_settings.return_value.ALERTMANAGER_URL = None

            client = AlertManagerClient()
            assert not client.is_available

    def test_available_with_url(self):
        """配置了 URL → is_available 为 True"""
        from app.integrations.alertmanager.client import AlertManagerClient

        with patch("app.integrations.alertmanager.client.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock()
            mock_settings.return_value.ALERTMANAGER_URL = "http://alertmanager:9093"

            client = AlertManagerClient()
            assert client.is_available

    @pytest.mark.asyncio
    async def test_get_alerts_returns_empty_when_unavailable(self):
        """未配置时 → 返回空列表"""
        from app.integrations.alertmanager.client import AlertManagerClient

        with patch("app.integrations.alertmanager.client.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock()
            mock_settings.return_value.ALERTMANAGER_URL = None

            client = AlertManagerClient()
            alerts = await client.get_alerts()
            assert alerts == []

    @pytest.mark.asyncio
    async def test_get_alerts_success(self):
        """配置正确 → 返回告警列表"""
        from app.integrations.alertmanager.client import AlertManagerClient

        with patch("app.integrations.alertmanager.client.get_settings") as mock_settings, \
             patch("app.integrations.alertmanager.client.httpx.AsyncClient") as mock_httpx:

            mock_settings.return_value = MagicMock()
            mock_settings.return_value.ALERTMANAGER_URL = "http://alertmanager:9093"

            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = [{"labels": {"alertname": "TestAlert"}}]

            mock_client = AsyncMock()
            mock_client.get.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.return_value = mock_client

            client = AlertManagerClient()
            alerts = await client.get_alerts()
            assert len(alerts) == 1
            assert alerts[0]["labels"]["alertname"] == "TestAlert"

    @pytest.mark.asyncio
    async def test_get_alerts_handles_error(self):
        """HTTP 错误 → 返回空列表"""
        from app.integrations.alertmanager.client import AlertManagerClient

        with patch("app.integrations.alertmanager.client.get_settings") as mock_settings, \
             patch("app.integrations.alertmanager.client.httpx.AsyncClient") as mock_httpx:

            mock_settings.return_value = MagicMock()
            mock_settings.return_value.ALERTMANAGER_URL = "http://alertmanager:9093"

            mock_resp = MagicMock()
            mock_resp.status_code = 500

            mock_client = AsyncMock()
            mock_client.get.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.return_value = mock_client

            client = AlertManagerClient()
            alerts = await client.get_alerts()
            assert alerts == []

    @pytest.mark.asyncio
    async def test_create_silence_unavailable(self):
        """未配置 → 返回失败"""
        from app.integrations.alertmanager.client import AlertManagerClient

        with patch("app.integrations.alertmanager.client.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock()
            mock_settings.return_value.ALERTMANAGER_URL = None

            client = AlertManagerClient()
            result = await client.create_silence(matchers=[{"name": "alertname", "value": "Test"}])
            assert result["success"] is False

    @pytest.mark.asyncio
    async def test_create_silence_success(self):
        """创建静默成功"""
        from app.integrations.alertmanager.client import AlertManagerClient

        with patch("app.integrations.alertmanager.client.get_settings") as mock_settings, \
             patch("app.integrations.alertmanager.client.httpx.AsyncClient") as mock_httpx:

            mock_settings.return_value = MagicMock()
            mock_settings.return_value.ALERTMANAGER_URL = "http://alertmanager:9093"

            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"silenceID": "abc123"}

            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.return_value = mock_client

            client = AlertManagerClient()
            result = await client.create_silence(
                matchers=[{"name": "alertname", "value": "HighCPU", "isRegex": False}],
                duration="1h",
            )
            assert result["success"] is True
            assert result["silence_id"] == "abc123"


class TestAlertTools:
    """alert_tools 测试"""

    @pytest.mark.asyncio
    async def test_get_active_alerts_returns_list(self):
        """get_active_alerts 返回列表"""
        from app.tools.alert_tools import get_active_alerts
        with patch("app.integrations.alertmanager.client.get_alertmanager_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.is_available = False
            mock_get_client.return_value = mock_client

            result = await get_active_alerts()
            assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_silence_alert_returns_dict(self):
        """silence_alert 返回字典"""
        from app.tools.alert_tools import silence_alert
        with patch("app.integrations.alertmanager.client.get_alertmanager_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.is_available = False
            mock_get_client.return_value = mock_client

            result = await silence_alert("TestAlert")
            assert isinstance(result, dict)
            assert result["success"] is False

    @pytest.mark.asyncio
    async def test_get_alert_statistics_returns_dict(self):
        """get_alert_statistics 返回字典"""
        from app.tools.alert_tools import get_alert_statistics
        with patch("app.integrations.alertmanager.client.get_alertmanager_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.is_available = False
            mock_get_client.return_value = mock_client

            result = await get_alert_statistics()
            assert isinstance(result, dict)
            assert "by_severity" in result
            assert "by_service" in result
            assert "top_alerts" in result
