# CodeSage – AI Code Error Analyzer

CodeSage is a Django + Channels project that runs Python, Java, and C programs, captures errors/output, and now uses the Ollama local API on the backend to generate:

- beginner-friendly explanations
- AI suggested code
- improvement tips
- context-aware mentor chat replies

## Setup

```bash
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```env
DJANGO_SECRET_KEY=change-this
DJANGO_DEBUG=1
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost
EXECUTION_TIMEOUT=20
MAX_CODE_SIZE=50000
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=deepseek-coder:latest
OLLAMA_TIMEOUT=90
OLLAMA_TEMPERATURE=0.2
```

Then start Ollama in another terminal and pull the model once:

```bash
ollama serve
ollama pull deepseek-coder:latest
```

Then run Django:

```bash
python manage.py migrate
python manage.py runserver
```

## How AI works

1. You run code from the editor.
2. The backend executes it safely in a temporary workspace.
3. Code, stdout, stderr, and execution status are sent to Ollama from the Django backend.
4. The app checks whether Ollama is reachable and whether the selected model is installed.
5. The app shows AI explanation, AI suggested code, tips, and mentor chat answers.
6. If Ollama is not configured or the request fails, the app falls back to the internal rule-based analyzer.

## Important

- Keep `OLLAMA_MODEL` in `.env`, not in frontend JavaScript.
- Java requires `javac` and `java` installed.
- C requires `gcc` installed.
- The generated fix is shown as **Suggested Code**, not guaranteed perfect code.
