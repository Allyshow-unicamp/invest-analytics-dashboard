# Publicar com Git e GitHub CLI

Execute em PowerShell. Os comandos criam um repositório independente na pasta do projeto, fazem três commits convencionais e publicam o código novo como repositório público.

Nesta máquina, o Git identificava `C:\` como raiz herdada. Inicialize explicitamente o diretório abaixo antes de adicionar arquivos. Não execute `git add .` a partir da raiz herdada.

## 1. Inicialização local

```powershell
$projectRoot = 'C:\Users\allys\Documents\Investimentos'
Set-Location -LiteralPath $projectRoot
git init -b main .

$actualRoot = (git rev-parse --show-toplevel).Trim()
if ([IO.Path]::GetFullPath($actualRoot) -ne [IO.Path]::GetFullPath($projectRoot)) {
    throw 'A raiz Git não corresponde à pasta do projeto.'
}
```

Se o Git pedir identidade, configure o nome e o e-mail desejados **neste repositório**, usando `git config user.name` e `git config user.email`. O GitHub permite usar o endereço privado `noreply` da conta.

## 2. Validação e commits

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m ruff check .
if ($LASTEXITCODE -ne 0) { throw 'Lint falhou.' }
.\.venv\Scripts\python.exe -m ruff format --check .
if ($LASTEXITCODE -ne 0) { throw 'Formatação falhou.' }
.\.venv\Scripts\python.exe -m mypy
if ($LASTEXITCODE -ne 0) { throw 'Tipagem falhou.' }
.\.venv\Scripts\python.exe -m pytest
if ($LASTEXITCODE -ne 0) { throw 'Testes falharam.' }

git add .gitignore pyproject.toml requirements.txt app.py core data services ui .streamlit/config.toml
git diff --cached --stat
git commit -m "feat: build modular investment analytics dashboard"
if ($LASTEXITCODE -ne 0) { throw 'Commit de implementação falhou.' }

git add README.md docs
git commit -m "docs: document financial methodology architecture and publishing"
if ($LASTEXITCODE -ne 0) { throw 'Commit de documentação falhou.' }

git add tests .github/workflows/ci.yml requirements-dev.txt
git commit -m "test: cover financial calculations data contracts and dashboard flows"
if ($LASTEXITCODE -ne 0) { throw 'Commit de testes falhou.' }

git status --short
git ls-files
git check-ignore credentials-motor-quant-finance.json
```

Os caminhos são adicionados explicitamente. O arquivo de credenciais deve aparecer como ignorado e não deve estar em `git ls-files`. O legado, os CSVs privados e o ambiente virtual também ficam fora dos commits.

## 3. Autenticação e publicação pública

Se a conta já estiver autenticada, basta confirmar com `gh auth status` e seguir para a criação. Caso contrário:

```powershell
gh auth login --hostname github.com --git-protocol https --web
gh auth status
gh auth setup-git
```

Crie e envie o repositório para a conta ativa:

```powershell
gh repo create invest-analytics-dashboard --public --source . --remote origin --description "Workspace de pesquisa de carteiras, risco e dividendos com Python, Streamlit e Plotly" --push
if ($LASTEXITCODE -ne 0) { throw 'Publicação falhou; confira autenticação, nome e remotos.' }
gh repo view --json nameWithOwner,url,visibility
gh run list --limit 3
```

O nome foi escolhido para este projeto. Se já existir na conta, escolha outro nome em `gh repo create`. Se `origin` já estiver configurado, confira `git remote -v` antes de alterar o destino.

A opção `--public` torna os arquivos versionados acessíveis a qualquer pessoa. O comando não publica arquivos ignorados ou não commitados. A semântica de `--source`, `--remote`, `--public` e `--push` está no [manual oficial do GitHub CLI](https://cli.github.com/manual/gh_repo_create).

Depois do primeiro push, acompanhe o workflow **Quality checks** na aba Actions. Para badge dinâmico, substitua um badge estático do README por `https://github.com/SEU_USUARIO/invest-analytics-dashboard/actions/workflows/ci.yml/badge.svg`.
