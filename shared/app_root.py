"""Корень данных воркера: `prompts/`, `config/`, `workspace/`.

В образе это `/app` (`COPY worker/ .`), а на стенде харнесса БФТ воркер идёт юнитом из
рабочей копии репозитория (юнит задаёт APP_ROOT). Прошитый `/app/prompts` ронял intake_gate
на smoke T1 (#329). Одно место — чтобы смена корня не была правкой трёх модулей.
"""
import os
from pathlib import Path

APP_ROOT = Path(os.environ.get("APP_ROOT", "/app"))
