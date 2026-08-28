# Руководство по внедрению централизованных стандартов кодирования

> Основано на исследовании Issue #107
> Практическое руководство для реализации

---

## Быстрый старт (MVP за 1 день)

### Шаг 1: Создание репозитория стандартов (30 минут)

```bash
# 1. Создайте новый репозиторий poh-coding-standards
gh repo create po-helper-org/poh-coding-standards --private

# 2. Клонируйте и создайте базовую структуру
git clone git@github.com:po-helper-org/poh-coding-standards.git
cd poh-coding-standards

# 3. Создайте структуру директорий
mkdir -p universal/{architecture,security,testing}
mkdir -p python/{naming,structure,best-practices}
mkdir -p javascript/{naming,structure,best-practices}

# 4. Создайте индексный файл
touch index.json
```

### Шаг 2: Миграция первых правил (1 час)

**Создайте файл `universal/architecture/declarative-patterns.md`:**

```markdown
---
id: "universal/architecture/declarative-patterns"
language: "*"
category: "architecture"
priority: "high"
status: "active"
version: "1.0.0"
last_updated: "2026-08-23"
tags: ["architecture", "configuration", "best-practices"]
---

# Декларативные паттерны优于 хардкод

## Принцип
Всегда используйте декларативные паттерны вместо хардкода. Конфигурация должна быть источником истины.

## Когда применять
- Конфигурация сервисов
- Определение маршрутов
- Настройка пайплайнов
- Определение правил валидации

## Примеры

### Правильно
```yaml
# config/services.yaml
services:
  user-service:
    host: ${USER_SERVICE_HOST}
    port: ${USER_SERVICE_PORT}
    timeout: 30
```

### Неправильно
```python
# services.py
USER_SERVICE_HOST = "localhost"
USER_SERVICE_PORT = 8080
USER_SERVICE_TIMEOUT = 30
```

## Исключения
- Только когда декларативный подход невозможен по техническим причинам
- Должен быть documented в code review комментарии

## Связанные правила
- [`universal/security/secrets-management`](../security/secrets-management.md)
```

**Создайте файл `python/naming/conventions.md`:**

```markdown
---
id: "python/naming/conventions"
language: "python"
category: "naming"
priority: "high"
status: "active"
version: "1.0.0"
last_updated: "2026-08-23"
tags: ["naming", "variables", "functions", "classes"]
---

# Python: Naming Conventions

## Переменные и функции
Используйте `snake_case` для локальных переменных и функций.

**Примеры:**
```python
user_name = "John"      # Правильно
get_user_data()         # Правильно

userName = "John"       # Неправильно
getUserData()           # Неправильно
```

## Классы
Используйте `PascalCase` для классов.

**Примеры:**
```python
class UserService:      # Правильно
    pass

class userService:      # Неправильно
    pass
```

## Константы
Используйте `UPPER_SNAKE_CASE` для констант.

**Примеры:**
```python
MAX_RETRIES = 3         # Правильно
API_TIMEOUT = 30        # Правильно

maxRetries = 3          # Неправильно
apiTimeout = 30         # Неправильно
```

## Приватные методы
Используйте `_leading_underscore` для приватных методов.

**Примеры:**
```python
class UserService:
    def _internal_method(self):  # Правильно
        pass
    
    def internalMethod(self):     # Неправильно
        pass
```
```

### Шаг 3: Генерация индекса (15 минут)

**Создайте скрипт `generate_index.py`:**

```python
#!/usr/bin/env python3
import json
import os
from pathlib import Path
import re

def extract_frontmatter(file_path):
    """Extract YAML frontmatter from markdown file"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    match = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
    if not match:
        return None
    
    frontmatter = match.group(1)
    # Simple YAML parsing (for production, use PyYAML)
    metadata = {}
    for line in frontmatter.split('\n'):
        if ':' in line:
            key, value = line.split(':', 1)
            metadata[key.strip()] = value.strip().strip('"\'')
    
    return metadata

def generate_index(standards_dir="."):
    """Generate index.json from all markdown files"""
    standards = []
    
    for root, dirs, files in os.walk(standards_dir):
        # Skip hidden directories and common exclusions
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['node_modules', '__pycache__']]
        
        for file in files:
            if file.endswith('.md'):
                file_path = Path(root) / file
                relative_path = file_path.relative_to(standards_dir)
                
                metadata = extract_frontmatter(file_path)
                if metadata:
                    metadata['path'] = str(relative_path)
                    standards.append(metadata)
    
    index = {
        'version': '1.0.0',
        'generated_at': '2026-08-23',
        'total_standards': len(standards),
        'standards': standards
    }
    
    with open('index.json', 'w', encoding='utf-8') as f:
        json.dump(index, f, indent=2, ensure_ascii=False)
    
    print(f"Generated index with {len(standards)} standards")

if __name__ == '__main__':
    generate_index()
```

**Запустите генерацию:**

```bash
python generate_index.py
```

### Шаг 4: Первый коммит (15 минут)

```bash
git add .
git commit -m "Initial coding standards

- Add universal architecture rules
- Add Python naming conventions
- Add index generation script"
git push origin main
```

---

## Подключение к существующему репозиторию (30 минут)

### Шаг 1: Добавление submodule (5 минут)

```bash
cd your-existing-repo
git submodule add https://github.com/po-helper-org/poh-coding-standards.git .standards
git commit -m "Add centralized coding standards as submodule"
```

### Шаг 2: Создание конфигурации (5 минут)

**Создайте файл `.standards-config.toml`:**

```toml
[standards]
source = ".standards"
version = "main"  # или конкретный commit hash

[overrides]
enabled = true
directory = ".standards.overrides"

[validation]
enabled = true
strict = false  # true = блокирует коммиты при нарушениях
```

### Шаг 3: Интеграция с AI-агентом (20 минут)

**Создайте файл `load_standards.py`:**

```python
#!/usr/bin/env python3
import json
import os
from pathlib import Path
import tomli  # pip install tomli

def load_config():
    """Load standards configuration"""
    config_path = Path(".standards-config.toml")
    if not config_path.exists():
        return {
            'standards': {'source': '.standards', 'version': 'main'},
            'overrides': {'enabled': True, 'directory': '.standards.overrides'},
            'validation': {'enabled': True, 'strict': False}
        }
    
    with open(config_path, 'rb') as f:
        return tomli.load(f)

def load_standards_index():
    """Load standards index"""
    config = load_config()
    standards_dir = Path(config['standards']['source'])
    index_path = standards_dir / 'index.json'
    
    if not index_path.exists():
        print("Warning: index.json not found, standards may be outdated")
        return []
    
    with open(index_path, 'r', encoding='utf-8') as f:
        return json.load(f)['standards']

def load_standard_content(rule_path):
    """Load content of a specific standard"""
    config = load_config()
    standards_dir = Path(config['standards']['source'])
    file_path = standards_dir / rule_path
    
    if not file_path.exists():
        return None
    
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()

def get_relevant_standards(context="", language="*", max_rules=10):
    """Get standards relevant to context (simple keyword matching)"""
    all_standards = load_standards_index()
    relevant = []
    
    context_lower = context.lower()
    
    for standard in all_standards:
        # Filter by language
        if language != "*" and standard.get('language') != "*" and standard.get('language') != language:
            continue
        
        # Simple keyword matching
        score = 0
        content = load_standard_content(standard['path'])
        if content:
            content_lower = content.lower()
            
            # Check for keyword matches
            keywords = ['architecture', 'security', 'naming', 'testing', 'best-practice']
            for keyword in keywords:
                if keyword in context_lower and keyword in content_lower:
                    score += 1
            
            # Check for category match
            if standard.get('category', '').lower() in context_lower:
                score += 2
            
            # Check priority
            if standard.get('priority') == 'critical':
                score += 3
            elif standard.get('priority') == 'high':
                score += 2
        
        if score > 0:
            standard['relevance_score'] = score
            relevant.append(standard)
    
    # Sort by relevance score
    relevant.sort(key=lambda x: x['relevance_score'], reverse=True)
    
    return relevant[:max_rules]

def format_standards_for_prompt(standards):
    """Format standards for inclusion in AI prompt"""
    formatted = []
    formatted.append("# CODING STANDARDS")
    formatted.append("")
    
    for standard in standards:
        content = load_standard_content(standard['path'])
        if content:
            # Extract the content after frontmatter
            parts = content.split('---', 2)
            if len(parts) >= 3:
                main_content = parts[2].strip()
            else:
                main_content = content
            
            formatted.append(f"## {standard.get('id', 'Unknown Rule')}")
            formatted.append(main_content)
            formatted.append("")
    
    return "\n".join(formatted)

def main():
    """Example usage"""
    # Get standards for Python code
    python_standards = get_relevant_standards(
        context="Python function naming and class structure",
        language="python",
        max_rules=5
    )
    
    # Format for AI prompt
    prompt_section = format_standards_for_prompt(python_standards)
    print(prompt_section)
    
    # Or get all critical standards
    all_standards = load_standards_index()
    critical = [s for s in all_standards if s.get('priority') == 'critical']
    print(f"\nFound {len(critical)} critical standards")

if __name__ == '__main__':
    main()
```

### Шаг 4: Тестирование (5 минут)

```bash
# Установка зависимостей
pip install tomli

# Тест загрузки стандартов
python load_standards.py
```

---

## Интеграция с существующими AI-агентами

### Вариант 1: Инъекция в системный промпт (простейший)

**Обновите ваш агент-код:**

```python
from load_standards import format_standards_for_prompt, get_relevant_standards

def create_system_prompt(task_description, language="python"):
    """Create system prompt with integrated standards"""
    
    # Get relevant standards
    standards = get_relevant_standards(
        context=task_description,
        language=language,
        max_rules=5
    )
    
    # Format standards
    standards_text = format_standards_for_prompt(standards)
    
    # Create system prompt
    system_prompt = f"""
Ты — AI-агент для разработки ПО. При написании кода строго следуй этим стандартам:

{standards_text}

## Задача
{task_description}

## Требования
1. Следуй стандартам выше
2. Пиши чистый, поддерживаемый код
3. Добавляй комментарии для сложной логики
4. Включай тесты для нового кода
"""
    
    return system_prompt

# Использование
prompt = create_system_prompt(
    task_description="Создать класс UserService с методами для получения и сохранения пользователей",
    language="python"
)
```

### Вариант 2: Интеграция с Claude Code (существующий контур)

**Обновите `worker/Dockerfile`:**

```dockerfile
# Добавьте после существующих скиллов
COPY .standards /app/.standards
COPY load_standards.py /app/load_standards.py

# Установите зависимости
RUN pip install tomli
```

**Обновите загрузку скиллов:**

```python
# В worker/activities.py
def load_standards_for_claude():
    """Load standards for Claude Code"""
    try:
        from load_standards import get_relevant_standards, format_standards_for_prompt
        
        # Get high-priority standards
        standards = get_relevant_standards(
            context="general development",
            language="*",
            max_rules=3
        )
        
        return format_standards_for_prompt(standards)
    except Exception as e:
        print(f"Warning: Could not load standards: {e}")
        return ""

# Используйте в _run_skill или при подготовке промптов
standards_text = load_standards_for_claude()
```

---

## Валидация и CI-интеграция

### Базовая CI-проверка (30 минут)

**Создайте `.github/workflows/validate-standards.yml`:**

```yaml
name: Validate Coding Standards

on:
  pull_request:
    paths:
      - '.standards/**'
      - '.standards-config.toml'
      - '**.py'
      - '**.js'

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
        with:
          submodules: recursive
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install tomli
      
      - name: Check standards version
        run: |
          cd .standards
          CURRENT_VERSION=$(git rev-parse HEAD)
          echo "Current standards version: $CURRENT_VERSION"
          
          # Check if standards are outdated (warning only)
          git fetch origin main
          LATEST_VERSION=$(git rev-parse origin/main)
          if [ "$CURRENT_VERSION" != "$LATEST_VERSION" ]; then
            echo "⚠️ Warning: Standards are outdated"
            echo "Current: $CURRENT_VERSION"
            echo "Latest: $LATEST_VERSION"
            echo "Consider updating with: git submodule update --remote .standards"
          fi
      
      - name: Validate standards index
        run: |
          python .standards/generate_index.py
          if [ ! -f .standards/index.json ]; then
            echo "❌ Failed to generate standards index"
            exit 1
          fi
          echo "✅ Standards index is valid"
      
      - name: Check for critical rule violations (basic)
        run: |
          python -c "
import json
from pathlib import Path

# Load standards
with open('.standards/index.json') as f:
    standards = json.load(f)['standards']

# Check for critical standards
critical = [s for s in standards if s.get('priority') == 'critical']
print(f'Found {len(critical)} critical standards')

# Basic Python naming check (example)
python_files = list(Path('.').rglob('*.py'))
violations = []

for py_file in python_files:
    content = py_file.read_text()
    # Check for camelCase variables (simplified)
    import re
    if re.search(r'\b[a-z]+[A-Z]\w*\s*=', content):
        violations.append(f'{py_file}: possible camelCase variable')

if violations:
    print('⚠️ Possible naming convention violations:')
    for v in violations[:10]:  # Limit output
        print(f'  {v}')
"
```

---

## Мониторинг и метрики

### Базовый мониторинг (1 час)

**Создайте `scripts/collect_metrics.py`:**

```python
#!/usr/bin/env python3
import json
import subprocess
from pathlib import Path
from datetime import datetime

def collect_standards_metrics():
    """Collect metrics about standards usage"""
    
    metrics = {
        'timestamp': datetime.now().isoformat(),
        'standards': {},
        'repositories': {}
    }
    
    # Standards metrics
    standards_dir = Path('.standards')
    if standards_dir.exists():
        # Count total standards
        index_path = standards_dir / 'index.json'
        if index_path.exists():
            with open(index_path) as f:
                index = json.load(f)
                metrics['standards']['total'] = index['total_standards']
                
                # Count by priority
                by_priority = {}
                for standard in index['standards']:
                    priority = standard.get('priority', 'unknown')
                    by_priority[priority] = by_priority.get(priority, 0) + 1
                metrics['standards']['by_priority'] = by_priority
                
                # Count by language
                by_language = {}
                for standard in index['standards']:
                    language = standard.get('language', 'unknown')
                    by_language[language] = by_language.get(language, 0) + 1
                metrics['standards']['by_language'] = by_language
    
    # Repository metrics
    try:
        # Get current commit
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD']).decode().strip()
        metrics['repositories']['current_commit'] = commit
        
        # Get standards commit
        standards_commit = subprocess.check_output(
            ['git', 'submodule', 'status', '.standards'],
            cwd='.'
        ).decode().strip().split()[1]
        metrics['repositories']['standards_commit'] = standards_commit
        
    except subprocess.CalledProcessError:
        pass
    
    # Save metrics
    metrics_dir = Path('.standards-metrics')
    metrics_dir.mkdir(exist_ok=True)
    
    metrics_file = metrics_dir / f"metrics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(metrics_file, 'w') as f:
        json.dump(metrics, f, indent=2)
    
    print(f"Metrics saved to {metrics_file}")
    return metrics

if __name__ == '__main__':
    metrics = collect_standards_metrics()
    print(json.dumps(metrics, indent=2))
```

**Запустите сбор метрик:**

```bash
mkdir -p scripts
python scripts/collect_metrics.py
```

---

## Локальные расширения стандартов

### Создание локальных правил (15 минут)

**Создайте `.standards.overrides/project-specific.md`:**

```markdown
---
id: "overrides/project-specific"
language: "*"
category: "project"
priority: "medium"
status: "active"
version: "1.0.0"
last_updated: "2026-08-23"
---

# Проект-специфичные правила

## Локальные соглашения
Эти правила специфичны для данного проекта и переопределяют общие стандарты.

## Исключения
Для этого проекта мы используем TypeScript вместо чистого JavaScript.
```typescript
// Даже если общие стандарты рекомендуют camelCase для JS,
// мы используем PascalCase для интерфейсов
interface UserService {  // Правильно для этого проекта
    getUserById(id: string): Promise<User>;
}
```

## Специфичные паттерны
- Используйте Repository pattern для доступа к данным
- Все API вызовы должны идти через ApiClient
- Логирование должно использовать Winston (а не console.log)
```

---

## Устранение проблем

### Проблема: Submodule не клонируется

**Решение:**

```bash
# Инициализация submodule
git submodule init
git submodule update

# Или одной командой
git submodule update --init --recursive
```

### Проблема: Стандарты устарели

**Решение:**

```bash
# Обновление до последней версии
git submodule update --remote .standards

# Или до конкретной версии
cd .standards
git checkout <specific-commit-hash>
cd ..
git add .standards
git commit -m "Update standards to version abc123"
```

### Проблема: Конфликт при merge

**Решение:**

```bash
# Разрешение конфликта в submodule
cd .standards
git checkout main
git pull origin main
cd ..
git add .standards
git commit -m "Resolve submodule conflict"
```

---

## Следующие шаги после MVP

1. **Разработка MCP-сервера** (2-3 недели)
   - Эндпоинты для поиска и получения правил
   - Векторный поиск для релевантности
   - Кэширование для производительности

2. **Расширение валидации** (1-2 недели)
   - LLM-проверки качества правил
   - Автоматическое тестирование примеров
   - CI-интеграция с блокировками

3. **Миграция на все репозитории** (1+ месяц)
   - Приоритизация по активности
   - Обучение команды
   - Сбор обратной связи

---

## Полезные ресурсы

- **Полное исследование:** `docs/issue-107-research.md`
- **Краткое резюме:** `docs/issue-107-summary.md`
- **Git Submodule документация:** https://git-scm.com/book/en/v2/Git-Tools-Submodules
- **Frontmatter спецификация:** https://jekyllrb.com/docs/front-matter/
- **MCP Protocol:** https://modelcontextprotocol.io/

---

> **Это практическое руководство поможет вам начать внедрение централизованных стандартов за 1 день. Для полноценного продакшен-решения следуйте плану из полного исследования.**
