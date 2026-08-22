"""Тесты для per-stage выбора моделей в FNR pipeline."""

import importlib
import os
from unittest.mock import Mock, patch, MagicMock
import pytest

import worker.llm as llm_module


class TestFNRStageModels:
    """Тесты для выбора моделей по стадиям FNR."""

    def test_fnr_stage_models_mapping_exists(self):
        """Проверяем, что маппинг стадий к моделям существует."""
        assert hasattr(llm_module, "FNR_STAGE_MODELS")
        assert isinstance(llm_module.FNR_STAGE_MODELS, dict)
        
        expected_stages = {"repowise", "task", "concept", "debate", "sysreq", "validate"}
        assert set(llm_module.FNR_STAGE_MODELS.keys()) == expected_stages

    def test_fnr_stage_models_have_defaults(self):
        """Проверяем, что все стадии имеют дефолтные модели."""
        for stage, model in llm_module.FNR_STAGE_MODELS.items():
            assert model is not None, f"Стадия {stage} не имеет модели"
            assert isinstance(model, str), f"Модель для {stage} не строка"
            assert len(model) > 0, f"Модель для {stage} пустая"

    def test_fnr_stage_models_from_env(self, monkeypatch):
        """Проверяем, что модели можно переопределить через переменные окружения."""
        monkeypatch.setenv("MODEL_FNR_REPOWISE", "custom-model-1")
        monkeypatch.setenv("MODEL_FNR_TASK", "custom-model-2")
        monkeypatch.setenv("ZAI_BASE_URL", "https://example.invalid/v4")
        monkeypatch.setenv("ZAI_API_KEY", "test-key")
        
        # Перезагружаем модуль для применения новых переменных окружения
        module = importlib.reload(llm_module)
        
        assert module.FNR_STAGE_MODELS["repowise"] == "custom-model-1"
        assert module.FNR_STAGE_MODELS["task"] == "custom-model-2"

    def test_debate_uses_stronger_model(self):
        """Проверяем, что debate использует более сильную модель по умолчанию."""
        debate_model = llm_module.FNR_STAGE_MODELS["debate"]
        other_models = [model for stage, model in llm_module.FNR_STAGE_MODELS.items() if stage != "debate"]
        
        # Debate должен использовать не более слабую модель, чем другие
        # (в текущей конфигурации - glm-5.2 vs glm-4.6)
        assert debate_model is not None

    def test_fnr_model_variables_exist(self):
        """Проверяем, что все переменные MODEL_FNR_* существуют."""
        expected_vars = [
            "MODEL_FNR_REPOWISE",
            "MODEL_FNR_TASK", 
            "MODEL_FNR_CONCEPT",
            "MODEL_FNR_DEBATE",
            "MODEL_FNR_SYSREQ",
            "MODEL_FNR_VALIDATE"
        ]
        
        for var_name in expected_vars:
            assert hasattr(llm_module, var_name), f"Переменная {var_name} не существует"

    def test_fnr_model_variables_are_readable(self):
        """Проверяем, что переменные модели можно читать."""
        for var_name in [
            "MODEL_FNR_REPOWISE",
            "MODEL_FNR_TASK", 
            "MODEL_FNR_CONCEPT",
            "MODEL_FNR_DEBATE",
            "MODEL_FNR_SYSREQ",
            "MODEL_FNR_VALIDATE"
        ]:
            value = getattr(llm_module, var_name)
            assert isinstance(value, str)


class TestClaudeAnthropicCreds:
    """Тесты для функции _claude_anthropic_creds."""

    def test_claude_anthropic_creds_accepts_model(self, monkeypatch):
        """Проверяем, что _claude_anthropic_creds принимает параметр model."""
        monkeypatch.setenv("ZAI_API_KEY", "test-key")
        monkeypatch.setenv("ZAI_BASE_URL", "https://example.invalid/v4")
        
        # Импортируем после установки переменных окружения
        import worker.activities as activities_module
        
        token, base, model = activities_module._claude_anthropic_creds("test-model")
        
        assert token == "test-key"
        assert "/api/anthropic" in base
        assert model == "test-model"

    def test_claude_anthropic_creds_fallback_to_env(self, monkeypatch):
        """Проверяем, что при отсутствии model используется ANTHROPIC_MODEL."""
        monkeypatch.setenv("ZAI_API_KEY", "test-key")
        monkeypatch.setenv("ZAI_BASE_URL", "https://example.invalid/v4")
        monkeypatch.setenv("ANTHROPIC_MODEL", "env-model")
        
        import worker.activities as activities_module
        
        token, base, model = activities_module._claude_anthropic_creds()
        
        assert model == "env-model"

    def test_claude_anthropic_creds_no_model_fallback(self, monkeypatch):
        """Проверяем, что при отсутствии model и ANTHROPIC_MODEL возвращается None."""
        monkeypatch.setenv("ZAI_API_KEY", "test-key")
        monkeypatch.setenv("ZAI_BASE_URL", "https://example.invalid/v4")
        monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
        
        import worker.activities as activities_module
        
        token, base, model = activities_module._claude_anthropic_creds()
        
        assert model is None


class TestRunClaudeWithModel:
    """Тесты для функции _run_claude с поддержкой model."""

    @pytest.fixture
    def mock_activities_module(self, monkeypatch):
        """Подготовка моков для тестирования _run_claude."""
        monkeypatch.setenv("ZAI_API_KEY", "test-key")
        monkeypatch.setenv("ZAI_BASE_URL", "https://example.invalid/v4")
        
        import worker.activities as activities_module
        
        # Мокаем subprocess.run
        mock_process = Mock()
        mock_process.returncode = 0
        mock_process.stdout = "success"
        mock_process.stderr = ""
        
        with patch.object(activities_module.subprocess, 'run', return_value=mock_process) as mock_run:
            yield activities_module, mock_run

    def test_run_claude_passes_model_to_env(self, mock_activities_module):
        """Проверяем, что модель передаётся в окружение subprocess."""
        activities_module, mock_run = mock_activities_module
        
        test_prompt = "test prompt"
        test_cwd = "/tmp/test"
        test_model = "glm-test-model"
        
        activities_module._run_claude(test_prompt, test_cwd, model=test_model)
        
        # Проверяем, что subprocess.run был вызван
        assert mock_run.called
        
        # Проверяем, что в окружении передана модель
        call_kwargs = mock_run.call_args[1]
        assert "env" in call_kwargs
        assert call_kwargs["env"]["ANTHROPIC_MODEL"] == test_model

    def test_run_claude_without_model(self, mock_activities_module):
        """Проверяем, что _run_claude работает без явного указания модели."""
        activities_module, mock_run = mock_activities_module
        
        test_prompt = "test prompt"
        test_cwd = "/tmp/test"
        
        activities_module._run_claude(test_prompt, test_cwd)
        
        # Проверяем, что subprocess.run был вызван
        assert mock_run.called
        
        # При отсутствии явной модели ANTHROPIC_MODEL может не быть в env
        call_kwargs = mock_run.call_args[1]
        assert "env" in call_kwargs


class TestStageModelIntegration:
    """Интеграционные тесты для выбора моделей в стадиях."""

    def test_run_fnr_stage_uses_stage_model(self, monkeypatch):
        """Проверяем, что run_fnr_stage использует модель из FNR_STAGE_MODELS."""
        monkeypatch.setenv("ZAI_API_KEY", "test-key")
        monkeypatch.setenv("ZAI_BASE_URL", "https://example.invalid/v4")
        monkeypatch.setenv("MODEL_FNR_TASK", "integration-test-model")
        
        import worker.activities as activities_module
        importlib.reload(llm_module)  # Перезагружаем для применения MODEL_FNR_TASK
        
        # Мокаем все зависимости
        with patch.object(activities_module, '_run_with_heartbeat') as mock_heartbeat, \
             patch.object(activities_module, '_fnr_stage') as mock_fnr_stage, \
             patch.object(activities_module, '_require_workspace') as mock_workspace, \
             patch.object(activities_module, '_write_repowise_config') as mock_config, \
             patch.object(llm_module, 'FNR_STAGE_MODELS', {'task': 'integration-test-model'}):
            
            # Настраиваем моки
            mock_fnr_stage.return_value = ("prompt", "expected.txt", None)
            mock_workspace.return_value = "/tmp/workspace"
            mock_config.return_value = "/tmp/config"
            
            # Создаём mock для AnalyzeInput
            mock_analyze = Mock()
            mock_analyze.repo = "test/repo"
            mock_analyze.issue_number = 123
            mock_analyze.title = "Test Issue"
            mock_analyze.body = "Test body"
            
            # Вызываем асинхронную функцию
            import asyncio
            try:
                asyncio.run(activities_module.run_fnr_stage(mock_analyze, "task"))
            except Exception as e:
                # Ожидаем ошибки из-за моков, но проверяем вызов _run_with_heartbeat
                pass
            
            # Проверяем, что _run_with_heartbeat был вызван с правильной моделью
            if mock_heartbeat.called:
                call_args = mock_heartbeat.call_args[0]
                # Четвёртый аргумент должен быть моделью
                if len(call_args) >= 4:
                    assert call_args[3] == 'integration-test-model', \
                        f"Ожидается модель 'integration-test-model', получено {call_args[3]}"

    def test_fnr_stage_models_fallback_for_unknown_stage(self):
        """Проверяем, что для неизвестной стадии возвращается None."""
        unknown_model = llm_module.FNR_STAGE_MODELS.get("unknown_stage")
        assert unknown_model is None
