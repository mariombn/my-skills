#!/usr/bin/env bash
# Compatible with Bash 3.2+ (macOS and Linux). No sudo, eval, or archive extraction.
# Keep execution at the end: an incomplete curl download must not start installation.
set -eo pipefail

main() {
  export LC_ALL=C
  umask 077
  local target source_dir ref harness_input skill_input yes overwrite scope
  target=$(pwd -P); source_dir=''; ref=main; harness_input=''; skill_input=''
  scope=''; yes=0; overwrite=0; temp=''; lock=''; stage=''; backup=''
  local -a catalog selected_harnesses selected_skills roots
  catalog=(); selected_harnesses=(); selected_skills=(); roots=()

  die() { printf 'Erro: %s\n' "$*" >&2; exit 1; }
  usage() {
    cat <<'HELP'
Uso: bash install.sh [opções]
Instala no projeto (padrão com --yes) ou no HOME após escolha explícita.
  --scope project|user       Projeto atual ou skills pessoais no HOME
  --harnesses claude,codex,pi  Escolha um ou mais (ou all)
  --skills nome,outra         Escolha skills (ou all)
  --yes                      Confirma instalação sem terminal; NÃO sobrescreve
  --overwrite                Substitui conflitos, guardando backup no destino
  --ref REF                  Branch, tag ou commit do mariombn/my-skills (main)
  --source-dir DIR           Lê manifesto e skills de um checkout local
  --help                     Mostra esta ajuda
Sem --scope (exceto com --yes), --harnesses/--skills, há menus de seleção múltipla via /dev/tty.
HELP
  }
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --scope|--harnesses|--skills|--ref|--source-dir)
        [ "$#" -ge 2 ] && [ -n "$2" ] || die "Falta valor para $1"
        case "$1" in
          --scope) scope=$2;; --harnesses) harness_input=$2;; --skills) skill_input=$2;;
          --ref) ref=$2;; --source-dir) source_dir=$2;;
        esac
        shift 2;;
      --yes) yes=1; shift;; --overwrite) overwrite=1; shift;;
      --help|-h) usage; return 0;; *) die "Opção desconhecida: $1";;
    esac
  done
  case "$scope" in ''|project|user) ;; *) die 'Escopo inválido: use project ou user.';; esac
  [[ "$ref" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || die 'REF inválida (use tag, SHA ou branch sem barras).'
  [ "$yes" -eq 0 ] || { [ -n "$harness_input" ] && [ -n "$skill_input" ]; } || die '--yes exige --harnesses e --skills.'
  if [ -n "$source_dir" ]; then
    source_dir=$(cd "$source_dir" && pwd -P) || die 'Checkout local inexistente.'
  else
    command -v curl >/dev/null 2>&1 || die 'Instale curl primeiro.'
  fi
  local hash_tool
  if command -v sha256sum >/dev/null 2>&1; then hash_tool=sha256sum
  elif command -v shasum >/dev/null 2>&1; then hash_tool=shasum
  else die 'É necessário sha256sum (Linux) ou shasum (macOS).'; fi
  cleanup() {
    [ -z "$stage" ] || rm -rf -- "$stage"
    [ -z "$temp" ] || rm -rf -- "$temp"
    [ -z "$lock" ] || rmdir -- "$lock" 2>/dev/null || true
  }
  trap cleanup EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  temp=$(mktemp -d "${TMPDIR:-/tmp}/llm-skills.XXXXXXXX") || die 'Não foi possível criar diretório temporário.'
  # Do not follow symlinks anywhere below a local source or destination root.
  check_path() {
    local base=$1 relative=$2 component
    local -a pieces
    IFS=/ read -r -a pieces <<< "$relative"
    for component in "${pieces[@]}"; do
      base="$base/$component"
      [ ! -L "$base" ] || die "Link simbólico não permitido: $base"
    done
  }
  fetch() {
    local path=$1 out=$2
    if [ -n "$source_dir" ]; then
      check_path "$source_dir" "$path"
      [ -f "$source_dir/$path" ] || die "Arquivo ausente: $path"
      cp "$source_dir/$path" "$out"
    else
      curl --fail --silent --show-error --location --proto '=https' --proto-redir '=https' \
        --connect-timeout 15 --max-time 120 --retry 2 \
        "https://raw.githubusercontent.com/mariombn/my-skills/$ref/$path" --output "$out" || die "Download falhou: $path"
    fi
  }
  fetch manifest.sha256 "$temp/manifest.sha256"
  local digest path extra name found existing row
  local -a seen_paths
  seen_paths=()
  while read -r digest path extra || [ -n "${digest:-}" ]; do
    [ -n "$digest" ] || continue
    [[ "$digest" =~ ^[0-9a-f]{64}$ ]] && [ -z "$extra" ] || die 'Manifesto inválido.'
    [[ "$path" =~ ^skills/[a-z0-9]+(-[a-z0-9]+)*/[A-Za-z0-9_./-]+$ ]] || die "Caminho inválido no manifesto: $path"
    case "/$path/" in */../*|*/./*|*//*|*/-*) die "Caminho inseguro: $path";; esac
    for existing in "${seen_paths[@]}"; do [ "$existing" != "$path" ] || die "Arquivo duplicado: $path"; done
    seen_paths+=("$path")
    name=${path#skills/}; name=${name%%/*}
    [ "${#name}" -le 64 ] || die 'Nome de skill muito longo.'
    found=0
    for existing in "${catalog[@]}"; do [ "$existing" != "$name" ] || found=1; done
    [ "$found" -eq 1 ] || catalog+=("$name")
  done < "$temp/manifest.sha256"
  [ "${#catalog[@]}" -gt 0 ] || die 'Catálogo vazio.'
  for name in "${catalog[@]}"; do
    found=0
    for path in "${seen_paths[@]}"; do [ "$path" != "skills/$name/SKILL.md" ] || found=1; done
    [ "$found" -eq 1 ] || die "SKILL.md ausente: $name"
  done
  local tty_open=0 answer
  prompt() {
    if [ "$tty_open" -eq 0 ]; then
      { exec 3<>/dev/tty; } 2>/dev/null || die 'Sem terminal. Use --harnesses ... --skills ... --yes.'
      tty_open=1
    fi
    printf '%s' "$1" >&3
    IFS= read -r answer <&3 || die 'Entrada cancelada.'
  }
  if [ -z "$scope" ]; then
    if [ "$yes" -eq 1 ]; then scope=project
    else
      prompt $'Escolha o escopo:\n  1) Projeto atual (padrão)\n  2) Usuário (HOME, disponível entre projetos)\nEscopo [1]: '
      case "$answer" in ''|1|project) scope=project;; 2|user) scope=user;;
        *) die 'Escopo inválido: use 1/project ou 2/user.';; esac
    fi
  fi
  if [ "$scope" = user ]; then
    case "${HOME:-}" in /*) ;; *) die 'HOME deve ser um diretório absoluto existente para --scope user.';; esac
    [ -d "$HOME" ] || die 'HOME deve ser um diretório absoluto existente para --scope user.'
    target=$(cd "$HOME" && pwd -P) || die 'Não foi possível acessar HOME.'
    [ "$target" != / ] || die 'HOME não pode ser a raiz do sistema.'
  fi
  if [ -z "$harness_input" ]; then
    prompt $'Escolha os agentes (números separados por vírgula):\n  1) Claude Code\n  2) Codex\n  3) Pi\n  all) Todos\n> '
    harness_input=$answer
  fi
  local token normalized
  normalized=${harness_input//,/ }
  local -a tokens
  read -r -a tokens <<< "$normalized"
  [ "${#tokens[@]}" -gt 0 ] || die 'Selecione pelo menos um agente.'
  for token in "${tokens[@]}"; do
    case "$token" in 1|claude) name=claude;; 2|codex) name=codex;; 3|pi) name=pi;;
      all|todos) selected_harnesses=(claude codex pi); continue;; *) die "Agente inválido: $token";; esac
    found=0
    for existing in "${selected_harnesses[@]}"; do [ "$existing" != "$name" ] || found=1; done
    [ "$found" -eq 1 ] || selected_harnesses+=("$name")
  done
  if [ -z "$skill_input" ]; then
    printf '\nSkills disponíveis:\n' >&2
    local i=0
    for name in "${catalog[@]}"; do i=$((i + 1)); printf '  %s) %s\n' "$i" "$name" >&2; done
    prompt 'Skills (números/nomes separados por vírgula, ou all): '
    skill_input=$answer
  fi
  normalized=${skill_input//,/ }
  read -r -a tokens <<< "$normalized"
  [ "${#tokens[@]}" -gt 0 ] || die 'Selecione pelo menos uma skill.'
  for token in "${tokens[@]}"; do
    if [ "$token" = all ] || [ "$token" = todos ]; then selected_skills=("${catalog[@]}"); continue; fi
    name=$token
    if [[ "$token" =~ ^[0-9]+$ ]]; then
      [ "${#token}" -le 6 ] || die 'Índice inválido.'
      row=$((10#$token))
      [ "$row" -ge 1 ] && [ "$row" -le "${#catalog[@]}" ] || die "Índice inválido: $token"
      name=${catalog[$((row - 1))]}
    fi
    found=0
    for existing in "${catalog[@]}"; do [ "$existing" != "$name" ] || found=1; done
    [ "$found" -eq 1 ] || die "Skill desconhecida: $name"
    found=0
    for existing in "${selected_skills[@]}"; do [ "$existing" != "$name" ] || found=1; done
    [ "$found" -eq 1 ] || selected_skills+=("$name")
  done
  # Explicit built-in dependency; never execute metadata or skill contents.
  # Keep this mapping and its tests in sync when adding dependent skills.
  found=0
  for name in "${selected_skills[@]}"; do [ "$name" != grill-me ] || found=1; done
  if [ "$found" -eq 1 ]; then
    found=0
    for name in "${catalog[@]}"; do [ "$name" != grilling ] || found=1; done
    [ "$found" -eq 1 ] || die 'Dependência ausente no catálogo: grill-me exige grilling.'
    found=0
    for name in "${selected_skills[@]}"; do [ "$name" != grilling ] || found=1; done
    if [ "$found" -eq 0 ]; then
      selected_skills+=(grilling)
      printf 'Dependência adicionada: grilling (exigida por grill-me).\n'
    fi
  fi
  for name in "${selected_harnesses[@]}"; do
    case "$name" in claude) path=.claude/skills;; codex|pi) path=.agents/skills;; esac
    found=0
    for existing in "${roots[@]}"; do [ "$existing" != "$path" ] || found=1; done
    [ "$found" -eq 1 ] || roots+=("$path")
  done
  printf '\nEscopo: %s\nBase: %s\nAgentes: %s\nSkills: %s\n' "$scope" "$target" "${selected_harnesses[*]}" "${selected_skills[*]}"
  printf 'Destinos absolutos:\n'
  for path in "${roots[@]}"; do printf '  %s/%s\n' "$target" "$path"; done
  printf 'Codex e Pi compartilham .agents/skills; ambos podem descobrir essas skills.\n'
  if [ "$overwrite" -eq 1 ]; then printf 'Conflitos serão substituídos com backup preservado.\n';
  else printf 'Skills existentes serão preservadas (ignoradas).\n'; fi
  if [ "$yes" -eq 0 ]; then
    prompt 'Instalar? [s/N] '
    case "$answer" in s|S|sim|y|Y|yes) ;; *) printf 'Cancelado.\n'; return 0;; esac
  fi
  # Download and verify everything selected before touching the selected destination.
  local actual
  while read -r digest path extra || [ -n "${digest:-}" ]; do
    [ -n "$digest" ] || continue
    name=${path#skills/}; name=${name%%/*}; found=0
    for existing in "${selected_skills[@]}"; do [ "$existing" != "$name" ] || found=1; done
    [ "$found" -eq 1 ] || continue
    mkdir -p "$temp/$(dirname "$path")"
    fetch "$path" "$temp/$path"
    if [ "$hash_tool" = sha256sum ]; then actual=$(sha256sum "$temp/$path");
    else actual=$(shasum -a 256 "$temp/$path"); fi
    actual=${actual%% *}
    [ "$actual" = "$digest" ] || die "SHA-256 divergente: $path; nenhum arquivo foi instalado."
  done < "$temp/manifest.sha256"
  # Preflight ALL destinations, then acquire an installer-specific lock in the selected base.
  local root dest count=0 skipped=0
  for root in "${roots[@]}"; do
    check_path "$target" "$root"
    for name in "${selected_skills[@]}"; do check_path "$target" "$root/$name"; done
  done
  mkdir "$target/.llm-skills-install.lock" 2>/dev/null || die 'Outra instalação está ativa (ou existe .llm-skills-install.lock).'
  lock="$target/.llm-skills-install.lock"
  for root in "${roots[@]}"; do
    mkdir -p "$target/$root"
    for name in "${selected_skills[@]}"; do
      dest="$target/$root/$name"
      check_path "$target" "$root/$name"
      if [ -e "$dest" ] && [ "$overwrite" -eq 0 ]; then
        printf 'Preservado: %s\n' "$root/$name"; skipped=$((skipped + 1)); continue
      fi
      stage=$(mktemp -d "$target/$root/.llm-skills-stage.XXXXXXXX")
      cp -R "$temp/skills/$name/." "$stage/"
      if [ -e "$dest" ]; then
        if [ -z "$backup" ]; then
          backup=$(mktemp -d "$target/.llm-skills-backup.XXXXXXXX")
          printf 'Backup: %s\n' "$backup"
        fi
        mkdir -p "$backup/$root"
        mv "$dest" "$backup/$root/$name"
      fi
      if ! mv "$stage" "$dest"; then
        if [ -n "$backup" ] && [ -e "$backup/$root/$name" ]; then mv "$backup/$root/$name" "$dest"; fi
        die "Falha ao instalar $root/$name"
      fi
      stage=''; count=$((count + 1)); printf 'Instalado: %s\n' "$root/$name"
    done
  done
  printf '\nConcluído: %s instalado(s), %s preservado(s). Reabra o agente se necessário.\n' "$count" "$skipped"
}
main "$@"
