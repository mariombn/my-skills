# my-skills

Coleção pessoal de skills para agentes de programação, com instalação por projeto ou por usuário e seleção múltipla de **Claude Code, Codex e Pi**.

No escopo **project**, o instalador usa o diretório em que você executar o comando, sem procurar a raiz Git. No escopo **user**, usa seu HOME e disponibiliza as skills entre projetos nessa máquina. Não usa `sudo` nem instala para outros usuários.

## Instalação rápida

Entre no projeto que deve receber as skills:

```bash
cd /caminho/do/seu/projeto
curl -fsSL https://raw.githubusercontent.com/mariombn/my-skills/main/install.sh | bash
```

O primeiro menu escolhe o escopo: `1`/Enter para projeto atual, `2` para usuário. Em seguida, permite selecionar agentes por número, separados por vírgula (`1,3`), e depois escolher skills por número ou nome. `all` seleciona todas as opções. Os prompts usam `/dev/tty`, portanto funcionam mesmo quando o script chega por um pipe de `curl`.

**Executar um script remoto dá a ele as permissões do seu usuário.** Leia o instalador e as skills antes de executar. Para revisar primeiro:

```bash
curl -fsSL https://raw.githubusercontent.com/mariombn/my-skills/main/install.sh -o /tmp/my-skills-install.sh
less /tmp/my-skills-install.sh
bash /tmp/my-skills-install.sh
```

Para uma instalação reproduzível, use o mesmo SHA completo de commit tanto na URL quanto em `--ref`:

```bash
REF=COLOQUE_AQUI_O_SHA_DO_COMMIT_REVISADO
curl -fsSL "https://raw.githubusercontent.com/mariombn/my-skills/$REF/install.sh" |
  bash -s -- --ref "$REF" --harnesses claude,codex,pi --skills all --yes
```

`--ref` aceita branches sem barras, tags e SHAs. O padrão `main` acompanha a versão atual; se os arquivos mudarem durante o download, a checagem de integridade pode abortar. Tente novamente ou fixe um commit.

## Onde ficam os arquivos

| Agente selecionado | `--scope project` | `--scope user` |
| --- | --- | --- |
| Claude Code | `.claude/skills/<nome>/SKILL.md` | `~/.claude/skills/<nome>/SKILL.md` |
| Codex | `.agents/skills/<nome>/SKILL.md` | `~/.agents/skills/<nome>/SKILL.md` |
| Pi atual | `.agents/skills/<nome>/SKILL.md` | `~/.agents/skills/<nome>/SKILL.md` |

O resumo mostra os caminhos absolutos antes da confirmação. `HOME` deve ser um diretório absoluto existente no escopo `user`; não há fallback para o diretório atual. Um HOME que é link simbólico é resolvido para seu diretório físico; links abaixo desse destino continuam sendo recusados.

Codex e Pi compartilham o diretório padronizado `.agents/skills`. Selecionar ambos cria **uma única cópia**, evitando duplicatas. Selecionar somente um deles ainda permite que o outro descubra essas skills, caso seja usado no mesmo projeto ou usuário; a seleção escolhe diretórios, não configura isolamento entre agentes.

Versões antigas do Pi podem exigir `.pi/skills`; este instalador mira a versão atual com suporte a `.agents/skills`. Atualize o Pi ou copie manualmente a skill revisada para o caminho exigido pela sua versão. Uma cópia anterior com o mesmo nome em `.pi/skills` pode ter prioridade sobre `.agents/skills` e provocar aviso de colisão. Revise essas cópias antes de migrar; o instalador não as remove.

O caminho pessoal atual do Codex é `$HOME/.agents/skills`, não `$CODEX_HOME/skills`. `CODEX_HOME` controla dados/configuração do Codex, mas este instalador mantém o local de skills pessoais documentado, mesmo quando essa variável está definida. No Pi, `PI_CODING_AGENT_DIR` (ou `agentDir` no SDK) muda o diretório próprio do agente, normalmente `~/.pi/agent`, que também pode conter `skills/`. O local compartilhado `~/.agents/skills` continua sendo suportado no Pi atual. Este instalador não segue esses overrides nem altera configuração; para versões antigas ou descoberta personalizada, use os caminhos e opções documentados pelo seu agente. Revise colisões com skills de mesmo nome em outros locais.

Depois da instalação, reabra o agente se a skill não aparecer. Claude: `/review-checklist`; Codex: `/skills` ou `$review-checklist`; Pi: `/skill:review-checklist` e `/reload` para recarregar.

## Opções

```text
--scope project|user        Projeto atual ou HOME; menu interativo quando omitido
--harnesses claude,codex,pi   Agentes, separados por vírgula; aceita all
--skills review-checklist    Skills por nome ou número; aceita all
--yes                       Confirma sem interação; exige as duas seleções
--overwrite                 Substitui conflitos e preserva uma cópia de backup
--ref REF                   Branch, tag ou commit (padrão: main)
--source-dir DIR            Usa um checkout local; não acessa a rede
--help                      Exibe ajuda
```

Em CI ou sem um terminal, informe as seleções e `--yes`. Por compatibilidade, omitir `--scope` com `--yes` continua instalando **somente no projeto**:

```bash
curl -fsSL https://raw.githubusercontent.com/mariombn/my-skills/main/install.sh |
  bash -s -- --harnesses codex,pi --skills review-checklist --yes
```

Para instalar para seu usuário explicitamente:

```bash
curl -fsSL https://raw.githubusercontent.com/mariombn/my-skills/main/install.sh |
  bash -s -- --scope user --harnesses claude,codex,pi --skills grill-me --yes
```

Selecionar `grill-me` inclui automaticamente `grilling` no mesmo destino; ambas aparecem no resumo. Selecionar `grilling` diretamente não instala o wrapper. O instalador valida e verifica também os arquivos da dependência antes de escrever. Skills já instaladas, incluindo dependências, continuam preservadas sem `--overwrite`; se houver uma cópia local incompatível, revise-a e reinstale ambas com `--overwrite`.

A partir de um clone, permanecendo no projeto de destino:

```bash
bash /caminho/my-skills/install.sh --source-dir /caminho/my-skills
```

## Reinstalação, atualização e recuperação

- Por padrão, uma skill já existente é **ignorada por inteiro**, preservando suas alterações. `--yes` não autoriza substituições.
- Para atualizar uma skill existente, use `--overwrite`. A versão anterior é movida para `.llm-skills-backup.<id>/<diretório-de-skills>/<nome>` na base escolhida (projeto ou HOME). O caminho do backup aparece na saída; revise-o antes de removê-lo.
- As cópias são independentes da coleção. Editar uma skill instalada não altera este repositório.
- O instalador baixa e verifica todos os arquivos selecionados antes de começar a instalar. A instalação é feita por skill, **não é uma transação de todos os agentes**. Uma interrupção pode deixar parte da seleção instalada; repita para completar, conferindo os backups.
- Um lock `.llm-skills-install.lock` evita duas instâncias do instalador na mesma base (projeto ou HOME). É removido ao terminar normalmente ou receber INT/TERM. Após encerramento forçado, confirme que não há instalação ativa antes de apagar um lock remanescente.
- A desinstalação é manual: revise e remova apenas as pastas de skills desejadas. Excluir a cópia compartilhada em `.agents/skills` afeta Codex e Pi.

## Segurança e limites

Requisitos do instalador: Bash 3.2+, `curl` para acesso remoto, `sha256sum` ou `shasum`, e utilitários Unix usuais. Python 3 é necessário **somente para os testes e manutenção do manifesto**.

O manifesto `manifest.sha256` lista apenas arquivos de `skills/`, com caminhos restritos e SHA-256. Arquivos são baixados individualmente via HTTPS, sem extrair arquivos compactados nem executar conteúdo de skills. Links simbólicos no caminho de origem local ou abaixo do destino são recusados. O temporário é privado e é limpo ao sair. Downloads não preservam permissões executáveis: scripts futuros devem ser invocados explicitamente com seu interpretador, após revisão.

Hashes detectam conteúdo corrompido ou versões inconsistentes; **não autenticam o autor** se o repositório ou o instalador tiverem sido comprometidos. A própria skill pode orientar o agente a usar ferramentas: leia todo o conteúdo e mantenha as aprovações do agente. Não execute o instalador em diretórios que terceiros possam modificar simultaneamente; os testes de links não eliminam corridas contra outro processo hostil.

O instalador não instala agentes, não configura contas e não altera arquivos de configuração. Políticas corporativas e versões dos agentes podem restringir a descoberta. Os testes verificam o layout e o instalador; não garantem que um modelo seguirá a skill corretamente.

## Catálogo

- **[review-checklist](skills/review-checklist/SKILL.md)**: revisão focada de alterações, problemas verificáveis, testes executados e limites da avaliação. Exemplo original criado para esta coleção; não é uma cópia de skill de terceiros.

- **[grill-me](skills/grill-me/SKILL.md)**: comando explícito de Matt Pocock para testar um plano ou decisão por entrevista. Instala também **[grilling](skills/grilling/SKILL.md)**, que faz as perguntas por rodadas de decisões independentes, com recomendações, aguardando suas respostas antes de avançar. Licença MIT incluída em cada pasta.

Exemplos: Claude `/grill-me`, Codex `$grill-me`, Pi `/skill:grill-me`, seguidos do plano. A primitiva `grilling` também pode ser escolhida pelo agente quando você pedir para testar suas ideias; `review-checklist` continua focada em revisão de código, não entrevista de produto.

O wrapper original usava apenas a ferramenta `Skill`: esta cópia usa essa ferramenta quando disponível ou lê `../grilling/SKILL.md`. A primitiva também permite pesquisa direta com ferramentas de leitura quando não há subagentes. São as únicas adaptações no texto upstream; as rodadas e a confirmação final permanecem intactas. Metadados upstream `agents/openai.yaml` são incluídos, preservando a invocação explícita do wrapper no Codex. Veja o commit, a licença e os detalhes em [PROVENANCE.md](PROVENANCE.md). A compatibilidade de descoberta foi conferida na documentação; o comportamento da entrevista não foi executado nos três agentes.

## Desenvolvimento

```bash
python3 -m unittest discover -s tests -v
bash -n install.sh
python3 scripts/update_manifest.py --check
```

Os testes cobrem instalação em caminho com espaços, seleção múltipla, compartilhamento Codex/Pi, pipe com terminal real, ausência de TTY, reinstalação, backups, links simbólicos, manifesto malicioso, checksums, lock e falha de download com `curl` simulado. Todos os processos, inclusive os testes de terminal, usam HOME temporário isolado. Também cobrem ambos os escopos, escolhas interativas, dependências, seleção numérica, sobrescrita e rejeição de HOME inválido. Não precisam de rede.

A CI executa no Linux e macOS, usando `/bin/bash` (Bash 3.2 no macOS). A implementação usa apenas recursos compatíveis com Bash 3.2; a execução local inicial foi verificada em Linux/Bash 5.2. O resultado da CI é a evidência de execução nativa no macOS. O caminho HTTP real precisa ser testado após a publicação.

## Contribuição e licenciamento

Veja [CONTRIBUTING.md](CONTRIBUTING.md) e [PROVENANCE.md](PROVENANCE.md). Uma licença para o conteúdo original ainda não foi escolhida; a visibilidade pública, por si só, não concede uma licença geral de redistribuição. Não presuma que conteúdo externo pode ser copiado por estar no GitHub.

## Referências oficiais

Convenções verificadas em 12/10/2026:

- [Claude Code: skills e diretórios de projeto](https://code.claude.com/docs/en/skills)
- [OpenAI: skills locais e `.agents/skills`](https://developers.openai.com/codex/skills/) (atualmente redireciona para ChatGPT Learn)
- [Pi: formato, descoberta e `.agents/skills`](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/skills.md)
- [Pi: configuração e ordem dos diretórios](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/configuration.md)
- [Especificação Agent Skills](https://agentskills.io/specification)

A coleção usa o formato `SKILL.md` com `name` e `description`. O wrapper `grill-me` conserva controles opcionais de invocação do upstream; os fallbacks documentados evitam exigir uma ferramenta `Skill` específica.
